"""SC-M 动态镜头实际抽帧审核；所有图片摘要加入既有有声预览批准绑定。"""
from io import BytesIO

from PIL import Image, ImageDraw

from .contracts import bytes_digest, canonical
from .emphasis_preview import extract_markers


def motion_card_evidence(visual, compiled, loc):
    cards = compiled["motion_cards"]["events"]
    if not cards:
        return {}
    frames = []
    for card in cards:
        first, last = card["start_frame"], card["end_frame"]
        duration = last - first
        for label, index in (
            ("before", first),
            ("enter", first + min(10, duration - 1)),
            ("focus", first + min(27, duration - 1)),
            ("hold", first + duration // 2),
            ("exit", last - 2),
        ):
            if not 0 <= index < compiled["total_frames"]:
                raise ValueError("Motion-card audit frame leaves composition")
            frames.append((card, label, index))
    image_map, video_sha, batches = extract_markers(visual, [row[2] for row in frames])
    outputs, inventory, tiles = {}, [], []
    base = loc["preview"] + "/motion_cards"
    for card, marker, index in frames:
        data = image_map[index]
        name = f"{base}/{card['id']}-{marker}-{index:06}.png"
        outputs[name] = data
        inventory.append({"card_id": card["id"], "recipe": card["recipe"], "marker": marker,
                          "frame": index, "file": name, "sha256": bytes_digest(data)})
        with Image.open(BytesIO(data)) as source:
            thumb = Image.new("RGB", (320, 204), "#eeeeee")
            thumb.paste(source.convert("RGB").resize((320, 180)), (0, 24))
            ImageDraw.Draw(thumb).text((4, 4), f"{card['id']} {marker} f={index}", fill="black")
            tiles.append(thumb)
    width, rows = 1280, (len(tiles) + 3) // 4
    sheet = Image.new("RGB", (width, rows * 204), "#dddddd")
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (i % 4 * 320, i // 4 * 204))
    memory = BytesIO()
    sheet.save(memory, format="JPEG", quality=90)
    outputs[loc["preview"] + "/motion_cards_sheet.jpg"] = memory.getvalue()
    outputs[loc["preview"] + "/motion_cards.json"] = canonical({
        "artifact_kind": compiled["artifact_kind"], "video_sha256": video_sha,
        "decode_batches": batches, "unique_frames": len(image_map),
        "selected_motion_cards": cards, "frames": inventory,
        "human_full_listening": "NOT_RUN",
    })
    return outputs
