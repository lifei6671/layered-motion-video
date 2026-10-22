"""Cover Studio 扩展图层与组合的数据契约。

采用场景 v2 可选 extras 集合，保持已保存的五个基础图层兼容。
自由图层的位置、尺寸以原始画幅百分比保存；组合的成员位置保持在画布坐标系中。
"""

from __future__ import annotations

import re
from math import isfinite

from canvas_config import SIZES

MAX_LAYERS = 40
MAX_GROUPS = 12
MAX_MEMBERS = 20
ALLOWED_TYPES = frozenset(("text", "image", "rect", "ellipse"))
IMAGE_ID_RE = re.compile(r"^[0-9a-f]{64}\.(?:png|jpg|jpeg|webp)$")
LAYER_ID_RE = re.compile(r"^custom-[0-9a-f]{12}$")
GROUP_ID_RE = re.compile(r"^group-[0-9a-f]{12}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class ExtraLayerError(ValueError):
    pass


def numeric(value, low: float, high: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ExtraLayerError(f"{label}必须是有限数字。")
    if not low <= value <= high:
        raise ExtraLayerError(f"{label}超出允许范围（{low}～{high}）。")
    return round(float(value), 4)


def color(value, label: str) -> str:
    if not isinstance(value, str) or not COLOR_RE.fullmatch(value):
        raise ExtraLayerError(f"{label}需要使用 #RRGGBB 颜色。")
    return value.lower()


def validate_frame(frame: object, kind: str = "") -> dict:
    required = {"x", "y", "width", "height", "angle"}
    allowed = required | ({"scaleY"} if kind == "text" else set())
    if not isinstance(frame, dict) or not required.issubset(frame) or set(frame) - allowed:
        raise ExtraLayerError("扩展图层需要完整的 x、y、width、height、angle。")
    result = {
        key: numeric(frame[key], 0 if key in ("x", "y") else 1, 100, "frame." + key)
        for key in ("x", "y", "width", "height")
    }
    result["angle"] = numeric(frame["angle"], -180, 180, "frame.angle")
    if "scaleY" in frame:
        result["scaleY"] = numeric(frame["scaleY"], .25, 4, "frame.scaleY")
    if result["x"] + result["width"] > 100.001 or result["y"] + result["height"] > 100.001:
        raise ExtraLayerError("自由图层不得超出画布边界。")
    return result


def _style(value: object, kind: str) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ExtraLayerError("自由图层样式必须为对象。")
    if kind == "text":
        defaults = {"fontSize": 58, "fill": "#ffffff", "opacity": 1}
    elif kind == "image":
        defaults = {"opacity": 1}
    else:
        defaults = {
            "fill": "#c8ac86", "stroke": "#ffffff",
            "strokeWidth": 0, "opacity": 1,
        }
    if set(value) - set(defaults):
        raise ExtraLayerError("自由图层样式包含未知属性。")
    result = defaults | value
    if "fontSize" in result:
        result["fontSize"] = numeric(result["fontSize"], 16, 400, "字号")
    if "strokeWidth" in result:
        result["strokeWidth"] = numeric(result["strokeWidth"], 0, 20, "描边宽度")
    result["opacity"] = numeric(result["opacity"], 0, 1, "透明度")
    for key in ("fill", "stroke"):
        if key in result:
            result[key] = color(result[key], key)
    return result


def normalize_extras(value: object, *, check_font=None) -> dict:
    if value is None:
        return {"layers": [], "groups": []}
    if not isinstance(value, dict) or set(value) - {"layers", "groups"}:
        raise ExtraLayerError("扩展图层集合必须包含有效的 layers、groups。")
    layers = value.get("layers", [])
    groups = value.get("groups", [])
    if not isinstance(layers, list) or len(layers) > MAX_LAYERS:
        raise ExtraLayerError("自由图层最多 40 个。")
    if not isinstance(groups, list) or len(groups) > MAX_GROUPS:
        raise ExtraLayerError("组合最多 12 个。")
    normalized = []
    for record in layers:
        if not isinstance(record, dict):
            raise ExtraLayerError("自由图层定义必须是对象。")
        allowed = {
            "id", "name", "type", "zIndex", "locked", "visible", "frame",
            "text", "fontId", "assetId", "style", "groupId", "ratioFrames",
        }
        if set(record) - allowed:
            raise ExtraLayerError("自由图层定义含未知字段。")
        lid, kind = record.get("id"), record.get("type")
        if not isinstance(lid, str) or not LAYER_ID_RE.fullmatch(lid):
            raise ExtraLayerError("自由图层 ID 不合法。")
        if kind not in ALLOWED_TYPES:
            raise ExtraLayerError("自由图层仅支持文字、图片、矩形与椭圆。")
        name = record.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 70:
            raise ExtraLayerError("自由图层名称须为 1～70 字。")
        z = record.get("zIndex")
        if isinstance(z, bool) or not isinstance(z, int) or not 50 <= z <= 999:
            raise ExtraLayerError("自由图层顺序须为 50～999 的整数。")
        locked, visible = record.get("locked", False), record.get("visible", True)
        if not isinstance(locked, bool) or not isinstance(visible, bool):
            raise ExtraLayerError("自由图层锁定和显示状态必须为布尔值。")
        group_id = record.get("groupId")
        if group_id is not None and (
            not isinstance(group_id, str) or not GROUP_ID_RE.fullmatch(group_id)
        ):
            raise ExtraLayerError("自由图层组合引用无效。")
        original_frame = validate_frame(record.get("frame"), kind)
        ratio_frames = record.get("ratioFrames", {})
        if not isinstance(ratio_frames, dict) or set(ratio_frames) - set(SIZES):
            raise ExtraLayerError("自由图层包含未知画幅或不合法的画幅布局。")
        overrides = {
            ratio: validate_frame(frame, kind)
            for ratio, frame in ratio_frames.items()
        }
        result = {
            "id": lid, "name": name.strip(), "type": kind,
            "frame": original_frame, "ratioFrames": overrides,
            "zIndex": z, "visible": visible, "locked": locked,
            "groupId": group_id, "style": _style(record.get("style"), kind),
        }
        if kind == "text":
            text = record.get("text")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 300:
                raise ExtraLayerError("自由文字内容须为 1～300 字。")
            fid = record.get("fontId")
            if not isinstance(fid, str) or not 1 <= len(fid) <= 100:
                raise ExtraLayerError("自由文字缺少字体引用。")
            if check_font is not None and not check_font(fid):
                raise ExtraLayerError("自由文字字体不存在，请重新选择。")
            result.update(text=text.strip(), fontId=fid)
        if kind == "image":
            asset = record.get("assetId")
            if not isinstance(asset, str) or not IMAGE_ID_RE.fullmatch(asset):
                raise ExtraLayerError("自由图片只能引用素材库中已有的图片。")
            result["assetId"] = asset
        normalized.append(result)
    index = {layer["id"]: layer for layer in normalized}
    if len(index) != len(normalized):
        raise ExtraLayerError("自由图层 ID 不能重复。")
    if len({layer["zIndex"] for layer in normalized}) != len(normalized):
        raise ExtraLayerError("自由图层 zIndex 不能重复。")

    normalized_groups = []
    members_all = set()
    for group in groups:
        if not isinstance(group, dict) or set(group) - {"id", "name", "members", "visible", "locked"}:
            raise ExtraLayerError("组合定义包含未知字段。")
        gid, members = group.get("id"), group.get("members")
        if not isinstance(gid, str) or not GROUP_ID_RE.fullmatch(gid):
            raise ExtraLayerError("组合 ID 不合法。")
        if not isinstance(members, list) or not 2 <= len(members) <= MAX_MEMBERS:
            raise ExtraLayerError("组合需要 2～20 个自由图层成员。")
        if any(not isinstance(mid, str) or mid not in index for mid in members):
            raise ExtraLayerError("组合引用不存在的图层。")
        if len(set(members)) != len(members) or members_all.intersection(members):
            raise ExtraLayerError("组合成员不能重复或跨组合引用。")
        members_all.update(members)
        if any(index[mid]["groupId"] != gid for mid in members):
            raise ExtraLayerError("组合 ID 与成员关联不一致。")
        label = group.get("name", "组合")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 70:
            raise ExtraLayerError("组合名称须为 1～70 个字符。")
        visible, locked = group.get("visible", True), group.get("locked", False)
        if not isinstance(visible, bool) or not isinstance(locked, bool):
            raise ExtraLayerError("组合的显隐与锁定状态必须是布尔值。")
        normalized_groups.append({
            "id": gid, "name": label.strip(), "members": list(members),
            "visible": visible, "locked": locked,
        })
    if len({group["id"] for group in normalized_groups}) != len(normalized_groups):
        raise ExtraLayerError("组合 ID 不能重复。")
    if any(layer["groupId"] is not None and layer["id"] not in members_all for layer in normalized):
        raise ExtraLayerError("自由图层引用了不存在的组合。")
    return {"layers": normalized, "groups": normalized_groups}
