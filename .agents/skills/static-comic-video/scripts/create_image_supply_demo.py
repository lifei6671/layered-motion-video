"""Create six synthetic image-supply shots, two per channel."""
import argparse
import copy
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tests"))
from PIL import Image, ImageDraw
from create_fixture import create_fixture
from human_support import simulated
from image_support import HUMAN, decision_for, make_brief, make_submission
from static_comic import image_supply as images
from static_comic.contracts import bytes_digest, canonical, digest, validate


def create_demo(root):
    root = Path(root)
    board = create_fixture(root)  # Requires an empty directory; never overwrites an episode.
    parts = ["第一张测试图。", "第二张测试图。", "第三张测试图。", "第四张测试图。", "第五张测试图。", "第六张测试图。"]
    raw = "".join(parts).encode("utf-8")
    shots, end = [], 0
    for i, text in enumerate(parts):
        shot = copy.deepcopy(board["shots"][0])
        shot.update(id=f"SHOT-{i+1:03}", image=f"assets/images/shot_{i+1:04}.png",
                    script_range=[end, end + len(text)], start_samples=i * 95000,
                    speech_interval_samples=[i * 95000 + 1000, i * 95000 + 90000], transition_out=None)
        end += len(text)
        shots.append(shot)
        im = Image.new("RGB", (640, 360), "#f3ecdb")
        draw = ImageDraw.Draw(im)
        draw.rectangle((256, 144, 384, 216), fill=["#df7a58", "#55a2b4", "#8eab62"][i//2], outline="#333333", width=3)
        draw.text((24, 24), f"SYNTHETIC TEST ONLY / SHOT {i+1}", fill="black")
        im.save(root / shot["image"])
    board.update(shots=shots, script_sha256=bytes_digest(raw))
    modes = ["agent_generate", "third_party_retrieve", "manual_generate"]
    assignments = [{"source_mode": mode, "channel": "synthetic-" + mode} for mode in modes]
    policy = {"schema_version": "1.0", "mode": "mixed", "status": "SOURCE_POLICY_PENDING", "default_channel": None,
              "allowed_channels": assignments, "shots": {s["id"]: assignments[i//2] for i, s in enumerate(shots)},
              "supersedes": None, "confirmation": None}
    images.write_docs(root, {"input/script.txt": raw, "input/storyboard.json": board, images.POLICY: policy,
                            images.MANIFEST: {"schema_version": "1.0", "assets": []},
                            "SYNTHETIC-ONLY.txt": b"NOT REAL HUMAN APPROVAL. NO EXTERNAL PROVIDER CALLED. TIMING REMAINS TECHNICAL FIXTURE.\n"})
    images.confirm(root, "policy", simulated("policy", {"payload_sha256": images.policy_options(root)["payload_sha256"], "human": HUMAN}))
    brief = make_brief(board)
    result = images.plan(root, brief)
    images.confirm(root, "plan", simulated("plan", {"payload_sha256": result["payload_sha256"], "human": HUMAN}))
    req = images.requests(root)
    for i, shot in enumerate(shots):
        images.dispatch(root, shot["id"])
        if i == 0:
            images.dispatch(root, shot["id"], unavailable="Synthetic test failure; not an actual provider availability claim")
        images.ingest(root, make_submission(root, req, i))
    images.report(root)
    review = decision_for(root)
    images.review(root, decision_for(root, ["SHOT-002"], "REJECTED"))
    images.ingest(root, make_submission(root, req, 1))
    images.review(root, decision_for(root))
    result = images.verify(root)
    images.report(root)
    cases = []
    for kind, value in [("imageBrief", brief), ("imageRequests", req), ("imageSubmission", make_submission(root, req, 0)),
                        ("imageReview", review), ("imageSupply", images.supply(root)),
                        ("manifest", {"schema_version": "1.0", "assets": []})]:
        validate(kind, value)
        cases.append({"name": "p3a-" + kind, "kind": kind, "valid": True, "value": value})
        bad = copy.deepcopy(value)
        bad["unknown_field"] = True
        cases.append({"name": "p3a-unknown-" + kind, "kind": kind, "valid": False, "value": bad})
    invalid = copy.deepcopy(review)
    invalid["items"][0]["checks"]["comic_style"] = "yes"
    cases.append({"name": "p3a-review-boolean", "kind": "imageReview", "valid": False, "value": invalid})
    images.write_docs(root, {"review/demo-result.json": {"artifact_kind": "synthetic_test", "result": result,
                        "source_modes": modes, "counts": [2, 2, 2], "real_human_acceptance": "NOT_RUN",
                        "real_tool_acquisition": "NOT_RUN", "formal_render": "BLOCKED_BY_TECHNICAL_TIMING"}})
    return cases


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--contracts-output", required=True)
    args = parser.parse_args()
    cases = create_demo(args.output)
    Path(args.contracts_output).write_bytes(canonical(cases) + b"\n")
    print("PASS: synthetic six-shot demo; human acceptance NOT_RUN")
