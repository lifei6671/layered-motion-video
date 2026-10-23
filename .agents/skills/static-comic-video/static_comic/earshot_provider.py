"""SC-A1：Earshot 离线代码音效供应端。

本模块只负责调用锁定版本的纯 DSP bank，将音效生成到指定单期的资源候选。
不得代替人工试听与签署、不得重写主旁白母带、不得加载 CLAP/AST/联网模型。
"""
from io import BytesIO
from pathlib import Path
import argparse
from html import escape
import json
import re
import subprocess
import sys
import wave

import numpy as np

from .cache import publish
from .contracts import bytes_digest, canonical, digest, read_json, validate
from .paths import read_bytes, resolve_path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/earshot-runtime/source"
SOURCE_COMMIT = "591fa3e028032e6dce56620a20e932e35667e8d8"
BANK_VERSION = "forge_v2r6+forge04r1+fit1+pluck1"
SAMPLE_RATE = 48000
MAX_SECONDS = 12
MAX_BYTES = MAX_SECONDS * SAMPLE_RATE * 2 * 2 + 44
# 上游 252 音效中所有纯 DSP 及音符生成类别均可手动挑选；15 个
# 基于 CC0 录音拟合的 fit/* 暂未开放，须单独保留逐录音来源证据。
# 自动推荐仍只选少数适合漫画的 ui_pop / swish / cut_hit，避免音效滥用。
ALLOWED_CATEGORIES = frozenset((
    "click", "pro_click", "hover_tick", "pro_hover_tick", "tap", "pro_tap",
    "toggle", "pop", "pro_pop", "pro_pop_in", "notify", "pro_notify",
    "shimmer", "pro_shimmer", "whoosh_fast", "whoosh_big", "pro_whoosh_big",
    "swish", "swipe", "riser", "pro_riser", "downlifter", "pro_zip",
    "impact", "pro_impact", "sub_drop", "pro_sub_drop", "logo_sting",
    "pro_logo_sting", "glitch", "pro_glitch", "typing_key", "pro_typing_key",
    "pro_typing_run", "pluck", "cut_hit", "reverse_swell", "ui_pop",
    "knock", "mallet", "drip", "shutter",
))
ALLOWED_USES = frozenset(("keyword", "scene", "transition", "narrative"))
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*/[a-z0-9_-]+$")


def local_runtime():
    """只允许本仓库 reports/ 下被锁版本的独立运行时，不执行外部输入路径。"""
    base = SOURCE.resolve()
    if not base.is_relative_to(ROOT.resolve()) or not (base / "earshot/forge/bank.py").is_file():
        raise ValueError("EARSHOT_UNAVAILABLE: install pinned source in reports/earshot-runtime/source")
    def git(*argv):
        try:
            result = subprocess.run(["git", "-C", str(base), *argv], capture_output=True,
                                    text=True, check=True, timeout=12)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError("EARSHOT_UNAVAILABLE: cannot validate pinned source") from error
        return result.stdout.strip()
    if git("rev-parse", "HEAD") != SOURCE_COMMIT:
        raise ValueError("EARSHOT_VERSION_MISMATCH: source revision differs from verified commit")
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("EARSHOT_DIRTY_SOURCE: refusing modified or unknown upstream files")
    return base


def load_bank():
    runtime = local_runtime()
    if str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))
    from earshot.forge import bank  # 只用 numpy/scipy DSP，刻意不引用 AI 听音模块。
    if bank.VERSION != BANK_VERSION:
        raise ValueError("EARSHOT_VERSION_MISMATCH: sound bank version differs from lock")
    return bank


def sound_catalog(bank):
    return sorted(
        ({"id": item["id"], "category": item["id"].split("/")[0],
          "duration_s": item.get("dur_s"), "peak_s": item.get("peak_s")}
         for item in bank.list() if item["id"].split("/")[0] in ALLOWED_CATEGORIES),
        key=lambda item: item["id"])


def wav_bytes(values):
    arr = np.asarray(values)
    if arr.ndim == 1:
        arr = np.column_stack((arr, arr))
    if arr.ndim != 2 or arr.shape[1] not in (1, 2):
        raise ValueError("EARSHOT_AUDIO_INVALID: only mono/stereo audio can be imported")
    if arr.shape[1] == 1:
        arr = np.repeat(arr, 2, axis=1)
    if not 0 < len(arr) <= MAX_SECONDS * SAMPLE_RATE or not np.isfinite(arr).all():
        raise ValueError("EARSHOT_AUDIO_BUDGET: invalid samples/duration")
    if np.max(np.abs(arr)) >= 1:
        raise ValueError("EARSHOT_AUDIO_CLIPPED: audio sample exceeds PCM budget")
    pcm = np.rint(arr.astype(np.float64) * 32767).astype("<i2")
    stream = BytesIO()
    with wave.open(stream, "wb") as output:
        output.setframerate(SAMPLE_RATE)
        output.setnchannels(2)
        output.setsampwidth(2)
        output.writeframes(pcm.tobytes())
    data = stream.getvalue()
    if len(data) > MAX_BYTES:
        raise ValueError("EARSHOT_AUDIO_BUDGET: rendered WAV exceeds maximum bytes")
    return data, len(arr)


def render(root, sound_id, *, uses, seed=None, duration_s=None, apex_s=None,
           pitch=None, technical_fixture=False):
    """输出音效文件、许可附件、严格资源清单；默认仅 CANDIDATE。"""
    root = Path(root).resolve(strict=True)
    if (not IDENTIFIER.fullmatch(sound_id)
            or sound_id.split("/")[0] not in ALLOWED_CATEGORIES):
        raise ValueError("EARSHOT_ID_UNSUPPORTED: use an approved category and bank ID")
    uses = sorted(set(uses))
    if not uses or any(kind not in ALLOWED_USES for kind in uses):
        raise ValueError("EARSHOT_USES_INVALID: at least one known SFX use is required")
    if seed is not None and not 0 <= seed <= 2**31-1:
        raise ValueError("EARSHOT_SEED_INVALID")
    if duration_s is not None and not 0.04 <= duration_s <= MAX_SECONDS:
        raise ValueError("EARSHOT_DURATION_BUDGET")
    if apex_s is not None and (duration_s is None or not 0 <= apex_s <= duration_s):
        raise ValueError("EARSHOT_APEX_BOUNDS: apex requires a valid duration")
    if pitch is not None and (not isinstance(pitch, str) or
                              not re.fullmatch(r"[A-Ga-g](?:#|b|s)?[0-8]", pitch)):
        raise ValueError("EARSHOT_PITCH_INVALID")
    bank = load_bank()
    if sound_id not in {item["id"] for item in bank.list()}:
        raise ValueError("EARSHOT_UNKNOWN_BANK_SOUND")
    kwargs = {"sr": SAMPLE_RATE, "peak_db": -8.0}
    if seed is not None:
        kwargs["seed"] = seed
    if duration_s is not None:
        kwargs["dur"] = duration_s
    if apex_s is not None:
        kwargs["apex"] = apex_s
    if pitch is not None:
        kwargs["pitch"] = pitch
    try:
        values, meta = bank.render(sound_id, **kwargs)
    except (TypeError, ValueError) as error:
        raise ValueError(f"EARSHOT_RENDER_REJECTED: {error}") from error
    if not meta.get("checks", {}).get("ok", False):
        raise ValueError("EARSHOT_SOUND_AUDIT_FAILED: generated take failed model-free checks")
    data, length = wav_bytes(values)
    cue_points = {
        "onset_samples": min(length-1, max(0, round(float(meta["onset_s"])*SAMPLE_RATE))),
        "peak_samples": min(length-1, max(0, round(float(meta["peak_s"])*SAMPLE_RATE))),
        "end_samples": min(length-1, max(0, round(float(meta["end_s"])*SAMPLE_RATE))),
    }
    if not cue_points["onset_samples"] <= cue_points["peak_samples"] <= cue_points["end_samples"]:
        raise ValueError("EARSHOT_SYNC_INVALID: actual signal cue points are out of order")
    opts = {"bank_id": sound_id, "bank_version": bank.VERSION, "commit": SOURCE_COMMIT,
            "seed": seed, "duration_s": duration_s, "apex_s": apex_s, "pitch": pitch,
            "sample_rate": SAMPLE_RATE, "uses": uses, "peak_db": -8.0}
    identifier = "earshot-" + digest(opts)[:22]
    output_path = f"assets/sfx/{identifier}.wav"
    legal_path = "assets/sfx/licenses/earshot-MIT.txt"
    license_data = (local_runtime() / "LICENSE").read_bytes()
    if b"Copyright (c) 2026 Leon Lin" not in license_data:
        raise ValueError("EARSHOT_LICENSE_INVALID: expected source license was not found")
    legal = resolve_path(root, legal_path)
    if legal.exists() and legal.read_bytes() != license_data:
        raise ValueError("EARSHOT_LICENSE_CONFLICT: local license evidence changed")
    manifest_name = "assets/sfx/manifest.json"
    manifest_path = resolve_path(root, manifest_name)
    manifest = validate("sfxManifest", read_json(read_bytes(root, manifest_name, 4*1024*1024))) \
        if manifest_path.exists() else {"schema_version": "1.0", "assets": []}
    asset = {
        "asset_id": identifier, "path": output_path, "sha256": bytes_digest(data),
        "source_kind": "local_created",
        "source_uri": f"https://github.com/Leonxlnx/earshot/tree/{SOURCE_COMMIT}",
        "author": "Leon Lin / Earshot procedural sound bank",
        "license": "MIT", "usage_scope": "Local video SFX; no production use without human review",
        "license_evidence": {"path": legal_path, "sha256": bytes_digest(license_data)},
        "review_status": "TECHNICAL_ONLY" if technical_fixture else "CANDIDATE",
        "sample_rate": SAMPLE_RATE, "channels": 2, "duration_samples": length, "tags": uses,
        "generator": {"provider": "earshot", "bank_id": sound_id,
                      "bank_version": bank.VERSION, "source_commit": SOURCE_COMMIT,
                      "options_sha256": digest(opts)},
        "cue_points": cue_points,
    }
    found = [item for item in manifest["assets"] if item["asset_id"] == identifier]
    if found and (len(found) != 1 or
                  {k: v for k, v in found[0].items() if k != "review_status"} !=
                  {k: v for k, v in asset.items() if k != "review_status"}):
        raise ValueError("EARSHOT_ASSET_CONFLICT: existing ID has different bytes or metadata")
    existing = resolve_path(root, output_path)
    if existing.exists() and existing.read_bytes() != data:
        raise ValueError("EARSHOT_ASSET_CONFLICT: existing WAV was changed")
    outputs = {}
    if not existing.exists():
        outputs[output_path] = data
    if not legal.exists():
        outputs[legal_path] = license_data
    if not found:
        manifest["assets"].append(asset)
        manifest["assets"].sort(key=lambda entry: entry["asset_id"])
        outputs[manifest_name] = canonical(validate("sfxManifest", manifest))+b"\n"
    provenance = {"schema_version": "1.0", "generator": asset["generator"],
                  "asset_sha256": asset["sha256"], "license_sha256": asset["license_evidence"]["sha256"],
                  "cue_points": cue_points, "samples": length, "options": opts,
                  "audit_clean": True, "technical_fixture": technical_fixture}
    outputs[f"reports/earshot/{identifier}.json"] = canonical(provenance)+b"\n"
    if outputs:
        publish(root, outputs)
    status = found[0]["review_status"] if found else asset["review_status"]
    return {"status": status,
            "asset_id": identifier, "asset_path": output_path, "sha256": asset["sha256"],
            "cue_points": cue_points, "duration_samples": length,
            "manifest": manifest_name, "uses": uses,
            "requires_human_review": status != "TECHNICAL_ONLY", "source_commit": SOURCE_COMMIT}


def audition(root):
    """生成无脚本、可直接在本机浏览器试听的 HTML；不等价于批准。"""
    root = Path(root).resolve(strict=True)
    source = resolve_path(root, "assets/sfx/manifest.json")
    if not source.exists():
        raise ValueError("EARSHOT_LIBRARY_EMPTY: no sound candidates have been generated")
    manifest = validate("sfxManifest", read_json(read_bytes(root, "assets/sfx/manifest.json", 4*1024*1024)))
    assets = [item for item in manifest["assets"]
              if item.get("generator",{}).get("provider")=="earshot"]
    if not assets:
        raise ValueError("EARSHOT_LIBRARY_EMPTY: no sound candidates have been generated")
    rows=[]
    for asset in sorted(assets, key=lambda item:item["asset_id"]):
        if not re.fullmatch(r"assets/sfx/earshot-[a-f0-9]{22}\.wav", asset["path"]):
            raise ValueError("EARSHOT_AUDITION_PATH: unexpected generated asset path")
        # 清单可能已由用户修改；试听仍须验证当前 WAV 字节。
        data = read_bytes(root,asset["path"],MAX_BYTES)
        if bytes_digest(data)!=asset["sha256"]:
            raise ValueError("EARSHOT_AUDITION_HASH: generated file changed")
        title=escape(asset["generator"]["bank_id"])
        asset_id=escape(asset["asset_id"])
        uri="../../"+escape(asset["path"],quote=True)
        status=escape(asset["review_status"])
        duration=f"{asset['duration_samples']/SAMPLE_RATE:.3f}"
        rows.append(f'<article><h2>{title}</h2><p>{asset_id} · {duration}s · {status}</p>'
                    f'<audio controls preload="none" src="{uri}"></audio>'
                    f'<small>许可来源：MIT · 原始资源 SHA256：{escape(asset["sha256"])}</small></article>')
    html=('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
          '<meta name="viewport" content="width=device-width, initial-scale=1">'
          '<title>Earshot 本地音效候选试听</title>'
          '<style>body{font:16px system-ui,sans-serif;max-width:850px;margin:40px auto;'
          'background:#fcfbf8;color:#272727;padding:0 16px}article{background:white;'
          'border:1px solid #ddd;border-radius:12px;padding:18px;margin:16px 0}'
          'h2{font-size:20px}p,small{color:#666}audio{display:block;width:100%;margin:12px 0}'
          'small{overflow-wrap:anywhere}</style><h1>Earshot 音效候选试听</h1>'
          '<p>试听不是批准。进入正式视频前必须使用原有人工资源收据。</p>'
          +''.join(rows)+'</html>')
    output="reports/earshot/audition.html"
    publish(root,{output:html.encode("utf-8")})
    return {"status":"AUDITION_READY","path":output,"count":len(rows),
            "human_resource_approval":"NOT_RUN"}


def main(argv):
    parser = argparse.ArgumentParser(description="Pinned offline Earshot sound bank supplier (no AI models)")
    parser.add_argument("command", choices=("doctor", "list", "render", "propose-cues", "audition"))
    parser.add_argument("--project")
    parser.add_argument("--sound")
    parser.add_argument("--uses", nargs="+", default=["keyword"], choices=sorted(ALLOWED_USES))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--apex", type=float)
    parser.add_argument("--pitch")
    parser.add_argument("--technical-fixture", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        bank = load_bank()
        return {"status": "PASS", "bank_version": bank.VERSION, "source_commit": SOURCE_COMMIT,
                "available": len(bank.list()), "supported": len(sound_catalog(bank)),
                "fit_deferred": True, "models_used": False}
    if args.command == "list":
        return {"status": "PASS", "bank": BANK_VERSION, "sounds": sound_catalog(load_bank())}
    if args.command == "audition":
        if not args.project:
            raise ValueError("Earshot audition requires --project")
        return audition(args.project)
    if args.command == "propose-cues":
        if not args.project:
            raise ValueError("Earshot propose-cues requires --project")
        from .earshot_cues import propose_card_sounds
        from .project import compile_project
        compiled = compile_project(args.project, technical_fixture=args.technical_fixture, write=False)
        return propose_card_sounds(args.project, compiled, technical=args.technical_fixture)
    if not args.project or not args.sound:
        raise ValueError("Earshot render requires --project and --sound")
    return render(args.project, args.sound, uses=args.uses, seed=args.seed,
                  duration_s=args.duration, apex_s=args.apex, pitch=args.pitch,
                  technical_fixture=args.technical_fixture)
