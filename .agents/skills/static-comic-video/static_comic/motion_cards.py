"""SC-M：受控动态字卡编排，复用旁白锁定帧，不改变原音频或分镜。

事件是已选择的视觉计划，而不是允许执行的 React/JS 代码。候选建议
另存于 work/motion；只有 input/motion_cards.json 会参与真实编译。
"""
from pathlib import Path
import re

from .contracts import bytes_digest, canonical, digest, read_json, validate
from .emphasis_timing import speech_samples, stable_window
from .paths import read_bytes, resolve_path
from .timeline import FPS, frame_at

PLAN = "input/motion_cards.json"
RECIPE_LIMITS = {
    "talkcraft-number-slab": (42, 150),
    "talkcraft-ink-underline": (32, 150),
    "talkcraft-chapter-card": (48, 180),
}
NUMBER = re.compile(r"[+-]?[0-9]+(?:\.[0-9]{1,6})?(?:%|％|元|倍|万|亿|人|次|个)?\Z")
# 单镜头最多一个全屏字卡；相邻一分钟最多两个，避免把漫画变成 PPT。
MAX_PER_SHOT = 1
MAX_PER_MINUTE = 2


def selected_plan(root, script_bytes):
    path = resolve_path(root, PLAN)
    if not path.exists():
        return None
    raw = read_bytes(root, PLAN, 4 * 1024 * 1024)
    plan = validate("motionPlan", read_json(raw))
    if plan["script_sha256"] != bytes_digest(script_bytes):
        raise ValueError("MOTION_PLAN_STALE: original script changed; select/review again")
    return plan


def empty_plan(script_bytes):
    return {"schema_version": "1.0", "script_sha256": bytes_digest(script_bytes), "events": []}


def compile_cards(root, board, execution, visual_emphasis, *, script_bytes):
    """在原画稳定窗口内编译全局绝对帧；拒绝编造文字和事件冲突。"""
    plan = selected_plan(root, script_bytes)
    if plan is None:
        return {"events": [], "outputs": {}, "input_hashes": {}, "present": False}
    script = script_bytes.decode("utf-8-sig")
    shot_by_id = {shot["id"]: (i, shot) for i, shot in enumerate(board["shots"])}
    card_list = []
    ids = set()
    # 排序以时间为主，确保同一计划在任意 JSON 数组顺序下都得到稳定顺序。
    for card in sorted(plan["events"], key=lambda event: (event["start_frame"], event["id"])):
        card = validate("motionCardEvent", card)
        sid, cid = card["shot_id"], card["id"]
        if cid in ids or sid not in shot_by_id:
            raise ValueError(f"{cid}: duplicate card ID or unknown shot")
        ids.add(cid)
        idx, shot = shot_by_id[sid]
        lo, hi = card["script_range"]
        left, right = shot["script_range"]
        if not left <= lo < hi <= right or script[lo:hi] != card["text"]:
            raise ValueError(f"{cid}: text differs from the exact Unicode source range")
        if any(c in card["text"] for c in "\r\n\t<>") or any(c in card.get("label", "") for c in "\r\n\t<>"):
            raise ValueError(f"{cid}: unsupported multiline/markup text")
        if card.get("label") and card["label"] not in script[left:right]:
            raise ValueError(f"{cid}: explanatory label is not grounded in the shot script")
        max_chars = 12 if card["recipe"] == "talkcraft-number-slab" else 14
        if len(card["text"]) > max_chars or len(card.get("label", "")) > 20:
            raise ValueError(f"{cid}: motion card text exceeds readable width budget")
        if card["recipe"] == "talkcraft-number-slab" and not NUMBER.fullmatch(card["text"]):
            raise ValueError(f"{cid}: number card requires a literal numeric token")
        lower, upper = stable_window(idx, execution)
        start, end = card["start_frame"], card["end_frame"]
        minimum, maximum = RECIPE_LIMITS[card["recipe"]]
        if not lower <= start < end <= upper or not minimum <= end - start <= maximum:
            raise ValueError(f"{cid}: motion card outside stable window or recipe duration budget")
        if any(other["shot_id"] == sid for other in card_list):
            raise ValueError(f"{cid}: max one dynamic card per shot")
        if any(start < other["end_frame"] and other["start_frame"] < end for other in card_list):
            raise ValueError(f"{cid}: motion card overlaps another dynamic card")
        if any(start < item["end_frame"] and item["start_frame"] < end for item in visual_emphasis):
            raise ValueError(f"{cid}: full-screen card overlaps keyword visual emphasis")
        if sum(abs(other["start_frame"] - start) < FPS * 60 for other in card_list) >= MAX_PER_MINUTE:
            raise ValueError(f"{cid}: full-screen motion card density budget exceeded")
        card_list.append(validate("compiledMotionCard", card))
    if len(card_list) > 100:
        raise ValueError("Too many motion cards in one composition")
    prefix = "work/timeline"
    # technical_fixture 与 production 用独立锁文件，不能互相当成审批结果。
    if execution and board["shots"][0]["timing_source"] == "technical_fixture":
        prefix += "/technical"
    lock = {"schema_version": "1.0", "script_sha256": plan["script_sha256"],
            "plan_sha256": digest(plan), "events": card_list}
    outputs = {f"{prefix}/motion_cards.lock.json": canonical(lock) + b"\n"}
    from .cache import versions
    hashes = {"input/motion_cards.json": bytes_digest(read_bytes(root, PLAN, 4 * 1024 * 1024)),
              "motion_cards/compiler": digest(versions("static_comic/motion_cards.py"))}
    return {"events": card_list, "outputs": outputs, "input_hashes": hashes, "present": True}


def propose_rules(root, compiled):
    """规则只产出候选：精确数字 + 已有可靠字级声学证据；不擅自改选定计划。"""
    from .cache import publish
    board = compiled["timeline"]
    script_bytes = read_bytes(root, "input/script.txt", 4 * 1024 * 1024)
    script = script_bytes.decode("utf-8-sig")
    aligned_path = resolve_path(root, "work/alignment/aligned.json")
    if not aligned_path.exists():
        return {"status": "UNAVAILABLE", "reason": "No verified character alignment; refusing guessed numeric timing",
                "selected_plan_changed": False}
    aligned = read_json(read_bytes(root, "work/alignment/aligned.json", 32 * 1024 * 1024))
    events = []
    absolute = [row["execution"] for row in board["shots"]]
    for idx, row in enumerate(board["shots"]):
        shot = row["source"]
        a, b = shot["script_range"]
        passage = script[a:b]
        # 只从可信原文取出三类有明确语义的短片段，未命中即零事件。
        # 数字优先，然后是真正的章节切换、最后是概念定义；不猜测人像或画面情绪。
        candidates = []
        candidates.extend((match, "talkcraft-number-slab", "paper", 52)
                          for match in re.finditer(r"[0-9]+(?:\.[0-9]{1,6})?(?:%|％|元|倍|万|亿)", passage))
        candidates.extend((match, "talkcraft-chapter-card", "ink", 80)
                          for match in re.finditer(r"第[一二三四五六七八九十0-9]{1,4}[章节]|首先|接下来|最后|总结", passage))
        candidates.extend((match, "talkcraft-ink-underline", "paper", 62)
                          for match in re.finditer(r"(?:所谓|这就是)([\u4e00-\u9fff]{2,8})", passage))
        for match, recipe, style, tail in candidates:
            # 概念只强调被定义的名词，不把「所谓」或「这就是」也做成大字。
            lo, hi = match.span(1) if recipe == "talkcraft-ink-underline" else match.span()
            span = [a + lo, a + hi]
            try:
                speech = speech_samples(aligned, span)
            except (ValueError, KeyError, IndexError):
                continue
            lower, upper = stable_window(idx, absolute)
            center = frame_at(speech[0])
            start = center - 10
            end = max(center + tail, frame_at(speech[1]) + 18)
            minimum, maximum = RECIPE_LIMITS[recipe]
            if lower <= start < end <= upper and minimum <= end - start <= maximum:
                events.append({
                    "id": f"MC-{shot['id']}-{lo}",
                    "shot_id": shot["id"], "recipe": recipe,
                    "script_range": span, "text": passage[lo:hi],
                    "style": style, "source": "rules",
                    "start_frame": start, "end_frame": end,
                })
                break  # 仅建议一个，避免因候选密度强迫观众阅读。
    # 同一滑动一分钟仅保留两张，避免稠密的数字广告式切换。
    chosen = []
    for e in sorted(events, key=lambda x: (x["start_frame"], x["id"])):
        if sum(abs(s["start_frame"] - e["start_frame"]) < FPS * 60 for s in chosen) < MAX_PER_MINUTE:
            chosen.append(e)
    proposed = validate("motionPlan", {**empty_plan(script_bytes), "events": chosen})
    technical = compiled["artifact_kind"] == "technical_fixture"
    target = "work/motion/technical/proposals.json" if technical else "work/motion/proposals.json"
    publish(root, {target: canonical(proposed) + b"\n"})
    return {"status": "PROPOSED", "path": target, "count": len(chosen),
            "model_observation": "NOT_RUN", "selected_plan_changed": False}


def main(argv):
    import argparse
    from .cache import publish
    from .project import compile_project
    parser = argparse.ArgumentParser(description="Controlled motion-card proposals and selection")
    parser.add_argument("command", choices=("propose", "import", "inspect"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--file", help="Episode-relative, validated plan to import")
    parser.add_argument("--replace", action="store_true", help="Explicitly replace a preselected plan")
    parser.add_argument("--provider", choices=("rules", "agent"), default="rules")
    parser.add_argument("--technical-fixture", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.project).resolve(strict=True)
    if args.command == "import":
        if not args.file:
            raise ValueError("motion import requires --file")
        script = read_bytes(root, "input/script.txt", 4 * 1024 * 1024)
        value = validate("motionPlan", read_json(read_bytes(root, args.file, 4 * 1024 * 1024)))
        if value["script_sha256"] != bytes_digest(script):
            raise ValueError("MOTION_PLAN_STALE: proposed script hash does not match current source")
        current = resolve_path(root, PLAN)
        if current.exists() and read_json(read_bytes(root, PLAN, 4 * 1024 * 1024)) != value and not args.replace:
            raise ValueError("Existing selected motion plan differs; use --replace after review")
        # 导入前执行同一编译边界，不让无效时间窗计划进入选定入口。
        compiled = compile_project(root, technical_fixture=args.technical_fixture, write=False)
        rows = compiled["timeline"]["shots"]
        # import 之前可先用临时 input 验证；这里逐项复用安全断言，
        # 当前文件需要完整 staged 验收时由随后 compile 再核验。
        validate_proposal(value, rows, compiled["emphasis"]["visual"], script.decode("utf-8-sig"))
        publish(root, {PLAN: canonical(value) + b"\n"})
        return {"status": "IMPORTED", "path": PLAN, "count": len(value["events"]),
                "requires_preview_review": True}
    compiled = compile_project(root, technical_fixture=args.technical_fixture, write=False)
    if args.command == "inspect":
        return {"status": "PASS", "events": compiled["motion_cards"]["events"],
                "selected": compiled["motion_cards"]["present"],
                "human_preview_approval": "NOT_RUN"}
    if args.provider == "agent":
        return {"status": "UNAVAILABLE", "reason": "No local visual Agent runtime registered for motion cards",
                "next": "Agent inspects approved comic frames and verified speech, writes a strict motionPlan JSON; import it explicitly."}
    return propose_rules(root, compiled)


def validate_proposal(plan, rows, visuals, script):
    """导入前验内容事实、稳定窗口、密度与互斥；未执行磁盘写入。"""
    board = {"shots": [r["source"] for r in rows]}
    execution = [r["execution"] for r in rows]
    # 与生产 compiler 使用同一个数据协议；无须临时重写 input 文件。
    ids = set()
    chosen = []
    for card in sorted(plan["events"], key=lambda e: (e["start_frame"], e["id"])):
        if card["id"] in ids or card["shot_id"] not in {s["id"] for s in board["shots"]}:
            raise ValueError("Duplicate/unknown card")
        ids.add(card["id"])
        idx = next(i for i,s in enumerate(board["shots"]) if s["id"]==card["shot_id"])
        source = board["shots"][idx]
        lo,hi = card["script_range"]
        if not source["script_range"][0]<=lo<hi<=source["script_range"][1] or script[lo:hi]!=card["text"]:
            raise ValueError("Card text and original script range mismatch")
        if any(c in card["text"]+card.get("label","") for c in "\r\n\t<>"):
            raise ValueError("Unsafe card text")
        if card.get("label") and card["label"] not in script[source["script_range"][0]:source["script_range"][1]]:
            raise ValueError("Card label not grounded in original script")
        max_chars = 12 if card["recipe"]=="talkcraft-number-slab" else 14
        if len(card["text"])>max_chars or len(card.get("label",""))>20:
            raise ValueError("Motion-card text is too long to remain readable")
        if card["recipe"]=="talkcraft-number-slab" and not NUMBER.fullmatch(card["text"]):
            raise ValueError("Number card must be an exact numeric token")
        minimum,maximum=RECIPE_LIMITS[card["recipe"]]
        low,high=stable_window(idx,execution)
        start,end=card["start_frame"],card["end_frame"]
        if not low<=start<end<=high or not minimum<=end-start<=maximum:
            raise ValueError("Motion card conflicts with transition/shot frame budget")
        if any(c["shot_id"]==card["shot_id"] or (start<c["end_frame"] and c["start_frame"]<end) for c in chosen):
            raise ValueError("Overlapping or duplicate-shot motion card")
        if any(start<v["end_frame"] and v["start_frame"]<end for v in visuals):
            raise ValueError("Motion card conflicts with locked keyword emphasis")
        if sum(abs(start-c["start_frame"])<FPS*60 for c in chosen)>=MAX_PER_MINUTE:
            raise ValueError("Motion card density limit")
        chosen.append(card)
    return chosen
