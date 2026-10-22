"""在隔离目录运行 Fabric.js 浏览器校验，生成封面与多画幅几何对照。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Thread

from PIL import Image, ImageDraw
from werkzeug.serving import make_server

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import app  # noqa: E402
from editor_build import ensure_editor_bundle  # noqa: E402
from layout_compare import compare_from_browser_output


def win_path(path: Path) -> str:
    value = str(path.resolve())
    return value[4:] if os.name == "nt" and value.startswith("\\\\?\\") else value


def prepare_test_data(original: Path, destination: Path) -> None:
    """复制经典配置及其图片引用，测试设计写入临时数据目录。"""
    destination.mkdir(parents=True, exist_ok=True)
    legacy = original / "preset.json"
    if not legacy.is_file():
        return
    import json

    settings = json.loads(legacy.read_text(encoding="utf-8"))
    (destination / "preset.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    for kind in ("background", "avatar"):
        meta = settings.get("assets", {}).get(kind, {})
        filename = meta.get("file") if isinstance(meta, dict) else None
        if (
            isinstance(filename, str)
            and filename.startswith(kind + ".")
            and Path(filename).name == filename
        ):
            original_file = original / filename
            if original_file.is_file():
                shutil.copy2(original_file, destination / filename)


def fixtures(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    bg = Image.new("RGB", (900, 1200), (126, 153, 177))
    draw_bg = ImageDraw.Draw(bg)
    draw_bg.rectangle((100, 140, 770, 1060), outline=(238, 213, 171), width=30)
    bg.save(output / "fixture-background.png")
    avatar = Image.new("RGB", (400, 400), (223, 185, 119))
    ImageDraw.Draw(avatar).ellipse((65, 50, 330, 335), fill=(54, 74, 91))
    avatar.save(output / "fixture-avatar.png")


def main() -> int:
    ready, message = ensure_editor_bundle(BASE)
    print(message, flush=True)
    if not ready:
        return 2
    real_data, real_preset = app.DATA_DIR, app.PRESET_FILE
    output = BASE / "output" / "fabric-poc-check"
    fixtures(output)

    try:
        with tempfile.TemporaryDirectory(prefix="scene-poc-", dir=BASE / "output") as temp:
            app.DATA_DIR = Path(temp) / "data"
            app.PRESET_FILE = app.DATA_DIR / "preset.json"
            prepare_test_data(real_data, app.DATA_DIR)
            server = make_server("127.0.0.1", 0, app.app, threaded=True)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.socket.getsockname()[1]
                runner = BASE / "fabric-poc" / "tests" / "browser-check.mjs"
                command = [
                    "node", win_path(runner),
                    f"http://127.0.0.1:{port}", win_path(output),
                ]
                print("浏览器渲染验证开始：", command[2], flush=True)
                result = subprocess.run(
                    command, cwd=win_path(BASE / "fabric-poc"),
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=150, check=False,
                )
                print(result.stdout, flush=True)
                if result.stderr:
                    print(result.stderr, file=sys.stderr, flush=True)
                if result.returncode == 0:
                    report = compare_from_browser_output(
                        result.stdout, output / "layout-comparison.json"
                    )
                    print("几何排版对照：", report, flush=True)
                print("浏览器验证结果：", result.returncode, flush=True)
                return result.returncode
            finally:
                server.shutdown()
                thread.join(timeout=5)
    finally:
        app.DATA_DIR, app.PRESET_FILE = real_data, real_preset


if __name__ == "__main__":
    raise SystemExit(main())
