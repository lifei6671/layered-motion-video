"""SC-A2：独立动态镜头的音效峰值候选，不改当前用户选定计划。"""
from .cache import publish
from .contracts import canonical, read_json, validate
from .emphasis import empty_plan, load_policy, validate_plan
from .paths import read_bytes, resolve_path


# 不把每个视觉事件都拟音；只在已授权的原文数值/纸墨/章节动作上建议。
STYLE_PREFERENCE = {
    "talkcraft-number-slab": ("keyword", "ui_pop/", "impact"),
    "talkcraft-ink-underline": ("keyword", "swish/", "impact"),
    "talkcraft-chapter-card": ("transition", "cut_hit/", "impact"),
}


def propose_card_sounds(root, compiled, *, technical=False):
    from .cache import publish
    cards = compiled["motion_cards"]["events"]
    script = read_bytes(root, "input/script.txt", 4*1024*1024)
    shot_ids = [row["source"]["id"] for row in compiled["timeline"]["shots"]]
    plan_file = resolve_path(root, "input/emphasis_plan.json")
    if plan_file.exists():
        base = validate_plan(read_json(read_bytes(root,"input/emphasis_plan.json",4*1024*1024)),
                             script_bytes=script,shot_ids=shot_ids)
    else:
        base = empty_plan(script,shot_ids)
    plan = read_json(canonical(base))
    policy = load_policy(root)
    assets_file = resolve_path(root,"assets/sfx/manifest.json")
    if not cards or not assets_file.exists() or not policy["audio"]["enabled"]:
        return {"status":"NO_CANDIDATES","count":0,"reason":"No selected cards, sound assets or active audio policy",
                "selected_plan_changed":False}
    assets = validate("sfxManifest",
                      read_json(read_bytes(root,"assets/sfx/manifest.json",4*1024*1024)))["assets"]
    decisions = {row["shot_id"]:row for row in plan["shot_decisions"]}
    existing_ids = {row["id"] for row in plan["audio_events"] + plan["visual_events"]}
    linked = {row["anchor"]["motion_card_id"] for row in plan["audio_events"]
              if row["anchor"]["type"]=="motion_marker"}
    count = 0
    for card in cards:
        if card["id"] in linked or decisions[card["shot_id"]]["sfx_decision"]=="silence":
            continue
        kind, prefix, marker = STYLE_PREFERENCE[card["recipe"]]
        if kind not in policy["audio"]["uses"]:
            continue
        choices = sorted((asset for asset in assets
            if kind in asset["tags"] and asset.get("generator",{}).get("provider")=="earshot"
            and asset["generator"]["bank_id"].startswith(prefix)
            and asset["review_status"] in (("TECHNICAL_ONLY","APPROVED") if technical else ("APPROVED",))),
            key=lambda item:item["asset_id"])
        if not choices:
            continue
        cid = "EASFX-" + card["id"][3:]
        if cid in existing_ids:
            continue
        plan["audio_events"].append({
            "id":cid,"kind":kind,"sfx_asset_id":choices[0]["asset_id"],
            "anchor":{"type":"motion_marker","motion_card_id":card["id"],
                      "marker":marker,"offset_samples":0},
            "sync_to":"peak", "gain_db":-14,
            "fade_in_samples":0,"fade_out_samples":480,
            "allow_tail_trim":True,"pinned":False,"source":"rules",
        })
        count += 1
    validate_plan(plan,script_bytes=script,shot_ids=shot_ids)
    target="work/audio/earshot/technical/proposals.json" if technical else "work/audio/earshot/proposals.json"
    if count:
        publish(root,{target:canonical(plan)+b"\n"})
    return {"status":"PROPOSED" if count else "NO_CANDIDATES",
            "count":count, "path":target if count else None,
            "selected_plan_changed":False,
            "requires_preview_review":True,
            "note":"The selected emphasis plan is unchanged; import proposals explicitly."}
