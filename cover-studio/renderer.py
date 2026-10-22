"""固定布局的高分辨率封面渲染引擎。渲染成功意味着所有标题字符均可完整显示。"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Union

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
from canvas_config import SIZES

FontSource = Union[str, bytes, Path]

MAX_IMAGE_PIXELS = 48_000_000
OPENING = set("（【《〈「『([{“‘")
CLOSING = set("，。！？：；、）】》〉」』)]}”’")


class CoverError(ValueError):
    pass


@dataclass
class TextLayout:
    lines: list[str]
    font: ImageFont.FreeTypeFont
    font_size: int
    height: int
    line_gap: int


def load_image(data: bytes, label: str) -> Image.Image:
    if not data:
        raise CoverError(f"{label}为空，请重新选择图片。")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise CoverError(f"{label}分辨率过大，最大支持4800万像素。")
            source = ImageOps.exif_transpose(source)
            source.load()
            return source.convert("RGBA")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError) as exc:
        if isinstance(exc, CoverError):
            raise
        raise CoverError(f"{label}不是可读取的 PNG、JPEG 或 WebP 图片。") from exc


@lru_cache(maxsize=6)
def _decompress_web_font(path: str, mtime_ns: int, file_size: int, flavor: str) -> tuple[bytes, frozenset[int]]:
    """将 WOFF/WOFF2 在内存中转换为原生字体格式，按文件修改时间缓存。"""
    fmt = flavor.upper()
    if file_size <= 0 or file_size > 25 * 1024 * 1024:
        raise CoverError(f"{fmt} 字体大小不合法，单文件最多支持 25 MB。")
    font = None
    try:
        with open(path, "rb") as handle:
            font = TTFont(handle, lazy=False)
            if font.flavor != flavor:
                raise CoverError(f"文件 {Path(path).name} 不是有效的 {fmt} 字体。")
            character_map = font.getBestCmap() or {}
            font.flavor = None
            stream = io.BytesIO()
            font.save(stream)
            payload = stream.getvalue()
        if len(payload) > 96 * 1024 * 1024:
            raise CoverError(f"{fmt} 字体解压后超过 96 MB，请换用较小的字体文件。")
        return payload, frozenset(character_map.keys())
    except CoverError:
        raise
    except Exception as exc:
        raise CoverError(f"无法读取 {fmt} 字体 {Path(path).name}，请检查文件完整性及字体依赖。") from exc
    finally:
        if font is not None:
            font.close()


def _web_font_content(source: FontSource) -> tuple[bytes, frozenset[int]] | None:
    if not isinstance(source, (str, Path)):
        return None
    path = Path(source)
    flavor = path.suffix.lower().lstrip(".")
    if flavor not in ("woff", "woff2"):
        return None
    try:
        stat = path.stat()
    except OSError as exc:
        raise CoverError(f"{flavor.upper()} 字体文件不存在或不可读取：{path.name}。") from exc
    return _decompress_web_font(str(path.resolve()), stat.st_mtime_ns, stat.st_size, flavor)


def validate_font_text(source: FontSource, value: str, label: str) -> None:
    """检测 WOFF/WOFF2 子集字体缺失字符；网页和 PNG 导出共用此校验。"""
    decoded = _web_font_content(source)
    if decoded is None or not value:
        return
    _, supported_codepoints = decoded
    missing = list(dict.fromkeys(
        char for char in value
        if not char.isspace() and ord(char) not in supported_codepoints
    ))
    if missing:
        sample = "、".join(missing[:8])
        suffix = "等" if len(missing) > 8 else ""
        fmt = Path(source).suffix.lstrip(".").upper()
        raise CoverError(
            f"{label}选择的 {fmt} 字体缺少字符：{sample}{suffix}。"
            "该字体可能是英文网页字体或中文子集字体，请换用包含所需字符的完整字体。"
        )


def open_font(source: FontSource, size: int) -> ImageFont.FreeTypeFont:
    decoded = _web_font_content(source)
    try:
        payload = io.BytesIO(decoded[0]) if decoded is not None else (
            io.BytesIO(source) if isinstance(source, bytes) else str(source)
        )
        return ImageFont.truetype(payload, size, index=0)
    except (OSError, ValueError, TypeError) as exc:
        raise CoverError("字体无法加载，请选用有效的 TTF、OTF、TTC、OTC、WOFF 或 WOFF2 字体文件。") from exc


def _bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font)


def _width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    left, _, right, _ = _bbox(draw, text, font)
    return right - left


def _best_break(draw: ImageDraw.ImageDraw, value: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str] | None:
    """中文两行光学均衡换行，避开行首闭合标点和行尾起始标点。"""
    parts = value.split("\n")
    if len(parts) > 2 or any(not part.strip() for part in parts):
        return None
    if len(parts) == 2:
        return parts if all(_width(draw, line, font) <= max_width for line in parts) else None

    text = parts[0].strip()
    if _width(draw, text, font) <= max_width:
        return [text]
    candidates = []
    for pos in range(1, len(text)):
        left, right = text[:pos].strip(), text[pos:].strip()
        if not left or not right or left[-1] in OPENING or right[0] in CLOSING:
            continue
        width_l, width_r = _width(draw, left, font), _width(draw, right, font)
        if max(width_l, width_r) > max_width:
            continue
        # 视觉宽度接近优先，同时避免短到像落单字的行。
        score = abs(width_l - width_r) + 0.15 * max(width_l, width_r)
        candidates.append((score, [left, right]))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _fit_text(
    draw: ImageDraw.ImageDraw,
    value: str,
    font_source: FontSource,
    max_width: int,
    max_height: int,
    starting_size: int,
    min_size: int,
    gap_ratio: float,
    label: str,
) -> TextLayout:
    for size in range(starting_size, min_size - 1, -2):
        font = open_font(font_source, size)
        lines = _best_break(draw, value, font, max_width)
        if not lines:
            continue
        heights = [_bbox(draw, line, font)[3] - _bbox(draw, line, font)[1] for line in lines]
        gap = round(size * gap_ratio)
        total = sum(heights) + gap * (len(lines) - 1)
        if total <= max_height:
            return TextLayout(lines, font, size, total, gap)
    raise CoverError(f"{label}在当前画幅内无法完整排入两行，请缩短文字或选择更宽的画幅。")


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    layout: TextLayout,
    cx: int,
    y: int,
    fill: tuple[int, int, int],
) -> int:
    for line in layout.lines:
        left, top, right, bottom = _bbox(draw, line, layout.font)
        x = round(cx - (left + right) / 2)
        draw.text((x, y - top), line, font=layout.font, fill=fill)
        y += bottom - top + layout.line_gap
    return y - layout.line_gap


def _apply_glow(image: Image.Image) -> Image.Image:
    width, height = image.size
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(layer)
    for center_x, strength, stretch in ((0.12, 76, 0.33), (0.45, 43, 0.35), (0.87, 67, 0.37)):
        cx = round(width * center_x)
        radius_x = round(width * stretch / 2)
        radius_y = round(height * 0.16)
        glow_draw.ellipse((cx - radius_x, -radius_y, cx + radius_x, radius_y), fill=(235, 239, 240, strength))
    layer = layer.filter(ImageFilter.GaussianBlur(max(16, round(width * 0.035))))
    return Image.alpha_composite(image, layer)


def _compose_background(
    width: int,
    height: int,
    data: bytes | None,
    darkness: int,
    focus_y: int,
    glow: bool,
) -> Image.Image:
    if data is not None:
        image = load_image(data, "背景图")
        image = ImageOps.fit(
            image, (width, height), method=Image.Resampling.LANCZOS,
            centering=(0.5, focus_y / 100),
        )
    else:
        image = Image.new("RGBA", (width, height), (7, 8, 10, 255))
    # 不透明的暗化层确保白色标题在不同来源的底图上具有对比度。
    if data is not None and darkness:
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, round(darkness * 2.55)))
        image = Image.alpha_composite(image, overlay)
    if glow:
        image = _apply_glow(image)
    return image


def _draw_avatar(base: Image.Image, avatar_bytes: bytes, x: int, y: int, size: int) -> None:
    original = load_image(avatar_bytes, "头像")
    circle = ImageOps.fit(original, (size, size), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    # 细而克制的轮廓有利于深背景下头像识别。
    outline = ImageDraw.Draw(base)
    outline.ellipse((x - 2, y - 2, x + size + 1, y + size + 1), outline=(220, 220, 212, 225), width=2)
    base.paste(circle, (x, y), mask)


def render_account_layer(account: str, ratio: str, subtitle_font: FontSource) -> Image.Image:
    """使用 Pillow 生成紧贴实际字形边界的透明图层，供网页拖动和最终合成共用。"""
    if ratio not in SIZES:
        raise CoverError("不支持的画幅比例。")
    account = account.strip()
    if len(account) > 60:
        raise CoverError("账号名称超过长度限制。")
    if not account:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    validate_font_text(subtitle_font, account, "账号名称")
    width, height = SIZES[ratio]
    measuring = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    desired = max(18, round(min(width * 0.036, height * 0.046)))
    for font_size in range(desired, 11, -1):
        font = open_font(subtitle_font, font_size)
        left, top, right, bottom = measuring.textbbox((0, 0), account, font=font)
        text_width, text_height = max(1, right - left), max(1, bottom - top)
        if text_width <= round(width * 0.96) and text_height <= round(height * 0.96):
            layer = Image.new("RGBA", (text_width, text_height), (0, 0, 0, 0))
            ImageDraw.Draw(layer).text((-left, -top), account, font=font, fill=(147, 148, 150, 255))
            return layer
    raise CoverError("账号名称在当前画幅内过长，请缩短文字。")


def account_pixel_position(
    ratio: str, account_x: float, account_y: float, layer_size: tuple[int, int],
) -> tuple[int, int]:
    """位置采用画布左上角的百分比坐标，裁切到文字完整可见的范围内。"""
    if ratio not in SIZES:
        raise CoverError("不支持的画幅比例。")
    if not all(math.isfinite(value) and 0 <= value <= 100 for value in (account_x, account_y)):
        raise CoverError("账号位置须为 0 至 100 之间的百分比。")
    width, height = SIZES[ratio]
    text_width, text_height = layer_size
    return (
        max(0, min(round(width * account_x / 100), width - text_width)),
        max(0, min(round(height * account_y / 100), height - text_height)),
    )


def _cropped_text_layer(canvas: Image.Image) -> tuple[Image.Image, tuple[int, int]]:
    bounds = canvas.getbbox()
    if bounds is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0)), (0, 0)
    return canvas.crop(bounds), bounds[:2]


def _position_layer(
    ratio: str,
    layer_size: tuple[int, int],
    default: tuple[int, int],
    x: float | None,
    y: float | None,
    label: str,
) -> tuple[int, int]:
    """允许各坐标保留自动布局，手动坐标使用左上角画幅百分比并限制在画布内。"""
    width, height = SIZES[ratio]
    for value in (x, y):
        if value is not None and (not math.isfinite(value) or not 0 <= value <= 100):
            raise CoverError(f"{label}的位置须在 0～100% 范围内。")
    max_x = max(0, width - layer_size[0])
    max_y = max(0, height - layer_size[1])
    px = default[0] if x is None else round(width * x / 100)
    py = default[1] if y is None else round(height * y / 100)
    return max(0, min(px, max_x)), max(0, min(py, max_y))


def build_text_layers(
    *,
    title: str,
    subtitle: str,
    account: str,
    ratio: str,
    title_font: FontSource,
    subtitle_font: FontSource,
    title_x: float | None = None,
    title_y: float | None = None,
    subtitle_x: float | None = None,
    subtitle_y: float | None = None,
    account_x: float = 7.2,
    account_y: float = 68.0,
) -> tuple[dict[str, dict], dict]:
    """计算与高清导出共用的三块透明文字层和原生像素坐标。

    大小标题默认位置由原版自动排版计算。只有手工拖动才覆盖其坐标；
    小标题的分隔线和小标题固定在同一透明图层中一起移动。
    """
    if ratio not in SIZES:
        raise CoverError("不支持的画幅比例。")
    title = title.strip().replace("\r\n", "\n").replace("\r", "\n")
    subtitle = subtitle.strip().replace("\r\n", "\n").replace("\r", "\n")
    account = account.strip()
    if not title or not subtitle:
        raise CoverError("大标题与小标题不能为空。")
    if len(title) > 80 or len(subtitle) > 120 or len(account) > 60:
        raise CoverError("输入文字超过长度限制。")
    validate_font_text(title_font, title, "大标题")
    validate_font_text(subtitle_font, subtitle, "小标题")
    validate_font_text(subtitle_font, account, "账号名称")

    width, height = SIZES[ratio]
    portrait = height >= width
    title_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    title_draw = ImageDraw.Draw(title_canvas)
    title_top = round(height * (0.255 if portrait else 0.17))
    title_area = round(height * (0.30 if portrait else 0.35))
    title_start = round(min(width * (0.175 if portrait else 0.135), height * 0.215))
    title_min = max(40, round(min(width, height) * 0.048))
    title_layout = _fit_text(
        title_draw, title, title_font, round(width * 0.89),
        title_area, title_start, title_min, 0.15, "大标题",
    )
    title_end = _draw_centered(
        title_draw, title_layout, width // 2, title_top, (255, 252, 244),
    )
    title_image, title_default = _cropped_text_layer(title_canvas)

    subtitle_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sub_draw = ImageDraw.Draw(subtitle_canvas)
    subtitle_top = max(
        title_end + round(height * 0.029),
        round(height * (0.435 if portrait else 0.485)),
    )
    subtitle_limit = round(height * (0.68 if portrait else 0.735))
    sub_area = subtitle_limit - subtitle_top
    if sub_area <= 0:
        raise CoverError("标题区域空间不足，请缩短大标题。")
    sub_start = round(min(width * 0.054, height * 0.08))
    sub_min = max(22, round(min(width, height) * 0.025))
    sub_layout = _fit_text(
        sub_draw, subtitle, subtitle_font, round(width * 0.87),
        sub_area, sub_start, sub_min, 0.14, "小标题",
    )
    sub_end = _draw_centered(
        sub_draw, sub_layout, width // 2, subtitle_top, (248, 247, 242),
    )
    line_y = sub_end + round(height * 0.016)
    if line_y < round(height * 0.75):
        line_span = round(width * 0.61)
        sub_draw.line(
            (width // 2 - line_span // 2, line_y, width // 2 + line_span // 2, line_y),
            fill=(166, 167, 165, 205),
            width=max(1, round(width / 600)),
        )
    subtitle_image, subtitle_default = _cropped_text_layer(subtitle_canvas)

    account_image = render_account_layer(account, ratio, subtitle_font)
    account_position = account_pixel_position(ratio, account_x, account_y, account_image.size)
    account_default = account_pixel_position(ratio, 7.2, 68.0, account_image.size)

    layers = {
        "title": {
            "image": title_image,
            "position": _position_layer(ratio, title_image.size, title_default, title_x, title_y, "大标题"),
            "default_position": title_default,
        },
        "subtitle": {
            "image": subtitle_image,
            "position": _position_layer(ratio, subtitle_image.size, subtitle_default, subtitle_x, subtitle_y, "小标题"),
            "default_position": subtitle_default,
        },
        "account": {
            "image": account_image,
            "position": account_position,
            "default_position": account_default,
        },
    }
    info = {
        "width": width,
        "height": height,
        "ratio": ratio,
        "title_lines": title_layout.lines,
        "title_font_size": title_layout.font_size,
        "subtitle_lines": sub_layout.lines,
        "subtitle_font_size": sub_layout.font_size,
        "subtitle_text_end": sub_end,
        "title_position": layers["title"]["position"],
        "subtitle_position": layers["subtitle"]["position"],
        "title_size": title_image.size,
        "subtitle_size": subtitle_image.size,
        "account_position": account_position,
        "account_size": account_image.size if account else (0, 0),
    }
    return layers, info


def render_cover(
    *,
    title: str,
    subtitle: str,
    account: str,
    ratio: str,
    title_font: FontSource,
    subtitle_font: FontSource,
    background: bytes | None = None,
    avatar: bytes | None = None,
    darkness: int = 78,
    focus_y: int = 50,
    glow: bool = True,
    title_x: float | None = None,
    title_y: float | None = None,
    subtitle_x: float | None = None,
    subtitle_y: float | None = None,
    account_x: float = 7.2,
    account_y: float = 68.0,
    include_title: bool = True,
    include_subtitle: bool = True,
    include_account: bool = True,
) -> tuple[Image.Image, dict]:
    """返回画布成品或隐藏指定文字层的预览底图，所有位置来自统一图层。"""
    if ratio not in SIZES:
        raise CoverError("不支持的画幅比例。")
    if not 0 <= darkness <= 95 or not 0 <= focus_y <= 100:
        raise CoverError("背景参数超出允许范围。")

    layers, info = build_text_layers(
        title=title, subtitle=subtitle, account=account, ratio=ratio,
        title_font=title_font, subtitle_font=subtitle_font,
        title_x=title_x, title_y=title_y,
        subtitle_x=subtitle_x, subtitle_y=subtitle_y,
        account_x=account_x, account_y=account_y,
    )
    width, height = SIZES[ratio]
    portrait = height >= width
    base = _compose_background(width, height, background, darkness, focus_y, glow)

    # 头像与背景组成固定底图。三个文字图层独立定位，位置调整不影响字形排版。
    title_default_sub_end = info["subtitle_text_end"]
    avatar_size = round(min(width * 0.245, height * 0.23))
    brand_top = max(
        round(height * (0.635 if portrait else 0.76)),
        title_default_sub_end + round(height * 0.065),
    )
    if brand_top + avatar_size > height * 0.94:
        avatar_size = max(0, round(height * 0.94) - brand_top)
    if avatar is not None and avatar_size >= 48:
        _draw_avatar(
            base, avatar, width - round(width * 0.075) - avatar_size,
            brand_top, avatar_size,
        )

    for name, visible in (
        ("title", include_title),
        ("subtitle", include_subtitle),
        ("account", include_account),
    ):
        if visible and (name != "account" or account.strip()):
            layer = layers[name]
            base.alpha_composite(layer["image"], dest=layer["position"])

    return base.convert("RGB"), info
