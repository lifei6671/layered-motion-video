"""Record exact local model bytes after explicit preparation, without network access."""
import argparse
import hashlib
from importlib.metadata import version
from importlib.util import find_spec
import json
from pathlib import Path


def entry(path, revision):
    root = path.resolve(strict=True)
    files = {}
    for item in sorted(root.rglob("*")):
        if item.is_file():
            with item.open("rb") as stream:
                files[item.relative_to(root).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    if not files:
        raise ValueError(f"Empty model: {root}")
    return {"path": str(root), "revision": revision, "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asr", required=True, type=Path)
    parser.add_argument("--asr-revision", required=True)
    parser.add_argument("--alignment", required=True, type=Path)
    parser.add_argument("--alignment-revision", required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], required=True)
    parser.add_argument("--compute-type", choices=["int8", "float16", "float32"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    vad = Path(find_spec("whisperx").origin).parent / "assets"
    lock = {"device": args.device, "compute_type": args.compute_type,
            "asr": entry(args.asr, args.asr_revision),
            "alignment": entry(args.alignment, args.alignment_revision),
            "vad": entry(vad, "whisperx-" + version("whisperx"))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
