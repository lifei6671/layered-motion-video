from human_support import simulated
"""Synthetic evidence for temporary test episodes; never real human approval."""
from static_comic import image_supply as images
from static_comic.contracts import bytes_digest, digest
from static_comic.paths import write_bytes

HUMAN = {"actor": "TEST ONLY", "actor_role": "human", "at": "2026-10-21T00:00:00Z",
         "evidence": "Synthetic test receipt; never use for real production"}


def make_brief(board):
    return {"style_version": "test-v1", "style": "暖色漫画，细黑线条", "characters": "无人物；几何方块身份一致",
            "objects": "保持同一方块比例", "lighting": "左上柔光", "exclusions": "不要文字、水印、写实照片和裁切主体",
            "publication_scope": "仅合成测试，不授权发布",
            "shots": [{"shot_id": s["id"], "visual_task": "测试占位方块", "picture_type": "漫画示意图",
                       "composition": "主体居中，四边留白"} for s in board["shots"]]}


def make_submission(root, req, index):
    item = req["shots"][index]
    raw = b"SYNTHETIC TEST EVIDENCE ONLY"
    path = "work/images/test-evidence.txt"
    write_bytes(root, path, raw)
    evidence = {"path": path, "sha256": bytes_digest(raw)}
    return {"shot_id": item["shot_id"], "request_sha256": digest(req), **item["assignment"],
            "file": item["formal_path"], "usage_role": "final_artwork", "tool": "test-fixture",
            "tool_version": "1", "prompt": item["prompt"], "query": "synthetic geometry",
            "author": "fixture script", "source_uri": "https://example.invalid/test-only", "site": "test-only",
            "accessed_at": "2026-10-21T00:00:00Z", "download_method": "synthetic local fixture, no network",
            "license": {"id": "test-only", "evidence": "Generated geometric fixture", "usage_scope": "Tests only",
                        "attribution": "fixture script", "publication_allowed": True},
            "license_evidence": evidence, "references": [], "request_record": evidence, "output_record": evidence}


def decision_for(root, indices=None, decision="APPROVED"):
    req = images.requests(root)
    board = images.read_doc(root, "input/storyboard.json", "storyboard")
    shots = {s["id"]: s for s in board["shots"]}
    records = images.supply(root)["records"]
    if indices is not None:
        records = [r for r in records if r["shot_id"] in indices]
    return simulated("images", {"request_sha256": digest(req), "human": HUMAN, "items": [
        {"shot_id": r["shot_id"], "candidate_sha256": r["candidate"]["sha256"], "record_sha256": digest(r),
         "geometry_sha256": images.review_geometry(req, shots[r["shot_id"]]),
         "decision": decision, "reason": "Synthetic automated test decision, not human acceptance",
         "checks": {k: True for k in ("comic_style", "character_identity", "narrative", "composition", "motion_safe",
                                      "resolution_accepted", "publication_rights", "attribution_ready")}}
        for r in records]})


def seed_supply(root, board):
    result = images.plan(root, make_brief(board))
    images.confirm(root, "plan", simulated("plan", {"payload_sha256": result["payload_sha256"], "human": HUMAN}))
    req = images.requests(root)
    for index in range(len(req["shots"])):
        images.ingest(root, make_submission(root, req, index))
    images.review(root, decision_for(root))
