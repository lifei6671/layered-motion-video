"""Cover Studio 设计文件仓库：文件系统持久化、修订冲突处理和素材快照。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from scene_models import MAX_SCENE_BYTES, SceneError, normalize_scene, timestamp

DESIGN_FILE = re.compile(r"^[0-9a-f]{32}$")
ASSET_FILE = re.compile(r"^[0-9a-f]{64}\.(?:png|jpg|jpeg|webp)$")
SUPPORTED_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp",
}
_SCENE_WRITE_LOCK = RLock()


def _folder(root: Path) -> Path:
    return root / "designs"


def _path(root: Path, ident: str) -> Path:
    if not isinstance(ident, str) or not DESIGN_FILE.fullmatch(ident):
        raise SceneError("设计标识不合法。")
    return _folder(root) / (ident + ".json")


def _safe_save(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".scene-", dir=str(path.parent), delete=False,
        ) as stream:
            temp = Path(stream.name)
            stream.write(data)
        os.replace(temp, path)
    finally:
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def asset_folder(root: Path) -> Path:
    return _folder(root) / "assets"


def asset_path(root: Path, ident: str) -> Path:
    if not isinstance(ident, str) or not ASSET_FILE.fullmatch(ident):
        raise SceneError("图片素材标识不合法。")
    return asset_folder(root) / ident


def put_asset(root: Path, raw: bytes, suffix: str) -> str:
    if suffix not in SUPPORTED_MIME:
        raise SceneError("图片格式须为 PNG、JPEG 或 WebP。")
    if not 0 < len(raw) <= 18 * 1024 * 1024:
        raise SceneError("图片大小须在 18 MB 以内。")
    from renderer import load_image
    from PIL import Image
    from io import BytesIO

    loaded = load_image(raw, "场景图片素材")
    if loaded.width * loaded.height > 48_000_000:
        raise SceneError("图片像素数量超过 4800 万。")
    with Image.open(BytesIO(raw)) as source:
        actual_format = source.format
    expected_format = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}[suffix]
    if actual_format != expected_format:
        raise SceneError("图片实际编码与扩展名不一致，请使用正确格式保存。")
    digest = hashlib.sha256(raw).hexdigest()
    ident = digest + suffix
    path = asset_path(root, ident)
    if not path.exists():
        _safe_save(path, raw)
    return ident


def get_scene(root: Path, ident: str, *, check_font=None) -> dict:
    path = _path(root, ident)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise SceneError("指定设计不存在。") from exc
    if len(raw) > MAX_SCENE_BYTES:
        raise SceneError("设计文件超出大小限制。")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise SceneError("设计文件内容无法解析。") from exc
    scene = normalize_scene(data, check_font=check_font)
    if scene["id"] != ident:
        raise SceneError("设计文件标识与内容不一致。")
    return scene


def list_scenes(root: Path) -> list[dict]:
    directory = _folder(root)
    if not directory.is_dir():
        return []
    items = []
    for path in directory.glob("*.json"):
        if not DESIGN_FILE.fullmatch(path.stem):
            continue
        try:
            record = get_scene(root, path.stem)
            items.append({
                "id": record["id"], "name": record["name"],
                "revision": record["revision"],
                "updatedAt": record["updatedAt"],
                "activeRatio": record["activeRatio"],
            })
        except (SceneError, OSError, ValueError):
            continue
    return sorted(items, key=lambda item: item.get("updatedAt") or "", reverse=True)


def _freeze_legacy_assets(root: Path, scene: dict, read_legacy) -> dict:
    normalized = dict(scene)
    normalized["assets"] = {
        k: dict(v) for k, v in scene["assets"].items()
    }
    for kind, spec in normalized["assets"].items():
        if spec["source"] == "legacy":
            record = read_legacy(kind)
            if not record:
                raise SceneError(f"旧模板的{kind}素材不可读取，请重新选择图片。")
            data, suffix = record
            item_id = put_asset(root, data, suffix)
            normalized["assets"][kind] = {"source": "managed", "id": item_id}
    return normalized


def _save_scene_unlocked(root: Path, scene: dict, *, check_font=None,
                         read_legacy=None, ident: str | None = None) -> dict:
    normalized = normalize_scene(scene, check_font=check_font)
    if ident is not None:
        current = get_scene(root, ident)
        if normalized["id"] not in (ident, None):
            raise SceneError("设计标识与更新对象不匹配。")
        if normalized["revision"] != current["revision"]:
            raise SceneError("设计版本已更新，请重新打开后再保存。")
        normalized["id"] = ident
        normalized["revision"] = current["revision"] + 1
    else:
        normalized["id"] = uuid4().hex
        normalized["revision"] = 1

    if any(x["source"] == "legacy" for x in normalized["assets"].values()):
        if read_legacy is None:
            raise SceneError("缺少原始素材解析器。")
        normalized = _freeze_legacy_assets(root, normalized, read_legacy)

    for kind, value in normalized["assets"].items():
        if value["source"] == "managed" and not asset_path(root, value["id"]).is_file():
            raise SceneError(f"{kind}素材文件不存在，请重新选择。")
    for extra in normalized["extras"]["layers"]:
        if extra["type"] == "image" and not asset_path(root, extra["assetId"]).is_file():
            raise SceneError(f"自由图片 {extra['name']} 的素材文件不存在。")

    normalized["updatedAt"] = timestamp()
    path = _path(root, normalized["id"])
    payload = json.dumps(normalized, ensure_ascii=False, indent=2).encode("utf-8")
    if len(payload) > MAX_SCENE_BYTES:
        raise SceneError("设计文件超出大小限制。")
    _safe_save(path, payload)
    return normalized

def save_scene(root: Path, scene: dict, *, check_font=None,
               read_legacy=None, ident: str | None = None) -> dict:
    """在一个 Flask 进程内串行化校验和写入，确保版本冲突检测有效。"""
    with _SCENE_WRITE_LOCK:
        return _save_scene_unlocked(
            root, scene, check_font=check_font,
            read_legacy=read_legacy, ident=ident,
        )
