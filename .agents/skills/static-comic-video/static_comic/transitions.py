"""Semantic transition planning, confirmation and storyboard application.
"""
from copy import deepcopy
from datetime import datetime
from html import escape
from pathlib import Path

from .contracts import SCHEMA_PATH, bytes_digest, canonical, digest, read_json, validate
from .image_supply import read_doc, write_docs, verify as verify_images
from .paths import read_bytes, resolve_path
from .project import SMALL_FILE, check_human, load_project
from .speech import LIMIT, VERSION, apply_alignment, binding, evaluate, read_evidence
from .speech_text import check_overrides, make_plan
from .timeline import compile_timing, frame_at
from .human_review import require_newer

INPUT = "work/planning/transition_input.json"
CANDIDATES = "work/planning/transition_candidates.json"
REVIEWS = "review/transition_approvals.json"


def without_transitions(board):
    value = deepcopy(board)
    for shot in value["shots"]:
        shot["transition_out"] = None
    return value


def current(root):
    docs, hashes, _ = load_project(root)
    image_result = verify_images(root, docs)
    board = docs["storyboard"]
    if any(s["timing_source"] == "technical_fixture" for s in board["shots"]):
        raise ValueError("TransitionPlanner requires production images and speech evidence, not technical fixture timing")
    text = read_bytes(root, "input/script.txt", SMALL_FILE).decode("utf-8-sig")
    error, aligned, resolved, acoustic = None, None, None, None
    try:
        resolved = apply_alignment(root, docs, hashes, technical_fixture=False)
        aligned = read_json(read_bytes(root, "work/alignment/aligned.json", LIMIT))
        raw = read_evidence(root, aligned["raw_ref"])
        # Transition-only replay changes binding, never the acoustic evidence.
        acoustic = {k: raw[k] for k in ("audio", "coarse_ref", "plan", "windows")}
        acoustic.update({k: raw[k] for k in ("model_lock", "whisperx_version") if k in raw})
    except (ValueError, OSError) as failure:
        error = str(failure)
    override = deepcopy(docs.get("overrides"))
    if override:
        override.pop("storyboard_sha256")
    context = digest({"board": without_transitions(board), "script": hashes["input/script.txt"],
                      "audio": hashes[board["audio"]["source"]], "images": image_result["input_hashes"],
                      "acoustic": acoustic, "timing_error": error, "overrides": override,
                      "contract": bytes_digest(SCHEMA_PATH.read_bytes())})
    assets = {a["shot_id"]: a for a in docs["manifest"]["assets"]}
    approvals = {a["shot_id"]: a for a in docs["approvals"]["receipts"]}
    boundaries = []
    for index, (before, after) in enumerate(zip(board["shots"], board["shots"][1:])):
        a, b = before["script_range"]
        c, d = after["script_range"]
        anchors, pause, boundary = [], None, None
        if resolved:
            left, right = resolved["shots"][index:index+2]
            boundary = right["start_samples"]
            pause = right["speech_interval_samples"][0] - left["speech_interval_samples"][1]
            anchors.append({"id": "boundary", "sample": boundary, "script_range": [c, d],
                            "quote": text[c:d], "source": right["timing_source"]})
            for i, (source_range, char) in enumerate(zip(aligned["reading_map"]["source_ranges"], aligned["characters"])):
                lo, hi = source_range
                if a <= lo < hi <= d and char["source"] == "acoustic_aligned" and char["samples"]:
                    for edge, sample in zip(("start", "end"), char["samples"]):
                        anchors.append({"id": f"char-{i}-{edge}", "sample": sample, "script_range": source_range,
                                        "quote": text[lo:hi], "source": "acoustic_aligned"})
        boundaries.append({"from_shot": before, "to_shot": after, "from_asset": assets[before["id"]],
                           "to_asset": assets[after["id"]], "from_approval": approvals[before["id"]],
                           "to_approval": approvals[after["id"]], "from_text": text[a:b], "to_text": text[c:d],
                           "anchors": anchors, "pause_samples": pause, "logical_boundary_samples": boundary})
    request = validate("plannerInput", {"schema_version": "1.0", "context_sha256": context,
                       "source_storyboard_sha256": hashes["input/storyboard.json"],
                       "timing_status": "REVIEW_REQUIRED" if error else "PASS", "timing_error": error,
                       "boundaries": boundaries})
    return request, docs, hashes, resolved


def prepare(root):
    request, _, _, _ = current(root)
    draft = {"input_sha256": digest(request), "author": {"name": "FILL_ACTUAL_OBSERVER", "role": "agent",
             "at": "FILL_TIME_WITH_TIMEZONE", "evidence": "FILL_ACTUAL_IMAGE_VIEW_TOOL_OR_USER_RECORD"},
             "boundaries": [{"from_shot_id": b["from_shot"]["id"], "to_shot_id": b["to_shot"]["id"],
                "viewed_images": [], "observations": {"before": "", "after": "", "continuity": ""},
                "relation": "continuous_narration", "evidence": [], "visual_evidence": "", "intent": "",
                "type": "cut", "duration_frames": 0, "placement": "start_at_anchor", "anchor_id": None,
                "direction": "not_applicable", "direction_evidence": "", "black_interval_reason": "",
                "image_text_conflict": False} for b in request["boundaries"]]}
    write_docs(root, {INPUT: request, "work/planning/transition_proposal.template.json": draft})
    return {"status": "REVIEW_REQUIRED", "input_sha256": digest(request), "input": INPUT,
            "timing_status": request["timing_status"], "timing_error": request["timing_error"],
            "next": "View both approved originals, fill concrete observations and evidence; submit propose."}


def loaded_input(root):
    request = read_doc(root, INPUT, "plannerInput")
    live, docs, hashes, resolved = current(root)
    if request["context_sha256"] != live["context_sha256"]:
        raise ValueError("Transition inputs are stale; prepare, view originals and replan")
    compared = []
    for source in (request, live):
        value = deepcopy(source)
        value.pop("source_storyboard_sha256")
        for boundary in value["boundaries"]:
            for side in ("from_shot", "to_shot"):
                boundary[side]["transition_out"] = None
        compared.append(value)
    if compared[0] != compared[1]:
        raise ValueError("Transition input evidence was edited; regenerate from approved sources")
    return request, docs, hashes, resolved


def plan(request, proposal, resolved):
    """Pure discrete planning: missing evidence becomes boundary-specific issues."""
    validate("transitionProposal", proposal)
    if proposal["input_sha256"] != digest(request):
        raise ValueError("Proposal input hash is stale")
    stamp = datetime.fromisoformat(proposal["author"]["at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None or not all(proposal["author"][k].strip() for k in ("name", "evidence")):
        raise ValueError("Observer timestamp requires timezone")
    expected = [(b["from_shot"]["id"], b["to_shot"]["id"]) for b in request["boundaries"]]
    submitted = [(b["from_shot_id"], b["to_shot_id"]) for b in proposal["boundaries"]]
    if submitted != expected:
        raise ValueError("Proposal must cover every non-final boundary exactly once in order")
    items = []
    for boundary, item in zip(request["boundaries"], proposal["boundaries"]):
        issues = []
        def issue(code, detail):
            issues.append({"code": code, "detail": detail})
        if item["viewed_images"] != [boundary[k]["sha256"] for k in ("from_asset", "to_asset")]:
            issue("ORIGINALS_NOT_VIEWED", "必须实际查看当前两张已批准原画，并记录顺序一致的图片 hash。")
        for key, value in {**item["observations"], "visual_evidence": item["visual_evidence"], "intent": item["intent"]}.items():
            if len(value.strip()) < 8 or value.strip() in [boundary[k]["path"] for k in ("from_asset", "to_asset")]:
                issue("CONCRETE_EVIDENCE_REQUIRED", f"{key}: 需描述实际主体、构图、动作或衔接意图，不能只写文件名或空泛短语。")
        if item["image_text_conflict"]:
            issue("IMAGE_TEXT_CONFLICT", "图文存在冲突，先修订素材或原文并重新确认。")
        if not item["evidence"]:
            issue("TEXT_EVIDENCE_REQUIRED", "每个边界（含硬切）必须提供具体原文引用及码点区间。")
        for evidence in item["evidence"]:
            lo, hi = evidence["script_range"]
            valid = False
            for side in ("from", "to"):
                a, b = boundary[side + "_shot"]["script_range"]
                if a <= lo < hi <= b and evidence["quote"] == boundary[side + "_text"][lo-a:hi-a]:
                    valid = True
            if not valid:
                issue("TEXT_EVIDENCE_MISMATCH", "原文引用必须准确属于边界相邻一侧的原始码点区间。")
        anchor = next((a for a in boundary["anchors"] if a["id"] == item["anchor_id"]), None)
        if request["timing_status"] != "PASS" or anchor is None:
            issue("TIME_EVIDENCE_REQUIRED", request["timing_error"] or "选择已核验语音边界或字符锚点，不能填写猜测时间。")
        if item["type"].startswith("wipe_"):
            if item["direction"] != item["type"][5:] or len(item["direction_evidence"].strip()) < 8:
                issue("DIRECTION_UNCLEAR", "新画面从哪侧开始覆盖必须与真实画面方向证据一致。")
        if item["type"] == "fade_black" and len(item["black_interval_reason"].strip()) < 8:
            issue("BLACK_INTERVAL_UNEXPLAINED", "明确黑场如何表达时间跨越或章节间隔。")
        if ((item["type"] == "cut") != (item["duration_frames"] == 0)
                or item["type"] == "fade_black" and item["duration_frames"] < 3):
            issue("INVALID_EFFECT_DURATION", "硬切为 0 帧；其他效果正整数帧；淡黑至少 3 帧。")
        transition = None
        if anchor:
            transition = validate("transition", {"to_shot_id": item["to_shot_id"],
                **{k: item[k] for k in ("relation", "visual_evidence", "intent", "type", "duration_frames", "placement")},
                "evidence": "；".join(e["quote"] for e in item["evidence"]) or "待补原文证据",
                "semantic_anchor_samples": anchor["sample"], "planning_source": "agent_reviewed" if proposal["author"]["role"] == "agent" else "human",
                "image_hashes": [boundary[k]["sha256"] for k in ("from_asset", "to_asset")],
                "image_approval_hashes": [digest(boundary[k]) for k in ("from_approval", "to_approval")]}) if item["visual_evidence"] and item["intent"] else None
        items.append({"from_shot_id": item["from_shot_id"], "to_shot_id": item["to_shot_id"],
                      "issues": issues, "transition": transition})
    if resolved and all(i["transition"] for i in items):
        board = install(resolved, items)
        try:
            compile_timing(board)
        except ValueError as error:
            # Shared budgets can implicate both neighboring boundaries.
            affected = [s["id"] for s in board["shots"] if s["id"] in str(error)]
            for item in items:
                if not affected or item["from_shot_id"] in affected or item["to_shot_id"] in affected:
                    item["issues"].append({"code": "EFFECT_CAPACITY", "detail": str(error)})
    return validate("transitionCandidates", {"schema_version": "1.0", "input_sha256": digest(request),
                    "context_sha256": request["context_sha256"], "proposal": proposal, "items": items,
                    "status": "REVIEW_REQUIRED" if any(i["issues"] for i in items) else "READY_FOR_REVIEW"})


def install(board, items):
    result = deepcopy(board)
    for shot, item in zip(result["shots"][:-1], items):
        shot["transition_out"] = deepcopy(item["transition"])
    result["shots"][-1]["transition_out"] = None
    return result


def propose(root, proposal):
    request, _, _, resolved = loaded_input(root)
    value = plan(request, proposal, resolved)
    write_docs(root, {CANDIDATES: value})
    return {"status": value["status"], "candidate_sha256": digest(value), "items": value["items"]}


def checked_candidates(root):
    request, docs, hashes, resolved = loaded_input(root)
    value = read_doc(root, CANDIDATES, "transitionCandidates")
    if plan(request, value["proposal"], resolved) != value:
        raise ValueError("Transition candidates were edited or are stale; resubmit proposal")
    return request, value, docs, hashes, resolved


def confirm(root, decision):
    validate("transitionDecision", decision)
    check_human(decision["human"], scope="transitions", expected={k: v for k, v in decision.items() if k != "human"})
    _, value, _, _, _ = checked_candidates(root)
    if decision["candidate_sha256"] != digest(value):
        raise ValueError("Semantic decision targets stale candidates")
    reviews = {"schema_version": "1.0", "candidate_sha256": digest(value), "receipts": []}
    if resolve_path(root, REVIEWS).exists():
        previous = read_doc(root, REVIEWS, "transitionReviews")
        if previous["candidate_sha256"] == digest(value):
            reviews = previous
    seen = set()
    for item in decision["items"]:
        pair = item["from_shot_id"], item["to_shot_id"]
        candidate = next((c for c in value["items"] if (c["from_shot_id"], c["to_shot_id"]) == pair), None)
        if pair in seen or candidate is None:
            raise ValueError("Duplicate or unknown semantic decision boundary")
        seen.add(pair)
        if not item["reason"].strip():
            raise ValueError("Semantic decision reason is required")
        if item["decision"] == "APPROVED" and (candidate["issues"] or not all(item["checks"].values())):
            raise ValueError("Unresolved boundary issues or failed semantic checks cannot be approved")
        previous = next((r for r in reviews["receipts"] if
                         (r["item"]["from_shot_id"], r["item"]["to_shot_id"]) == pair), None)
        if previous:
            try:
                check_human(previous["human"], scope="transitions",
                            expected={"candidate_sha256": digest(value)}, item=previous["item"])
            except (ValueError, OSError):
                pass  # An invalid legacy record cannot veto a fresh valid decision.
            else:
                require_newer(decision["human"], previous["human"])
        reviews["receipts"] = [r for r in reviews["receipts"] if
                                (r["item"]["from_shot_id"], r["item"]["to_shot_id"]) != pair]
        reviews["receipts"].append({"human": decision["human"], "item": item})
    write_docs(root, {REVIEWS: reviews, f"review/transitions/events/{digest(reviews)}.json": reviews})
    return {"status": "RECORDED", "review_sha256": digest(reviews)}


def approved(root, value):
    reviews = read_doc(root, REVIEWS, "transitionReviews")
    if reviews["candidate_sha256"] != digest(value) or value["status"] != "READY_FOR_REVIEW":
        raise ValueError("Semantic approval is stale or candidates require review")
    expected = {(i["from_shot_id"], i["to_shot_id"]) for i in value["items"]}
    actual = [(r["item"]["from_shot_id"], r["item"]["to_shot_id"]) for r in reviews["receipts"]]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Every boundary requires explicit semantic approval")
    for receipt in reviews["receipts"]:
        check_human(receipt["human"], scope="transitions",
                    expected={"candidate_sha256": digest(value)}, item=receipt["item"])
        if receipt["item"]["decision"] != "APPROVED" or not all(receipt["item"]["checks"].values()):
            raise ValueError("Semantic boundary rejected or checks not accepted")
    return reviews


def replay(root, docs, hashes, new_board):
    """Prepare a transition-only SC-P3 replay, preserving all old raw evidence."""
    if without_transitions(docs["storyboard"]) != without_transitions(new_board):
        raise ValueError("SC-P4 replay may only change transition_out")
    apply_alignment(root, docs, hashes, technical_fixture=False)
    old = read_json(read_bytes(root, "work/alignment/aligned.json", LIMIT))
    raw = deepcopy(read_evidence(root, old["raw_ref"]))
    new_hashes = dict(hashes)
    board_bytes = canonical(new_board) + b"\n"
    new_hashes["input/storyboard.json"] = bytes_digest(board_bytes)
    outputs = {"input/storyboard.json": board_bytes,
               f"work/planning/history/{hashes['input/storyboard.json']}.json": read_bytes(root, "input/storyboard.json", SMALL_FILE),
               f"work/planning/history/{digest(old)}.json": old}
    override = deepcopy(docs.get("overrides"))
    if override is not None:
        outputs[f"work/planning/history/{hashes['input/overrides.json']}.json"] = read_bytes(root, "input/overrides.json", SMALL_FILE)
        override["storyboard_sha256"] = new_hashes["input/storyboard.json"]
        data = canonical(override) + b"\n"
        new_hashes["input/overrides.json"] = bytes_digest(data)
        outputs["input/overrides.json"] = data
    samples = raw["audio"]["master"]["samples"]
    script = read_bytes(root, "input/script.txt", SMALL_FILE).decode("utf-8-sig")
    entries = check_overrides(override, new_board, script, new_hashes, samples)
    new_plan = make_plan(script, new_board, read_evidence(root, raw["coarse_ref"]), entries, samples)
    if canonical(new_plan) != canonical(raw["plan"]):
        raise ValueError("Transition edit changed acoustic plan; rerun align explicitly")
    raw.update(binding=binding(new_board, new_hashes, False), replay_of=old["raw_ref"])
    result = evaluate(new_board, new_plan, raw["windows"], entries, samples)
    if result["status"] != "PASS":
        raise ValueError("Transition replay failed: " + str(result["anomalies"]))
    for key in ("boundaries", "characters", "speech_intervals", "reading_map"):
        if result[key] != old[key]:
            raise ValueError("Transition-only replay changed speech evidence")
    raw_name = f"work/alignment/evidence/{digest(raw)}.json"
    outputs[raw_name] = canonical(raw)
    outputs["work/alignment/aligned.json"] = {"version": VERSION, "binding": raw["binding"], "raw_ref": raw_name, **result}
    return outputs


def apply(root):
    request, value, docs, hashes, resolved = checked_candidates(root)
    reviews = approved(root, value)
    if hashes["input/storyboard.json"] != request["source_storyboard_sha256"]:
        raise ValueError("Storyboard changed since preparation; prepare a new plan")
    compile_timing(install(resolved, value["items"]))
    new_board = validate("storyboard", install(docs["storyboard"], value["items"]))
    outputs = replay(root, docs, hashes, new_board)
    outputs["review/transitions/applied.json"] = {"candidate_sha256": digest(value), "review_sha256": digest(reviews),
        "context_sha256": request["context_sha256"], "storyboard_sha256": bytes_digest(outputs["input/storyboard.json"])}
    write_docs(root, outputs)
    return {"status": "APPLIED", "next": "Run validate/compile to let SC-P1 produce the execution windows"}


def verify(root):
    request, value, docs, _, _ = checked_candidates(root)
    reviews = approved(root, value)
    applied = read_json(read_bytes(root, "review/transitions/applied.json", SMALL_FILE))
    expected = {"candidate_sha256": digest(value), "review_sha256": digest(reviews),
                "context_sha256": request["context_sha256"],
                "storyboard_sha256": bytes_digest(read_bytes(root, "input/storyboard.json", SMALL_FILE))}
    if applied != expected or install(docs["storyboard"], value["items"]) != docs["storyboard"]:
        raise ValueError("Confirmed semantic plan was not applied or storyboard/approval changed")
    return {"status": "PASS", "input_hashes": {INPUT: digest(request), CANDIDATES: digest(value), REVIEWS: digest(reviews)}}


def report(root):
    request, value, _, _, resolved = checked_candidates(root)
    rows, outputs, windows = [], {}, {}
    if value["status"] == "READY_FOR_REVIEW":
        _, timing = compile_timing(install(resolved, value["items"]))
        windows = {s["id"]: s["transition_out"] for s in timing[:-1]}
    from .images import prepare_image
    docs, _, _ = load_project(root)
    for boundary, item, proposal in zip(request["boundaries"], value["items"], value["proposal"]["boundaries"]):
        thumbs = []
        for side in ("from", "to"):
            shot, asset = boundary[side + "_shot"], boundary[side + "_asset"]
            raw = read_bytes(root, asset["path"], 64 * 1024 * 1024)
            _, preview, _ = prepare_image(raw, shot, docs["render"], {"logical_frames": 2, "head_hold_frames": 0,
                              "physical_frames": 2, "sequence_start_frame": 0})
            name = f"review/transitions/{shot['id']}.png"
            outputs[name] = preview
            thumbs.append(f'<figure><img width="360" src="{shot["id"]}.png"><figcaption>{escape(shot["id"] + " " + asset["source_mode"])}</figcaption></figure>')
        detail = {"before_text": boundary["from_text"], "after_text": boundary["to_text"],
                  "motion_before": boundary["from_shot"]["motion"], "motion_after": boundary["to_shot"]["motion"],
                  "pause_samples": boundary["pause_samples"], "proposal": proposal, "issues": item["issues"],
                  "compiled_window_preview": windows.get(item["from_shot_id"])}
        rows.append(f'<section><h2>{item["from_shot_id"]} → {item["to_shot_id"]}</h2><div class="pair">' +
                    ''.join(thumbs) + '</div><pre>' + escape(canonical(detail).decode("utf-8")) + '</pre></section>')
    html = '<!doctype html><meta charset="utf-8"><title>转场语义审核</title><style>body{font:16px sans-serif;margin:32px;max-width:1100px}.pair{display:flex}figure{margin:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{border-bottom:1px solid #aaa}</style><h1>待审候选：存在不等于批准</h1><p>窗口由 SC-P1 计算；正式执行须逐边界人工确认并 apply、compile。</p>' + ''.join(rows)
    outputs["review/transitions/index.html"] = html.encode("utf-8")
    write_docs(root, outputs)
    return {"status": value["status"], "report": "review/transitions/index.html", "candidate_sha256": digest(value)}


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="SC-P4 approved-original semantic transition planning")
    parser.add_argument("action", choices=("prepare", "propose", "report", "confirm", "apply", "verify"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", help="Episode-relative proposal or explicit human decision JSON")
    args = parser.parse_args(argv)
    root = Path(args.project).resolve(strict=True)
    if args.action in ("propose", "confirm"):
        if not args.input:
            raise ValueError("--input is required")
        data = read_json(read_bytes(root, args.input, SMALL_FILE))
        return {"propose": propose, "confirm": confirm}[args.action](root, data)
    return {"prepare": prepare, "report": report, "apply": apply, "verify": verify}[args.action](root)
