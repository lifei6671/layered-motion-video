"""Validate an episode and compile approved image snapshots; no media rendering."""
from datetime import datetime
from pathlib import Path
import re

import yaml

from .contracts import SCHEMA_PATH, bytes_digest, canonical, digest, read_json, validate
from .images import prepare_image
from .paths import read_bytes, resolve_path, write_bytes
from .timeline import compile_timing
from .cache import cached, cached_json, lookup, publish, versions

COMPILER_VERSION = "sc-p4.1"
SMALL_FILE = 4 * 1024 * 1024
IMAGE_FILE = 64 * 1024 * 1024


def check_human_metadata(human):
    """Legacy metadata only, for acoustic annotations and TEST_ONLY delivery."""
    if not all(human[k].strip() for k in ("actor", "at", "evidence")):
        raise ValueError("Human receipt needs actor, time and interaction evidence")
    if human.get("actor_role") != "human":
        raise ValueError("Human role required")
    parsed = datetime.fromisoformat(human["at"].replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Human receipt timestamp requires a timezone")


def check_human(human, *, scope, expected=None, item=None):
    from .human_review import verify
    verify(human, scope, expected, item=item)
    check_human_metadata(human)


def check_source_policy(policy, shots):
    if policy["status"] != "APPROVED" or policy["confirmation"] is None:
        raise ValueError("SOURCE_POLICY_PENDING: user source confirmation is required")
    check_human(policy["confirmation"]["human"], scope="policy",
                expected={"payload_sha256": policy["confirmation"]["payload_sha256"]})
    payload = {k: v for k, v in policy.items() if k != "confirmation"}
    if policy["confirmation"]["payload_sha256"] != digest(payload):
        raise ValueError("Source policy confirmation is stale; changed channels require user confirmation")
    ids = {s["id"] for s in shots}
    if set(policy["shots"]) - ids:
        raise ValueError("Source policy references an unknown shot")
    if policy["mode"] == "mixed" and set(policy["shots"]) != ids:
        raise ValueError("Mixed policy needs confirmed assignments for every shot")
    if policy["mode"] != "mixed" and not policy["default_channel"]:
        raise ValueError("Single-source policy requires default_channel")
    assignments = {}
    for sid in ids:
        assignment = policy["shots"].get(sid, {"source_mode": policy["mode"], "channel": policy["default_channel"]})
        if policy["mode"] != "mixed" and assignment["source_mode"] != policy["mode"]:
            raise ValueError(f"{sid}: single-source policy cannot switch source mode")
        if assignment not in policy["allowed_channels"]:
            raise ValueError(f"{sid}: channel is not allowed")
        assignments[sid] = assignment
    return assignments


def check_approval(shot, asset, policy_hash, assignment, receipts):
    sid = shot["id"]
    if asset["purpose"] != "production" or asset["review_status"] != "APPROVED":
        raise ValueError(f"{sid}: REVIEW_REQUIRED; candidate/reference/fixture images cannot enter production")
    if any(asset[k] != assignment[k] for k in ("source_mode", "channel")):
        raise ValueError(f"{sid}: source differs from the confirmed policy")
    if asset["source_mode"] == "third_party_retrieve":
        if not asset["source_uri"].startswith(("https://", "http://")) or not asset["query"].strip():
            raise ValueError(f"{sid}: third-party source URL and query are required")
    elif not asset["prompt"].strip():
        raise ValueError(f"{sid}: generation prompt is required")
    receipt = receipts.get(sid)
    if receipt is None or receipt["status"] != "APPROVED":
        raise ValueError(f"{sid}: REVIEW_REQUIRED; image existence is not approval")
    check_human(receipt["human"], scope="images")
    if asset["reviewer"] != receipt["human"]:
        raise ValueError(f"{sid}: manifest reviewer differs from the approval receipt")
    if (receipt["image_sha256"] != asset["sha256"] or receipt["asset_sha256"] != digest(asset)
            or receipt["policy_sha256"] != policy_hash):
        raise ValueError(f"{sid}: image approval is stale (image, source, license or policy changed)")


def load_project(root):
    root = Path(root).resolve(strict=True)
    raw = {}
    docs = {}
    locations = {"storyboard": "input/storyboard.json", "policy": "input/image_source_policy.json",
                 "manifest": "assets/images/manifest.json", "approvals": "review/image_approvals.json"}
    for kind, name in locations.items():
        raw[name] = read_bytes(root, name, SMALL_FILE)
        docs[kind] = validate(kind, read_json(raw[name]))
    raw["input/render.yaml"] = read_bytes(root, "input/render.yaml", SMALL_FILE)
    try:
        render = yaml.safe_load(raw["input/render.yaml"].decode("utf-8-sig"))
    except yaml.YAMLError as error:
        raise ValueError(f"input/render.yaml: invalid YAML: {error}") from error
    docs["render"] = validate("render", render)
    raw["input/script.txt"] = read_bytes(root, "input/script.txt", SMALL_FILE)
    text = raw["input/script.txt"].decode("utf-8-sig")  # Byte IO preserves CR and LF.
    board = docs["storyboard"]
    if bytes_digest(raw["input/script.txt"]) != board["script_sha256"]:
        raise ValueError("Original script bytes changed; ranges and approvals require review")
    source = board["audio"]["source"]
    if source not in ("input/voice.mp3", "input/voice.wav"):
        raise ValueError("Audio source must be input/voice.mp3 or input/voice.wav")
    raw[source] = read_bytes(root, source, 512 * 1024 * 1024)
    if bytes_digest(raw[source]) != board["audio"]["sha256"]:
        raise ValueError("Audio source hash mismatch")
    end = 0
    ids = []
    for index, shot in enumerate(board["shots"], 1):
        start, stop = shot["script_range"]
        if start != end or not start < stop <= len(text):
            raise ValueError(f"{shot['id']}: script_range must cover original code points continuously")
        end = stop
        ids.append(shot["id"])
        if shot["image"] != f"assets/images/shot_{index:04}.png":
            raise ValueError(f"{shot['id']}: expected formal filename shot_{index:04}.png")
    if end != len(text) or len(set(ids)) != len(ids):
        raise ValueError("Incomplete script ranges or duplicate shot IDs")
    override_path = resolve_path(root, "input/overrides.json")
    if override_path.exists():
        raw["input/overrides.json"] = read_bytes(root, "input/overrides.json", SMALL_FILE)
        override = validate("overrides", read_json(raw["input/overrides.json"]))
        for key, source_name in (("script_sha256", "input/script.txt"), ("audio_sha256", source),
                                 ("storyboard_sha256", "input/storyboard.json")):
            if override[key] != bytes_digest(raw[source_name]):
                raise ValueError(f"Stale overrides: {key}")
        docs["overrides"] = override
    hashes = {name: bytes_digest(data) for name, data in raw.items()}
    hashes["contract"] = bytes_digest(SCHEMA_PATH.read_bytes())
    offset = 3 if raw["input/script.txt"].startswith(b"\xef\xbb\xbf") else 0
    offsets = [offset]
    for char in text:
        offset += len(char.encode("utf-8"))
        offsets.append(offset)
    return docs, hashes, {"codepoint_count": len(text), "raw_byte_count": len(raw["input/script.txt"]),
                         "codepoint_to_raw_utf8_byte": offsets, "script_sha256": board["script_sha256"]}


def compile_project(root, *, technical_fixture=False, write=True):
    root = Path(root).resolve(strict=True)
    docs, hashes, source_index = load_project(root)
    board, policy = docs["storyboard"], docs["policy"]
    ids = [shot["id"] for shot in board["shots"]]
    assets = {a["shot_id"]: a for a in docs["manifest"]["assets"]}
    if len(assets) != len(docs["manifest"]["assets"]) or set(assets) != set(ids):
        raise ValueError("Asset manifest must contain exactly one asset per shot")
    receipts = {r["shot_id"]: r for r in docs["approvals"]["receipts"]}
    if len(receipts) != len(docs["approvals"]["receipts"]) or set(receipts) - set(ids):
        raise ValueError("Duplicate or unknown active image approval")
    assignments = None if technical_fixture else check_source_policy(policy, board["shots"])
    policy_hash = digest(policy)
    image_bytes = {}
    for shot in board["shots"]:
        sid, asset = shot["id"], assets[shot["id"]]
        if asset["path"] != shot["image"]:
            raise ValueError(f"{sid}: candidate has not been selected at its formal path")
        if technical_fixture:
            if asset["purpose"] != "technical_fixture" or shot["timing_source"] != "technical_fixture":
                raise ValueError(f"{sid}: explicit fixture mode requires fixture images and timing")
        else:
            if shot["timing_source"] == "technical_fixture":
                raise ValueError(f"{sid}: fixture timing cannot enter production")
            check_approval(shot, asset, policy_hash, assignments[sid], receipts)
        image_bytes[sid] = read_bytes(root, asset["path"], IMAGE_FILE)
        if bytes_digest(image_bytes[sid]) != asset["sha256"]:
            raise ValueError(f"{sid}: image bytes changed; approval invalid")
    for index, shot in enumerate(board["shots"][:-1]):
        tr = shot["transition_out"]
        if tr and tr["image_hashes"] != [assets[shot["id"]]["sha256"], assets[ids[index + 1]]["sha256"]]:
            raise ValueError(f"{shot['id']}: transition visual evidence is stale")
        if not technical_fixture and tr and tr["planning_source"] == "technical_fixture":
            raise ValueError(f"{shot['id']}: fixture transition cannot enter production")
        if not technical_fixture and tr and tr.get("image_approval_hashes") != [
                digest(receipts[shot["id"]]), digest(receipts[ids[index + 1]])]:
            raise ValueError(f"{shot['id']}: transition image approval is stale; review semantics again")
    if not technical_fixture:
        from .image_supply import verify as verify_image_supply
        supply_hashes = verify_image_supply(root, docs)["input_hashes"]
        hashes.update(supply_hashes)
    else:
        supply_hashes = {}
    alignment_path = resolve_path(root, "work/alignment/aligned.json")
    if not technical_fixture or alignment_path.exists():
        from .speech import apply_alignment
        board = apply_alignment(root, docs, hashes, technical_fixture=technical_fixture)
    elif docs.get("overrides", {}).get("entries"):
        raise ValueError("SC-P3 alignment is required to apply nonempty overrides")
    if not technical_fixture and len(board["shots"]) > 1:
        from .transitions import verify as verify_semantic_plan
        hashes.update(verify_semantic_plan(root)["input_hashes"])
    compiler_key = versions('static_comic/project.py', 'static_comic/timeline.py',
                            'static_comic/contracts.py', 'schemas/contracts.json')
    timing_key = {'version': compiler_key, 'board': board}
    if write:
        cached_json(root, 'image-authorization', {'version': compiler_key,
            'policy': policy, 'assets': docs['manifest'], 'receipts': docs['approvals'],
            'supply': supply_hashes, 'technical': technical_fixture}, lambda: {'validated': True})
        total, timing = cached_json(root, 'timeline', timing_key, lambda: compile_timing(board))
    else:
        total, timing = compile_timing(board)
    video = {k: docs["render"][k] for k in ("width", "height", "fps_num", "fps_den")}
    video["total_frames"] = total
    artifact = "technical_fixture" if technical_fixture else "production"
    remotion = "work/remotion/technical" if technical_fixture else "work/remotion"
    timeline_dir = "work/timeline/technical" if technical_fixture else "work/timeline"
    prepared, outputs, geometry, staging = {}, {}, [], []
    execution = []
    for shot, clock in zip(board["shots"], timing):
        sid, asset = shot["id"], assets[shot["id"]]
        image_key = {'version': versions('static_comic/images.py', packages=('Pillow',)),
                     'image': asset['sha256'], 'shot': {k: shot[k] for k in
                     ('id', 'motion', 'cover_anchor', 'subject_bbox')}, 'render': docs['render'], 'clock': clock}
        def build_image(temp):
            encoded, preview, detail = prepare_image(image_bytes[sid], shot, docs['render'], clock)
            (temp/'image.png').write_bytes(encoded)
            (temp/'cover.png').write_bytes(preview)
            (temp/'geometry.json').write_bytes(canonical(detail))
        folder, record, _ = lookup(root, 'image-'+sid.lower(), image_key)
        if write:
            folder, _ = cached(root, 'image-'+sid.lower(), image_key, build_image)
        if write or record is not None:
            encoded, preview = (folder/'image.png').read_bytes(), (folder/'cover.png').read_bytes()
            detail = read_json((folder/'geometry.json').read_bytes())
        else:
            encoded, preview, detail = prepare_image(image_bytes[sid], shot, docs['render'], clock)
        if not technical_fixture and detail["subject_status"] == "REVIEW_REQUIRED":
            raise ValueError(f"{sid}: subject cropped at frames {detail['clipped_global_frames'][:8]}; revise composition")
        image_hash = bytes_digest(encoded)
        staged = f"images/{image_hash}.png"
        prepared[staged] = encoded
        execution.append({**clock, "motion": shot["motion"], "staged_image": staged, "image_sha256": image_hash})
        staging.append({"shot_id": sid, "source_sha256": asset["sha256"], "asset_sha256": digest(asset),
                        "staged_image": staged, "staged_sha256": image_hash})
        outputs[f"{timeline_dir}/cover/{sid}.png"] = preview
        geometry.append(detail)
    from .emphasis import load_extension
    from .emphasis_timing import compile_events
    from .motion_cards import compile_cards
    # 先锁定动态字卡、再编译可关联其动作节点的音效，保持单一整数帧时钟。
    # 文字覆盖冲突在两侧编译完成后统一拒绝，防止改变现有审核后的布局。
    script_bytes = read_bytes(root, "input/script.txt", SMALL_FILE)
    extension = load_extension(root, script_bytes=script_bytes,
                               shot_ids=ids, technical=technical_fixture)
    motion_cards = compile_cards(root, board, execution, [],
                                 script_bytes=script_bytes)
    emphasis = compile_events(root, extension, board, execution, geometry, prepared,
                              motion_cards=motion_cards['events'],
                              technical=technical_fixture, write=write)
    if any(card['start_frame'] < event['end_frame'] and event['start_frame'] < card['end_frame']
           for card in motion_cards['events'] for event in emphasis['visual']):
        raise ValueError('MOTION_EMPHASIS_COLLISION: selected card overlaps locked keyword animation')
    props_data = {"schema_version": "2.0", "artifact_kind": artifact, "video": video, "shots": execution}
    if emphasis['visual']:
        props_data['visual_emphasis'] = emphasis['visual']
    if motion_cards['events']:
        props_data['motion_cards'] = motion_cards['events']
    if extension['policy']['mode'] != 'disabled':
        hashes.update({'emphasis/'+k: v for k,v in extension['input_hashes'].items()})
        hashes['emphasis/observations'] = digest(emphasis['observations'])
    if motion_cards['present']:
        hashes.update(motion_cards['input_hashes'])
    outputs.update(emphasis['outputs'])
    outputs.update(motion_cards['outputs'])
    props = validate("props", props_data)
    timeline = validate("timeline", {"schema_version": "2.0", "compiler_version": COMPILER_VERSION,
                        "artifact_kind": artifact, "episode_id": board["episode_id"], "input_hashes": hashes,
                        "audio": board["audio"], "video": video,
                        "shots": [{"source": source, "execution": target} for source, target in zip(board["shots"], execution)]})
    manifest_data = {"schema_version": "1.0", "artifact_kind": artifact,
                     "policy_sha256": policy_hash, "images": staging}
    if emphasis['resources']:
        manifest_data['resources'] = emphasis['resources']
    manifest = validate("staging", manifest_data)
    outputs.update({f"{timeline_dir}/timeline.lock.json": canonical(timeline) + b"\n",
                    f"{timeline_dir}/source-index.json": canonical(source_index) + b"\n",
                    f"{timeline_dir}/geometry.json": canonical({"artifact_kind": artifact, "shots": geometry}) + b"\n",
                    f"{remotion}/props.json": canonical(props) + b"\n",
                    f"{remotion}/staging-manifest.json": canonical(manifest) + b"\n"})
    for staged, data in prepared.items():
        outputs[f"{remotion}/public/{staged}"] = data
    for name in outputs:
        resolve_path(root, name, output=True)
    public = root / remotion / "public"
    existing = []
    declared = {r['path']:r['sha256'] for r in emphasis['resources']}
    old_manifest = resolve_path(root, f"{remotion}/staging-manifest.json")
    if old_manifest.exists():
        previous = validate('staging', read_json(read_bytes(root, f"{remotion}/staging-manifest.json", SMALL_FILE)))
        declared.update({r['path']:r['sha256'] for r in previous.get('resources',[])})
    if public.exists():
        for path in public.rglob("*"):
            relative = path.relative_to(root).as_posix()
            resolve_path(root, relative + "/.probe" if path.is_dir() else relative, output=True)
            if path.is_dir():
                if path not in [public / p for p in ('images','fonts','effects')]:
                    raise ValueError("Unexpected directory in public; refuse to expose or delete it")
                continue
            name = path.relative_to(public).as_posix()
            if not re.fullmatch(r"images/[a-f0-9]{64}\.png", name) and name not in declared:
                raise ValueError("Public directory contains non-staged data; remove it explicitly")
            data = read_bytes(root, relative, IMAGE_FILE)
            if bytes_digest(data) != path.stem or (name in declared and declared[name] != path.stem):
                raise ValueError(f"Corrupt staged snapshot: {name}")
            existing.append(path)
    if write:
        def build_staging(temp):
            for name, data in outputs.items():
                path = temp/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        staged_folder, _ = cached(root, 'staging', {'version': compiler_key,
            'outputs': {name: bytes_digest(data) for name, data in outputs.items()}}, build_staging)
        publish(root, {name: staged_folder/name for name in outputs})
        for staged, data in prepared.items():
            if read_bytes(root, f"{remotion}/public/{staged}", IMAGE_FILE) != data:
                raise ValueError(f"Staged image hash verification failed: {staged}")
        for old in existing:
            if old.relative_to(public).as_posix() not in prepared:
                old.unlink()  # Only validated, content-addressed generated snapshots.
    return {"status": "PASS", "artifact_kind": artifact, "total_frames": total,
            "timeline": timeline, "props": props, "staging": manifest,
            "geometry": geometry, "emphasis": {k:v for k,v in emphasis.items() if k != 'outputs'},
            "motion_cards": {k:v for k,v in motion_cards.items() if k != 'outputs'},
            "emphasis_policy": extension['policy'], "written": list(outputs) if write else []}
