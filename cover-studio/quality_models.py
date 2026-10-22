"""封面安全区方案与人工重叠确认规则（场景 v2 可选扩展）。

平台参考布局为经验预设，并非官方客户端安全区。浏览器执行几何诊断，
服务端只校验质量偏好、画幅兼容性以及合法图层标识。
"""

from __future__ import annotations

from canvas_config import SIZES

QUALITY_PROFILES = {
    "general": tuple(SIZES),
    "vertical_video": ("3:4", "9:16", "4:5"),
    "graphic_post": ("3:4", "9:16", "4:5", "1:1"),
    "landscape_video": ("16:9", "4:3"),
}
MAX_ALLOWED_PAIRS = 100


class QualityError(ValueError):
    pass


def _normalize_pairs(value: object, layer_ids: set[str]) -> list[list[str]]:
    if not isinstance(value, list):
        raise QualityError("允许重叠的图层关系必须是列表。")
    pairs, seen = [], set()
    for pair in value:
        if (not isinstance(pair, list) or len(pair) != 2 or
            any(not isinstance(name, str) or name not in layer_ids for name in pair) or
            pair[0] == pair[1] or "background" in pair):
            raise QualityError("允许重叠的图层标识必须指向两个有效的前景图层。")
        canonical = sorted(pair)
        key = tuple(canonical)
        if key in seen:
            raise QualityError("允许重叠的图层关系不能重复。")
        seen.add(key)
        pairs.append(canonical)
    return sorted(pairs)


def normalize_quality(value: object, *, layer_ids: set[str]) -> dict:
    if value is None:
        return {"profilesByRatio": {}, "allowedOverlaps": [], "allowedByRatio": {}}
    if not isinstance(value, dict) or set(value) - {
        "profilesByRatio", "allowedOverlaps", "allowedByRatio"
    }:
        raise QualityError("布局质量配置格式不正确。")
    profiles = value.get("profilesByRatio", {})
    if not isinstance(profiles, dict):
        raise QualityError("布局安全区方案须为对象。")
    selected = {}
    for ratio, profile in profiles.items():
        if ratio not in SIZES:
            raise QualityError("布局诊断包含未知画幅比例。")
        if not isinstance(profile, str) or profile not in QUALITY_PROFILES:
            raise QualityError("安全区配置名称不正确。")
        if ratio not in QUALITY_PROFILES[profile]:
            raise QualityError("此安全区方案不支持当前画幅。")
        if profile != "general":
            selected[ratio] = profile

    legacy_pairs = _normalize_pairs(value.get("allowedOverlaps", []), layer_ids)
    by_ratio = value.get("allowedByRatio", {})
    if not isinstance(by_ratio, dict) or set(by_ratio) - set(SIZES):
        raise QualityError("画幅专用重叠确认配置格式不正确。")
    normal_by_ratio = {}
    for ratio, pairs in by_ratio.items():
        normalized = _normalize_pairs(pairs, layer_ids)
        if normalized:
            normal_by_ratio[ratio] = normalized
    total = len(legacy_pairs) + sum(len(v) for v in normal_by_ratio.values())
    if total > MAX_ALLOWED_PAIRS:
        raise QualityError("允许重叠的图层关系最多支持 100 组。")
    return {
        "profilesByRatio": dict(sorted(selected.items())),
        "allowedOverlaps": legacy_pairs,
        "allowedByRatio": dict(sorted(normal_by_ratio.items()))
    }
