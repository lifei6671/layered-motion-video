"""Reuse the SC-P3 Chinese speech probe as an explicitly technical audible preview."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import wave

import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from static_comic.contracts import canonical, read_json
from static_comic.media import file_hash
from create_fixture import create_fixture


def create_demo(root):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError('Demo requires a new empty directory')
    root.mkdir(parents=True, exist_ok=True)
    origin = BASE/'reports/sc-p3/normal'
    for folder in ('input', 'assets', 'review', 'work/audio', 'work/alignment'):
        shutil.copytree(origin/folder, root/folder)
    (root/'TECHNICAL-ONLY.txt').write_text(
        'Technical images and existing Chinese speech probe only. No real artwork, semantic approval, '
        'complete listening or production-quality acceptance. No new TTS/ASR/model download.\n', encoding='utf-8')
    commands = []
    for action in ('preview', 'inspect'):
        command = [sys.executable, '-m', 'static_comic', action, '--project', str(root), '--technical-fixture']
        result = subprocess.run(command, cwd=BASE, capture_output=True, timeout=1200)
        commands.append({'args': command, 'exit_code': result.returncode,
                         'stdout': result.stdout.decode('utf-8'), 'stderr': result.stderr.decode('utf-8')})
        if result.returncode:
            raise ValueError(str(commands[-1]))
    record = {'artifact_kind': 'technical_fixture', 'source': 'reports/sc-p3/normal',
              'source_voice_sha256': file_hash(origin/'input/voice.wav'),
              'copied_voice_sha256': file_hash(root/'input/voice.wav'),
              'source_aligned_sha256': file_hash(origin/'work/alignment/aligned.json'),
              'copied_aligned_sha256': file_hash(root/'work/alignment/aligned.json'),
              'commands': commands, 'preview': read_json(result.stdout),
              'real_user_acceptance': 'NOT_RUN'}
    (root/'demo-result.json').write_bytes(canonical(record)+b'\n')
    return record


def create_clock_probe(root):
    """Synthetic receipts exercise only the isolated technical output paths."""
    root = Path(root).resolve()
    board = create_fixture(root)
    samples = 575088
    times = np.arange(samples) / 48000
    pcm = np.stack([.3*np.sin(2*np.pi*220*times), .3*np.sin(2*np.pi*330*times)], axis=1)
    with wave.open(str(root/'input/voice.wav'), 'wb') as audio:
        audio.setnchannels(2); audio.setsampwidth(2); audio.setframerate(48000)
        audio.writeframes((pcm*32767).astype('<i2').tobytes())
    board['audio']['sha256'] = file_hash(root/'input/voice.wav')
    (root/'input/storyboard.json').write_bytes(canonical(board)+b'\n')
    (root/'TECHNICAL-ONLY.txt').write_text('11.981-second tones, geometry images and SYNTHETIC TEST ONLY approval. No actual user approval.\n',encoding='utf-8')
    commands=[]
    for action in ('preview', 'approve', 'render-visual', 'mux', 'verify'):
        command=[sys.executable, '-m', 'static_comic', action, '--project', str(root), '--technical-fixture']
        if action == 'approve':
            binding=read_json(commands[-1]['stdout'].encode())['binding_sha256']
            decision={'stage':'preview','binding_sha256':binding,'decision':'APPROVED',
                'human':{'actor':'SYNTHETIC TEST ONLY','actor_role':'human','at':'2026-10-21T00:00:00Z',
                         'evidence':'Automated technical regression data; not a real user decision'},
                'checks':{'semantics':True,'full_listening':True,'formal_quality':False},
                'reason':'Synthetic protocol test only; no real listening or semantic approval'}
            (root/'review/test-decision.json').write_bytes(canonical(decision)+b'\n')
            command+=['--input','review/test-decision.json']
        result=subprocess.run(command,cwd=BASE,capture_output=True,timeout=1200)
        commands.append({'args':command,'exit_code':result.returncode,'stdout':result.stdout.decode('utf-8'),
                         'stderr':result.stderr.decode('utf-8')})
        if result.returncode:
            raise ValueError(str(commands[-1]))
    (root/'cli-commands.json').write_bytes(canonical({'artifact_kind':'technical_fixture','commands':commands})+b'\n')
    return read_json(result.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    parser.add_argument('--clock-output', help='Optional separate technical full-flow 11.981s regression directory')
    args=parser.parse_args()
    if not args.output and not args.clock_output:
        parser.error('Provide --output and/or --clock-output')
    if args.output:
        print(canonical(create_demo(args.output)['preview']).decode('utf-8'))
    if args.clock_output:
        print(canonical(create_clock_probe(args.clock_output)).decode('utf-8'))
