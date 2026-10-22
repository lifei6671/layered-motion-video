"""Ordered, reversible source/reading matching; no character-rate timing guesses."""
from difflib import SequenceMatcher
import re
import unicodedata

from .contracts import digest, validate
from .timeline import seconds_to_samples


def chinese_number(value):
    if "." in value:
        whole, fraction = value.split(".")
        return chinese_number(whole) + "点" + "".join("零一二三四五六七八九"[int(x)] for x in fraction)
    if len(value) > 4 or (len(value) > 1 and value[0] == "0"):
        return "".join("零一二三四五六七八九"[int(x)] for x in value)
    number = int(value)
    if number == 0:
        return "零"
    result, zero = "", False
    for power in (3, 2, 1, 0):
        digit, number = divmod(number, 10 ** power)
        if digit:
            if zero:
                result += "零"
            result += "零一二三四五六七八九"[digit] + ("", "十", "百", "千")[power]
            zero = False
        elif result and number:
            zero = True
    return result[1:] if result.startswith("一十") else result


def normalize(text, offset=0):
    """Each spoken codepoint retains a many-to-many source interval."""
    chars, ranges = [], []
    pattern = r"[0-9０-９]+(?:[.．][0-9０-９]+)?[%％]?|[A-Za-z]+|."
    for token in re.finditer(pattern, text, re.DOTALL):
        raw = unicodedata.normalize("NFKC", token.group())
        if re.fullmatch(r"\d+(?:\.\d+)?%?", raw):
            spoken = ("百分之" + chinese_number(raw[:-1])) if raw.endswith("%") else chinese_number(raw)
        elif raw in ("kg", "km", "cm", "mm"):
            spoken = {"kg": "千克", "km": "千米", "cm": "厘米", "mm": "毫米"}[raw]
        else:
            spoken = "".join(c.lower() for c in raw if unicodedata.category(c)[0] in ("L", "N"))
        chars.extend(spoken)
        ranges.extend([[offset + token.start(), offset + token.end()]] * len(spoken))
    return "".join(chars), ranges


def check_overrides(overrides, board, script, hashes, samples):
    from .project import check_human_metadata as check_human
    if overrides is None:
        return []
    validate("overrides", overrides)
    for key, path in (("script_sha256", "input/script.txt"), ("audio_sha256", board["audio"]["source"]),
                      ("storyboard_sha256", "input/storyboard.json")):
        if overrides[key] != hashes[path]:
            raise ValueError(f"Stale overrides: {key}")
    ranges = {"reading": [], "window": []}
    pairs = list(zip([s["id"] for s in board["shots"]], [s["id"] for s in board["shots"]][1:]))
    boundaries = set()
    corrections = set()
    for entry in overrides["entries"]:
        check_human(entry["human"])
        if not entry["reason"].strip():
            raise ValueError("Override reason cannot be blank")
        kind = entry["kind"]
        if kind == "asr_correction":
            lo, hi = entry["script_range"]
            key = (lo, hi, entry["expected"], entry["recognized"])
            if (not 0 <= lo <= hi <= len(script) or key in corrections
                    or entry["expected"] == entry["recognized"]
                    or any(lo < s["script_range"][0] < hi for s in board["shots"])):
                raise ValueError("Conflicting or invalid ASR correction")
            corrections.add(key)
            continue
        if kind == "boundary":
            pair = (entry["from_shot_id"], entry["to_shot_id"])
            if pair not in pairs or pair in boundaries or not 0 < entry["sample"] < samples:
                raise ValueError("Conflicting, unknown or out-of-range boundary override")
            boundaries.add(pair)
            continue
        lo, hi = entry["script_range"]
        if not 0 <= lo < hi <= len(script) or any(lo < b and a < hi for a, b in ranges[kind]):
            raise ValueError(f"Conflicting or invalid {kind} override range")
        if any(lo < s["script_range"][0] < hi for s in board["shots"]):
            raise ValueError("Override range cannot cross a shot boundary")
        ranges[kind].append((lo, hi))
        if kind == "reading" and not normalize(entry["reading"])[0]:
            raise ValueError("Empty spoken reading")
        if kind == "window" and not 0 <= entry["samples"][0] < entry["samples"][1] <= samples:
            raise ValueError("Window override outside master audio")
    windows = sorted((e for e in overrides["entries"] if e["kind"] == "window"), key=lambda e:e["script_range"])
    if any(a["samples"][1] > b["samples"][0] for a, b in zip(windows, windows[1:])):
        raise ValueError("Window overrides overlap or reverse audio order")
    return overrides["entries"]


def reading_map(script, entries):
    edits = sorted((e for e in entries if e["kind"] == "reading"), key=lambda e:e["script_range"])
    text, ranges, origins, cursor = "", [], [], 0
    for entry in edits + [None]:
        lo = entry["script_range"][0] if entry else len(script)
        part, mapping = normalize(script[cursor:lo], cursor)
        text += part; ranges.extend(mapping); origins.extend(["normalized"] * len(part))
        if entry:
            part = normalize(entry["reading"])[0]
            text += part; ranges.extend([entry["script_range"]] * len(part)); origins.extend(["manual_reading"] * len(part))
            cursor = entry["script_range"][1]
    return {"text": text, "source_ranges": ranges, "origins": origins}


def make_plan(script, board, coarse, entries, samples):
    reading = reading_map(script, entries)
    text, mapping = reading["text"], reading["source_ranges"]
    segments, asr, asr_ranges = [], "", []
    previous = 0
    raw_segments = coarse["response"].get("segments")
    if not isinstance(raw_segments,list):
        raise ValueError("ASR response requires a segment array")
    for raw in raw_segments:
        if not isinstance(raw,dict) or any(type(raw.get(k)) not in (int,float) for k in ("start","end")):
            raise ValueError("ASR segment requires numeric start/end")
        if not isinstance(raw.get("text"), str):
            raise ValueError("ASR segment text must be a string")
        start, end = seconds_to_samples(str(raw["start"])), seconds_to_samples(str(raw["end"]))
        valid = previous <= start < end <= samples
        previous = max(previous,end)
        part = normalize(raw["text"])[0]
        segments.append({"reading_range": [len(asr), len(asr) + len(part)], "samples": [start, end], "raw": raw, "valid_time":valid})
        asr += part; asr_ranges.extend([[start, end]] * len(part))
    matcher = SequenceMatcher(None, text, asr, autojunk=False)
    opcodes = matcher.get_opcodes()
    equal = {j + n:i + n for tag, i, stop, j, end in opcodes if tag == "equal" for n in range(stop-i)}
    anomalies = []
    def issue(kind, lo, hi, audio, detail):
        if lo < hi:
            source_range = [mapping[lo][0], mapping[hi-1][1]]
        else:
            point = mapping[lo][0] if lo < len(mapping) else len(script)
            source_range = [point, point]
        ids = [s["id"] for s in board["shots"] if
               (s["script_range"][0] < source_range[1] and source_range[0] < s["script_range"][1]) or
               (source_range[0] == source_range[1] and s["script_range"][0] <= source_range[0] < s["script_range"][1])]
        anomalies.append({"kind": kind, "script_range": source_range, "samples": audio,
                          "shot_ids": ids or [board["shots"][-1]["id"]], "detail": detail})
    for tag, lo, hi, a, b in opcodes:
        if tag != "equal":
            interval = [asr_ranges[a][0], asr_ranges[b-1][1]] if a < b else (
                asr_ranges[min(a, len(asr_ranges)-1)] if asr_ranges else [0, samples])
            issue({"delete":"missing_or_truncated", "insert":"extra_speech", "replace":"content_mismatch"}[tag],
                  lo, hi, interval, {"expected":text[lo:hi], "recognized":asr[a:b]})
    if not coarse.get("backend_matches"):
        issue("backend_changed", 0, len(text), [0, samples], "VoiceStudio returned an unexpected engine/model")
    windows = []
    for segment in segments:
        a, b = segment["reading_range"]
        matched = [equal.get(i) for i in range(a,b)]
        if not segment["valid_time"]:
            located = [i for i in matched if i is not None]
            issue("invalid_asr_window", min(located) if located else 0, max(located)+1 if located else len(text),
                  segment["samples"], "ASR window overlaps, reverses or exceeds audio; possible truncation, never clamp into a trusted window")
            continue
        if matched and all(i is not None for i in matched) and matched == list(range(matched[0],matched[0]+len(matched))):
            windows.append({"reading_range":[matched[0], matched[-1]+1], "samples":segment["samples"], "source":"coarse_segment"})
    for entry in (e for e in entries if e["kind"] == "window"):
        lo, hi = entry["script_range"]
        indices = [i for i,(a,b) in enumerate(mapping) if a >= lo and b <= hi]
        if not indices or any(a < hi and lo < b and not (a >= lo and b <= hi) for a,b in mapping):
            raise ValueError("Window splits a normalized/confirmed reading token")
        a,b = indices[0],indices[-1]+1
        windows = [w for w in windows if not (w["reading_range"][0] < b and a < w["reading_range"][1])]
        windows.append({"reading_range":[a,b],"samples":entry["samples"],"source":"manual_window"})
    windows.sort(key=lambda w:w["reading_range"])
    if any(a["samples"][1] > b["samples"][0] for a,b in zip(windows,windows[1:])):
        raise ValueError("Trusted windows overlap or reverse audio order")
    for window in windows:
        lo,hi = window["reading_range"]
        window["text"] = text[lo:hi]
        # Wav2vec windows are cut on the 16 kHz grid; record the actual origin once.
        window["input_16k"] = [window["samples"][0] // 3, (window["samples"][1]+2) // 3]
        window["origin_samples"] = window["input_16k"][0] * 3
        if window["samples"][1] - window["samples"][0] > 30 * 48000:
            issue("window_too_long",lo,hi,window["samples"],"Confirm windows of at most 30 seconds")
    resolved = []
    for anomaly in list(anomalies):
        if anomaly["kind"] != "invalid_asr_window":
            continue
        lo,hi = anomaly["script_range"]
        confirmations = sorted((e for e in entries if e["kind"] == "window"),key=lambda e:e["script_range"])
        cursor = lo
        used = []
        for entry in confirmations:
            a,b = entry["script_range"]
            if a <= cursor < b:
                cursor = b; used.append(entry)
        if cursor >= hi:
            resolved.append({"anomaly":anomaly,"confirmations":used})
            anomalies.remove(anomaly)
    corrected = []
    for entry in (e for e in entries if e["kind"] == "asr_correction"):
        if entry["coarse_sha256"] != digest(coarse):
            raise ValueError("ASR correction targets stale coarse evidence")
        matches = [a for a in anomalies if a["kind"] in
                   ("content_mismatch", "extra_speech", "missing_or_truncated")
                   and a["script_range"] == entry["script_range"]
                   and a["detail"] == {"expected":entry["expected"], "recognized":entry["recognized"]}]
        if len(matches) != 1:
            raise ValueError("ASR correction must match one exact current content anomaly")
        corrected.append({"anomaly":matches[0], "confirmation":entry})
        anomalies.remove(matches[0])
    result = {"reading":reading, "asr_normalized":asr, "ordered_opcodes":opcodes,
            "matching_ratio":matcher.ratio(), "windows":windows, "anomalies":anomalies,
            "resolved_timing_anomalies":resolved}
    if corrected:
        result["resolved_asr_anomalies"] = corrected
    return result
