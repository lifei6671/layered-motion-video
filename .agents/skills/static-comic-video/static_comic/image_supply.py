"""Image requests, candidate provenance and user review.
"""
from copy import deepcopy
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path

from PIL import Image
import yaml

from .cache import publish
from .contracts import bytes_digest, canonical, digest, read_json, validate
from .images import MAX_PIXELS, prepare_image
from .paths import read_bytes, resolve_path, write_bytes
from .project import IMAGE_FILE, SMALL_FILE, check_human, check_source_policy

REQUESTS = "work/planning/image_requests.json"
SUPPLY = "work/images/image_supply.json"
POLICY = "input/image_source_policy.json"
APPROVALS = "review/image_approvals.json"
MANIFEST = "assets/images/manifest.json"


def read_doc(root, name, kind):
    return validate(kind, read_json(read_bytes(root, name, SMALL_FILE)))


def write_docs(root, outputs):
    publish(root, {name: data if isinstance(data, bytes) else canonical(data) + b"\n"
                   for name, data in outputs.items()})


def inputs(root, *, planned_boxes=None, planned_motions=None):
    board = read_doc(root, "input/storyboard.json", "storyboard")
    raw = read_bytes(root, "input/script.txt", SMALL_FILE)
    if bytes_digest(raw) != board["script_sha256"]:
        raise ValueError("Original script bytes changed")
    text = raw.decode("utf-8-sig")
    end, ids = 0, set()
    for index, shot in enumerate(board["shots"], 1):
        a, b = shot["script_range"]
        if a != end or not a < b <= len(text) or shot["id"] in ids:
            raise ValueError("Invalid image request script ranges or shot IDs")
        if shot["image"] != f"assets/images/shot_{index:04}.png":
            raise ValueError("Invalid formal image filename")
        end = b
        ids.add(shot["id"])
    if end != len(text):
        raise ValueError("Incomplete image request script ranges")
    policy = read_doc(root, POLICY, "policy")
    assignments = check_source_policy(policy, board["shots"])
    # Timing and transition planning belong to P3/P4 and may change independently.
    visual = [{k: s[k] for k in ("id", "image", "script_range", "narrative", "motion",
                               "cover_anchor", "subject_bbox")} for s in board["shots"]]
    if planned_boxes is not None:
        # Acquisition binds the original planning hint; measured boxes belong to review.
        for shot in visual:
            if shot["id"] in planned_boxes:
                shot["subject_bbox"] = planned_boxes[shot["id"]]
    if planned_motions is not None:
        # Preserve the acquisition request; current motion is bound by visual review.
        for shot in visual:
            if shot["id"] in planned_motions:
                shot["motion"] = planned_motions[shot["id"]]
    context = digest({"episode_id": board["episode_id"], "script_sha256": board["script_sha256"],
                      "shots": visual, "render_sha256": bytes_digest(read_bytes(root, "input/render.yaml", SMALL_FILE))})
    return board, text, policy, assignments, context


def confirmation_payload(value):
    return {k: v for k, v in value.items() if k != "confirmation"}


def confirm(root, kind, decision):
    validate("imageDecision", decision)
    check_human(decision["human"], scope=kind, expected={k: v for k, v in decision.items() if k != "human"})
    if kind == "policy":
        value = read_doc(root, POLICY, "policy")
        value["status"] = "APPROVED"
        name = POLICY
    else:
        value = requests(root, confirmed=False)
        name = REQUESTS
    if digest(confirmation_payload(value)) != decision["payload_sha256"]:
        raise ValueError("Confirmation payload is stale")
    value["confirmation"] = decision
    if kind == "policy":
        board = read_doc(root, "input/storyboard.json", "storyboard")
        check_source_policy(value, board["shots"])
    write_docs(root, {name: value})
    return {"status": "APPROVED", "payload_sha256": decision["payload_sha256"]}


def policy_options(root):
    """Read current policy without mutating it; report only observed availability."""
    value = (read_doc(root, POLICY, "policy") if resolve_path(root, POLICY).exists() else
             {"schema_version": "1.0", "mode": "mixed", "status": "SOURCE_POLICY_PENDING",
              "default_channel": None, "allowed_channels": [], "shots": {},
              "supersedes": None, "confirmation": None})
    proposed = {**value, "status": "APPROVED"}
    result = {"status": "SOURCE_POLICY_PENDING", "mode": value["mode"],
              "allowed_channels": value["allowed_channels"], "shots": value["shots"],
              "default_channel": value["default_channel"],
              "payload_sha256": digest(confirmation_payload(proposed)), "channels": []}
    if value["confirmation"] is not None:
        try:
            board = read_doc(root, "input/storyboard.json", "storyboard")
            result["shots"] = check_source_policy(value, board["shots"])
            result["status"] = "APPROVED"
        except (ValueError, OSError) as error:
            result.update(status="REVIEW_REQUIRED", reason=str(error))
    if result["status"] != "APPROVED":
        result.update(question="本期图片选用 Agent 生图、第三方图库、人工生图，还是逐镜头混合？请确认工具/站点及混合映射。",
                      options=["agent_generate", "third_party_retrieve", "manual_generate", "mixed"])
    # Capability failures are separate from user authorization; never probe or dispatch on query.
    if result["status"] == "APPROVED" and resolve_path(root, REQUESTS).exists():
        try:
            req = requests(root)
            records = supply(root)["records"]
            for assignment in value["allowed_channels"]:
                failures = [r for r in records if r["status"] == "UNAVAILABLE"
                            and r["request_sha256"] == digest(req)
                            and result["shots"].get(r["shot_id"]) == assignment]
                result["channels"].append({**assignment, "status": "UNAVAILABLE" if failures else "NOT_PROBED",
                                           "reasons": [r["reason"] for r in failures]})
        except (ValueError, OSError):
            pass  # Stale acquisition records do not establish current channel availability.
    return result


def plan(root, brief):
    validate("imageBrief", brief)
    board, text, policy, assignments, context = inputs(root)
    briefs = {s["shot_id"]: s for s in brief["shots"]}
    if len(briefs) != len(brief["shots"]) or set(briefs) != set(assignments):
        raise ValueError("Brief must cover every shot exactly once")
    shots, prompts = [], []
    for shot in board["shots"]:
        sid = shot["id"]
        item = briefs[sid]
        a, b = shot["script_range"]
        prompt = (f"创作一幅用于中文静态漫画视频的完整插画。镜头 {sid}。\n"
                  f"口播原文：{text[a:b]}\n视觉任务：{item['visual_task']}。画面类型：{item['picture_type']}。\n"
                  f"主体与构图：{item['composition']}。\n统一画风（{brief['style_version']}）：{brief['style']}。\n"
                  f"角色一致性：{brief['characters']}。物体约束：{brief['objects']}。\n"
                  f"灯光：{brief['lighting']}。横向 16:9，建议 2304×1296 或更高同等比例。\n"
                  f"运镜留白：{shot['motion']['type']}，缩放 {shot['motion']['scale_from']}→"
                  f"{shot['motion']['scale_to']}；主体安全区 {shot['subject_bbox']}，主体不得被裁切。\n"
                  f"具体排除项：{brief['exclusions']}。\n输出 PNG，最终严格命名为 {shot['image']}。")
        shots.append({"shot_id": sid, "script": text[a:b], **{k: item[k] for k in
                      ("visual_task", "picture_type", "composition")},
                      **{k: brief[k] for k in ("style_version", "characters", "objects")},
                      "aspect_ratio": "16:9", "recommended_size": [2304, 1296], "motion": shot["motion"],
                      "subject_bbox": shot["subject_bbox"], "assignment": assignments[sid],
                      "suggested_channel": assignments[sid], "formal_path": shot["image"], "prompt": prompt})
        prompts.append(f"## {sid}\n\n{prompt}\n")
    value = validate("imageRequests", {"schema_version": "1.0", "context_sha256": context,
                     "policy_sha256": digest(policy), "brief": brief, "shots": shots, "confirmation": None})
    write_docs(root, {REQUESTS: value, "work/planning/image_prompts.md":
                     ("# 逐镜头独立提示词\n\n" + "\n".join(prompts)).encode("utf-8")})
    return {"status": "REVIEW_REQUIRED", "payload_sha256": digest(confirmation_payload(value)),
            "requests": REQUESTS, "prompts": "work/planning/image_prompts.md"}


def requests(root, *, confirmed=True):
    value = read_doc(root, REQUESTS, "imageRequests")
    board, text, policy, assignments, context = inputs(
        root, planned_boxes={s["shot_id"]: s["subject_bbox"] for s in value["shots"]},
        planned_motions={s["shot_id"]: s["motion"] for s in value["shots"]})
    if value["context_sha256"] != context or value["policy_sha256"] != digest(policy):
        raise ValueError("Image requests are stale; replan and reconfirm")
    shots = value["shots"]
    if len(shots) != len(assignments) or {s["shot_id"] for s in shots} != set(assignments):
        raise ValueError("Image requests must cover every shot exactly once")
    if any(s["assignment"] != assignments[s["shot_id"]] for s in shots):
        raise ValueError("Image request source differs from confirmed policy")
    by_id = {s["id"]: s for s in board["shots"]}
    for item in shots:
        shot = by_id[item["shot_id"]]
        a, b = shot["script_range"]
        if item["formal_path"] != shot["image"] or item["script"] != text[a:b]:
            raise ValueError("Image request differs from storyboard")
    if confirmed:
        receipt = value["confirmation"]
        if not receipt or receipt["payload_sha256"] != digest(confirmation_payload(value)):
            raise ValueError("Confirmed storyboard and image requests required")
        check_human(receipt["human"], scope="plan", expected={"payload_sha256": receipt["payload_sha256"]})
    return value


def supply(root):
    value = (read_doc(root, SUPPLY, "imageSupply") if resolve_path(root, SUPPLY).exists()
             else {"schema_version": "1.0", "records": []})
    if len({r["shot_id"] for r in value["records"]}) != len(value["records"]):
        raise ValueError("Duplicate image supply record")
    return value


def save_record(root, record, extra=None):
    value = supply(root)
    value["records"] = [r for r in value["records"] if r["shot_id"] != record["shot_id"]] + [record]
    validate("imageSupply", value)
    # Append content-addressed audit events; current state is an explicit pointer.
    outputs = {SUPPLY: value, f"review/images/events/{digest(record)}.json": record}
    outputs.update(extra or {})
    write_docs(root, outputs)


def dispatch(root, sid, *, unavailable=None):
    req = requests(root)
    item = next((s for s in req["shots"] if s["shot_id"] == sid), None)
    if item is None:
        raise ValueError("Unknown shot ID")
    status = ("UNAVAILABLE" if unavailable else "WAITING_FOR_USER"
              if item["assignment"]["source_mode"] == "manual_generate" else "PLANNED")
    reason = unavailable or ("等待用户提供图片；正式路径中的现有文件也须登记审图。"
                             if status == "WAITING_FOR_USER" else "仅准备已确认请求；请通过已连接且授权的工具执行。")
    record = {"shot_id": sid, "request_sha256": digest(req), "status": status,
              "reason": reason, "candidate": None, "review": None}
    save_record(root, record)
    return {**record, "request": item}


def check_evidence(root, evidence):
    raw = read_bytes(root, evidence["path"], IMAGE_FILE)
    if bytes_digest(raw) != evidence["sha256"]:
        raise ValueError(f"Changed provenance evidence: {evidence['path']}")


def check_submission(root, req, submission):
    validate("imageSubmission", submission)
    item = next((s for s in req["shots"] if s["shot_id"] == submission["shot_id"]), None)
    if item is None or submission["request_sha256"] != digest(req):
        raise ValueError("Unknown shot or stale acquisition request")
    if {k: submission[k] for k in ("source_mode", "channel")} != item["assignment"]:
        raise ValueError("Acquisition channel differs; user must reconfirm policy")
    stamp = datetime.fromisoformat(submission["accessed_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Acquisition time must include timezone")
    if submission["source_mode"] == "third_party_retrieve":
        if not submission["source_uri"].startswith(("https://", "http://")) or not all(
                submission[k].strip() for k in ("query", "site", "author", "download_method")):
            raise ValueError("Third-party source URL/site/query/author/download evidence required")
    elif submission["prompt"] != item["prompt"]:
        raise ValueError("Generation must record the full confirmed Chinese prompt")
    for key in ("license_evidence", "request_record", "output_record"):
        check_evidence(root, submission[key])
    for reference in submission["references"]:
        check_evidence(root, reference["license_evidence"])
    return item


def inspect_candidate(root, candidate, shot):
    raw = read_bytes(root, candidate["path"], IMAGE_FILE)
    if bytes_digest(raw) != candidate["sha256"]:
        raise ValueError("Candidate bytes changed; approval invalid")
    original = read_bytes(root, f"work/images/originals/{candidate['original_sha256']}.bin", IMAGE_FILE)
    if bytes_digest(original) != candidate["original_sha256"]:
        raise ValueError("Original acquisition bytes changed")
    render = validate("render", yaml.safe_load(read_bytes(root, "input/render.yaml", SMALL_FILE).decode("utf-8-sig")))
    # Geometry endpoints plus a sampled sweep: the compiler later checks every real frame.
    clock = {"logical_frames": 61, "head_hold_frames": 0, "physical_frames": 61, "sequence_start_frame": 0}
    _, preview, detail = prepare_image(raw, shot, render, clock)
    return preview, {k: v for k, v in detail.items() if k != "frames"}


def ingest(root, submission):
    req = requests(root)
    check_submission(root, req, submission)
    raw = read_bytes(root, submission["file"], IMAGE_FILE)
    try:
        with Image.open(BytesIO(raw)) as im:
            if im.format not in ("PNG", "JPEG", "WEBP") or getattr(im, "n_frames", 1) != 1:
                raise ValueError("Candidate must be a single PNG/JPEG/WebP image")
            if im.width * im.height > MAX_PIXELS:
                raise ValueError("Candidate image too large")
            im.load()
            if im.format == "PNG":
                encoded = raw
            else:
                buf = BytesIO()
                im.convert("RGBA").save(buf, format="PNG", exif=im.getexif(), icc_profile=im.info.get("icc_profile"))
                encoded = buf.getvalue()
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError(f"Cannot decode candidate: {error}") from error
    candidate = {"path": f"work/images/candidates/{bytes_digest(encoded)}.png", "sha256": bytes_digest(encoded),
                 "original_sha256": bytes_digest(raw), "submission": deepcopy(submission)}
    record = {"shot_id": submission["shot_id"], "request_sha256": digest(req), "status": "CANDIDATE_READY",
              "reason": "候选已导入，尚未经过技术检查及用户审图。", "candidate": candidate, "review": None}
    save_record(root, record, {candidate["path"]: encoded,
                              f"work/images/originals/{bytes_digest(raw)}.bin": raw})
    return {"status": record["status"], "candidate_sha256": candidate["sha256"], "record_sha256": digest(record)}


def rights(submission):
    license = submission["license"]
    return (submission["usage_role"] == "final_artwork" and license["publication_allowed"]
            and all(license[k].strip() for k in ("id", "evidence", "usage_scope"))
            and all(r["derivation_allowed"] for r in submission["references"]))


def asset_for(req, record, human):
    item = next(s for s in req["shots"] if s["shot_id"] == record["shot_id"])
    sub = record["candidate"]["submission"]
    return validate("asset", {"shot_id": record["shot_id"], "path": item["formal_path"],
                    "sha256": record["candidate"]["sha256"], "purpose": "production",
                    "style_version": item["style_version"], "review_status": "APPROVED", "reviewer": human,
                    **{k: sub[k] for k in ("source_mode", "channel", "prompt", "query", "author", "source_uri",
                                           "accessed_at", "download_method", "license")}})


def review_geometry(req, shot):
    """Bind a review to measured geometry without rewriting acquisition history."""
    return digest({"request_sha256": digest(req), "shot_id": shot["id"],
                   "subject_bbox": shot["subject_bbox"], "motion": shot["motion"]})


def review(root, decision):
    validate("imageReview", decision)
    check_human(decision["human"], scope="images", expected={k: v for k, v in decision.items() if k != "human"})
    req = requests(root)
    if decision["request_sha256"] != digest(req):
        raise ValueError("Review request hash is stale")
    records = {r["shot_id"]: r for r in supply(root)["records"]}
    ids = [i["shot_id"] for i in decision["items"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate batch decision; select each exact image once")
    board, _, policy, _, _ = inputs(root)
    shots = {s["id"]: s for s in board["shots"]}
    manifest = (read_doc(root, MANIFEST, "manifest") if resolve_path(root, MANIFEST).exists()
                else {"schema_version": "1.0", "assets": []})
    approvals = (read_doc(root, APPROVALS, "approvals") if resolve_path(root, APPROVALS).exists()
                 else {"schema_version": "1.0", "receipts": []})
    outputs = {}
    for item in decision["items"]:
        sid = item["shot_id"]
        record = records.get(sid)
        if not record or not record["candidate"] or record["request_sha256"] != digest(req):
            raise ValueError("No current candidate for review")
        if item["record_sha256"] != digest(record) or item["candidate_sha256"] != record["candidate"]["sha256"]:
            raise ValueError("Review targets a stale candidate/record")
        if item.get("geometry_sha256") != review_geometry(req, shots[sid]):
            raise ValueError("Review geometry is missing or stale; show the current report again")
        if item["decision"] == "APPROVED":
            check_submission(root, req, record["candidate"]["submission"])
            _, detail = inspect_candidate(root, record["candidate"], shots[sid])
            if not all(item["checks"].values()) or detail["subject_status"] != "PASS":
                raise ValueError("Image visual checks and motion safety must pass")
            if not rights(record["candidate"]["submission"]):
                raise ValueError("Publication rights unresolved or reference_only / derivative forbidden")
        record["status"] = item["decision"]
        record["reason"] = item["reason"]
        record["review"] = {"human": decision["human"], "item": item}
        approvals["receipts"] = [r for r in approvals["receipts"] if r["shot_id"] != sid]
        manifest["assets"] = [a for a in manifest["assets"] if a["shot_id"] != sid]
        if item["decision"] == "APPROVED":
            asset = asset_for(req, record, decision["human"])
            manifest["assets"].append(asset)
            approvals["receipts"].append({"shot_id": sid, "status": "APPROVED", "human": decision["human"],
                                         "image_sha256": asset["sha256"], "asset_sha256": digest(asset),
                                         "policy_sha256": digest(policy), "supply_sha256": digest(record)})
            raw = read_bytes(root, record["candidate"]["path"], IMAGE_FILE)
            if bytes_digest(raw) != asset["sha256"]:
                raise ValueError("Candidate bytes changed before publication")
            outputs[asset["path"]] = raw
        outputs[f"review/images/events/{digest(record)}.json"] = record
    outputs.update({SUPPLY: {"schema_version": "1.0", "records": list(records.values())},
                    MANIFEST: manifest, APPROVALS: approvals})
    validate("imageSupply", outputs[SUPPLY])
    validate("manifest", manifest)
    validate("approvals", approvals)
    write_docs(root, outputs)
    return {"status": "RECORDED", "decisions": {i["shot_id"]: i["decision"] for i in decision["items"]}}


def verify_approved(root, req, shot, record, receipt, current_asset, policy):
    """Verify one image independently, also used by a partially completed review board."""
    sid = shot["id"]
    if (not record or record["status"] != "APPROVED" or not record["candidate"] or not record["review"]
            or record["request_sha256"] != digest(req) or not receipt
            or receipt.get("supply_sha256") != digest(record)):
        raise ValueError(f"{sid}: image supply approval missing or stale")
    sub = record["candidate"]["submission"]
    check_submission(root, req, sub)
    human, item = record["review"]["human"], record["review"]["item"]
    check_human(human, scope="images", expected={"request_sha256": digest(req)}, item=item)
    original = read_json(read_bytes(root, f"review/images/events/{item['record_sha256']}.json", SMALL_FILE))
    validate("imageSupply", {"schema_version": "1.0", "records": [original]})
    if (digest(original) != item["record_sha256"]
            or any(original[k] != record[k] for k in ("shot_id", "request_sha256", "candidate"))):
        raise ValueError(f"{sid}: Human-approved acquisition record changed")
    if item.get("geometry_sha256") != review_geometry(req, shot):
        raise ValueError(f"{sid}: approved review geometry is missing or stale")
    if (not rights(sub) or item["decision"] != "APPROVED" or not all(item["checks"].values())
            or item["shot_id"] != sid or item["candidate_sha256"] != record["candidate"]["sha256"]):
        raise ValueError(f"{sid}: rights or human visual review invalid")
    asset = asset_for(req, record, human)
    if current_asset != asset:
        raise ValueError(f"{sid}: approved supply differs from manifest")
    from .project import check_approval
    check_approval(shot, asset, digest(policy), next(s["assignment"] for s in req["shots"] if s["shot_id"] == sid), {sid: receipt})
    _, detail = inspect_candidate(root, record["candidate"], shot)
    if detail["subject_status"] != "PASS":
        raise ValueError(f"{sid}: motion safety is not verified")
    if bytes_digest(read_bytes(root, asset["path"], IMAGE_FILE)) != asset["sha256"]:
        raise ValueError(f"{sid}: formal image bytes changed")


def verify(root, docs=None):
    """Validate current image files, provenance and approvals."""
    req = requests(root)
    records = {r["shot_id"]: r for r in supply(root)["records"]}
    manifest = docs["manifest"] if docs else read_doc(root, MANIFEST, "manifest")
    approvals = docs["approvals"] if docs else read_doc(root, APPROVALS, "approvals")
    assets = {a["shot_id"]: a for a in manifest["assets"]}
    receipts = {r["shot_id"]: r for r in approvals["receipts"]}
    if len(assets) != len(manifest["assets"]) or len(receipts) != len(approvals["receipts"]):
        raise ValueError("Duplicate asset or approval")
    board, _, policy, _, _ = inputs(root)
    hashes = {REQUESTS: digest(req), SUPPLY: digest(supply(root))}
    for shot in board["shots"]:
        sid = shot["id"]
        verify_approved(root, req, shot, records.get(sid), receipts.get(sid), assets.get(sid), policy)
    if set(assets) != {s["id"] for s in board["shots"]} or set(receipts) != set(assets):
        raise ValueError("Production image coverage must be exact")
    return {"status": "PASS", "input_hashes": hashes, "shots": len(assets)}


def report(root):
    req = requests(root)
    records = {r["shot_id"]: r for r in supply(root)["records"]}
    board, _, policy, _, _ = inputs(root)
    shots = {s["id"]: s for s in board["shots"]}
    receipts, assets = {}, {}
    if any(r["status"] == "APPROVED" for r in records.values()):
        receipts = {r["shot_id"]: r for r in read_doc(root, APPROVALS, "approvals")["receipts"]}
        assets = {a["shot_id"]: a for a in read_doc(root, MANIFEST, "manifest")["assets"]}
    rows, outputs, details = [], {}, []
    for item in req["shots"]:
        sid = item["shot_id"]
        record = records.get(sid)
        status, reason, picture, info = "PLANNED", "尚未取得候选", "", None
        if record:
            status, reason = record["status"], record["reason"]
            if record["request_sha256"] != digest(req):
                status, reason = "REVIEW_REQUIRED", "请求或渠道已改变，旧候选失效"
            elif record["candidate"]:
                try:
                    check_submission(root, req, record["candidate"]["submission"])
                    preview, info = inspect_candidate(root, record["candidate"], shots[sid])
                    outputs[f"review/images/{sid}.png"] = preview
                    picture = f'<img width="480" src="{sid}.png" alt="{sid}">'
                    if status == "CANDIDATE_READY":
                        status = "REVIEW_REQUIRED"
                        record.update(status=status, reason="技术检查已完成；人物、画风、叙事、权利及构图须用户审查。")
                        save_record(root, record)
                except (ValueError, OSError) as error:
                    status, reason = "REVIEW_REQUIRED", str(error)
            if status == "APPROVED":
                try:
                    verify_approved(root, req, shots[sid], record, receipts.get(sid), assets.get(sid), policy)
                except (ValueError, OSError) as error:
                    status, reason = "REVIEW_REQUIRED", str(error)
        detail = {"shot_id": sid, "status": status, "reason": reason, "technical": info,
                  "motion": shots[sid]["motion"],
                  "geometry_sha256": review_geometry(req, shots[sid]),
                  "record_sha256": digest(record) if record else None,
                  "candidate_sha256": record["candidate"]["sha256"] if record and record["candidate"] else None}
        details.append(detail)
        sub = record["candidate"]["submission"] if record and record["candidate"] else {}
        fields = {"口播": item["script"], "运镜": shots[sid]["motion"], "原采集运镜": item["motion"],
                  "来源": item["assignment"],
                  "原始来源": sub.get("source_uri"), "用途": sub.get("usage_role"), "许可": sub.get("license"),
                  "目标发布范围": req["brief"]["publication_scope"], "审核": detail}
        rows.append(f'<section><h2>{sid} — {status}</h2>{picture}<pre>{escape(str(fields))}</pre></section>')
    html = '<!doctype html><meta charset="utf-8"><title>逐镜头审图</title><style>body{font:16px sans-serif;max-width:1100px;margin:32px auto}pre{white-space:pre-wrap}section{border-bottom:1px solid #aaa;padding:20px}</style><h1>候选审图：工具成功不等于用户批准</h1>' + "".join(rows)
    outputs.update({"review/images/index.html": html.encode("utf-8"), "review/images/report.json":
                    {"request_sha256": digest(req), "shots": details}})
    write_docs(root, outputs)
    return {"status": "REVIEW_REQUIRED", "report": "review/images/index.html", "shots": details}


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="SC-P3A image supply and human review")
    parser.add_argument("action", choices=("policy", "confirm-policy", "plan", "confirm-plan", "dispatch",
                                           "unavailable", "ingest", "review", "report", "verify"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", help="Episode-relative JSON brief, submission or explicit human decision")
    parser.add_argument("--shot")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    root = Path(args.project).resolve(strict=True)
    data = read_json(read_bytes(root, args.input, SMALL_FILE)) if args.input else None
    if args.action in ("plan", "ingest", "review", "confirm-policy", "confirm-plan") and data is None:
        raise ValueError("--input is required")
    if args.action in ("dispatch", "unavailable") and not args.shot:
        raise ValueError("--shot is required")
    if args.action == "unavailable" and not args.reason:
        raise ValueError("--reason must record observed capability failure")
    if args.action.startswith("confirm-"):
        return confirm(root, args.action.split("-", 1)[1], data)
    if args.action in ("dispatch", "unavailable"):
        return dispatch(root, args.shot, unavailable=args.reason if args.action == "unavailable" else None)
    if args.action in ("plan", "ingest", "review"):
        return {"plan": plan, "ingest": ingest, "review": review}[args.action](root, data)
    return {"policy": policy_options, "report": report, "verify": verify}[args.action](root)
