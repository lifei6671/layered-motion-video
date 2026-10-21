"""Generate synthetic transition protocol and effect fixtures."""
import argparse
import copy
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tests"))
from create_image_supply_demo import create_demo as create_images
from speech_support import seed_alignment
from transition_support import proposal_for, decision_for
from static_comic import transitions
from static_comic.contracts import canonical, digest, validate
from static_comic.project import compile_project


def create_demo(root):
    root = Path(root)
    create_images(root)
    board = transitions.read_doc(root, "input/storyboard.json", "storyboard")
    manifest = transitions.read_doc(root, "assets/images/manifest.json", "manifest")
    assets = {a["shot_id"]: a for a in manifest["assets"]}
    approvals = {a["shot_id"]: a for a in transitions.read_doc(root, "review/image_approvals.json", "approvals")["receipts"]}
    for i, shot in enumerate(board["shots"]):
        shot["timing_source"] = "manual_confirmed"
        if i < len(board["shots"]) - 1:
            following = board["shots"][i+1]
            shot["transition_out"] = {"to_shot_id": following["id"], "relation": "synthetic_placeholder",
                 "evidence": "合成测试占位硬切", "visual_evidence": "合成测试几何方块", "intent": "仅用于初始化对齐协议",
                 "type": "cut", "duration_frames": 0, "placement": "start_at_anchor",
                 "semantic_anchor_samples": following["start_samples"], "planning_source": "human",
                 "image_hashes": [assets[s["id"]]["sha256"] for s in (shot, following)],
                 "image_approval_hashes": [digest(approvals[s["id"]]) for s in (shot, following)]}
    transitions.write_docs(root, {"input/storyboard.json": board,
        "SYNTHETIC-ONLY.txt": b"TEST ONLY. Synthetic images, speech windows and human receipts. Production-shaped compiler path is exercised only as a development fixture. No real semantic or publication acceptance.\n"})
    seed_alignment(root)
    proposal = proposal_for(root)
    effects = ["cut", "fade", "wipe_from_left", "wipe_from_right", "fade_black"]
    placements = ["start_at_anchor", "center_on_anchor", "end_at_anchor", "start_at_anchor", "end_at_anchor"]
    for item, effect, placement in zip(proposal["boundaries"], effects, placements):
        item.update(type=effect, duration_frames=0 if effect == "cut" else 12, placement=placement)
        if effect != "cut":
            item.update(intent=f"仅合成协议测试：执行 {effect} 并核对 {placement} 的整数窗口；不代表真实叙事选择。",
                        visual_evidence="合成测试：居中的彩色矩形便于辨认覆盖方向及端点；效果只用于执行契约覆盖。")
        if effect.startswith("wipe_"):
            item.update(relation="spatial_progression", direction=effect[5:],
                        direction_evidence="仅效果覆盖测试：约定后图从左边进入。" if effect.endswith("left") else "仅效果覆盖测试：约定后图从右边进入。")
        if effect == "fade_black":
            item.update(relation="chapter_end", black_interval_reason="仅效果覆盖测试：用中间黑帧模拟章节间隔；不表示真实叙事判断。")
    transitions.propose(root, proposal)
    candidates = transitions.read_doc(root, transitions.CANDIDATES, "transitionCandidates")
    decision = decision_for(root)
    transitions.confirm(root, decision)
    transitions.apply(root)
    compiled = compile_project(root)
    transitions.report(root)
    result = {"artifact_kind": "synthetic_test", "boundaries": 5, "effects": effects, "total_frames": compiled["total_frames"],
              "compiler_path": "production-shaped path with synthetic receipts, not real approval",
              "real_human_semantic_acceptance": "NOT_RUN", "real_image_acquisition": "NOT_RUN",
              "real_audio_inference": "NOT_RUN", "effect_variety": "Fixture coverage only; no production diversity quota"}
    transitions.write_docs(root, {"review/demo-result.json": result})
    cases = []
    for kind, value in [("plannerInput", transitions.read_doc(root, transitions.INPUT, "plannerInput")),
                        ("transitionProposal", proposal), ("transitionCandidates", candidates),
                        ("transitionDecision", decision),
                        ("transitionReviews", transitions.read_doc(root, transitions.REVIEWS, "transitionReviews"))]:
        validate(kind, value)
        cases.append({"name": "p4-" + kind, "kind": kind, "valid": True, "value": value})
        bad = copy.deepcopy(value)
        bad["execute_shell"] = "never executed"
        cases.append({"name": "p4-closed-" + kind, "kind": kind, "valid": False, "value": bad})
    for field, value in (("type", "custom_react"), ("duration_frames", 1.5), ("physical_frames", 90)):
        bad = copy.deepcopy(proposal)
        bad["boundaries"][0][field] = value
        cases.append({"name": "p4-invalid-" + field, "kind": "transitionProposal", "valid": False, "value": bad})
    return cases


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--contracts-output", required=True)
    args = parser.parse_args()
    cases = create_demo(args.output)
    Path(args.contracts_output).write_bytes(canonical(cases) + b"\n")
    print("PASS: synthetic P4 candidate/review/apply/compile; actual semantic acceptance NOT_RUN")
