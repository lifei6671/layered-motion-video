"""React/Remotion 共用的 CoverDocument v3；只在 HTTP / 文件边界校验。"""
from __future__ import annotations

import re
from copy import deepcopy
from math import isfinite

from scene_models import SceneError
from scene_store import ASSET_FILE, DESIGN_FILE

MAX_DOCUMENT_BYTES = 384 * 1024


def _number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not low <= value <= high:
        raise SceneError(f"{label} 须为 {low}～{high} 的有限数字。")
    return value


def _color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise SceneError("颜色须为 #RRGGBB。")
    return value


def _text(value, limit, label, *, empty=True):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise SceneError(f"{label} 长度不合法（最多 {limit} 字）。")
    try:
        value.encode("utf8")
    except UnicodeEncodeError as exc:
        raise SceneError(f"{label} 包含无效的 Unicode 字符。") from exc
    return value


def normalize_document(data, *, check_font=None):
    if not isinstance(data, dict) or data.get("schemaVersion") != 3 or data.get("kind") != "cover-document":
        raise SceneError("封面文档版本不兼容，请通过模板导入迁移。")
    allowed = {"schemaVersion", "kind", "id", "revision", "name", "width", "height", "background", "layers", "updatedAt", "sourceScene"}
    if set(data) - allowed:
        raise SceneError("文档含未知字段。")
    doc = deepcopy(data)
    ident = doc.get("id")
    if ident is not None and (not isinstance(ident, str) or not DESIGN_FILE.fullmatch(ident)):
        raise SceneError("文档标识不合法。")
    revision = doc.get("revision")
    if type(revision) is not int or not 0 <= revision <= 2**31 - 1:
        raise SceneError("文档版本号不合法。")
    _text(doc.get("name"), 70, "文档名称", empty=False)
    for axis in ("width", "height"):
        if type(doc.get(axis)) is not int or not 100 <= doc[axis] <= 8192:
            raise SceneError("画布尺寸须为 100～8192 的整数。")
    _color(doc.get("background"))
    if doc.get("updatedAt") is not None:
        _text(doc["updatedAt"], 60, "更新时间")
    if "sourceScene" in doc and (not isinstance(doc["sourceScene"], dict) or doc["sourceScene"].get("schemaVersion") != 2):
        raise SceneError("原始场景格式不正确。")
    layers = doc.get("layers")
    if not isinstance(layers, list) or len(layers) > 60:
        raise SceneError("封面最多支持 60 个图层。")
    ids = set()
    font_ids = set()
    fields = {"id", "name", "type", "frame", "visible", "locked", "opacity", "text", "fontId", "fontSize", "fontWeight", "align", "lineHeight", "letterSpacing", "color", "stroke", "strokeWidth", "shadow", "assetId", "fit", "focusY", "darkness", "radius"}
    for layer in layers:
        if not isinstance(layer, dict) or not fields.issubset(layer) or set(layer) - fields - {"textScaleY", "glow", "imageShape"}:
            raise SceneError("图层字段不完整或含未知字段。")
        lid = _text(layer["id"], 80, "图层标识", empty=False)
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", lid) or lid in ids:
            raise SceneError("图层标识重复或不合法。")
        ids.add(lid)
        _text(layer["name"], 70, "图层名称", empty=False)
        kind = layer["type"]
        if kind not in ("text", "image", "rect", "ellipse"):
            raise SceneError("图层类型不支持。")
        for flag in ("visible", "locked"):
            if not isinstance(layer[flag], bool):
                raise SceneError("图层显示和锁定状态须为布尔值。")
        frame = layer["frame"]
        if not isinstance(frame, dict) or set(frame) != {"x", "y", "width", "height", "rotation"}:
            raise SceneError("图层 frame 不完整。")
        for axis in ("x", "y"):
            _number(frame[axis], -16384, 16384, axis)
        for axis in ("width", "height"):
            _number(frame[axis], 1, 16384, axis)
        _number(frame["rotation"], -180, 180, "旋转")
        for field, low, high in (("opacity", 0, 1), ("fontSize", 8, 500), ("fontWeight", 100, 1000), ("lineHeight", .5, 4), ("letterSpacing", -75, 500), ("strokeWidth", 0, 32), ("focusY", 0, 100), ("darkness", 0, 100), ("radius", 0, 8192)):
            _number(layer[field], low, high, field)
        for color in ("color", "stroke"):
            _color(layer[color])
        if "textScaleY" in layer:
            _number(layer["textScaleY"], .1, 10, "文字纵向缩放")
        if "glow" in layer and not isinstance(layer["glow"], bool):
            raise SceneError("背景光晕须为布尔值。")
        if layer.get("imageShape", "rectangle") not in ("rectangle", "circle"):
            raise SceneError("图片形状不支持。")
        if kind == "image" and layer.get("imageShape") == "circle" and abs(frame["width"] - frame["height"]) > .01:
            raise SceneError("圆形图片的宽高须一致。")
        if layer["align"] not in ("left", "center", "right", "justify") or layer["fit"] not in ("cover", "contain", "fill"):
            raise SceneError("对齐或裁切方式不支持。")
        _text(layer["text"], 500, "图层文字")
        _text(layer["fontId"], 100, "字体标识")
        _text(layer["assetId"], 80, "素材标识")
        if kind == "text":
            if not layer["fontId"]:
                raise SceneError("文字图层缺少字体。")
            font_ids.add(layer["fontId"])
        if (kind == "image" or layer["assetId"]) and layer["assetId"] not in ("builtin:noir", "builtin:tech") and not ASSET_FILE.fullmatch(layer["assetId"]):
            raise SceneError("图片素材标识不合法。")
        if kind == "text" and layer["assetId"]:
            raise SceneError("文字图层不支持图片填充。")
        shadow = layer["shadow"]
        if not isinstance(shadow, dict) or set(shadow) != {"enabled", "color", "opacity", "blur", "x", "y"}:
            raise SceneError("阴影字段不完整。")
        if not isinstance(shadow["enabled"], bool):
            raise SceneError("阴影开关须为布尔值。")
        _color(shadow["color"])
        for field, low, high in (("opacity", 0, 1), ("blur", 0, 100), ("x", -100, 100), ("y", -100, 100)):
            _number(shadow[field], low, high, "阴影 " + field)
    if check_font is not None:
        for fid in font_ids:
            if not check_font(fid):
                raise SceneError("字体不存在，请刷新目录后重新选择。")
    return doc
