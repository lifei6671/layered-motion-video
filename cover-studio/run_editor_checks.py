"""隔离数据运行 React 编辑器实际浏览器、正式静帧及像素基准检查。"""
from __future__ import annotations

import hashlib
from copy import deepcopy
import logging
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Thread

from PIL import Image, ImageChops, ImageStat
from werkzeug.serving import make_server

import app as webapp
from font_catalog import default_local_font_id
from editor_build import ensure_editor_bundle
from react_editor import ensure_react_bundle

ROOT = Path(__file__).resolve().parent


def main():
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    ready, message = ensure_react_bundle(ROOT)
    if not ready:
        print(message)
        return 2
    ready, message = ensure_editor_bundle(ROOT)
    if not ready:
        print(message)
        return 2
    output = ROOT / "output/editor-checks"
    output.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (640, 360), "#e7af62").save(output / "fixture-upload.png")
    with tempfile.TemporaryDirectory(prefix="cover-editor-check-") as temp:
        data = Path(temp)
        # Font files are immutable inputs. Reuse conversion caches, keeping design data isolated.
        cached_fonts = ROOT / "data/font-web"
        if cached_fonts.is_dir():
            shutil.copytree(cached_fonts, data / "font-web")
        Image.new("RGB", (1920, 1080), "#304050").save(data / "background.png")
        fid = default_local_font_id()
        preset = {"settings": {"title": "旧版兼容标题", "subtitle": "完整迁移测试", "account": "测试账号", "ratio": "16:9", "title_font_id": fid, "subtitle_font_id": fid,
                                "title_font_mode": "local", "subtitle_font_mode": "local", "title_x": 20, "title_y": 30},
                  "assets": {"background": {"file": "background.png", "name": "测试背景"}}}
        preset_file = data / "preset.json"
        preset_file.write_text(json.dumps(preset, ensure_ascii=False), encoding="utf8")
        before = hashlib.sha256(preset_file.read_bytes()).hexdigest()
        original_data, original_preset = webapp.DATA_DIR, webapp.PRESET_FILE
        webapp.DATA_DIR, webapp.PRESET_FILE = data, preset_file
        with webapp.app.test_client() as client:
            scene = client.get("/api/designs/legacy").get_json()
            scene["name"] = "自动折行迁移基准"
            scene["extras"]["layers"].append({"id": "custom-abcdef123456", "name": "长文字", "type": "text", "zIndex": 50,
                "locked": False, "visible": True, "groupId": None, "frame": {"x": 10, "y": 10, "width": 30, "height": 20, "angle": 0, "scaleY": 2},
                "ratioFrames": {}, "text": "自动折行迁移测试" * 5, "fontId": fid, "style": {"fontSize": 58, "fill": "#ffffff", "opacity": 1}})
            response = client.post("/api/designs", json=scene)
            assert response.status_code == 201, response.get_json()
            rotated = deepcopy(scene)
            rotated["name"] = "旋转迁移基准"
            rotated["extras"]["layers"] = [{"id": ident, "name": ident, "type": "rect", "zIndex": 50 + i,
                "visible": True, "locked": False, "groupId": None, "ratioFrames": {},
                "frame": {"x": 20 + i * 25, "y": 20, "width": 30, "height": 20, "angle": angle},
                "style": {"fill": "#f3ba36", "opacity": 1, "stroke": "#ffffff", "strokeWidth": 0}}
                for i, (ident, angle) in enumerate([("custom-111111111111", 90), ("custom-222222222222", -27)])]
            response = client.post("/api/designs", json=rotated)
            assert response.status_code == 201, response.get_json()
        server = make_server("127.0.0.1", 0, webapp.app, threaded=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            command = [shutil.which("node"), str(ROOT / "editor/tests/browser.mjs"), f"http://127.0.0.1:{server.server_port}", str(output)]
            result = subprocess.run(command, cwd=ROOT / "editor", capture_output=True, text=True, encoding="utf8", errors="replace", timeout=420, check=False)
            (output / "browser.stdout.log").write_text(result.stdout, encoding="utf8")
            (output / "browser.stderr.log").write_text(result.stderr, encoding="utf8")
            print(result.stdout, flush=True)
            if result.returncode:
                print(result.stderr, flush=True)
                return result.returncode
            assert hashlib.sha256(preset_file.read_bytes()).hexdigest() == before, "Original preset was modified"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            webapp.DATA_DIR, webapp.PRESET_FILE = original_data, original_preset
    preview = Image.open(output / "browser-artwork.png").convert("RGB")
    formal = Image.open(output / "formal.png").convert("RGB")
    assert preview.size == formal.size == (1920, 1080)
    diff = ImageChops.difference(preview, formal)
    means = ImageStat.Stat(diff).mean
    diff.save(output / "preview-export-diff.png")
    report = {"dimensions": list(formal.size), "mean_abs_rgb": means, "max_channel_error": max(hi for lo, hi in diff.getextrema()),
              "exact_match": diff.getbbox() is None, "threshold_mean": .1, "png_status": "PASS" if max(means) <= .1 else "FAIL"}
    with Image.open(output / "formal.jpg") as jpeg:
        assert jpeg.size == (1920, 1080) and jpeg.format == "JPEG"
        report["jpeg_status"] = "PASS"
    report["legacy_preset_bytes"] = "UNCHANGED"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        video = output / "cover-pipeline-smoke.mp4"
        result = subprocess.run([ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(output / "formal.png"), "-t", "0.2", "-r", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], capture_output=True, timeout=45, check=False)
        report["ffmpeg_image_consumer"] = "PASS" if result.returncode == 0 and video.stat().st_size > 0 else "FAIL"
    else:
        report["ffmpeg_image_consumer"] = "NOT_RUN"
    (output / "image-comparison.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(report), flush=True)
    return 0 if report["png_status"] == "PASS" and report["ffmpeg_image_consumer"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
