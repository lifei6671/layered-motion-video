"""从已索引的字体生成 Web 用 WOFF2 缓存；原始字体与 ID 不变。"""
import hashlib
import io
from pathlib import Path
from threading import RLock

from fontTools.ttLib import TTFont
from fontTools.ttLib.woff2 import WOFF2FlavorData

from font_preview import MAX_FONT_BYTES
from scene_models import SceneError
from scene_store import _safe_save

_LOCK = RLock()


def web_font_path(root, source):
    path = Path(source)
    status = path.stat()
    if not 0 < status.st_size <= MAX_FONT_BYTES:
        raise SceneError("字体文件大小超出限制。")
    if path.suffix.lower() == ".woff2":
        return path
    key = hashlib.sha256(f"{path.resolve()}|{status.st_mtime_ns}|{status.st_size}".encode("utf8")).hexdigest()
    target = root / "font-web" / (key + ".woff2")
    with _LOCK:
        if target.is_file():
            return target
        try:
            with TTFont(path, fontNumber=0, recalcBBoxes=False, recalcTimestamp=False) as font:
                font.flavor = "woff2"
                # Keep original outlines; optional glyf transforms are very slow on large CJK fonts.
                font.flavorData = WOFF2FlavorData(transformedTables=set())
                output = io.BytesIO()
                font.save(output, reorderTables=False)
                _safe_save(target, output.getvalue())
        except Exception as exc:
            raise SceneError("字体转为 WOFF2 失败，请检查该字体文件。") from exc
    return target
