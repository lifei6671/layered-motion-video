"""Create an explicitly non-production 11.981-second / 360-frame episode."""
import argparse
from io import BytesIO
from pathlib import Path
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from static_comic.contracts import bytes_digest, canonical


def create_fixture(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("Fixture destination must be empty")
    for name in ("input", "assets/images", "review", "work/images/candidates"):
        (root / name).mkdir(parents=True, exist_ok=True)
    parts = ["重复句。\r\n", "重复句。𠮷🙂\r\n", "结尾。"]
    script = b"\xef\xbb\xbf" + "".join(parts).encode("utf-8")
    (root / "input/script.txt").write_bytes(script)
    samples = 575088
    with wave.open(str(root / "input/voice.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\0\0" * samples)
    audio_bytes = (root / "input/voice.wav").read_bytes()
    assets, shots = [], []
    start = 0
    for index, (part, size, color) in enumerate(zip(parts, [(320, 240), (240, 320), (320, 180)],
                                                  ["#df7a58", "#55a2b4", "#8eab62"]), 1):
        image = Image.new("RGB", size, "#f3ecdb")
        draw = ImageDraw.Draw(image)
        w, h = size
        draw.rectangle((w*.4, h*.4, w*.6, h*.6), fill=color)
        draw.line((0, h/2, w, h/2), fill=color, width=2)
        draw.text((5, 5), f"TECHNICAL FIXTURE {index}", fill="black")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        raw = buffer.getvalue()
        name = f"assets/images/shot_{index:04}.png"
        (root / name).write_bytes(raw)
        sid = f"SHOT-{index:03}"
        assets.append({"shot_id": sid, "path": name, "sha256": bytes_digest(raw),
                       "source_mode": "manual_generate", "channel": "technical-fixture",
                       "purpose": "technical_fixture", "prompt": "Deterministic geometric test pattern",
                       "query": "", "author": "fixture script", "source_uri": "local:generated",
                       "accessed_at": "2026-10-21T00:00:00+08:00", "download_method": "local",
                       "style_version": "technical-v1",
                       "license": {"id": "test-only", "evidence": "Programmatically drawn shapes",
                                   "usage_scope": "Automated tests only", "attribution": "", "publication_allowed": False},
                       "review_status": "REVIEW_REQUIRED", "reviewer": None})
        shots.append({"id": sid, "image": name, "script_range": [start, start + len(part)],
                      "narrative": "Technical clock/geometry fixture, not a reviewed storyboard",
                      "start_samples": [0, 192000, 432000][index-1], "boundary_reason": "",
                      "speech_interval_samples": [[1000,190000], [193000,430000], [433000,574000]][index-1],
                      "timing_source": "technical_fixture",
                      "motion": {"type": "zoom_in", "scale_from": 1, "scale_to": 1.08,
                                 "crop_anchor_from": [0.5,0.5], "crop_anchor_to": [0.5,0.5], "easing": "smoothstep"},
                      "cover_anchor": [0.5, 0.5], "subject_bbox": [0.4,0.4,0.6,0.6], "transition_out": None})
        start += len(part)
    for index, placement in enumerate(["end_at_anchor", "start_at_anchor"]):
        shots[index]["transition_out"] = {
            "to_shot_id": shots[index+1]["id"], "relation": "test", "evidence": "Test only",
            "visual_evidence": "Colored shapes", "intent": "Exercise overlap budget",
            "type": "fade", "duration_frames": 12, "placement": placement,
            "semantic_anchor_samples": shots[index+1]["start_samples"], "planning_source": "technical_fixture",
            "image_hashes": [assets[index]["sha256"], assets[index+1]["sha256"]]}
    board = {"schema_version": "2.0", "episode_id": "clock-360", "script_sha256": bytes_digest(script),
             "audio": {"source": "input/voice.wav", "sha256": bytes_digest(audio_bytes),
                       "sample_rate": 48000, "duration_samples": samples}, "shots": shots}
    policy = {"schema_version": "1.0", "mode": "manual_generate", "status": "SOURCE_POLICY_PENDING",
              "default_channel": "technical-fixture",
              "allowed_channels": [{"source_mode": "manual_generate", "channel": "technical-fixture"}],
              "shots": {}, "supersedes": None, "confirmation": None}
    docs = {"input/storyboard.json": board, "input/image_source_policy.json": policy,
            "assets/images/manifest.json": {"schema_version": "1.0", "assets": assets},
            "review/image_approvals.json": {"schema_version": "1.0", "receipts": []}}
    for name, value in docs.items():
        (root / name).write_bytes(canonical(value) + b"\n")
    (root / "input/render.yaml").write_text(
        "width: 1920\nheight: 1080\nfps_num: 30\nfps_den: 1\nalpha_background: '#ffffff'\n", encoding="utf-8")
    return board


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    create_fixture(parser.parse_args().output)
