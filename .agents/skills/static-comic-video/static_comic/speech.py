"""Auditable SC-P3 alignment and replay into the one SC-P1 compiler."""
import copy
from importlib.metadata import version
import math
from pathlib import Path
import subprocess
import sys

from .contracts import bytes_digest, canonical, read_json
from .paths import read_bytes, write_bytes
from .speech_audio import prepare_audio, transcribe_service, wav_info
from .speech_text import check_overrides, make_plan
from .timeline import compile_timing, seconds_to_samples
from .cache import cached_json, publish, versions

VERSION = "sc-p3.1"
LIMIT = 32 * 1024 * 1024


def binding(board, hashes, technical_fixture):
    return {"script_sha256":hashes["input/script.txt"], "audio_sha256":hashes[board["audio"]["source"]],
            "storyboard_sha256":hashes["input/storyboard.json"],
            "overrides_sha256":hashes.get("input/overrides.json"),
            "artifact_kind":"technical_fixture" if technical_fixture else "production"}


def store_evidence(root, value):
    data = canonical(value)
    name = f"work/alignment/evidence/{bytes_digest(data)}.json"
    path = Path(root) / name
    if path.exists() and read_bytes(root, name, LIMIT) != data:
        raise ValueError("Existing evidence has changed")
    write_bytes(root, name, data)
    return name


def evaluate(board, plan, raw_windows, entries, samples):
    """Only raw dictionary-character timestamps can become acoustic evidence."""
    reading = plan["reading"]
    chars = [{"char":char, "source":"missing", "samples":None} for char in reading["text"]]
    anomalies = copy.deepcopy(plan["anomalies"])
    if len(raw_windows) != len(plan["windows"]):
        raise ValueError("Alignment window inventory differs from plan")
    for window, raw in zip(plan["windows"], raw_windows):
        if raw["window"] != window:
            raise ValueError("Alignment result bound to another window")
        acoustic = [char for segment in raw["result"]["segments"] for char in (segment.get("chars") or [])]
        lo, hi = window["reading_range"]
        if "".join(c["char"] for c in acoustic) != window["text"]:
            for i in range(lo,hi):
                chars[i]["source"] = "coarse_segment"
            continue
        previous = window["origin_samples"]
        for i, char in enumerate(acoustic, lo):
            evidence = {"char":char["char"], "raw":char, "source":"missing", "samples":None,
                        "origin_samples":window["origin_samples"]}
            values = [char.get(k) for k in ("start","end","score")]
            if char["char"].lower() not in raw["dictionary_characters"]:
                evidence["source"] = "wildcard"
            elif all(type(x) in (int,float) and math.isfinite(x) for x in values):
                if values[0] >= 0 and values[1] > values[0]:
                    start = seconds_to_samples(str(values[0]), window["origin_samples"])
                    end = seconds_to_samples(str(values[1]), window["origin_samples"])
                    if previous <= start < end <= min(samples, window["input_16k"][1]*3):
                        evidence["samples"] = [start,end]
                        evidence["source"] = "acoustic_aligned" if values[2] >= 0.2 else "low_score"
                        previous = end
            elif "start" in char or "end" in char:
                evidence["source"] = "interpolated_or_missing_score"
            chars[i] = evidence
    boundaries, intervals, interval_evidence = [], [], []
    for index, shot in enumerate(board["shots"]):
        lo,hi = shot["script_range"]
        indices = [i for i,(a,b) in enumerate(reading["source_ranges"]) if lo <= a and b <= hi]
        selected = [chars[i] for i in indices]
        good = [c for c in selected if c["source"] == "acoustic_aligned"]
        overrides = [e for e in entries if e["kind"] == "boundary" and e["to_shot_id"] == shot["id"]]
        manual = overrides[0] if overrides else None
        adjacent_confirmations = [e for e in entries if e["kind"] == "boundary" and
                                  shot["id"] in (e["from_shot_id"], e["to_shot_id"])]
        adjacent_confirmations += [e for e in entries if e["kind"] == "window" and e["script_range"] == [lo,hi]]
        first_ok = selected and selected[0]["source"] == "acoustic_aligned"
        uncertain = not selected or any(c["source"] != "acoustic_aligned" for c in selected)
        interval = [good[0]["samples"][0],good[-1]["samples"][1]] if good else None
        interval_source = "acoustic_aligned" if interval else "missing"
        if uncertain and adjacent_confirmations and indices:
            support = [w for w in plan["windows"] if w["reading_range"][0] < indices[-1]+1 and indices[0] < w["reading_range"][1]]
            covered = {i for w in support for i in range(*w["reading_range"])}
            if all(i in covered for i in indices):
                # A coarse envelope remains coarse even when a human confirms a
                # neighboring switch. Never manufacture missing character times.
                interval = [support[0]["samples"][0], support[-1]["samples"][1]]
                interval_source = "manual_window" if all(w["source"] == "manual_window" for w in support) else "coarse_segment"
        intervals.append(interval)
        interval_evidence.append({"shot_id":shot["id"], "samples":interval, "source":interval_source,
                                  "confirmations":adjacent_confirmations if uncertain else []})
        if index == 0:
            boundary = {"shot_id":shot["id"],"sample":0,"source":"audio_origin"}
        elif manual:
            boundary = {"shot_id":shot["id"],"sample":manual["sample"],"source":"manual_confirmed", "receipt":manual}
        elif first_ok:
            boundary = {"shot_id":shot["id"],"sample":selected[0]["samples"][0],"source":"acoustic_aligned"}
        else:
            boundary = {"shot_id":shot["id"],"sample":None,"source":"unconfirmed"}
        boundaries.append(boundary)
        # A manual boundary can confirm uncertain timing, never content differences.
        if not interval or (uncertain and not adjacent_confirmations):
            anomalies.append({"kind":"unconfirmed_timing", "script_range":[lo,hi], "samples":interval,
                              "shot_ids":[shot["id"]], "detail":"Missing/low-score character requires a trustworthy window or explicit boundary confirmation"})
    starts = [b["sample"] for b in boundaries]
    if any(s is None for s in starts) or any(a >= b for a,b in zip(starts,starts[1:]) if a is not None and b is not None):
        anomalies.append({"kind":"nonmonotonic_boundaries", "script_range":[0,board["shots"][-1]["script_range"][1]],
                          "samples":[0,samples],"shot_ids":[s["id"] for s in board["shots"]],"detail":"Boundary samples must strictly increase"})
    warnings = [{"reading_index":i,"script_range":reading["source_ranges"][i],"source":c["source"]}
                for i,c in enumerate(chars) if c["source"] != "acoustic_aligned"]
    candidate = copy.deepcopy(board)
    candidate["audio"]["duration_samples"] = samples
    if not anomalies:
        for i,shot in enumerate(candidate["shots"]):
            shot["start_samples"] = starts[i]
            shot["speech_interval_samples"] = intervals[i]
            shot["timing_source"] = "manual_confirmed" if (boundaries[i]["source"] == "manual_confirmed" or
                interval_evidence[i]["confirmations"]) else "acoustic_aligned"
            if boundaries[i].get("receipt"):
                shot["boundary_reason"] = boundaries[i]["receipt"]["reason"]
            if i and candidate["shots"][i-1]["transition_out"]:
                # Preserve the authored semantic anchor/placement. Adjusted boundary is explicit.
                shot["boundary_reason"] = shot["boundary_reason"] or "SC-P3 speech evidence boundary"
        try:
            # P3 establishes the clock before P4 can plan semantic transitions.
            # Temporary zero-frame cuts validate timing only; never publish them.
            timing_check = copy.deepcopy(candidate)
            for index, shot in enumerate(timing_check["shots"][:-1]):
                if shot["transition_out"] is None:
                    following = timing_check["shots"][index + 1]
                    shot["transition_out"] = {"type": "cut", "duration_frames": 0,
                        "to_shot_id": following["id"], "semantic_anchor_samples": following["start_samples"],
                        "placement": "start_at_anchor"}
            compile_timing(timing_check)
        except ValueError as error:
            anomalies.append({"kind":"timeline_conflict","script_range":[0,board["shots"][-1]["script_range"][1]],
                              "samples":[0,samples],"shot_ids":[s["id"] for s in board["shots"]],"detail":str(error)})
    return {"status":"REVIEW_REQUIRED" if anomalies else "PASS", "boundaries":boundaries, "reading_map":reading,
            "characters":chars,"warnings":warnings,"anomalies":anomalies,"speech_intervals":interval_evidence,
            "resolved_timing_anomalies":plan["resolved_timing_anomalies"],
            "candidate_storyboard":candidate if not anomalies else None,
            "human_boundary_audit":"NOT_RUN", "score_note":"Screening heuristic, not timestamp correctness probability",
            "time_precision":"WhisperX 3.8.6 rounds raw character seconds to 0.001 s; integer samples do not imply sample-accurate acoustics"}


def align_project(root, *, url, models_lock, technical_fixture=False):
    from .project import load_project
    root = Path(root).resolve(strict=True)
    docs, hashes, _ = load_project(root)
    board = docs["storyboard"]
    script = read_bytes(root,"input/script.txt",LIMIT).decode("utf-8-sig")
    lock = read_json(Path(models_lock).read_bytes())
    if version("whisperx") != "3.8.6":
        raise ValueError("SC-P3 requires the locked WhisperX 3.8.6 adapter")
    from scripts.probe_models import verify_model
    for kind in ('asr', 'alignment'):
        verify_model(lock[kind])
    audio = prepare_audio(root,board["audio"]["source"])
    samples = audio["master"]["samples"]
    entries = check_overrides(docs.get("overrides"),board,script,hashes,samples)
    adapter = versions('static_comic/speech.py', 'static_comic/speech_audio.py',
                       'static_comic/speech_text.py', 'static_comic/speech_worker.py',
                       'uv.lock', packages=('whisperx', 'torch', 'transformers', 'faster-whisper'))
    def coarse_asr():
        value = transcribe_service(root, url, lock)
        if value.get('backend_matches') is not True:
            evidence = store_evidence(root, value)
            raise ValueError('VoiceStudio backend changed; diagnostic evidence: '+evidence)
        make_plan(script, board, value, entries, samples)  # Reject malformed provider output before caching.
        return value
    coarse = cached_json(root, 'coarse-asr', {'audio': audio['align'], 'url': url,
                          'model': lock['asr'], 'version': adapter}, coarse_asr)
    coarse_ref = store_evidence(root,coarse)
    plan = make_plan(script,board,coarse,entries,samples)
    request = {"plan":plan,"lock":lock}
    request_ref = store_evidence(root,request)
    # Separate process bounds model runtime and keeps CLI JSON free of library stdout.
    command = [sys.executable,"-m","static_comic.speech_worker",str(root),request_ref]
    def align_windows():
        worker = subprocess.run(command,capture_output=True,timeout=1800,check=False)
        write_bytes(root,"work/alignment/worker.log",worker.stdout + worker.stderr)
        if worker.returncode:
            raise ValueError("Locked WhisperX alignment failed; see work/alignment/worker.log")
        windows = read_json(worker.stdout)
        evaluate(board, plan, windows, entries, samples)
        return windows
    raw_windows = cached_json(root, 'alignment', {'audio': audio['align'], 'request': request,
                              'version': adapter}, align_windows)
    raw = {"binding":binding(board,hashes,technical_fixture), "audio":audio,"coarse_ref":coarse_ref,
           "plan":plan,"windows":raw_windows,"model_lock":lock,"whisperx_version":version("whisperx")}
    raw_ref = store_evidence(root,raw)
    result = evaluate(board,plan,raw_windows,entries,samples)
    aligned = {"version":VERSION,"binding":raw["binding"],"raw_ref":raw_ref, **result}
    outputs = {"work/alignment/asr_segments.json": canonical({"evidence_ref":coarse_ref,"response":coarse["response"]}),
               "work/alignment/aligned.json": canonical(aligned),
               "work/alignment/review.json": canonical({k:aligned[k] for k in
                   ("status","boundaries","anomalies","warnings","human_boundary_audit")})}
    if "overrides" not in docs:
        template = {"schema_version":"1.0", **{k:v for k,v in raw["binding"].items() if k in ("script_sha256","audio_sha256","storyboard_sha256")}, "entries":[]}
        outputs["work/alignment/overrides.template.json"] = canonical(template)
    publish(root, outputs)
    return aligned


def read_evidence(root, name):
    import re
    if not re.fullmatch(r"work/alignment/evidence/[a-f0-9]{64}\.json",name):
        raise ValueError("Invalid alignment evidence reference")
    data = read_bytes(root,name,LIMIT)
    if bytes_digest(data) != Path(name).stem:
        raise ValueError("Raw alignment evidence hash mismatch")
    return read_json(data)


def apply_alignment(root, docs, hashes, *, technical_fixture):
    board = docs["storyboard"]
    aligned_data = read_bytes(root,"work/alignment/aligned.json",LIMIT)
    aligned = read_json(aligned_data)
    expected = binding(board,hashes,technical_fixture)
    if aligned.get("version") != VERSION or aligned.get("binding") != expected:
        raise ValueError("Stale or incompatible SC-P3 alignment; rerun align")
    raw = read_evidence(root,aligned["raw_ref"])
    if raw["binding"] != expected:
        raise ValueError("Stale raw alignment binding")
    for key,name in (("master","master_48k.wav"),("align","align_16k.wav")):
        if wav_info(read_bytes(root,"work/audio/"+name,512*1024*1024)) != raw["audio"][key]:
            raise ValueError("PCM audio changed after alignment")
    samples = raw["audio"]["master"]["samples"]
    script = read_bytes(root,"input/script.txt",LIMIT).decode("utf-8-sig")
    entries = check_overrides(docs.get("overrides"),board,script,hashes,samples)
    coarse = read_evidence(root,raw["coarse_ref"])
    plan = make_plan(script,board,coarse,entries,samples)
    if canonical(plan) != canonical(raw["plan"]):
        raise ValueError("Alignment plan differs from source/overrides")
    result = evaluate(board,plan,raw["windows"],entries,samples)
    if any(canonical(result[k]) != canonical(aligned.get(k)) for k in result):
        raise ValueError("Derived alignment was edited; change overrides and rerun align")
    if result["status"] != "PASS":
        raise ValueError("SC-P3 REVIEW_REQUIRED: " + ", ".join(a["kind"] for a in result["anomalies"]))
    candidate = result["candidate_storyboard"]
    if technical_fixture:
        for shot in candidate["shots"]:
            shot["timing_source"] = "technical_fixture"
    hashes["work/alignment/aligned.json"] = bytes_digest(aligned_data)
    hashes["work/audio/master_48k.wav"] = raw["audio"]["master"]["sha256"]
    return candidate
