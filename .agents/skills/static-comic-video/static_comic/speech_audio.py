"""Same-origin PCM preparation and the local VoiceStudio coarse-ASR boundary."""
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid
import wave

from .contracts import bytes_digest, canonical
from .paths import read_bytes, resolve_path, write_bytes
from .cache import cached, publish, versions
from .media import file_hash


def wav_info(data):
    with wave.open(BytesIO(data), "rb") as audio:
        if audio.getcomptype() != "NONE" or audio.getsampwidth() != 2:
            raise ValueError("Expected uncompressed signed 16-bit PCM")
        return {"sample_rate": audio.getframerate(), "channels": audio.getnchannels(),
                "samples": audio.getnframes(), "sha256": bytes_digest(data)}


def prepare_audio(root, source):
    targets = ["work/audio/master_48k.wav", "work/audio/align_16k.wav"]
    source_path = resolve_path(root, source)
    executable = shutil.which('ffmpeg')
    if not executable:
        raise ValueError('FFmpeg unavailable')
    key = {'source': file_hash(source_path), 'ffmpeg': file_hash(executable),
           'version': versions('static_comic/speech_audio.py'), 'rates': [48000, 16000]}
    def build(temp):
        paths = [temp/Path(name).name for name in targets]
        commands = []
        for src, dst, rate, channels in ((source_path, paths[0], 48000, 2), (paths[0], paths[1], 16000, 1)):
            command = [executable, '-v', 'error', '-nostdin', '-y', '-i', str(src), '-map', '0:a:0',
                       '-vn', '-ar', str(rate), '-ac', str(channels), '-c:a', 'pcm_s16le', str(dst)]
            result = subprocess.run(command, capture_output=True, timeout=180, check=False)
            if result.returncode:
                raise ValueError('Audio decoding failed: ' + result.stderr.decode('utf-8', errors='replace'))
            commands.append(command)
        info = {k: wav_info(p.read_bytes()) for k,p in zip(('master', 'align'), paths)}
        if info['master']['samples'] < 1 or abs(info['align']['samples']*3-info['master']['samples']) > 3:
            raise ValueError('Inconsistent PCM clocks')
        if file_hash(source_path) != key['source']:
            raise ValueError('Audio source changed during preparation')
        info.update(origin_samples=0, commands=commands)
        (temp/'audio.json').write_bytes(canonical(info))
    folder, _ = cached(root, 'audio', key, build)
    info = json.loads((folder/'audio.json').read_bytes())
    publish(root, {**{n: folder/Path(n).name for n in targets}, 'work/audio/audio.json': folder/'audio.json'})
    return info


def service_json(base, endpoint, *, body=None, content_type=None):
    url = urlsplit(base)
    if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1")
            or url.username or url.password or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError("VoiceStudio must be a loopback HTTP service root")
    headers = {"Content-Type": content_type} if content_type else {}
    with urlopen(Request(base.rstrip("/") + endpoint, data=body, headers=headers), timeout=180) as response:
        raw = response.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("Oversized VoiceStudio response")
    value = json.loads(raw)
    if not isinstance(value,dict):
        raise ValueError("VoiceStudio response must be a JSON object")
    return value


def transcribe_service(root, base, lock):
    before = service_json(base, "/engines/asr")
    expected_model = "Systran/faster-whisper-large-v3"
    if before.get("active") != "whisperx" or before.get("active_model") != expected_model:
        raise ValueError("VoiceStudio must already select whisperx / faster-whisper-large-v3; settings were not changed")
    # The active service's configured snapshot must be the caller's locked ASR.
    from scripts.probe_models import verify_model
    asr_path = verify_model(lock["asr"])
    if asr_path.name != lock["asr"]["revision"] or "models--Systran--faster-whisper-large-v3" not in asr_path.parts:
        raise ValueError("Service ASR lock must identify the installed large-v3 snapshot")
    boundary = "sc-" + uuid.uuid4().hex
    chunks = []
    for name, value in (("language", "zh"), ("mode", "reference"), ("refine", "false")):
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="align.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
    chunks.append(read_bytes(root, "work/audio/align_16k.wav", 512 * 1024 * 1024))
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    response = service_json(base, "/transcribe", body=b"".join(chunks),
                            content_type=f"multipart/form-data; boundary={boundary}")
    after = service_json(base, "/engines/asr")
    return {"provider": "voicestudio", "url": base, "mode": "reference", "before": before,
            "after": after, "response": response,
            "backend_matches": response.get("engine") == "whisperx" and
                after.get("active") == before.get("active") and after.get("active_model") == expected_model,
            "timing_source": "coarse_segment", "asr_lock": lock["asr"]}


def transcribe_local(root, lock):
    """Explicit offline coarse ASR; never a silent replacement for the service."""
    import numpy as np
    from faster_whisper import WhisperModel
    from scripts.probe_models import verify_model

    model_path = verify_model(lock["asr"])
    audio = read_bytes(root, "work/audio/align_16k.wav", 512 * 1024 * 1024)
    info = wav_info(audio)
    if info["sample_rate"] != 16000 or info["channels"] != 1:
        raise ValueError("Local ASR requires the prepared 16 kHz mono PCM")
    with wave.open(BytesIO(audio), "rb") as stream:
        samples = np.frombuffer(stream.readframes(info["samples"]), dtype="<i2").astype(np.float32) / 32768
    model = WhisperModel(str(model_path), device="cpu", compute_type="int8", local_files_only=True)
    parameters = {"language": "zh", "beam_size": 5, "condition_on_previous_text": False,
                  "vad_filter": True, "word_timestamps": True, "chunk_length": 30, "temperature": 0.0}
    segments, detected = model.transcribe(samples, **parameters)
    response = {"engine": "faster-whisper", "language": detected.language,
                "duration_s": info["samples"] / 16000, "segments": [
                    {"start": float(s.start), "end": float(s.end), "text": s.text,
                     "words": [{"word": w.word, "start": float(w.start), "end": float(w.end),
                                "probability": float(w.probability)} for w in s.words]} for s in segments]}
    return {"provider": "locked_local_faster_whisper", "mode": "reference", "response": response,
            "backend_matches": True, "timing_source": "coarse_segment", "asr_lock": lock["asr"],
            "audio": info, "device": "cpu", "compute_type": "int8", "parameters": parameters}
