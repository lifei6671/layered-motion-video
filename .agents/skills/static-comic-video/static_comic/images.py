"""Explicit EXIF/sRGB/alpha/cover preprocessing and deterministic crop geometry."""
from io import BytesIO
import math

from PIL import Image, ImageCms, ImageOps

MAX_PIXELS = 40_000_000


def validate_motion(motion):
    kind = motion["type"]
    z0, z1 = motion["scale_from"], motion["scale_to"]
    a0, a1 = motion["crop_anchor_from"], motion["crop_anchor_to"]
    if kind == "static" and (z0 != z1 or a0 != a1):
        raise ValueError("static motion cannot change scale or anchor")
    if kind == "zoom_in" and z1 <= z0:
        raise ValueError("zoom_in requires increasing scale")
    if kind == "zoom_out" and z1 >= z0:
        raise ValueError("zoom_out requires decreasing scale")
    if kind in ("pan_x", "pan_y"):
        axis = 0 if kind == "pan_x" else 1
        if z0 != z1 or z0 <= 1 or a0[axis] == a1[axis] or a0[1-axis] != a1[1-axis]:
            raise ValueError(f"{kind} requires constant scale > 1 and movement on only its axis")


def motion_at(motion, physical_frame, timing, width, height):
    j = max(0, min(timing["logical_frames"] - 1, physical_frame - timing["head_hold_frames"]))
    u = j / max(1, timing["logical_frames"] - 1)
    e = u * u * (3 - 2 * u)
    z = motion["scale_from"] + (motion["scale_to"] - motion["scale_from"]) * e
    ax, ay = [a + (b - a) * e for a, b in zip(motion["crop_anchor_from"], motion["crop_anchor_to"])]
    w, h = width / z, height / z
    return {"logical_frame": j, "scale": z, "anchor": [ax, ay],
            "crop": [(width - w) * ax, (height - h) * ay, w, h]}


def orient_bbox(bbox, orientation):
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    if not x0 < x1 or not y0 < y1:
        raise ValueError("subject_bbox must have positive width and height")
    points = []
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        points.append({1: (x, y), 2: (1-x, y), 3: (1-x, 1-y), 4: (x, 1-y),
                       5: (y, x), 6: (1-y, x), 7: (1-y, 1-x), 8: (y, 1-x)}[orientation])
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def prepare_image(raw, shot, render, timing):
    validate_motion(shot["motion"])
    try:
        opened = Image.open(BytesIO(raw))
    except Image.DecompressionBombError as error:
        raise ValueError(f"{shot['id']}: image exceeds decoder pixel limit: {error}") from error
    with opened as source:
        if source.format != "PNG" or getattr(source, "n_frames", 1) != 1:
            raise ValueError(f"{shot['id']}: a single-frame PNG is required")
        if source.width * source.height > MAX_PIXELS:
            raise ValueError(f"{shot['id']}: image exceeds {MAX_PIXELS} pixels")
        source.load()
        original_size = list(source.size)
        orientation = source.getexif().get(274, 1)
        if orientation not in range(1, 9):
            raise ValueError(f"{shot['id']}: invalid EXIF orientation")
        oriented = ImageOps.exif_transpose(source)
        bbox = orient_bbox(shot["subject_bbox"], orientation)
        icc = source.info.get("icc_profile")
        rgba = oriented.convert("RGBA")
        if icc:
            try:
                color = oriented if oriented.mode in ("RGB", "CMYK", "LAB", "L") else oriented.convert("RGB")
                color = ImageCms.profileToProfile(color, ImageCms.ImageCmsProfile(BytesIO(icc)),
                                                 ImageCms.createProfile("sRGB"), outputMode="RGB")
            except (ImageCms.PyCMSError, OSError, ValueError) as error:
                raise ValueError(f"{shot['id']}: invalid/unsupported ICC profile: {error}") from error
            color.putalpha(rgba.getchannel("A"))
            rgba = color
        background = Image.new("RGBA", rgba.size, render["alpha_background"])
        rgb = Image.alpha_composite(background, rgba).convert("RGB")
    w, h = rgb.size
    # Match ImageOps.fit exactly, retaining the floating-point source crop box.
    cw, ch = min(w, h * 16 / 9), min(h, w * 9 / 16)
    left = (w - cw) * shot["cover_anchor"][0]
    top = (h - ch) * shot["cover_anchor"][1]
    maximum_scale = max(shot["motion"]["scale_from"], shot["motion"]["scale_to"])
    if maximum_scale > math.sqrt(MAX_PIXELS / (16 * 9)) / 120:
        raise ValueError(f"{shot['id']}: requested preprocessing exceeds pixel budget")
    units = math.ceil(120 * maximum_scale)
    width, height = units * 16, units * 9
    if width * height > MAX_PIXELS:
        raise ValueError(f"{shot['id']}: requested preprocessing exceeds pixel budget")
    prepared = rgb.resize((width, height), Image.Resampling.LANCZOS,
                          box=(left, top, left + cw, top + ch))
    mapped = None if bbox is None else [
        (bbox[0] * w - left) / cw * width, (bbox[1] * h - top) / ch * height,
        (bbox[2] * w - left) / cw * width, (bbox[3] * h - top) / ch * height]
    frames, clipped = [], []
    for local in range(timing["physical_frames"]):
        geometry = motion_at(shot["motion"], local, timing, width, height)
        geometry["global_frame"] = timing["sequence_start_frame"] + local
        if mapped is not None:
            x, y, cw_frame, ch_frame = geometry["crop"]
            contained = (mapped[0] >= x - 1e-7 and mapped[1] >= y - 1e-7
                         and mapped[2] <= x + cw_frame + 1e-7 and mapped[3] <= y + ch_frame + 1e-7)
            geometry["subject_visible"] = contained
            if not contained:
                clipped.append(geometry["global_frame"])
        frames.append(geometry)
    # Discard EXIF and source ICC after conversion: snapshots have one interpretation.
    prepared.info.clear()
    encoded = BytesIO()
    prepared.save(encoded, format="PNG")
    preview = prepared.resize((480, 270), Image.Resampling.LANCZOS)
    preview_bytes = BytesIO()
    preview.save(preview_bytes, format="PNG")
    report = {"shot_id": shot["id"], "original_size": original_size, "orientation": orientation,
              "oriented_size": [w, h], "color": "converted_to_sRGB" if icc else "assumed_sRGB",
              "alpha_background": render["alpha_background"], "cover_box": [left, top, left + cw, top + ch],
              "prepared_size": [width, height], "subject_bbox_prepared": mapped,
              "subject_status": "UNVERIFIED" if mapped is None else ("REVIEW_REQUIRED" if clipped else "PASS"),
              "clipped_global_frames": clipped, "upscale_risk": cw < width or ch < height,
              "frames": frames}
    return encoded.getvalue(), preview_bytes.getvalue(), report
