"""Load explicitly locked local ASR/alignment weights; never fetch weights."""
import hashlib
import json
from pathlib import Path
import sys


def verify_model(entry):
    root = Path(entry["path"]).resolve(strict=True)
    if not entry["revision"] or not entry["files"]:
        raise ValueError("Model revision and file hashes are required")
    actual = {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}
    if set(actual) != set(entry["files"]):
        raise ValueError(f"Model file inventory changed: {root}")
    for name, path in actual.items():
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != entry["files"][name]:
            raise ValueError(f"Model SHA256 mismatch: {name}")
    return root


def main():
    import torch
    import numpy as np
    import whisperx
    from importlib.util import find_spec
    from whisperx.alignment import load_align_model

    lock = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    device = lock["device"]
    if device not in ("cpu", "cuda"):
        raise ValueError("device must be cpu or cuda")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("Requested CUDA is unavailable; no device fallback")
    asr_path = verify_model(lock["asr"])
    alignment_path = verify_model(lock["alignment"])
    vad_path = verify_model(lock["vad"])
    if vad_path != (Path(find_spec("whisperx").origin).parent / "assets").resolve():
        raise ValueError("VAD lock does not identify this WhisperX installation")
    asr = whisperx.load_model(str(asr_path), device=device, language="zh",
                             compute_type=lock["compute_type"], local_files_only=True)
    silence = asr.transcribe(np.zeros(16000, dtype=np.float32), batch_size=1)
    model, metadata = load_align_model("zh", device, model_name=str(alignment_path), model_cache_only=True)
    # Exercise weights, not merely package metadata or a filesystem existence check.
    sample = torch.zeros(1, 16000, device=device)
    with torch.inference_mode():
        logits = model(sample).logits
    if not torch.isfinite(logits).all():
        raise RuntimeError("Alignment model produced non-finite output")
    print(json.dumps({"status": "PASS", "device": device,
                      "asr_device": asr.model.model.device,
                      "silence_result": silence,
                      "alignment_language": metadata["language"],
                      "alignment_shape": list(logits.shape),
                      "scope": "Model loading and synthetic forward pass, not speech accuracy"}))


if __name__ == "__main__":
    main()
