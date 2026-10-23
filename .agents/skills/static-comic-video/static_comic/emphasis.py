"""Strict optional emphasis inputs and locally evidenced resource manifests.

This module validates data and source bytes; it never downloads assets, approves
human decisions or infers acoustic timing. Insets use top/right/bottom/left.
"""
from copy import deepcopy
from pathlib import Path

from .contracts import bytes_digest, canonical, digest, read_json, validate
from .paths import read_bytes, resolve_path

SMALL_FILE = 4 * 1024 * 1024
ASSET_FILE = 256 * 1024 * 1024
DEFAULT_POLICY = {
    "schema_version": "1.0", "mode": "disabled",
    "visual": {"enabled": False, "selection": "adaptive", "theme": "comic",
               "max_events_per_minute": 8, "max_events_per_shot": 3,
               "min_gap_frames": 12, "max_concurrent": 1,
               "allow_advanced": True, "allow_prerender": False,
               "safe_insets": [0.08, 0.08, 0.08, 0.16]},
    "audio": {"enabled": False, "uses": ["keyword", "scene", "transition", "narrative"],
              "max_events_per_minute": 10, "max_concurrent": 2,
              "default_sfx_gain_db": -12, "peak_ceiling_dbfs": -1.0,
              "sfx_peak_ceiling_dbfs": -6.0, "sample_rate": 48000, "channels": 2},
}


def _local_path(root, relative, *, prefix=None):
    """Reject redirected inputs too: resource evidence must remain in its subtree."""
    path = resolve_path(root, relative)
    if prefix and not relative.startswith(prefix + "/"):
        raise ValueError(f"Asset must be inside {prefix}: {relative}")
    current = Path(root).resolve(strict=True)
    for part in relative.split("/"):
        current /= part
        if current.is_symlink() or current.is_junction():
            raise ValueError(f"Input reparse point: {relative}")
    return path


def _read_optional(root, relative, kind):
    path = _local_path(root, relative)
    if not path.exists():
        return None
    return validate(kind, read_json(read_bytes(root, relative, SMALL_FILE)))


def load_policy(root):
    value = _read_optional(root, "input/emphasis_policy.json", "emphasisPolicy")
    policy = deepcopy(DEFAULT_POLICY)
    if value is not None:
        policy.update({k: v for k, v in value.items() if k not in ("visual", "audio")})
        for section in ("visual", "audio"):
            policy[section].update(value[section])
    validate("emphasisPolicy", policy)
    if policy["mode"] == "disabled" and (policy["visual"]["enabled"] or policy["audio"]["enabled"]):
        raise ValueError("emphasisPolicy: disabled mode cannot enable visual/audio")
    insets = policy["visual"]["safe_insets"]
    if insets[0] + insets[2] >= 1 or insets[1] + insets[3] >= 1:
        raise ValueError("emphasisPolicy: safe insets leave no visible region")
    return policy


def empty_plan(script_bytes, shot_ids, *, disabled=False):
    return {"schema_version": "1.0", "script_sha256": bytes_digest(script_bytes),
            "shot_decisions": [{"shot_id": sid, "text_decision": "skip" if disabled else "auto",
                                "sfx_decision": "silence" if disabled else "auto",
                                "reason_code": "DISABLED" if disabled else "LOW_SEMANTIC_VALUE",
                                "reason": "扩展关闭" if disabled else "尚无可信候选，保留原始画面与旁白"}
                               for sid in shot_ids],
            "visual_events": [], "audio_events": [], "excluded": []}


def _range(value, text, label):
    start, end = value
    if not 0 <= start < end <= len(text):
        raise ValueError(f"{label}: invalid script_range {value}")
    return text[start:end]


def validate_plan(plan, *, script_bytes, shot_ids):
    validate("emphasisPlan", plan)
    if plan["script_sha256"] != bytes_digest(script_bytes):
        raise ValueError("emphasisPlan: script_sha256 is stale")
    text = script_bytes.decode("utf-8-sig")
    ids = set(shot_ids)
    decisions = [row["shot_id"] for row in plan["shot_decisions"]]
    if len(decisions) != len(set(decisions)) or set(decisions) != ids:
        raise ValueError("shot_decisions must uniquely cover every shot_id")
    events = plan["visual_events"] + plan["audio_events"]
    event_ids = [event["id"] for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("emphasisPlan: duplicate event id")
    for event in plan["visual_events"]:
        if event["shot_id"] not in ids:
            raise ValueError(f"{event['id']}: unknown shot_id")
        if _range(event["script_range"], text, event["id"]) != event["text"]:
            raise ValueError(f"{event['id']}: text differs from exact source script_range")
        advanced = event["preset"] in ("ink_reveal", "light_sweep", "fragment_disperse", "particle_assemble")
        if event["tier"] != (2 if advanced else 1):
            raise ValueError(f"{event['id']}: preset and tier disagree")
    for event in plan["audio_events"]:
        anchor = event["anchor"]
        sid = anchor.get("shot_id", anchor.get("from_shot_id"))
        if sid is not None and sid not in ids:
            raise ValueError(f"{event['id']}: unknown anchor shot_id")
        if anchor["type"] == "speech_start":
            _range(anchor["script_range"], text, event["id"])
        # Missing visual references remain candidates: the timing compiler reports
        # SKIPPED or REVIEW_REQUIRED instead of silently changing fixed choices.
        if "trim_end_sample" in event and event["trim_end_sample"] <= event.get("trim_start_sample", 0):
            raise ValueError(f"{event['id']}: empty/reversed source trim")
    return plan


def load_plan(root, policy, *, script_bytes, shot_ids):
    if policy["mode"] == "disabled":
        return empty_plan(script_bytes, shot_ids, disabled=True)
    plan = _read_optional(root, "input/emphasis_plan.json", "emphasisPlan")
    if plan is None:
        plan = empty_plan(script_bytes, shot_ids)
    return validate_plan(plan, script_bytes=script_bytes, shot_ids=shot_ids)


def verify_asset(root, asset, *, kind, technical=False):
    """Verify one declared font/SFX and its local license attachment; no approvals."""
    if kind not in ("fonts", "sfx"):
        raise ValueError(f"Unsupported resource kind: {kind}")
    schema = "fontManifest" if kind == "fonts" else "sfxManifest"
    validate(schema, {"schema_version": "1.0", "assets": [asset]})
    label = asset["asset_id"]
    permitted = {"APPROVED", "TECHNICAL_ONLY"} if technical else {"APPROVED"}
    if asset["review_status"] not in permitted:
        raise ValueError(f"{label}: resource is not approved for this artifact kind")
    for key in ("source_uri", "author", "license", "usage_scope"):
        if not asset[key].strip():
            raise ValueError(f"{label}: missing {key}")
    if asset["source_kind"] == "licensed_third_party" and not asset["source_uri"].startswith("https://"):
        raise ValueError(f"{label}: third-party source must name its HTTPS source")
    path = _local_path(root, asset["path"], prefix=f"assets/{kind}")
    allowed = {".ttf", ".otf", ".woff", ".woff2"} if kind == "fonts" else {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aiff"}
    if path.suffix.lower() not in allowed:
        raise ValueError(f"{label}: unsupported resource extension")
    data = read_bytes(root, asset["path"], ASSET_FILE)
    if not data or bytes_digest(data) != asset["sha256"]:
        raise ValueError(f"{label}: asset SHA256 mismatch or empty file")
    evidence = asset["license_evidence"]
    _local_path(root, evidence["path"], prefix=f"assets/{kind}")
    license_bytes = read_bytes(root, evidence["path"], SMALL_FILE)
    if not license_bytes.strip() or bytes_digest(license_bytes) != evidence["sha256"]:
        raise ValueError(f"{label}: license evidence SHA256 mismatch or empty attachment")
    if not technical:
        from .project import check_human
        approvals = _read_optional(root, "review/emphasis_resource_approvals.json",
                                   "emphasisResourceApprovals")
        if approvals is None:
            raise ValueError(f"{label}: REVIEW_REQUIRED; signed resource approval is missing")
        matches = [item for item in approvals["decisions"]
                   if item["asset_kind"] == ("font" if kind == "fonts" else "sfx")
                   and item["asset_id"] == label]
        if len(matches) != 1:
            raise ValueError(f"{label}: REVIEW_REQUIRED; expected one current resource approval")
        decision = matches[0]
        if (decision["decision"] != "APPROVED" or decision["asset_sha256"] != asset["sha256"]
                or decision["asset_manifest_sha256"] != digest(asset)):
            raise ValueError(f"{label}: REVIEW_REQUIRED; resource or license approval is stale")
        check_human(decision["human"], scope="resources",
                    expected={k: v for k, v in decision.items() if k != "human"})
    if kind == "sfx":
        # 候选可携带实际生成的声音节点，但所有节点都必须位于当前已验哈希 WAV 内。
        cue = asset.get("cue_points")
        if cue is not None:
            onset, peak, end = (cue[k] for k in ("onset_samples", "peak_samples", "end_samples"))
            if not 0 <= onset <= peak <= end < asset["duration_samples"]:
                raise ValueError(f"{label}: Earshot sound cue points exceed current asset duration")
        generator = asset.get("generator")
        if generator is not None:
            if (asset["source_kind"] != "local_created" or
                    generator["provider"] != "earshot" or
                    not asset["source_uri"].startswith("https://github.com/Leonxlnx/earshot/tree/")):
                raise ValueError(f"{label}: generated source metadata conflicts with asset origin")
            if cue is None:
                raise ValueError(f"{label}: generated asset requires acoustic cue points")
        if ("normalized_path" in asset) != ("normalized_sha256" in asset):
            raise ValueError(f"{label}: normalized path/hash must be supplied together")
        if "normalized_path" in asset:
            _local_path(root, asset["normalized_path"], prefix="assets/sfx")
            if bytes_digest(read_bytes(root, asset["normalized_path"], ASSET_FILE)) != asset["normalized_sha256"]:
                raise ValueError(f"{label}: normalized SHA256 mismatch")
    return asset


def load_manifest(root, kind, *, technical=False, required_ids=None):
    """只核验这次计划引用的资源；未审核候选不得因同库存在而阻塞旧片。

    选中的 CANDIDATE/REJECTED/TECHNICAL_ONLY（正式模式）仍由 verify_asset
    拒绝，绝不因出现在资源库中就自动取得批准。
    """
    schema = "fontManifest" if kind == "fonts" else "sfxManifest"
    relative = f"assets/{kind}/manifest.json"
    manifest = _read_optional(root, relative, schema)
    if manifest is None or not manifest["assets"]:
        raise ValueError(f"Missing or empty required resource manifest: {relative}")
    required = set(required_ids) if required_ids is not None else None
    assets, seen = {}, set()
    for asset in manifest["assets"]:
        label = asset["asset_id"]
        if label in seen:
            raise ValueError(f"{relative}: duplicate asset_id {label}")
        seen.add(label)
        if required is not None and label not in required:
            continue
        if kind == "sfx" and required is None and asset["review_status"] not in (
                ("APPROVED", "TECHNICAL_ONLY") if technical else ("APPROVED",)):
            continue
        assets[label] = verify_asset(root, asset, kind=kind, technical=technical)
    if required is not None and set(assets) != required:
        raise ValueError(f"{relative}: selected plan references unknown sound/font resources")
    return assets


def load_extension(root, *, script_bytes, shot_ids, technical=False):
    policy = load_policy(root)
    plan = load_plan(root, policy, script_bytes=script_bytes, shot_ids=shot_ids)
    fonts = load_manifest(root, "fonts", technical=technical) if policy["visual"]["enabled"] else {}
    sfx = (load_manifest(root, "sfx", technical=technical,
                         required_ids={event["sfx_asset_id"] for event in plan["audio_events"]})
           if policy["audio"]["enabled"] and plan["audio_events"] else {})
    if fonts:
        for event in plan["visual_events"]:
            asset_id = event.get("font_asset_id")
            if asset_id is not None and asset_id not in fonts:
                raise ValueError(f"{event['id']}: unknown font_asset_id {asset_id}")
            if asset_id is None and len(fonts) != 1:
                raise ValueError(f"{event['id']}: font_asset_id required for multiple fonts")
    if sfx:
        for event in plan["audio_events"]:
            if event["sfx_asset_id"] not in sfx:
                raise ValueError(f"{event['id']}: unknown sfx_asset_id")
    approvals = (_read_optional(root, "review/emphasis_resource_approvals.json",
                                "emphasisResourceApprovals")
                 if not technical and (fonts or sfx) else None)
    hashes = {"policy_sha256": digest(policy), "plan_sha256": digest(plan),
              "fonts_sha256": digest(fonts), "sfx_sha256": digest(sfx),
              "resource_approvals_sha256": digest(approvals)}
    return {"policy": policy, "plan": plan, "fonts": fonts, "sfx": sfx, "input_hashes": hashes}


def normalized_plan_bytes(plan):
    """Stable serialization for imported candidates and reproducibility checks."""
    validate("emphasisPlan", plan)
    return canonical(plan) + b"\n"
