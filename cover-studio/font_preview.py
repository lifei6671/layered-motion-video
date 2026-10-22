"""为字体选择器生成和最终 Pillow 排版一致的字形样张。"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

CHINESE_EXAMPLES = "复利思维财富增长生活经济成长知识社会人生梦想工作未来你好世界"
LATIN_EXAMPLES = "Aa Bb 123"
MAX_FONT_BYTES = 80 * 1024 * 1024


def _chinese(codepoint: int) -> bool:
    return (
        0x3400 <= codepoint <= 0x9FFF
        or 0x20000 <= codepoint <= 0x2FA1F
        or 0xF900 <= codepoint <= 0xFAFF
    )


@lru_cache(maxsize=512)
def _inspect(path: str, modified_ns: int, file_size: int) -> dict[str, str]:
    if file_size < 1 or file_size > MAX_FONT_BYTES:
        return {"sample": "", "coverage": "invalid", "label": "字体大小超出限制"}
    font = None
    try:
        # 使用明确关闭的文件句柄，损坏的字体也不会遗留未关闭的资源。
        with open(path, "rb") as stream:
            font = TTFont(stream, fontNumber=0, lazy=False)
            charset = set((font.getBestCmap() or {}).keys())
        chinese_count = sum(1 for c in charset if _chinese(c))
        if chinese_count:
            sample = "".join(ch for ch in CHINESE_EXAMPLES if ord(ch) in charset)
            if len(sample) < 3:
                sample = "".join(chr(c) for c in sorted(charset) if 0x4E00 <= c <= 0x9FFF)[:7]
            else:
                sample = sample[:7]
            return {
                "sample": sample,
                "coverage": "chinese",
                "label": f"含中文字形 · {chinese_count} 字",
            }
        latin = "".join(ch for ch in LATIN_EXAMPLES if ch == " " or ord(ch) in charset).strip()
        if len(latin.replace(" ", "")) >= 2:
            return {"sample": latin, "coverage": "latin", "label": "仅含拉丁字形"}
        return {"sample": "", "coverage": "unsupported", "label": "暂无常用预览字符"}
    except Exception:
        return {"sample": "", "coverage": "invalid", "label": "字体无法解析"}
    finally:
        if font is not None:
            font.close()


def get_font_preview_info(font_path: str) -> dict[str, str]:
    try:
        p = Path(font_path)
        status = p.stat()
        return dict(_inspect(str(p.resolve()), status.st_mtime_ns, status.st_size))
    except OSError:
        return {"sample": "", "coverage": "invalid", "label": "字体文件不可用"}


def render_font_preview(font_path: str, *, compact: bool = False) -> bytes:
    """按实际字体绘制字形样张；下拉框使用紧凑大字版避免笔画过小。"""
    from renderer import open_font

    info = get_font_preview_info(font_path)
    if not info["sample"]:
        raise ValueError(info["label"])

    sample = info["sample"]
    if compact:
        sample = sample[:4] if info["coverage"] == "chinese" else sample[:5]
        max_width, canvas_height, max_font_size = 360, 96, 74
    else:
        max_width, canvas_height, max_font_size = 600, 104, 55

    measuring = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for font_size in range(max_font_size, 15, -2):
        font = open_font(font_path, font_size)
        bounds = measuring.textbbox((0, 0), sample, font=font)
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        if width <= max_width - 30 and height <= canvas_height - 20:
            canvas_width = min(max_width, max(78, width + 30)) if compact else max_width
            image = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.text(
                (15 - bounds[0], (canvas_height - height) // 2 - bounds[1]),
                sample, font=font, fill=(248, 241, 232, 255),
            )
            stream = io.BytesIO()
            image.save(stream, "PNG", optimize=True)
            return stream.getvalue()
    raise ValueError("字体预览内容宽度超出范围")
