"""字库缺字预检：只读取字体 cmap，避免调用图片合成接口。

Python 负责受控字体资源校验；浏览器继续负责所有视觉实时渲染。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont


class FontCoverageError(ValueError):
    pass


@lru_cache(maxsize=72)
def _get_charset(path: str, modified_ns: int, file_size: int) -> frozenset[int]:
    if file_size <= 0 or file_size > 80 * 1024 * 1024:
        raise FontCoverageError("字体文件大小超出预检限制。")
    font = None
    try:
        with open(path, "rb") as handle:
            font = TTFont(handle, fontNumber=0, lazy=False)
            charset = frozenset((font.getBestCmap() or {}).keys())
        return charset
    except Exception as exc:
        raise FontCoverageError("字体字形表无法读取。") from exc
    finally:
        if font is not None:
            font.close()


def missing_characters(font_file: str, text: str) -> list[str]:
    if not isinstance(text, str) or len(text) > 500:
        raise FontCoverageError("文字长度不能超过 500 字。")
    path = Path(font_file)
    try:
        stat = path.stat()
    except OSError as exc:
        raise FontCoverageError("字体文件不可读取。") from exc
    codepoints = _get_charset(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    return list(dict.fromkeys(
        ch for ch in text if not ch.isspace() and ord(ch) not in codepoints
    ))
