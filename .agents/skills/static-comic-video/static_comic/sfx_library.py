"""Licensed local effects, decoded once to content-addressed 48 kHz stereo PCM."""
import shutil
import math
from pathlib import Path
import tempfile

import numpy as np

from .cache import cached, lookup, publish, versions
from .contracts import canonical
from .media import file_hash, probe, run
from .paths import resolve_path
from .sfx_mix import pcm, stats

# A compressed audio asset can decompress into gigabytes. Bound the decoded
# amount before spawning FFmpeg, and cap both intermediate PCM outputs.
MAX_SOURCE_PCM_BYTES = 64 * 1024 * 1024
MAX_NORMALIZED_SAMPLES = 120 * 48000
MAX_NORMALIZED_PCM_BYTES = MAX_NORMALIZED_SAMPLES * 2 * 4 + 4096


def normalize_asset(root, asset, *, write=True, technical=False):
    """Validate permission and bytes before normalization, including on cache hits."""
    from .emphasis import verify_asset

    verify_asset(root, asset, kind='sfx', technical=technical)
    source = resolve_path(root, asset['path'])
    executable = shutil.which('ffmpeg')
    if not executable:
        raise ValueError('FFmpeg unavailable')
    key = {'asset': asset, 'ffmpeg': file_hash(executable), 'sample_rate': 48000, 'channels': 2,
           'version': versions('static_comic/sfx_library.py', 'static_comic/sfx_mix.py')}

    def build(temp):
        streams = probe(source)['streams']
        if len(streams) != 1 or streams[0]['codec_type'] != 'audio':
            raise ValueError(f'{asset["asset_id"]}: expected exactly one audio stream')
        stream = streams[0]
        supported = {'pcm_s16le', 'pcm_s24le', 'pcm_s32le', 'pcm_f32le', 'pcm_f64le',
                     'pcm_u8', 'flac', 'mp3', 'vorbis', 'opus', 'aac'}
        if stream['codec_name'] not in supported:
            raise ValueError(f'{asset["asset_id"]}: unsupported audio codec')
        rate, channels = int(stream['sample_rate']), stream['channels']
        if rate != asset['sample_rate'] or channels != asset['channels']:
            raise ValueError(f'{asset["asset_id"]}: source format differs from manifest')
        claimed_samples = asset['duration_samples']
        source_bytes = claimed_samples * channels * 4
        estimated_output = math.ceil(claimed_samples * 48000 / rate) + 8192
        if (claimed_samples <= 0 or source_bytes > MAX_SOURCE_PCM_BYTES
                or estimated_output > MAX_NORMALIZED_SAMPLES
                or estimated_output * 2 * 4 > MAX_NORMALIZED_PCM_BYTES):
            raise ValueError(f'{asset["asset_id"]}: SFX decoded PCM exceeds the bounded budget')
        declared_duration = stream.get('duration') or probe(source)['format'].get('duration')
        if declared_duration is not None and abs(float(declared_duration) - claimed_samples/rate) > .25:
            raise ValueError(f'{asset["asset_id"]}: audio duration differs from declared samples')
        original_float = temp/'original.f32'
        decode = [executable, '-v', 'error', '-xerror', '-nostdin', '-y', '-i', source, '-map', '0:a:0',
                  '-vn', '-c:a', 'pcm_f32le', '-fs', str(MAX_SOURCE_PCM_BYTES),
                  '-f', 'f32le', original_float]
        run(decode)
        byte_count = original_float.stat().st_size
        if (byte_count != source_bytes or byte_count > MAX_SOURCE_PCM_BYTES):
            raise ValueError(f'{asset["asset_id"]}: manifest duration differs from decoded samples or exceeds budget')
        original = np.frombuffer(original_float.read_bytes(), dtype='<f4')
        if (not np.isfinite(original).all() or float(np.max(np.abs(original))) >= 1):
            raise ValueError(f'{asset["asset_id"]}: invalid source samples (non-finite or clipped)')
        normalized_float = temp/'normalized.f32'
        convert = [executable, '-v', 'error', '-xerror', '-nostdin', '-y', '-i', source, '-map', '0:a:0',
                   '-vn', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_f32le',
                   '-fs', str(MAX_NORMALIZED_PCM_BYTES), '-f', 'f32le', normalized_float]
        run(convert)
        target_bytes = normalized_float.stat().st_size
        if (target_bytes > MAX_NORMALIZED_PCM_BYTES or target_bytes % 8 or target_bytes == 0):
            raise ValueError(f'{asset["asset_id"]}: normalized decoded samples exceed budget')
        values = np.frombuffer(normalized_float.read_bytes(), dtype='<f4').reshape(-1, 2)
        if len(values) > MAX_NORMALIZED_SAMPLES:
            raise ValueError(f'{asset["asset_id"]}: normalized audio duration exceeds budget')
        measurement = stats(values)
        if measurement['peak'] >= 1:
            raise ValueError(f'{asset["asset_id"]}: resampled source exceeds PCM range')
        target = temp/'normalized.wav'
        encode = [executable, '-v', 'error', '-nostdin', '-y', '-f', 'f32le', '-ar', '48000', '-ac', '2',
                  '-i', normalized_float, '-c:a', 'pcm_s16le', target]
        run(encode)
        if target.stat().st_size > MAX_NORMALIZED_SAMPLES*2*2+4096:
            raise ValueError(f'{asset["asset_id"]}: normalized WAV exceeds budget')
        output = pcm(target)
        sha = file_hash(target)
        if file_hash(source) != asset['sha256']:
            raise ValueError('Sound source changed during normalization')
        source_samples = len(original)//channels
        del original, values
        original_float.unlink()
        normalized_float.unlink()
        report = {**stats(output), 'asset_id': asset['asset_id'], 'asset_sha256': asset['sha256'],
                  'normalized_path': f'work/audio/sfx/{sha}.wav', 'normalized_sha256': sha,
                  'codec': 'pcm_s16le', 'source_codec': stream['codec_name'],
                  'source_sample_rate': rate, 'source_channels': channels,
                  'source_samples': source_samples,
                  'resample_error_samples': len(output)-source_samples*48000/rate,
                  'authorization': asset, 'inputs': key,
                  'commands': [[str(v) for v in c] for c in (decode, convert, encode)]}
        (temp/'normalization.json').write_bytes(canonical(report))
        return report

    if write:
        folder, result = cached(root, 'sfx-normalize', key, build)
        publish(root, {result['normalized_path']: folder/'normalized.wav',
                       result['normalized_path']+'.json': folder/'normalization.json'})
    else:
        _, record, _ = lookup(root, 'sfx-normalize', key)
        if record is None:
            with tempfile.TemporaryDirectory(prefix='sc-sfx-validate-') as directory:
                return build(Path(directory))
        result = record['result']
        published = resolve_path(root, result['normalized_path'])
        if published.exists() and file_hash(published) != result['normalized_sha256']:
            raise ValueError('Published normalized SFX hash mismatch')
    return result
