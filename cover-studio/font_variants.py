"""项目字体的规格信息识别：目录代表家族，文件代表可选规格。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

WEIGHT_NAMES = {
    100: "极细",
    200: "特细",
    250: "超细",
    300: "细体",
    350: "标准",
    400: "常规",
    500: "中等",
    600: "半粗",
    700: "粗体",
    800: "特粗",
    900: "极粗",
}
# 文件名优先于 OS/2 属性：有些字体自称 Bold，内部权重仍为 400。
WEIGHT_SUFFIXES = (
    ("extralight", 250),
    ("ultralight", 250),
    ("semibold", 600),
    ("demibold", 600),
    ("extrabold", 800),
    ("ultrabold", 800),
    ("hairline", 100),
    ("thin", 100),
    ("heavy", 900),
    ("black", 900),
    ("medium", 500),
    ("normal", 350),
    ("regular", 400),
    ("light", 300),
    ("lite", 300),
    ("bold", 700),
    ("book", 400),
)
FORMAT_ORDER = {".otf": 0, ".ttf": 1, ".woff2": 2, ".woff": 3, ".ttc": 4, ".otc": 5}


@lru_cache(maxsize=192)
def _metadata_weight(path: str, modified: int, size: int) -> int:
    if size <= 0 or size > 80 * 1024 * 1024:
        return 400
    font = None
    try:
        from fontTools.ttLib import TTFont

        with open(path, "rb") as stream:
            font = TTFont(stream, lazy=True)
            weight = int(getattr(font["OS/2"], "usWeightClass", 400))
            return min(900, max(100, weight))
    except Exception:
        # 损坏文件仍可出现在列表中，其可用性由字形检查标识。
        return 400
    finally:
        if font is not None:
            font.close()


def describe_variant(path: Path) -> dict:
    """根据完整文件名、字形关键字及字体元数据确定规格。"""
    stem = path.stem
    clean = re.sub(r"[-_ ]+\d+$", "", stem).lower()
    is_mono = "mono" in clean or "等宽" in clean
    italic = "italic" in clean or "oblique" in clean or "斜体" in clean

    weight = None
    for suffix, mapped in WEIGHT_SUFFIXES:
        if re.search(rf"{suffix}(?:[-_ ]+(?:italic|oblique))?$", clean):
            weight = mapped
            break
    if weight is None:
        try:
            stat = path.stat()
            weight = _metadata_weight(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        except OSError:
            weight = 400

    name = WEIGHT_NAMES.get(weight, f"字重 {weight}")
    shape = "等宽" if is_mono else "标准字形"
    if italic:
        shape += "斜体"
    format_name = path.suffix[1:].upper()
    return {
        "weight": weight,
        "weight_name": name,
        "shape": shape,
        "italic": italic,
        "monospace": is_mono,
        "format": format_name,
        "variant": f"{shape} · {name} · {format_name}",
        "format_order": FORMAT_ORDER.get(path.suffix.lower(), 5),
    }


def font_variant_sort_key(font: dict) -> tuple:
    """族内排序：标准字形在前，按字重从细到粗，再按文件格式排序。"""
    return (
        1 if font["monospace"] else 0,
        1 if font["italic"] else 0,
        font["weight"],
        font["format_order"],
        font["filename"].casefold(),
    )


def preferred_variant_key(font: dict) -> tuple:
    """新家族默认优先常规非等宽规格及可直接渲染的 OpenType。"""
    return (
        1 if font["monospace"] else 0,
        abs(font["weight"] - 400),
        1 if font["italic"] else 0,
        font["format_order"],
        font["filename"].casefold(),
    )
