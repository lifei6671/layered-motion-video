"""React 资源构建与 Node Remotion 静帧适配；兼容原 Flask 本机服务。"""
from pathlib import Path
import io
import json
import os
import shutil
import subprocess
import tempfile

from flask import Blueprint, current_app, jsonify, render_template, request, send_file

from cover_document import MAX_DOCUMENT_BYTES, normalize_document
from document_store import get_document, list_documents, save_document, delete_document
from font_catalog import get_font_by_id
from font_coverage import FontCoverageError, missing_characters
from scene_models import SceneError
from scene_store import _freeze_legacy_assets, get_scene
from web_fonts import web_font_path


def ensure_react_bundle(root):
    frontend = root / "editor"
    bundle = root / "static/editor.bundle.js"
    outputs = [bundle, root / "static/editor.bundle.css", root / "static/remotion-cover/index.html"]
    sources = [frontend / "package.json", frontend / "package-lock.json", frontend / "build.mjs", *list((frontend / "src").rglob("*"))]
    if all(p.is_file() for p in outputs) and all(p.stat().st_mtime_ns <= min(o.stat().st_mtime_ns for o in outputs) for p in sources if p.is_file()):
        return True, "React 封面编辑器资源已就绪。"
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        return False, "请安装 Node.js/npm，然后在 cover-studio/editor 运行 npm ci 与 npm run build。"
    cwd = str(frontend.resolve()).removeprefix("\\\\?\\")
    steps = []
    if not (frontend / "node_modules/react").is_dir() or not (frontend / "node_modules/@remotion/renderer").is_dir():
        steps.append(["ci", "--no-audit", "--no-fund"])
    steps.append(["run", "build"])
    for args in steps:
        command = ["cmd.exe", "/d", "/c", "npm", *args] if os.name == "nt" else [npm, *args]
        try:
            result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf8", errors="replace", timeout=300, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"React 编辑器准备失败：{exc}"
        if result.returncode:
            return False, "React 编辑器构建失败：" + (result.stderr or result.stdout)[-1500:]
    return all(p.is_file() for p in outputs), "React 编辑器构建完成。"


def register_editor(app, get_root, get_data, legacy_scene, legacy_asset):
    api = Blueprint("cover_editor", __name__)

    def body():
        if request.content_length is not None and request.content_length > MAX_DOCUMENT_BYTES:
            raise SceneError("封面文档超过 384 KB。")
        return request.get_json(silent=True)

    @api.get("/api/cover-documents")
    def documents():
        return jsonify(documents=list_documents(get_data()))

    @api.get("/api/cover-documents/<ident>")
    def read(ident):
        response = jsonify(document=get_document(get_data(), ident))
        response.headers["Cache-Control"] = "no-store"
        return response

    @api.post("/api/cover-documents")
    def create():
        return jsonify(document=save_document(get_data(), body(), check_font=get_font_by_id)), 201

    @api.post("/api/cover-validate")
    def validate():
        return jsonify(document=normalize_document(body()))

    @api.put("/api/cover-documents/<ident>")
    def update(ident):
        return jsonify(document=save_document(get_data(), body(), ident=ident, check_font=get_font_by_id))

    @api.delete("/api/cover-documents/<ident>")
    def remove(ident):
        data = body()
        delete_document(get_data(), ident, data.get("revision") if isinstance(data, dict) else None)
        return jsonify(deleted=ident)

    @api.get("/api/cover-templates")
    def templates():
        return jsonify(templates=list_documents(get_data(), collection="templates"))

    @api.post("/api/cover-templates")
    def create_template():
        return jsonify(document=save_document(get_data(), body(), check_font=get_font_by_id, collection="templates")), 201

    @api.get("/api/cover-templates/<ident>")
    def read_template(ident):
        response = jsonify(document=get_document(get_data(), ident, collection="templates"))
        response.headers["Cache-Control"] = "no-store"
        return response

    @api.delete("/api/cover-templates/<ident>")
    def remove_template(ident):
        data = body()
        delete_document(get_data(), ident, data.get("revision") if isinstance(data, dict) else None, collection="templates")
        return jsonify(deleted=ident)

    @api.get("/api/cover-font")
    def web_font():
        source = get_font_by_id(request.args.get("id", ""))
        if not source:
            raise SceneError("字体不存在，请刷新字体目录。")
        path = web_font_path(get_data(), source)
        return send_file(path, mimetype="font/woff2", as_attachment=request.args.get("download") == "1", download_name=Path(source).stem + ".woff2")

    @api.get("/api/cover-migration/<ident>")
    def migration(ident):
        scene = legacy_scene().get_json() if ident == "legacy" else get_scene(get_data(), ident)
        # Freeze legacy images to the existing content-addressed asset directory.
        return jsonify(scene=_freeze_legacy_assets(get_data(), scene, legacy_asset))

    @api.post("/api/cover-export")
    def export():
        doc = normalize_document(body(), check_font=get_font_by_id)
        image_format = request.args.get("format", "png")
        if image_format not in ("png", "jpeg"):
            raise SceneError("导出格式仅支持 PNG、JPEG。")
        for layer in doc["layers"]:
            if layer["visible"] and layer["type"] == "text":
                try:
                    missing = missing_characters(get_font_by_id(layer["fontId"]), layer["text"])
                except FontCoverageError as exc:
                    raise SceneError(layer["name"] + " 字形检查失败：" + str(exc)) from exc
                if missing:
                    raise SceneError(layer["name"] + " 字体缺少字符：" + "、".join(missing[:12]))
        node = shutil.which("node")
        if not node:
            raise SceneError("正式导出需要 Node.js，请安装后重试。")
        root = get_root()
        if not (root / "static/remotion-cover/index.html").is_file():
            raise SceneError("请先在 cover-studio/editor 运行 npm run build。")
        with tempfile.TemporaryDirectory(prefix="cover-render-") as temp:
            target = Path(temp)
            (target / "input.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf8")
            output = target / ("cover." + ("jpg" if image_format == "jpeg" else "png"))
            # Assets always come from this service, never a caller-supplied URL.
            port = request.environ.get("SERVER_PORT", "8765")
            asset_base = f"http://127.0.0.1:{int(port)}"
            command = [node, str(root / "editor/render.mjs"), str(target / "input.json"), str(output), asset_base, image_format]
            try:
                result = subprocess.run(command, cwd=str(root / "editor"), capture_output=True, text=True, encoding="utf8", errors="replace", timeout=150, check=False)
            except subprocess.TimeoutExpired as exc:
                raise SceneError("正式导出超时，请检查字体和图片后重试。") from exc
            if result.returncode or not output.is_file():
                current_app.logger.error("Cover render failed: %s", result.stderr[-2500:])
                raise SceneError("正式导出失败，请检查浏览器安装、图片和字体。服务日志包含详细错误。")
            from PIL import Image
            with Image.open(output) as image:
                if image.size != (doc["width"], doc["height"]):
                    raise SceneError("导出图片尺寸不符合文档尺寸。")
            data = output.read_bytes()
        return send_file(io.BytesIO(data), mimetype="image/jpeg" if image_format == "jpeg" else "image/png", as_attachment=True, download_name=output.name, max_age=0)

    @app.after_request
    def resource_cors(response):
        if request.path in ("/api/fabric-poc/font", "/api/cover-font") or request.path.startswith("/api/designs/assets/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    app.register_blueprint(api)
