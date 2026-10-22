"""封面工坊：本机字体目录和可拖动账号的网页服务。"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, jsonify, make_response, redirect, render_template, request, send_file, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from font_catalog import default_font_id, default_local_font_id, get_font_by_id, public_catalog
from font_preview import get_font_preview_info, render_font_preview
from font_coverage import FontCoverageError, missing_characters
from renderer import CoverError, build_text_layers, render_account_layer, render_cover
from canvas_config import SIZES
from scene_models import SceneError, from_legacy_preset, MAX_SCENE_BYTES
from scene_store import (
    asset_path, get_scene, list_scenes, put_asset, save_scene, SUPPORTED_MIME,
)

BASE_DIR = Path(__file__).resolve().parent
# Windows 的扩展路径前缀与 Jinja 的模板加载存在兼容性问题。
WEB_ROOT = str(BASE_DIR)
if os.name == "nt" and WEB_ROOT.startswith("\\\\?\\"):
    WEB_ROOT = WEB_ROOT[4:]

DATA_DIR = Path(os.environ.get("COVER_STUDIO_DATA_DIR", str(BASE_DIR / "data")))
PRESET_FILE = DATA_DIR / "preset.json"
MAX_UPLOAD = {"background": 18 * 1024 * 1024, "avatar": 12 * 1024 * 1024}
ACCEPTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}

app = Flask(__name__, root_path=WEB_ROOT, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
app.json.ensure_ascii = False

DEFAULT_SETTINGS = {
    "title": "复利思维",
    "subtitle": "存款百万不是结束而是开始",
    "account": "@咸鱼不翻身",
    "ratio": "3:4",
    "title_font_mode": "system",
    "subtitle_font_mode": "system",
    "title_font_id": "",
    "subtitle_font_id": "",
    "account_x": 20,
    "account_y": 55,
    "title_x": None,
    "title_y": None,
    "subtitle_x": None,
    "subtitle_y": None,
    "darkness": 78,
    "focus_y": 50,
    "glow": True,
}


def read_preset() -> dict:
    if not PRESET_FILE.is_file():
        return {"settings": {}, "assets": {}}
    try:
        content = json.loads(PRESET_FILE.read_text(encoding="utf-8"))
        if not isinstance(content, dict):
            return {"settings": {}, "assets": {}}
        return {
            "settings": content.get("settings") if isinstance(content.get("settings"), dict) else {},
            "assets": content.get("assets") if isinstance(content.get("assets"), dict) else {},
        }
    except (OSError, ValueError):
        return {"settings": {}, "assets": {}}


def _safe_name(filename: str) -> str:
    return filename.replace("\\", "/").split("/")[-1][:100]


def _read_upload(key: str) -> tuple[bytes, dict] | None:
    uploaded = request.files.get(key)
    if uploaded is None or not uploaded.filename:
        return None
    filename = _safe_name(uploaded.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in ACCEPTED_IMAGES:
        raise CoverError(f"图片格式不支持：{filename}，请使用 PNG、JPEG 或 WebP。")
    try:
        data = uploaded.stream.read(MAX_UPLOAD[key] + 1)
    finally:
        uploaded.close()
    if len(data) > MAX_UPLOAD[key]:
        raise CoverError(f"图片文件 {filename} 超过大小限制。")
    if not data:
        raise CoverError(f"文件 {filename} 为空。")
    return data, {"name": filename, "suffix": suffix}


def _saved_bytes(preset: dict, key: str) -> bytes | None:
    if key not in MAX_UPLOAD:
        return None
    meta = preset["assets"].get(key)
    if not isinstance(meta, dict):
        return None
    filename = meta.get("file")
    if (
        not isinstance(filename, str)
        or "/" in filename or "\\" in filename
        or not filename.startswith(key + ".")
        or Path(filename).suffix.lower() not in ACCEPTED_IMAGES
    ):
        return None
    path = DATA_DIR / filename
    try:
        if path.is_file() and path.stat().st_size <= MAX_UPLOAD[key]:
            return path.read_bytes()
    except OSError:
        pass
    return None


def _parse_int(name: str, lower: int, upper: int, default: int) -> int:
    try:
        value = int(request.form.get(name, str(default)))
    except (ValueError, TypeError) as exc:
        raise CoverError(f"参数 {name} 必须是整数。") from exc
    if not lower <= value <= upper:
        raise CoverError(f"参数 {name} 超出范围。")
    return value


def _parse_coordinate(name: str, default: float) -> float:
    try:
        value = float(request.form.get(name, str(default)))
    except (ValueError, TypeError) as exc:
        raise CoverError(f"参数 {name} 必须是数字。") from exc
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise CoverError(f"参数 {name} 须在 0 至 100 之间。")
    return round(value, 4)


def _parse_optional_coordinate(name: str) -> float | None:
    """空值表示继续使用排版引擎自动坐标，适用于尚未手动拖动的标题。"""
    raw = request.form.get(name)
    if raw is None or raw.strip() == "":
        return None
    return _parse_coordinate(name, 0.0)


def _resolve_settings() -> dict:
    settings = {
        "title": request.form.get("title", "").strip(),
        "subtitle": request.form.get("subtitle", "").strip(),
        "account": request.form.get("account", "").strip(),
        "ratio": request.form.get("ratio", "3:4"),
        "title_font_mode": request.form.get("title_font_mode", "system"),
        "subtitle_font_mode": request.form.get("subtitle_font_mode", "system"),
        "title_font_id": request.form.get("title_font_id", ""),
        "subtitle_font_id": request.form.get("subtitle_font_id", ""),
        "account_x": _parse_coordinate("account_x", 7.2),
        "account_y": _parse_coordinate("account_y", 68.0),
        "title_x": _parse_optional_coordinate("title_x"),
        "title_y": _parse_optional_coordinate("title_y"),
        "subtitle_x": _parse_optional_coordinate("subtitle_x"),
        "subtitle_y": _parse_optional_coordinate("subtitle_y"),
        "darkness": _parse_int("darkness", 0, 95, 78),
        "focus_y": _parse_int("focus_y", 0, 100, 50),
        "glow": request.form.get("glow", "true") == "true",
    }
    if settings["ratio"] not in SIZES:
        raise CoverError("画幅比例不支持。")
    for kind in ("title", "subtitle"):
        if settings[kind + "_font_mode"] not in ("system", "local"):
            raise CoverError("字体来源参数不正确。")
    return settings


def _build_context() -> tuple[dict, dict, dict, set[str], dict]:
    preset = read_preset()
    settings = _resolve_settings()
    new_uploads: dict[str, tuple[bytes, dict]] = {}
    clear: set[str] = set()

    for key in ("background", "avatar"):
        if request.form.get(key + "_action") == "clear":
            clear.add(key)
            continue
        upload = _read_upload(key)
        if upload is not None:
            new_uploads[key] = upload

    assets = {}
    for key in ("background", "avatar"):
        if key in clear:
            assets[key] = None
        elif key in new_uploads:
            assets[key] = new_uploads[key][0]
        else:
            assets[key] = _saved_bytes(preset, key)

    chosen_fonts = {}
    for kind in ("title", "subtitle"):
        mode = settings[kind + "_font_mode"]
        font_id = settings[kind + "_font_id"] or (
            default_local_font_id() if mode == "local" else default_font_id(kind)
        )
        if (mode == "local") != font_id.startswith("local:"):
            raise CoverError("字体来源与所选字体不匹配，请重新选择。")
        font_path = get_font_by_id(font_id)
        if font_path is None:
            raise CoverError("所选字体已不存在，请刷新字体列表后重新选择。")
        settings[kind + "_font_id"] = font_id
        chosen_fonts[kind] = font_path

    return preset, settings, assets, clear, {"new_uploads": new_uploads, "fonts": chosen_fonts}


def _image_response(image_bytes: bytes, *, info: dict | None = None):
    response = make_response(image_bytes)
    response.mimetype = "image/png"
    response.headers["Cache-Control"] = "no-store"
    if info is not None:
        response.headers["X-Title-Lines"] = str(len(info["title_lines"]))
        response.headers["X-Title-Font-Px"] = str(info["title_font_size"])
        response.headers["X-Subtitle-Lines"] = str(len(info["subtitle_lines"]))
        response.headers["X-Canvas-Size"] = f"{info['width']}x{info['height']}"
    return response


def _png_bytes(image) -> bytes:
    result = io.BytesIO()
    image.save(result, format="PNG", optimize=True)
    return result.getvalue()


def _render_from_request(
    *, include_account: bool = True,
    include_title: bool = True,
    include_subtitle: bool = True,
) -> tuple[bytes, dict, tuple]:
    context = _build_context()
    _, settings, assets, _, extras = context
    image, info = render_cover(
        title=settings["title"],
        subtitle=settings["subtitle"],
        account=settings["account"],
        ratio=settings["ratio"],
        title_font=extras["fonts"]["title"],
        subtitle_font=extras["fonts"]["subtitle"],
        background=assets["background"],
        avatar=assets["avatar"],
        darkness=settings["darkness"],
        focus_y=settings["focus_y"],
        glow=settings["glow"],
        title_x=settings["title_x"],
        title_y=settings["title_y"],
        subtitle_x=settings["subtitle_x"],
        subtitle_y=settings["subtitle_y"],
        account_x=settings["account_x"],
        account_y=settings["account_y"],
        include_title=include_title,
        include_subtitle=include_subtitle,
        include_account=include_account,
    )
    return _png_bytes(image), info, context


def _atomic_write(path: Path, data: bytes) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=DATA_DIR, prefix=".cover-", delete=False) as file:
            tmp_name = file.name
            file.write(data)
        os.replace(tmp_name, path)
    finally:
        if tmp_name is not None:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _persist(context: tuple) -> dict:
    prior, settings, _, clear, extras = context
    current_assets = dict(prior["assets"])
    old_paths = []
    for key in ("background", "avatar"):
        previous = current_assets.get(key)
        if isinstance(previous, dict) and isinstance(previous.get("file"), str):
            old_paths.append(previous["file"])
        if key in clear:
            current_assets.pop(key, None)
        elif key in extras["new_uploads"]:
            payload, uploaded_meta = extras["new_uploads"][key]
            filename = key + uploaded_meta["suffix"]
            _atomic_write(DATA_DIR / filename, payload)
            current_assets[key] = {"file": filename, "name": uploaded_meta["name"]}

    preset = {"settings": settings, "assets": current_assets}
    _atomic_write(PRESET_FILE, json.dumps(preset, ensure_ascii=False, indent=2).encode("utf-8"))

    retained = {item.get("file") for item in current_assets.values() if isinstance(item, dict)}
    for filename in old_paths:
        if (
            isinstance(filename, str) and filename not in retained
            and any(filename.startswith(key + ".") for key in ("background", "avatar"))
            and "/" not in filename and "\\" not in filename
        ):
            (DATA_DIR / filename).unlink(missing_ok=True)
    return preset


@app.get("/")
def index():
    """正式的浏览器封面编辑器：预览、图层操作与 PNG 导出均使用 Fabric.js。"""
    bundle = BASE_DIR / "static" / "fabric-poc.bundle.js"
    if not bundle.is_file() or bundle.stat().st_size == 0:
        return render_template("editor-build-required.html"), 503
    stylesheet = BASE_DIR / "static" / "fabric-poc.css"
    return render_template(
        "fabric-poc.html",
        editor_version=str(bundle.stat().st_mtime_ns),
        style_version=str(stylesheet.stat().st_mtime_ns) if stylesheet.is_file() else "0",
    )


@app.get("/legacy")
def legacy_editor():
    """独立的 Pillow 封面编辑与默认模板兼容入口。"""
    return render_template("index.html")


@app.get("/fabric-poc")
def previous_editor_link():
    """历史浏览器编辑页地址继续指向正式入口。"""
    return redirect(url_for("index"), code=302)


@app.get("/api/fabric-poc/font")
def fabric_font_file():
    """只允许通过字体目录索引读取文件，不接受任意文件路径。"""
    font_id = request.args.get("id", "")[:100]
    font_path = get_font_by_id(font_id) if font_id else None
    if font_path is None:
        return jsonify({"error": "字体不存在，请刷新字体列表。"}), 404
    suffix = Path(font_path).suffix.lower()
    mime = {
        ".ttf": "font/ttf", ".otf": "font/otf",
        ".woff": "font/woff", ".woff2": "font/woff2",
        ".ttc": "font/collection", ".otc": "font/collection",
    }.get(suffix)
    if not mime:
        return jsonify({"error": "不支持的字体格式。"}), 415
    return send_file(font_path, mimetype=mime, conditional=True, max_age=3600)


@app.post("/api/fabric-poc/font-coverage")
def fabric_font_coverage():
    """人工预检/导出时按需检查字体缺字；从已有字体 ID 白名单查找。"""
    if request.content_length is not None and request.content_length > 20_000:
        return jsonify({"error": "字体预检请求过大。"}), 413
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"checks"}:
        return jsonify({"error": "字体预检请求格式不正确。"}), 400
    checks = payload.get("checks")
    if not isinstance(checks, list) or len(checks) > 40:
        return jsonify({"error": "单次最多检查 40 个文字图层。"}), 400
    results = []
    for item in checks:
        if not isinstance(item, dict) or set(item) != {"fontId", "text", "label"}:
            return jsonify({"error": "字体预检项格式不正确。"}), 400
        font_id, caption, value = item.get("fontId"), item.get("label"), item.get("text")
        if not isinstance(font_id, str) or not 1 <= len(font_id) <= 100:
            return jsonify({"error": "字体标识格式不正确。"}), 400
        if not isinstance(caption, str) or not 1 <= len(caption) <= 70:
            return jsonify({"error": "文字图层名称无效。"}), 400
        if not isinstance(value, str) or len(value) > 500:
            return jsonify({"error": "单图层文字长度不能超过 500 字。"}), 400
        font_path = get_font_by_id(font_id)
        if not font_path:
            return jsonify({"error": "字体已不存在，请重新选择。"}), 404
        try:
            missing = missing_characters(font_path, value)
            results.append({
                "fontId": font_id, "label": caption,
                "missing": missing[:100], "missingCount": len(missing),
            })
        except FontCoverageError as exc:
            results.append({
                "fontId": font_id, "label": caption,
                "missing": [], "missingCount": 0, "error": str(exc),
            })
    return jsonify({"results": results, "checkedCount": len(results)})


@app.get("/api/fabric-poc/asset/<kind>")
def fabric_saved_asset(kind: str):
    """从当前模板读取已保存背景/头像，保留浏览器原生图片渲染。"""
    if kind not in ("background", "avatar"):
        return jsonify({"error": "不支持的素材类型。"}), 404
    preset_data = read_preset()
    data = _saved_bytes(preset_data, kind)
    if data is None:
        return jsonify({"error": "当前模板没有该素材。"}), 404
    meta = preset_data.get("assets", {}).get(kind, {})
    suffix = Path(meta.get("file", "")).suffix.lower()
    mime = {
        ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    return send_file(io.BytesIO(data), mimetype=mime, download_name="asset" + suffix, max_age=0)


def _legacy_asset_info(kind: str) -> tuple[bytes, str] | None:
    preset = read_preset()
    source = _saved_bytes(preset, kind)
    if source is None:
        return None
    meta = preset.get("assets", {}).get(kind, {})
    suffix = Path(meta.get("file", "")).suffix.lower()
    return (source, suffix) if suffix in SUPPORTED_MIME else None


@app.get("/api/designs/legacy")
def imported_legacy_design():
    """以可复制草稿形式导入当前经典版模板，不更新原有配置。"""
    data = read_preset()
    settings = dict(DEFAULT_SETTINGS)
    settings.update(data["settings"])
    title_id = settings.get("title_font_id") or default_font_id("title")
    subtitle_id = settings.get("subtitle_font_id") or default_font_id("subtitle")
    if get_font_by_id(title_id) is None:
        title_id = default_font_id("title")
    if get_font_by_id(subtitle_id) is None:
        subtitle_id = default_font_id("subtitle")
    names = {
        k: meta.get("name", "")
        for k, meta in data.get("assets", {}).items()
        if k in ("background", "avatar") and isinstance(meta, dict)
        and _saved_bytes(data, k) is not None
    }
    scene = from_legacy_preset(
        settings, names,
        title_font_id=title_id, subtitle_font_id=subtitle_id,
    )
    response = jsonify(scene)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/designs")
def designs_index():
    return jsonify({"designs": list_scenes(DATA_DIR)})


def _scene_body() -> dict:
    if request.content_length is not None and request.content_length > MAX_SCENE_BYTES:
        raise SceneError("设计请求超过 128 KB。")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise SceneError("提交的数据必须是 JSON 对象。")
    return body


@app.post("/api/designs")
def create_design():
    saved = save_scene(
        DATA_DIR, _scene_body(), check_font=get_font_by_id,
        read_legacy=_legacy_asset_info,
    )
    return jsonify({"design": saved}), 201


@app.get("/api/designs/<ident>")
def read_design(ident: str):
    return jsonify({"design": get_scene(DATA_DIR, ident)})


@app.put("/api/designs/<ident>")
def update_design(ident: str):
    saved = save_scene(
        DATA_DIR, _scene_body(), check_font=get_font_by_id,
        read_legacy=_legacy_asset_info, ident=ident,
    )
    return jsonify({"design": saved})


@app.post("/api/designs/assets")
def upload_design_asset():
    """保存一次上传，之后改字和拖动均只在浏览器中渲染。"""
    kind = request.form.get("kind")
    if kind not in ("background", "avatar", "layer"):
        raise SceneError("素材类型只允许背景、头像和自由图层。")
    file = request.files.get("file")
    if file is None or not file.filename:
        raise SceneError("请选择需要保存的图片文件。")
    filename = _safe_name(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_MIME:
        raise SceneError("只支持 PNG、JPEG 或 WebP 图片。")
    try:
        payload = file.stream.read(18 * 1024 * 1024 + 1)
    finally:
        file.close()
    item_id = put_asset(DATA_DIR, payload, suffix)
    return jsonify({"asset": {
        "source": "managed", "id": item_id, "kind": kind,
    }}), 201


@app.get("/api/designs/assets/<asset_id>")
def read_design_asset(asset_id: str):
    try:
        filename = asset_path(DATA_DIR, asset_id)
    except SceneError as exc:
        return jsonify({"error": str(exc)}), 404
    if not filename.is_file():
        return jsonify({"error": "素材文件不存在。"}), 404
    return send_file(
        filename, mimetype=SUPPORTED_MIME[filename.suffix.lower()],
        conditional=True, max_age=3600,
    )


@app.errorhandler(SceneError)
def handle_scene_error(exc: SceneError):
    message = str(exc)
    code = 409 if "版本已更新" in message else 400
    if "不存在" in message and code == 400:
        code = 404
    return jsonify({"error": message}), code


@app.get("/api/fonts")
def fonts():
    return jsonify(public_catalog())


@app.get("/api/font-preview")
def font_preview():
    """单字体真实字形预览，使用扫描产生的 ID，服务端从白名单解析路径。"""
    font_id = request.args.get("id", "")[:100]
    font_path = get_font_by_id(font_id) if font_id else None
    if not font_path:
        return jsonify({"error": "字体不存在，请刷新字体目录。"}), 404
    info = get_font_preview_info(font_path)
    if not info["sample"]:
        return jsonify({"error": info["label"]}), 422
    compact = request.args.get("compact") == "1"
    try:
        payload = render_font_preview(font_path, compact=compact)
    except (OSError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 422
    response = _image_response(payload)
    count = (4 if info["coverage"] == "chinese" else 5) if compact else len(info["sample"])
    response.headers["X-Preview-Characters"] = str(min(count, len(info["sample"])))
    return response


@app.get("/api/preset")
def preset():
    saved = read_preset()
    settings = dict(DEFAULT_SETTINGS)
    settings["title_font_id"] = default_font_id("title")
    settings["subtitle_font_id"] = default_font_id("subtitle")
    settings.update(saved["settings"])
    for kind in ("title", "subtitle"):
        mode = settings.get(kind + "_font_mode")
        if mode not in ("system", "local"):
            settings[kind + "_font_mode"] = "system"
            settings[kind + "_font_id"] = default_font_id(kind)
    names = {
        key: value.get("name", "")
        for key, value in saved["assets"].items()
        if key in ("background", "avatar") and isinstance(value, dict)
    }
    return jsonify({"settings": settings, "assets": names})


@app.post("/api/render")
def render():
    """兼容账号独立预览，同时支持三个文字图层的干净预览底图。"""
    mode = request.args.get("preview")
    show_account = mode not in ("1", "all-text")
    show_titles = mode != "all-text"
    png, info, _ = _render_from_request(
        include_title=show_titles, include_subtitle=show_titles,
        include_account=show_account,
    )
    return _image_response(png, info=info)


@app.post("/api/text-layers")
def text_layers():
    """一次返回三块 Pillow 透明图层及原生像素定位，供浏览器即时拖动。"""
    _, settings, _, _, extras = _build_context()
    layers, info = build_text_layers(
        title=settings["title"],
        subtitle=settings["subtitle"],
        account=settings["account"],
        ratio=settings["ratio"],
        title_font=extras["fonts"]["title"],
        subtitle_font=extras["fonts"]["subtitle"],
        title_x=settings["title_x"],
        title_y=settings["title_y"],
        subtitle_x=settings["subtitle_x"],
        subtitle_y=settings["subtitle_y"],
        account_x=settings["account_x"],
        account_y=settings["account_y"],
    )
    response_layers = {}
    for name, entry in layers.items():
        img = entry["image"]
        response_layers[name] = {
            "png": base64.b64encode(_png_bytes(img)).decode("ascii"),
            "width": img.width if name != "account" or settings["account"] else 0,
            "height": img.height if name != "account" or settings["account"] else 0,
            "position": list(entry["position"]),
            "default_position": list(entry["default_position"]),
        }
    response = jsonify({
        "width": info["width"],
        "height": info["height"],
        "layers": response_layers,
        "title_lines": info["title_lines"],
        "subtitle_lines": info["subtitle_lines"],
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/account-layer")
def account_layer():
    _, settings, _, _, extras = _build_context()
    layer = render_account_layer(settings["account"], settings["ratio"], extras["fonts"]["subtitle"])
    response = _image_response(_png_bytes(layer))
    response.headers["X-Layer-Width"] = str(layer.width if settings["account"] else 0)
    response.headers["X-Layer-Height"] = str(layer.height if settings["account"] else 0)
    return response


@app.post("/api/preset")
def save_preset():
    _, info, context = _render_from_request()
    saved = _persist(context)
    return jsonify({
        "ok": True,
        "message": "默认模板已保存，包括大标题、小标题与账号位置。",
        "assets": {
            key: meta.get("name", "")
            for key, meta in saved["assets"].items()
            if key in ("background", "avatar")
        },
        "canvas": f"{info['width']}x{info['height']}",
    })


@app.errorhandler(CoverError)
def cover_error(exc: CoverError):
    return jsonify({"error": str(exc)}), 400


@app.errorhandler(RequestEntityTooLarge)
def large_upload(_: RequestEntityTooLarge):
    return jsonify({"error": "上传内容过大，单次请求上限为40 MB。"}), 413


if __name__ == "__main__":
    from editor_build import ensure_editor_bundle

    ok, message = ensure_editor_bundle(BASE_DIR)
    print(message, flush=True)
    if not ok:
        print("经典封面编辑器仍可在 /legacy 打开。", flush=True)
    no_browser = "--no-browser" in sys.argv
    port = int(os.environ.get("COVER_STUDIO_PORT", "8765"))
    url = f"http://127.0.0.1:{port}"
    print(f"封面工坊：{url}", flush=True)
    if not no_browser:
        Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
