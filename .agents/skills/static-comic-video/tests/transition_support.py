from human_support import simulated
"""Synthetic semantic observations/decisions for temporary tests, never user review."""
from static_comic import transitions
from static_comic.contracts import digest
from image_support import HUMAN


def proposal_for(root):
    transitions.prepare(root)
    request = transitions.read_doc(root, transitions.INPUT, "plannerInput")
    items = []
    for i, b in enumerate(request["boundaries"]):
        items.append({"from_shot_id": b["from_shot"]["id"], "to_shot_id": b["to_shot"]["id"],
                      "viewed_images": [b[k]["sha256"] for k in ("from_asset", "to_asset")],
                      "observations": {"before": "合成测试：米色背景中央有彩色矩形，主体与边缘之间有留白。",
                                       "after": "合成测试：后图仍是米色背景，中央矩形颜色随镜头变化。",
                                       "continuity": "合成测试：几何方块的居中布局连续，无真实角色身份需要推断。"},
                      "relation": "continuous_narration", "evidence": [{"script_range": b["to_shot"]["script_range"],
                                                                        "quote": b["to_text"]}],
                      "visual_evidence": "合成测试：相邻方块保持居中，颜色变化足以区分镜头，无需显眼叠加效果。",
                      "intent": "合成测试：下一段口播开始时直接显示后图，避免几何块重叠造成双影。",
                      "type": "cut", "duration_frames": 0, "placement": "start_at_anchor",
                      "anchor_id": "boundary", "direction": "not_applicable", "direction_evidence": "",
                      "black_interval_reason": "", "image_text_conflict": False})
    return {"input_sha256": digest(request), "author": {"name": "SYNTHETIC TEST ONLY", "role": "agent",
            "at": "2026-10-21T00:00:00Z", "evidence": "Synthetic test observations, not real image viewing or human approval"},
            "boundaries": items}


def decision_for(root, *, decision="APPROVED", indices=None):
    value = transitions.read_doc(root, transitions.CANDIDATES, "transitionCandidates")
    return simulated("transitions", {"candidate_sha256": digest(value), "human": HUMAN, "items": [
        {"from_shot_id": item["from_shot_id"], "to_shot_id": item["to_shot_id"], "decision": decision,
         "reason": "Synthetic semantic decision for automated tests only",
         "checks": {k: True for k in ("semantics", "visual", "timing", "direction", "style_continuity")}}
        for i, item in enumerate(value["items"]) if indices is None or i in indices]})


def seed_transitions(root):
    transitions.propose(root, proposal_for(root))
    transitions.confirm(root, decision_for(root))
    transitions.apply(root)
