"""Generate and measure a 60/180-second synthetic workload."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.create_fixture import create_fixture
from static_comic import delivery
from static_comic.contracts import canonical
from static_comic.media import file_hash


def create_workload(root, seconds):
    if seconds not in (60, 180):
        raise ValueError("Only 60/180-second performance fixtures are supported")
    root = Path(root).resolve()
    board = create_fixture(root)
    original = board["audio"]["duration_samples"]
    samples = seconds * 48000
    with wave.open(str(root / "input/voice.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48000)
        stream.writeframes(b"\0\0" * samples)
    board["episode_id"] = f"sc-p7-synthetic-{seconds}s"
    board["audio"].update(duration_samples=samples, sha256=file_hash(root / "input/voice.wav"))
    for shot in board["shots"]:
        shot["start_samples"] = shot["start_samples"] * samples // original
        shot["speech_interval_samples"] = [s * samples // original for s in shot["speech_interval_samples"]]
        if shot["transition_out"]:
            shot["transition_out"]["semantic_anchor_samples"] = shot["transition_out"]["semantic_anchor_samples"] * samples // original
    (root / "input/storyboard.json").write_bytes(canonical(board))
    marker = {"scope": "SYNTHETIC PERFORMANCE ONLY", "seconds": seconds,
              "human_acceptance": "NOT_RUN", "content": "3 existing geometric test shots and silence"}
    (root / "performance-fixture.json").write_bytes(canonical(marker))
    return board


def run_benchmark(root, mode, seconds):
    root = Path(root).resolve()
    if mode == "cold":
        create_workload(root, seconds)
    else:
        marker = json.loads((root / "performance-fixture.json").read_bytes())
        if marker.get("scope") != "SYNTHETIC PERFORMANCE ONLY" or marker.get("seconds") != seconds:
            raise ValueError("Not the requested synthetic workload")
        if not (root / "benchmark-cold.json").is_file():
            raise ValueError("Run cold successfully before warm")
    result_path = root / f"benchmark-{mode}.json"
    if result_path.exists():
        raise ValueError("Benchmark result already exists; preserve the measurement")
    pre = delivery.preview(root, True)
    if mode == "cold":
        delivery.approve(root, {
            "stage": "preview", "binding_sha256": pre["binding_sha256"],
            "human": {"actor": "TEST_ONLY performance harness", "actor_role": "human",
                      "at": datetime.now(timezone.utc).isoformat(), "evidence": "SYNTHETIC fixture; no actual human approval"},
            "decision": "APPROVED", "checks": {"semantics": True, "full_listening": True, "formal_quality": False},
            "reason": "TEST_ONLY exercise technical rendering; never production acceptance"}, True)
    delivery.render_visual(root, True)
    verified = delivery.mux(root, True)
    if verified["production_accepted"]:
        raise AssertionError("Synthetic workload must never be production accepted")
    cache = {p.stem: json.loads(p.read_bytes()) for p in (root / "reports/cache").glob("*.json")}
    expected = "REBUILT" if mode == "cold" else "HIT"
    for stage in ("visual-preview", "visual-final", "mux-preview", "mux-final"):
        if cache[stage]["status"] != expected:
            raise AssertionError(f"{stage}: expected {expected}, got {cache[stage]['status']}")
    result = {"status": "PASS", "scope": "SYNTHETIC PERFORMANCE ONLY", "seconds": seconds,
              "frames": seconds * 30, "mode": mode, "cache_verified": True, "cache": cache,
              "human_acceptance": "NOT_RUN", "validation": verified,
              "final_sha256": file_hash(root / "output/technical/final.mp4")}
    result_path.write_bytes(canonical(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--seconds", type=int, choices=(60, 180), required=True)
    parser.add_argument("--mode", choices=("cold", "warm"), required=True)
    args = parser.parse_args()
    result = run_benchmark(args.project, args.mode, args.seconds)
    print(json.dumps({k: result[k] for k in ("status", "scope", "seconds", "mode", "cache_verified")}))
