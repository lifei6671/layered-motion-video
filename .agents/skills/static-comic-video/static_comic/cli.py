"""Small command boundary for the implemented phases."""
import argparse
import json
import sys
import subprocess
from pathlib import Path

from .project import compile_project


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'human-confirm':
        from .human_review import main as human_main
        try:
            print(json.dumps(human_main(sys.argv[2:]), ensure_ascii=True))
            return 0
        except (ValueError, OSError, EOFError) as error:
            print(json.dumps({'status': 'FAIL', 'error': str(error)}), file=sys.stderr)
            return 2

    if len(sys.argv) > 1 and sys.argv[1] in ('init', 'status', 'studio', 'preview', 'inspect', 'approve', 'render-visual', 'mux', 'verify'):
        from .delivery import main as delivery_main
        try:
            print(json.dumps(delivery_main(sys.argv[1:]), ensure_ascii=True))
            return 0
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            print(json.dumps({'status': 'FAIL', 'error': str(error)}), file=sys.stderr)
            return 2
    if len(sys.argv) > 1 and sys.argv[1] == "transitions":
        from .transitions import main as transition_main
        try:
            print(json.dumps(transition_main(sys.argv[2:]), ensure_ascii=True))
            return 0
        except (ValueError, OSError) as error:
            print(json.dumps({"status": "FAIL", "error": str(error)}), file=sys.stderr)
            return 2
    if len(sys.argv) > 1 and sys.argv[1] == "images":
        from .image_supply import main as image_main
        try:
            print(json.dumps(image_main(sys.argv[2:]), ensure_ascii=True))
            return 0
        except (ValueError, OSError) as error:
            print(json.dumps({"status": "FAIL", "error": str(error)}), file=sys.stderr)
            return 2
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        from .doctor import main as doctor_main
        return doctor_main()
    parser = argparse.ArgumentParser(description="Static comic compiler; see images/transitions/preview/approve --help for production workflow")
    parser.add_argument("command", choices=("validate", "compile", "align"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--technical-fixture", action="store_true", help="Separate, non-production fixture outputs")
    parser.add_argument("--voice-url", default="http://127.0.0.1:13900")
    parser.add_argument("--asr-source", choices=("voicestudio", "local"), default="voicestudio",
                        help="Coarse ASR source; local explicitly uses the locked offline model")
    parser.add_argument("--models-lock", default=str(Path(__file__).resolve().parents[1] / "reports/models.lock.json"))
    args = parser.parse_args()
    try:
        if args.command == "align":
            from .speech import align_project
            result = align_project(args.project, url=args.voice_url, models_lock=args.models_lock,
                                   technical_fixture=args.technical_fixture, asr_source=args.asr_source)
            print(json.dumps({k:result[k] for k in ("status","boundaries","anomalies")}, ensure_ascii=True))
            return 0 if result["status"] == "PASS" else 3
        result = compile_project(args.project, technical_fixture=args.technical_fixture, write=args.command == "compile")
        print(json.dumps({k: result[k] for k in ("status", "artifact_kind", "total_frames", "written")}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        # ASCII JSON remains parseable even on a Windows legacy-codepage console.
        print(json.dumps({"status": "FAIL", "error": str(error)}), file=sys.stderr)
        return 2
