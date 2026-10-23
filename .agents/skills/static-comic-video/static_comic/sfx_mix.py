"""Sample-addressed effects stem and full narration mix; never edits narration."""
from io import BytesIO
from pathlib import Path
import math
import shutil
import wave

import numpy as np

from .cache import cached, lookup, publish, versions
from .contracts import canonical
from .media import file_hash, run
from .paths import resolve_path


def pcm(path):
    with wave.open(BytesIO(Path(path).read_bytes()), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getcomptype()) != (48000, 2, 2, 'NONE'):
            raise ValueError('Expected 48 kHz stereo PCM s16le')
        samples = audio.getnframes()
        data = np.frombuffer(audio.readframes(samples), dtype='<i2').reshape(-1, 2)
    if len(data) != samples or not samples:
        raise ValueError('Empty or truncated PCM')
    return data.astype(np.float64) / 32768


def stats(data):
    if not data.size or not np.isfinite(data).all():
        raise ValueError('Empty or non-finite audio')
    peak = float(np.abs(data).max())
    rms = float(np.sqrt(np.mean(np.square(data, dtype=np.float64))))
    return {'samples': len(data), 'sample_rate': 48000, 'channels': 2,
            'peak': peak, 'peak_dbfs': 20*math.log10(peak) if peak else None,
            'rms_dbfs': 20*math.log10(rms) if rms else None,
            'clipped_samples': int(np.count_nonzero(np.abs(data) >= 1))}


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def number(value, name, lower, upper):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{name} must be finite in [{lower}, {upper}]')
    return value


def mix(root, events, policy, *, write=True):
    """Consume locked events, with normalized_path/hash; policy is its audio section.

    write=False validates a verified cache without creating or publishing artifacts.
    Missing caches fail explicitly. No effects retain the original delivery path.
    """
    master_name = 'work/audio/master_48k.wav'
    master = resolve_path(root, master_name)
    master_hash = file_hash(master)
    narration = pcm(master)
    samples = len(narration)
    if not events:
        return {'status': 'BYPASS', 'master_path': master_name, 'mix_path': master_name,
                'master_sha256': master_hash, 'mix_sha256': master_hash,
                'samples': samples, 'events': [], 'narration': stats(narration)}
    maximum = integer(policy.get('max_concurrent', 2), 'max_concurrent', 1)
    ceiling = number(policy.get('peak_ceiling_dbfs', -1), 'peak_ceiling_dbfs', -60, 0)
    stem_ceiling = number(policy.get('sfx_peak_ceiling_dbfs', -6), 'sfx_peak_ceiling_dbfs', -60, 0)
    if policy.get('sample_rate', 48000) != 48000 or policy.get('channels', 2) != 2:
        raise ValueError('Mix clock must be 48 kHz stereo')
    executable = shutil.which('ffmpeg')
    if not executable:
        raise ValueError('FFmpeg unavailable')
    paths, boundaries, ids = [], [], set()
    for event in events:
        label = event['id']
        if not isinstance(label, str) or not label or label in ids:
            raise ValueError('Duplicate or invalid sound event id')
        ids.add(label)
        if event['kind'] not in ('keyword', 'scene', 'transition', 'narrative'):
            raise ValueError(f'{label}: unsupported sound kind')
        start = integer(event['start_sample'], f'{label}/start_sample')
        trim = integer(event['source_trim_samples'], f'{label}/source_trim_samples')
        length = integer(event['play_samples'], f'{label}/play_samples', 1)
        fade_in = integer(event['fade_in_samples'], f'{label}/fade_in_samples')
        fade_out = integer(event['fade_out_samples'], f'{label}/fade_out_samples')
        number(event['gain_db'], f'{label}/gain_db', -96, 12)
        if start + length > samples or fade_in + fade_out > length:
            raise ValueError(f'{label}: event/fades exceed mother samples or event length')
        name = event['normalized_path']
        if not name.startswith('work/audio/sfx/') or not name.endswith('.wav'):
            raise ValueError(f'{label}: invalid normalized asset path')
        path = resolve_path(root, name)
        if file_hash(path) != event['normalized_sha256']:
            raise ValueError(f'{label}: normalized asset hash mismatch')
        if trim + length > len(pcm(path)):
            raise ValueError(f'{label}: source trim exceeds normalized asset')
        paths.append(path)
        boundaries.extend(((start, 1), (start + length, -1)))
    concurrent = peak_concurrent = 0
    for _, delta in sorted(boundaries):
        concurrent += delta
        peak_concurrent = max(peak_concurrent, concurrent)
    if peak_concurrent > maximum:
        raise ValueError('SFX concurrent budget exceeded')
    key = {'master': master_hash, 'events': events, 'policy': policy,
           'ffmpeg': file_hash(executable), 'version': versions('static_comic/sfx_mix.py')}

    def build(temp):
        filters, labels = [], []
        for i, event in enumerate(events):
            length, trim = event['play_samples'], event['source_trim_samples']
            chain = (f'[{i}:a:0]atrim=start_sample={trim}:end_sample={trim+length},'
                     f'asetpts=PTS-STARTPTS,volume={event["gain_db"]}dB:precision=double')
            for direction, start, count in (('in', 0, event['fade_in_samples']),
                                            ('out', length-event['fade_out_samples'], event['fade_out_samples'])):
                if count:
                    chain += f',afade=t={direction}:ss={start}:ns={count}'
            chain += f',adelay={event["start_sample"]}S:all=1,apad=whole_len={samples}[e{i}]'
            filters.append(chain); labels.append(f'[e{i}]')
        filters.append(''.join(labels) + f'amix=inputs={len(events)}:duration=first:normalize=0,atrim=end_sample={samples}[stem]')
        stem_float = temp/'stem.f32'
        command = [executable, '-v', 'error', '-xerror', '-nostdin', '-y']
        for path in paths:
            command += ['-i', path]
        command += ['-filter_complex', ';'.join(filters), '-map', '[stem]', '-ar', '48000', '-ac', '2',
                    '-c:a', 'pcm_f32le', '-f', 'f32le', stem_float]
        run(command)
        stem = np.frombuffer(stem_float.read_bytes(), dtype='<f4').reshape(-1, 2)
        measured = stats(stem)
        if len(stem) != samples or measured['peak'] > 10**(stem_ceiling/20):
            raise ValueError('SFX stem length/peak ceiling exceeded')
        stem_path, mix_path = temp/'sfx_stem_48k.wav', temp/'mix_48k.wav'
        encode = [executable, '-v', 'error', '-nostdin', '-y', '-f', 'f32le', '-ar', '48000', '-ac', '2',
                  '-i', stem_float, '-c:a', 'pcm_s16le', stem_path]
        run(encode)
        stem = pcm(stem_path)
        allowed = np.zeros(samples, dtype=bool)
        windows = []
        for event in events:
            start, end = event['start_sample'], event['start_sample'] + event['play_samples']
            allowed[start:end] = True
            active = np.flatnonzero(np.any(stem[start:end] != 0, axis=1))
            windows.append({'id': event['id'], 'start_sample': start, 'end_sample': end,
                            'nonzero_samples': len(active),
                            'first_nonzero_sample': start + int(active[0]) if len(active) else None,
                            'last_nonzero_sample': start + int(active[-1]) if len(active) else None})
        if np.any(stem[~allowed] != 0):
            raise ValueError('SFX stem contains audio outside locked event windows')
        expected = narration + stem
        mix_stats = stats(expected)
        if mix_stats['peak'] > 10**(ceiling/20):
            raise ValueError('Mix peak ceiling exceeded; reduce effects gain (narration is unchanged)')
        mix_command = [executable, '-v', 'error', '-nostdin', '-y', '-i', master, '-i', stem_path,
                       '-filter_complex', 'amix=inputs=2:duration=first:normalize=0',
                       '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', mix_path]
        run(mix_command)
        actual = pcm(mix_path)
        if actual.shape != expected.shape or float(np.max(np.abs(actual-expected))) > 1/32768:
            raise ValueError('Mixed PCM changed the complete narration sum')
        if file_hash(master) != master_hash or any(file_hash(p) != e['normalized_sha256'] for p,e in zip(paths, events)):
            raise ValueError('Audio source changed during mixing')
        stem_float.unlink()
        report = {'status': 'PASS', 'master_path': master_name, 'master_sha256': master_hash,
                  'stem_path': 'work/audio/sfx_stem_48k.wav', 'stem_sha256': file_hash(stem_path),
                  'mix_path': 'work/audio/mix_48k.wav', 'mix_sha256': file_hash(mix_path),
                  'samples': samples, 'events': events, 'inputs': key, 'peak_concurrent': peak_concurrent,
                  'event_windows': windows, 'outside_event_windows_silent': True,
                  'narration': stats(narration), 'stem': stats(stem), 'mix': stats(actual),
                  'narration_sum_verified': True, 'limiter_delay_samples': 0,
                  'commands': [[str(v) for v in c] for c in (command, encode, mix_command)],
                  'loudness_note': 'RMS dBFS, not integrated LUFS. Full human listening remains required.'}
        (temp/'mix.json').write_bytes(canonical(report))
        return report

    if write:
        folder, report = cached(root, 'sfx-mix', key, build)
        publish(root, {'work/audio/sfx_stem_48k.wav': folder/'sfx_stem_48k.wav',
                       'work/audio/mix_48k.wav': folder/'mix_48k.wav', 'reports/mix.json': folder/'mix.json'})
    else:
        folder, record, _ = lookup(root, 'sfx-mix', key)
        if record is None:
            raise ValueError('SFX mix cache unavailable; build the current mix first')
        report = record['result']
        for name, sha in ((report['stem_path'], report['stem_sha256']), (report['mix_path'], report['mix_sha256'])):
            if file_hash(resolve_path(root, name)) != sha:
                raise ValueError('Published SFX mix hash mismatch')
    return report
