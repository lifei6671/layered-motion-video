"""独立 v3 文档存储；复用已验证的原子写盘和受控素材目录。"""
import json
from threading import RLock
from uuid import uuid4

from cover_document import MAX_DOCUMENT_BYTES, normalize_document
from scene_models import SceneError, timestamp
from scene_store import DESIGN_FILE, _safe_save, asset_path

_LOCK = RLock()


def _path(root, ident, collection="documents"):
    if not isinstance(ident, str) or not DESIGN_FILE.fullmatch(ident):
        raise SceneError("文档标识不合法。")
    return root / collection / (ident + ".json")


def get_document(root, ident, *, collection="documents"):
    try:
        raw = _path(root, ident, collection).read_bytes()
    except FileNotFoundError as exc:
        raise SceneError("封面文档不存在。") from exc
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise SceneError("封面文档超过 384 KB。")
    try:
        doc = normalize_document(json.loads(raw))
    except (ValueError, UnicodeError) as exc:
        raise SceneError("封面文档格式错误：" + str(exc)) from exc
    if doc["id"] != ident:
        raise SceneError("文档标识与文件不一致。")
    return doc


def list_documents(root, *, collection="documents"):
    result = []
    for path in (root / collection).glob("*.json"):
        if not DESIGN_FILE.fullmatch(path.stem):
            continue
        try:
            doc = get_document(root, path.stem, collection=collection)
            result.append({key: doc[key] for key in ("id", "name", "revision", "width", "height", "updatedAt")})
        except (SceneError, OSError):
            continue
    return sorted(result, key=lambda d: d["updatedAt"] or "", reverse=True)


def save_document(root, body, *, ident=None, check_font=None, collection="documents"):
    with _LOCK:
        doc = normalize_document(body, check_font=check_font)
        if ident is not None:
            current = get_document(root, ident, collection=collection)
            if doc["id"] != ident or doc["revision"] != current["revision"]:
                raise SceneError("文档版本已更新，请另存副本或重新打开。")
            doc["revision"] += 1
        else:
            if doc["id"] is not None or doc["revision"] != 0:
                raise SceneError("新文档必须移除原标识与版本号。")
            doc["id"], doc["revision"] = uuid4().hex, 1
        for layer in doc["layers"]:
            if layer["assetId"] and not layer["assetId"].startswith("builtin:"):
                if not asset_path(root, layer["assetId"]).is_file():
                    raise SceneError("图层图片不存在，请重新上传。")
        doc["updatedAt"] = timestamp()
        payload = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf8")
        if len(payload) > MAX_DOCUMENT_BYTES:
            raise SceneError("封面文档超过 384 KB。")
        _safe_save(_path(root, doc["id"], collection), payload)
        return doc


def delete_document(root, ident, revision, *, collection="documents"):
    """删除明确版本的文档；素材可能被其他设计或模板引用，始终保留。"""
    with _LOCK:
        current = get_document(root, ident, collection=collection)
        if type(revision) is not int or revision != current["revision"]:
            raise SceneError("文档版本已更新，请刷新后重试删除。")
        _path(root, ident, collection).unlink()
