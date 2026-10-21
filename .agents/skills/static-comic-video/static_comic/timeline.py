"""Absolute integer sample clocks and non-overlapping transition budgets."""
from decimal import Decimal
from fractions import Fraction

RATE = 48000
FPS = 30


def total_frames(samples):
    return (samples * FPS + RATE - 1) // RATE


def frame_at(sample):
    return (2 * sample * FPS + RATE) // (2 * RATE)


def seconds_to_samples(raw_seconds, offset=0):
    """Decimal strings only; half-up once, then add an integer global offset."""
    if not isinstance(raw_seconds, str) or type(offset) is not int or offset < 0:
        raise ValueError("Seconds require decimal text and a nonnegative integer sample offset")
    value = Decimal(raw_seconds)
    if not value.is_finite() or value < 0:
        raise ValueError("Invalid seconds")
    fraction = Fraction(value) * RATE
    return (2 * fraction.numerator + fraction.denominator) // (2 * fraction.denominator) + offset


def compile_timing(board):
    shots = board["shots"]
    samples = int(board["audio"]["duration_samples"])
    total = total_frames(samples)
    starts = [int(shot["start_samples"]) for shot in shots]
    if starts[0] != 0 or any(s >= samples for s in starts):
        raise ValueError("First shot must start at sample 0; all starts must precede audio end")
    if any(b <= a for a, b in zip(starts, starts[1:])):
        raise ValueError("Shot sample boundaries must be strictly increasing")
    boundaries = [frame_at(s) for s in starts] + [total]
    lengths = [b - a for a, b in zip(boundaries, boundaries[1:])]
    transitions = []
    for index, shot in enumerate(shots):
        sid = shot["id"]
        if lengths[index] < 1:
            raise ValueError(f"{sid}: logical shot is shorter than one frame")
        lo, hi = shot["speech_interval_samples"]
        if not 0 <= lo < hi <= samples:
            raise ValueError(f"{sid}: invalid speech interval")
        tr = shot["transition_out"]
        if index == len(shots) - 1:
            if tr is not None:
                raise ValueError(f"{sid}: last shot must have null transition")
            transitions.append(None)
            continue
        if tr is None or tr["to_shot_id"] != shots[index + 1]["id"]:
            raise ValueError(f"{sid}: transition must reference the next shot")
        anchor = int(tr["semantic_anchor_samples"])
        if not 0 <= anchor <= samples:
            raise ValueError(f"{sid}: semantic anchor outside audio")
        if anchor != starts[index + 1] and not shots[index + 1]["boundary_reason"].strip():
            raise ValueError(f"{sid}: adjusted boundary requires a reason")
        length = int(tr["duration_frames"])
        if (tr["type"] == "cut") != (length == 0):
            raise ValueError(f"{sid}: cut requires zero frames; effects require positive frames")
        pre = {"start_at_anchor": 0, "end_at_anchor": length,
               "center_on_anchor": length // 2}[tr["placement"]]
        post = length - pre
        boundary = boundaries[index + 1]
        begin, end = boundary - pre, boundary + post
        if begin < 0 or end > total:
            raise ValueError(f"{sid} -> {tr['to_shot_id']}: transition window outside [0,{total})")
        transitions.append({"type": tr["type"], "duration_frames": length,
                            "placement": tr["placement"], "pre_frames": pre, "post_frames": post,
                            "semantic_anchor_samples": anchor, "semantic_anchor_frame": frame_at(anchor),
                            "transition_start_frame": begin, "transition_end_frame": end})
    result = []
    for index, shot in enumerate(shots):
        previous = transitions[index - 1] if index else None
        current = transitions[index]
        incoming = previous["post_frames"] if previous else 0
        outgoing = current["pre_frames"] if current else 0
        if incoming + outgoing >= lengths[index]:
            raise ValueError(f"{shot['id']}: adjacent transition windows leave no non-transition frame")
        head = previous["pre_frames"] if previous else 0
        tail = current["post_frames"] if current else 0
        result.append({"id": shot["id"], "start_frame": boundaries[index], "end_frame": boundaries[index + 1],
                       "sequence_start_frame": boundaries[index] - head, "head_hold_frames": head,
                       "logical_frames": lengths[index], "tail_hold_frames": tail,
                       "physical_frames": head + lengths[index] + tail, "transition_out": current})
    budget = sum(s["physical_frames"] for s in result) - sum(t["duration_frames"] for t in transitions if t)
    if budget != total:
        raise ValueError("Internal transition budget mismatch")
    return total, result
