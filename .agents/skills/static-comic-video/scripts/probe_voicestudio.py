"""Inspect the local service before preparing models; no uploads or downloads."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def inspect_service(base):
    url = urlsplit(base)
    if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1")
            or url.username or url.password or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError("Expected a local HTTP service root, e.g. http://127.0.0.1:13900")
    base = base.rstrip("/")
    checks = {}
    for endpoint in ("/health", "/openapi.json", "/engines/asr", "/dictation/readiness?purpose=transcribe"):
        try:
            with urlopen(base + endpoint, timeout=15) as response:
                data = json.load(response)
            if endpoint == "/openapi.json":
                paths = data["paths"]
                schemas = data.get("components", {}).get("schemas", {})
                selected = {path: definition for path, definition in paths.items()
                            if "transcrib" in path or "transcription" in path or "align" in path}
                data = {"paths": selected, "request_schemas": {
                    name: schema for name, schema in schemas.items()
                    if "transcrib" in name.lower() or "transcription" in name.lower() or "align" in name.lower()}}
            elif endpoint == "/engines/asr":
                data = {"active": data["active"], "active_model": data.get("active_model"),
                        "backend": next((b for b in data["backends"] if b["id"] == data["active"]), None)}
            checks[endpoint] = {"status": "PASS", "response": data}
        except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as error:
            checks[endpoint] = {"status": "UNAVAILABLE", "reason": str(error)}
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "url": base,
            "status": "PASS" if all(c["status"] == "PASS" for c in checks.values()) else "FAIL",
            "scope": "HTTP discovery only; inspect readiness and contracts separately. No inference, model installation or settings changes.",
            "checks": checks, "transcription_smoke": "NOT_RUN",
            "confirmed_text_alignment_acceptance": "NOT_RUN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_service(args.url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report["status"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
