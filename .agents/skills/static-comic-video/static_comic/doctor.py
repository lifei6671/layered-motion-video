"""Read-only runtime and local model checks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from .paths import process_args

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "renderer" / "static-comic"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(argv, cwd, timeout=60, env=None):
    """Run a native executable with separate arguments."""
    try:
        argv, cwd = process_args(argv, cwd)
        result = subprocess.run(
            argv, cwd=cwd,
            env=dict(os.environ if env is None else env, PYTHONIOENCODING="utf-8"), timeout=timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return {"status": "PASS" if result.returncode == 0 else "FAIL",
                "argv": [str(arg) for arg in argv], "cwd": str(cwd),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "UNAVAILABLE", "argv": [str(arg) for arg in argv],
                "cwd": str(cwd), "reason": str(error)}


def executable_check(name, args):
    path = shutil.which(name)
    if not path:
        return {"status": "UNAVAILABLE", "reason": f"{name} is not on PATH"}
    result = run([path, *args], ROOT)
    result["executable_sha256"] = sha256(path)
    return result


def local_cli(node, renderer=RENDERER):
    cli = renderer / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not cli.is_file():
        return {"status": "UNAVAILABLE", "reason": "Local Remotion missing; run npm ci in renderer/static-comic. No npx download attempted."}
    return run([node, cli, "versions"], renderer)


def path_probe():
    with tempfile.TemporaryDirectory(prefix="静态漫画 路径 ") as directory:
        result = run([sys.executable, "-c",
                      "import pathlib,sys; print(pathlib.Path.cwd().name); print(sys.argv[1])",
                      "中文 参数 & literal"], Path(directory))
        failure = run([sys.executable, "-c", "raise SystemExit(7)"], Path(directory))
        okay = (result["status"] == "PASS"
                and "中文 参数 & literal" in result["stdout"]
                and failure.get("returncode") == 7)
        return {"status": "PASS" if okay else "FAIL", "success": result,
                "expected_failure": failure}


def model_probe(lock_path):
    if lock_path is None:
        return {"status": "NOT_RUN", "reason": "Pass --models-lock with local model paths, revisions and file SHA256 values."}
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                       HF_HUB_DISABLE_TELEMETRY="1")
    return run([sys.executable, ROOT / "scripts" / "probe_models.py", lock_path],
               ROOT, timeout=300, env=environment)


def doctor(browser=None, models_lock=None):
    checks = {
        "python": {"status": "PASS" if sys.version_info[:2] == (3, 12) else "FAIL",
                   "version": platform.python_version(), "executable": sys.executable},
        "node": executable_check("node", ["--version"]),
        "ffmpeg": executable_check("ffmpeg", ["-version"]),
        "ffprobe": executable_check("ffprobe", ["-version"]),
        "unicode_process": path_probe(),
    }
    node = shutil.which("node")
    if node:
        checks["remotion_cli"] = local_cli(node)
        if browser and browser.is_file():
            checks["browser_react"] = run([node, RENDERER / "probe.mjs", browser], RENDERER)
            checks["browser_react"]["executable_sha256"] = sha256(browser)
        else:
            checks["browser_react"] = {"status": "UNAVAILABLE", "reason": "Pass --browser with an existing headless Chrome executable; doctor never downloads one."}
    else:
        checks["remotion_cli"] = checks["browser_react"] = {"status": "UNAVAILABLE", "reason": "Node is missing"}
    checks["whisperx_import"] = run([sys.executable, "-c",
        "import json,torch,whisperx.asr,whisperx.alignment; from importlib.metadata import version; "
        "print(json.dumps({'whisperx':version('whisperx'),'torch':torch.__version__,"
        "'cuda_available':torch.cuda.is_available(),'device_count':torch.cuda.device_count()}))"], ROOT, timeout=180)
    checks["models"] = model_probe(models_lock)
    locks = {str(path.relative_to(ROOT)): sha256(path) for path in
             (ROOT / "uv.lock", RENDERER / "package-lock.json") if path.is_file()}
    if len(locks) != 2:
        checks["dependency_locks"] = {"status": "FAIL", "reason": "Both lockfiles are required"}
    else:
        checks["dependency_locks"] = {"status": "PASS", "sha256": locks}
    return {"stage": "SC-P0", "checked_at": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "status": "PASS" if all(c["status"] == "PASS" for c in checks.values()) else "FAIL",
            "scope": "Runtime only; license, image capabilities and human acceptance are separate records.",
            "checks": checks}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["doctor"])
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--models-lock", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = doctor(args.browser.resolve() if args.browser else None,
                    args.models_lock.resolve() if args.models_lock else None)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content)
    return 0 if report["status"] == "PASS" else 1
