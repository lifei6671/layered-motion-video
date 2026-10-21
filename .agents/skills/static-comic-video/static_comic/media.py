"""SC-P5: copy a silent visual stream, encode the complete master, verify both."""
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import wave

import numpy as np
from .paths import process_args


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(command, *, cwd=None, timeout=1200):
    command, cwd = process_args(command, cwd)
    result = subprocess.run(command, cwd=cwd, capture_output=True,
                            timeout=timeout, check=False)
    if result.returncode:
        raise ValueError(f"Process failed ({result.returncode}): {command[0]}: " +
                         result.stderr.decode('utf-8', errors='replace')[-16000:])
    return result.stdout


def probe(path, *, packets=False):
    args = ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-count_frames']
    if packets:
        args += ['-select_streams', 'a:0', '-show_packets']
    return json.loads(run([*args, '-of', 'json', path]))


def mux_command(visual, master, target):
    return ['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(visual), '-i', str(master),
            '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
            '-ar', '48000', '-movflags', '+faststart', str(target)]


def decoded_video(path, frames):
    data = run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', path, '-map', '0:v:0',
                '-an', '-fps_mode', 'passthrough', '-f', 'framemd5', '-hash', 'sha256', '-'])
    lines = data.decode('ascii').splitlines()
    timebase = next((line.split(':', 1)[1].strip() for line in lines if line.startswith('#tb 0:')), None)
    rows = [line.split(',') for line in lines if line and not line.startswith('#')]
    if timebase != '1/30' or len(rows) != frames:
        raise ValueError('Decoded video frame count/timebase differs from the locked timeline')
    for index, row in enumerate(rows):
        if int(row[2]) != index or int(row[3]) != 1:
            raise ValueError('Decoded video PTS must start at zero and advance at 30 fps')
    return [row[-1].strip() for row in rows]


def check_video(info, frames, width, height, *, audible):
    streams = info['streams']
    kinds = sorted(s['codec_type'] for s in streams)
    if kinds != (['audio', 'video'] if audible else ['video']):
        raise ValueError('Expected exactly one video and ' + ('one audio' if audible else 'no audio') + ' stream')
    video = next(s for s in streams if s['codec_type'] == 'video')
    expected = {'codec_name': 'h264', 'width': width, 'height': height, 'pix_fmt': 'yuv420p',
                'sample_aspect_ratio': '1:1', 'color_space': 'bt709'}
    if any(video.get(k) != v for k, v in expected.items()):
        raise ValueError('Unexpected video codec, dimensions, pixel/color format or SAR')
    if (Fraction(video['avg_frame_rate']) != 30 or Fraction(video['r_frame_rate']) != 30
            or int(video['nb_read_frames']) != frames or Fraction(video.get('start_time', '0')) != 0
            or abs(Fraction(video['duration']) - Fraction(frames, 30)) > Fraction(1, 1000000)):
        raise ValueError('Video duration/fps/frame count differs from the locked timeline')
    return video


def verify_media(visual, master, *, frames, width, height, audible=None):
    """Decode completely; lossy AAC has padding, but must preserve the full PCM span."""
    visual_info = probe(visual)
    check_video(visual_info, frames, width, height, audible=False)
    visual_frames = decoded_video(visual, frames)
    with wave.open(BytesIO(Path(master).read_bytes()), 'rb') as source:
        samples, rate, channels = source.getnframes(), source.getframerate(), source.getnchannels()
        if rate != 48000 or channels != 2 or source.getsampwidth() != 2:
            raise ValueError('Master must be 48 kHz stereo PCM s16le')
        pcm = np.frombuffer(source.readframes(samples), dtype='<i2').astype(np.float32) / 32768
    if not 0 <= frames * 1600 - samples < 1600:
        raise ValueError('Visual coverage must exceed the complete master by less than one frame')
    result = {'status': 'PASS', 'total_frames': frames, 'width': width, 'height': height,
              'master_samples': samples, 'tail_samples': frames * 1600 - samples,
              'visual_sha256': file_hash(visual), 'master_sha256': file_hash(master),
              'decoded_video_sha256': hashlib.sha256(''.join(visual_frames).encode()).hexdigest(),
              'visual_probe': visual_info, 'full_video_decode': 'PASS'}
    if audible is None:
        return result
    info = probe(audible)
    check_video(info, frames, width, height, audible=True)
    if visual_frames != decoded_video(audible, frames):
        raise ValueError('Mux changed decoded video frames')
    audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    if audio['codec_name'] != 'aac' or int(audio['sample_rate']) != rate or audio['channels'] != channels:
        raise ValueError('Expected one 48 kHz stereo AAC stream')
    if abs(Fraction(audio.get('start_time', '0'))) > Fraction(1, rate):
        raise ValueError('AAC playback must start at the master origin')
    # MP4 may round its effective duration to a millisecond. Decoder output may
    # still expose up to one AAC frame of trailing padding, not missing speech.
    effective_samples = Fraction(audio['duration_ts']) * Fraction(audio['time_base']) * rate
    if abs(effective_samples - samples) > 48:
        raise ValueError('AAC effective playback duration does not preserve the full master')
    decoded = np.frombuffer(run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', audible,
        '-map', '0:a:0', '-vn', '-c:a', 'pcm_f32le', '-f', 'f32le', '-']), dtype='<f4')
    decoded_samples = len(decoded) // channels
    if len(decoded) % channels or not 0 <= decoded_samples - samples < 1024:
        raise ValueError('AAC decode is truncated or has unexplained excess padding')
    decoded = decoded[:len(pcm)]  # Measurement only: no media file is trimmed.
    measurements = []
    for start in range(0, samples, rate):
        end = min(start + rate, samples)
        a, b = pcm[start*channels:end*channels], decoded[start*channels:end*channels]
        energy = float(np.dot(a, a))
        error = float(np.dot(a-b, a-b))
        if energy < 1e-6:
            score = 1.0 if float(np.max(np.abs(b))) < .005 else 0.0
        else:
            score = float(np.dot(a, b) / max(float(np.sqrt(energy * np.dot(b, b))), 1e-12))
            if error / energy > .10:
                raise ValueError(f'AAC content differs from master at samples {start}:{end}')
        if not np.isfinite(score) or score < .97:
            raise ValueError(f'AAC head/body/tail content mismatch at samples {start}:{end}')
        measurements.append({'start_sample': start, 'end_sample': end, 'correlation': score})
    packet_info = probe(audible, packets=True)['packets']
    result.update(audible_sha256=file_hash(audible), mux_probe=info, decoded_video_matches=True,
                  full_audio_decode='PASS', audio={'effective_samples': float(effective_samples),
                  'decoded_samples': decoded_samples, 'padding_samples': decoded_samples-samples,
                  'first_packet': packet_info[0], 'last_packet': packet_info[-1],
                  'content_windows': measurements,
                  'note': 'AAC priming is signaled by skip_samples/edit list; trailing decode padding is measured. Complete listening remains a separate human check.'})
    return result
