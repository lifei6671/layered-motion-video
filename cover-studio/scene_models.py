"""Cover Studio 场景模型 v2。

负责旧版模板参数迁移、严格校验、画幅变体与素材引用。
这里定义数据，不引用 Fabric 或 Pillow 的排版计算。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from canvas_config import SIZES
from free_layer_models import ExtraLayerError, normalize_extras
from quality_models import QualityError, normalize_quality

SCHEMA_VERSION = 2
MAX_SCENE_BYTES = 128 * 1024
TEXT_LIMITS = {"title": 80, "subtitle": 120, "account": 60}
POSITIONABLE = ("title", "subtitle", "account")
SUPPORTED_ASSETS = ("background", "avatar")
TITLE_LAYOUT = {"maxLines": 2, "wrap": "balanced", "minFontPx": 42}
ASSET_KINDS = {"none", "legacy", "managed"}
TEXT_LAYER_IDS = ("title", "subtitle", "account")


def default_text_style(kind: str) -> dict:
    fills = {"title": "#fffcf4", "subtitle": "#f8f7f2", "account": "#939496"}
    if kind not in fills:
        raise SceneError("文字图层不存在。")
    return {
        "fontSize": None, "charSpacing": 0, "lineHeight": 1.15,
        "fill": fills[kind], "opacity": 1.0, "stroke": "#000000",
        "strokeWidth": 0, "angle": 0,
        "shadow": {
            "enabled": False, "color": "#000000", "opacity": 0.45,
            "blur": 0, "offsetX": 0, "offsetY": 0,
        },
    }


def default_avatar_style() -> dict:
    return {"opacity": 1.0, "angle": 0, "scale": 1.0}


def _number_in_range(value: Any, low: float, high: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise SceneError(f"{label} 必须是有限数值。")
    if not low <= value <= high:
        raise SceneError(f"{label} 须在 {low}～{high} 之间。")
    return round(float(value), 4)


def _hex_color(value: Any, label: str) -> str:
    import re

    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise SceneError(f"{label} 应为 #RRGGBB 格式的颜色。")
    return value.lower()


def _normalized_object(value: Any, defaults: dict, label: str) -> dict:
    if value is None:
        return deepcopy(defaults)
    if not isinstance(value, dict):
        raise SceneError(f"{label} 应为配置对象。")
    unexpected = set(value) - set(defaults)
    if unexpected:
        raise SceneError(f"{label} 存在未知属性：{', '.join(sorted(unexpected))}")
    merged = deepcopy(defaults)
    merged.update(value)
    return merged


def normalize_text_style(value: Any, kind: str) -> dict:
    style = _normalized_object(value, default_text_style(kind), kind + ".style")
    value_size = style["fontSize"]
    style["fontSize"] = None if value_size is None else _number_in_range(
        value_size, 16, 400, kind + ".fontSize"
    )
    style["charSpacing"] = _number_in_range(style["charSpacing"], -150, 1000, kind + ".charSpacing")
    style["lineHeight"] = _number_in_range(style["lineHeight"], .8, 2.5, kind + ".lineHeight")
    style["opacity"] = _number_in_range(style["opacity"], 0, 1, kind + ".opacity")
    style["strokeWidth"] = _number_in_range(style["strokeWidth"], 0, 16, kind + ".strokeWidth")
    style["angle"] = _number_in_range(style["angle"], -180, 180, kind + ".angle")
    style["fill"] = _hex_color(style["fill"], kind + ".fill")
    style["stroke"] = _hex_color(style["stroke"], kind + ".stroke")
    shadow = _normalized_object(style["shadow"], default_text_style(kind)["shadow"], kind + ".shadow")
    if not isinstance(shadow["enabled"], bool):
        raise SceneError(f"{kind}.shadow.enabled 必须是布尔值。")
    shadow["color"] = _hex_color(shadow["color"], kind + ".shadow.color")
    shadow["opacity"] = _number_in_range(shadow["opacity"], 0, 1, kind + ".shadow.opacity")
    shadow["blur"] = _number_in_range(shadow["blur"], 0, 60, kind + ".shadow.blur")
    for direction in ("offsetX", "offsetY"):
        shadow[direction] = _number_in_range(shadow[direction], -60, 60, kind + ".shadow." + direction)
    style["shadow"] = shadow
    return style


def normalize_avatar_style(value: Any) -> dict:
    style = _normalized_object(value, default_avatar_style(), "avatar.style")
    style["opacity"] = _number_in_range(style["opacity"], 0, 1, "avatar.opacity")
    style["angle"] = _number_in_range(style["angle"], -180, 180, "avatar.angle")
    style["scale"] = _number_in_range(style["scale"], .5, 2.5, "avatar.scale")
    return style


class SceneError(ValueError):
    pass


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def auto_position() -> dict:
    return {"mode": "auto", "x": None, "y": None}


def manual_position(x: float | None, y: float | None) -> dict:
    return {"mode": "manual", "x": x, "y": y}


def default_variant() -> dict:
    return {name: auto_position() for name in POSITIONABLE}


def make_layer_definitions() -> list[dict]:
    return [
        {
            "id": "background", "type": "image", "zIndex": 0, "locked": True,
            "assetRef": "background",
        },
        {
            "id": "avatar", "type": "image", "zIndex": 10, "locked": True,
            "assetRef": "avatar", "mask": "circle", "style": default_avatar_style(),
        },
        {
            "id": "title", "type": "text", "zIndex": 20, "locked": False,
            "contentRef": "title", "fontRef": "title", "layout": deepcopy(TITLE_LAYOUT),
            "style": default_text_style("title"),
        },
        {
            "id": "subtitle", "type": "group", "zIndex": 30, "locked": False,
            "children": ["subtitle-text", "subtitle-divider"],
            "style": default_text_style("subtitle"),
        },
        {
            "id": "account", "type": "text", "zIndex": 40, "locked": False,
            "contentRef": "account", "fontRef": "subtitle",
            "style": default_text_style("account"),
        },
    ]


def _check_coord(value: Any, key: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise SceneError(f"{key} 必须是数字或自动坐标。")
    if not 0 <= value <= 100:
        raise SceneError(f"{key} 须在 0 至 100 之间。")
    return round(float(value), 4)


def normalize_position(value: Any, key: str) -> dict:
    if not isinstance(value, dict):
        raise SceneError(f"图层 {key} 的位置配置必须是对象。")
    mode = value.get("mode", "auto")
    if mode not in ("auto", "manual"):
        raise SceneError(f"图层 {key} 的位置模式不支持：{mode}")
    if mode == "auto":
        return auto_position()
    x = _check_coord(value.get("x"), key + ".x")
    y = _check_coord(value.get("y"), key + ".y")
    if x is None and y is None:
        return auto_position()
    return manual_position(x, y)


def normalize_variant(value: Any, ratio: str) -> dict:
    if not isinstance(value, dict):
        raise SceneError(f"画幅 {ratio} 布局必须是对象。")
    unexpected = set(value) - set(POSITIONABLE)
    if unexpected:
        raise SceneError(f"画幅 {ratio} 含未知图层：{', '.join(sorted(unexpected))}")
    return {
        kind: normalize_position(value.get(kind, auto_position()), kind)
        for kind in POSITIONABLE
    }


def normalize_scene(data: Any, *, check_font=None) -> dict:
    if not isinstance(data, dict):
        raise SceneError("设计必须是 JSON 对象。")
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise SceneError("场景版本不兼容，请通过旧模板导入接口迁移。")

    ident = data.get("id")
    if ident is not None and (
        not isinstance(ident, str) or
        len(ident) > 80 or
        not all(c.isalnum() or c in "-_" for c in ident)
    ):
        raise SceneError("设计标识格式不正确。")
    name = data.get("name", "")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 70:
        raise SceneError("设计名称须为 1～70 个字符。")
    content = data.get("content")
    if not isinstance(content, dict):
        raise SceneError("缺少封面文案。")
    normalized_content = {}
    for key, limit in TEXT_LIMITS.items():
        text = content.get(key)
        if not isinstance(text, str) or len(text) > limit:
            raise SceneError(f"{key} 文案长度超出限制。")
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if key != "account" and not text:
            raise SceneError("大标题和小标题不能为空。")
        normalized_content[key] = text

    font_refs = data.get("fontRefs")
    if not isinstance(font_refs, dict):
        raise SceneError("字体引用缺失。")
    fonts = {}
    for role in ("title", "subtitle"):
        ref = font_refs.get(role)
        if not isinstance(ref, str) or not 1 <= len(ref) <= 100:
            raise SceneError(f"{role} 字体引用不正确。")
        if check_font is not None and not check_font(ref):
            raise SceneError(f"{role} 字体已不存在，请在字体库中重新选择。")
        fonts[role] = ref

    assets = data.get("assets", {})
    if not isinstance(assets, dict):
        raise SceneError("图片素材配置格式不正确。")
    normal_assets = {}
    for kind in SUPPORTED_ASSETS:
        value = assets.get(kind, {"source": "none"})
        if not isinstance(value, dict):
            raise SceneError(f"{kind} 素材配置格式错误。")
        source = value.get("source")
        if source not in ASSET_KINDS:
            raise SceneError(f"{kind} 素材来源不支持。")
        if source == "managed":
            item_id = value.get("id")
            if not isinstance(item_id, str) or not (item_id.endswith((".png", ".jpg", ".jpeg", ".webp")) and len(item_id) <= 72):
                raise SceneError(f"{kind} 素材引用格式不正确。")
            digest, _, suffix = item_id.partition(".")
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise SceneError(f"{kind} 素材引用的文件指纹不合法。")
            normal_assets[kind] = {"source": "managed", "id": item_id}
        elif source == "legacy":
            normal_assets[kind] = {"source": "legacy"}
        else:
            normal_assets[kind] = {"source": "none"}

    style = data.get("backgroundStyle", {})
    if not isinstance(style, dict):
        raise SceneError("背景样式须为对象。")
    darkness = style.get("darkness", 78)
    focus_y = style.get("focusY", 50)
    glow = style.get("glow", True)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in (darkness, focus_y)):
        raise SceneError("背景参数必须为数字。")
    if not (0 <= darkness <= 95 and 0 <= focus_y <= 100):
        raise SceneError("背景参数超出范围。")
    if not isinstance(glow, bool):
        raise SceneError("光晕开关应为布尔值。")

    active = data.get("activeRatio", "3:4")
    if active not in SIZES:
        raise SceneError("画幅比例无效。")
    all_variants = data.get("variants", {})
    if not isinstance(all_variants, dict):
        raise SceneError("画幅布局配置必须是对象。")
    if set(all_variants) - set(SIZES):
        raise SceneError("包含不支持的画幅比例。")
    variants = {ratio: normalize_variant(v, ratio) for ratio, v in all_variants.items()}
    variants.setdefault(active, default_variant())

    revisions = data.get("revision", 0)
    if isinstance(revisions, bool) or not isinstance(revisions, int) or not 0 <= revisions < 100000000:
        raise SceneError("设计修订号不合法。")

    # v2 图层集合固定，但隐藏、锁定和层级顺序可以编辑并持久化。
    # 以服务端定义为基础，避免请求篡改类型、文件路径或组合成员关系。
    definitions = make_layer_definitions()
    incoming_layers = data.get("layers")
    if incoming_layers is not None:
        if not isinstance(incoming_layers, list):
            raise SceneError("图层列表须为数组。")
        expected = {layer["id"] for layer in definitions}
        if (
            len(incoming_layers) != len(definitions)
            or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in incoming_layers)
            or {item["id"] for item in incoming_layers} != expected
        ):
            raise SceneError("当前场景版本需要完整的五个基础图层。")
        keyed = {item["id"]: item for item in incoming_layers}
        seen = set()
        for layer in definitions:
            saved = keyed[layer["id"]]
            if saved.get("type", layer["type"]) != layer["type"]:
                raise SceneError("图层类型不允许修改。")
            visible = saved.get("visible", True)
            locked = saved.get("locked", layer["locked"])
            z_index = saved.get("zIndex", layer["zIndex"])
            if not isinstance(visible, bool) or not isinstance(locked, bool):
                raise SceneError("图层可见性和锁定状态必须是布尔值。")
            if isinstance(z_index, bool) or not isinstance(z_index, int) or not 0 <= z_index <= 1000:
                raise SceneError("图层顺序须在 0～1000 范围内。")
            if z_index in seen:
                raise SceneError("图层顺序不能重复。")
            if layer["id"] == "background" and (z_index != 0 or locked is False):
                raise SceneError("背景图层必须位于最底层并保持锁定。")
            if layer["id"] != "background" and z_index == 0:
                raise SceneError("非背景图层必须位于背景上方。")
            seen.add(z_index)
            if layer["id"] in TEXT_LAYER_IDS:
                layer["style"] = normalize_text_style(saved.get("style"), layer["id"])
            elif layer["id"] == "avatar":
                layer["style"] = normalize_avatar_style(saved.get("style"))
            elif "style" in saved:
                raise SceneError("背景图层样式由背景配置统一管理。")
            layer.update(visible=visible, locked=locked, zIndex=z_index)
    else:
        for layer in definitions:
            layer["visible"] = True

    try:
        extras = normalize_extras(data.get("extras"), check_font=check_font)
    except ExtraLayerError as exc:
        raise SceneError(str(exc)) from exc
    all_layer_ids = {part["id"] for part in definitions}
    all_layer_ids.update(part["id"] for part in extras["layers"])
    all_layer_ids.update(group["id"] for group in extras["groups"])
    try:
        quality = normalize_quality(data.get("quality"), layer_ids=all_layer_ids)
    except QualityError as exc:
        raise SceneError(str(exc)) from exc

    return {
        "schemaVersion": SCHEMA_VERSION, "id": ident,
        "name": name.strip(), "revision": revisions,
        "updatedAt": data.get("updatedAt") if isinstance(data.get("updatedAt"), str) else None,
        "content": normalized_content, "fontRefs": fonts,
        "assets": normal_assets,
        "backgroundStyle": {
            "darkness": int(round(darkness)), "focusY": int(round(focus_y)),
            "glow": glow,
        },
        "activeRatio": active, "variants": variants,
        "layers": definitions, "extras": extras, "quality": quality,
    }


def from_legacy_preset(settings: dict, asset_names: dict, *,
                       title_font_id: str, subtitle_font_id: str) -> dict:
    """把旧模板映射为可复制的设计草稿，只在原始比例继承手工坐标。"""
    ratio = settings.get("ratio", "3:4")
    if ratio not in SIZES:
        ratio = "3:4"
    positions = default_variant()
    for name in POSITIONABLE:
        x, y = settings.get(name + "_x"), settings.get(name + "_y")
        if name == "account":
            x = 7.2 if x is None else x
            y = 68.0 if y is None else y
        if x is not None or y is not None:
            positions[name] = manual_position(x, y)

    scene = {
        "schemaVersion": SCHEMA_VERSION, "id": None,
        "name": "经典封面 · 黑底书法", "revision": 0,
        "content": {
            role: settings.get(role, default)
            for role, default in (
                ("title", "复利思维"),
                ("subtitle", "存款百万不是结束而是开始"),
                ("account", "@封面工坊"),
            )
        },
        "fontRefs": {"title": title_font_id, "subtitle": subtitle_font_id},
        "assets": {
            kind: {"source": "legacy"} if asset_names.get(kind) else {"source": "none"}
            for kind in SUPPORTED_ASSETS
        },
        "backgroundStyle": {
            "darkness": settings.get("darkness", 78),
            "focusY": settings.get("focus_y", 50),
            "glow": settings.get("glow", True),
        },
        "activeRatio": ratio, "variants": {ratio: positions},
        "layers": make_layer_definitions(),
        "extras": {"layers": [], "groups": []},
    }
    return normalize_scene(scene)
