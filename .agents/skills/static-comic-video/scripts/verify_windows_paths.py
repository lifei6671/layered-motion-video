"""Render 90-frame technical fixtures through both Windows path formats."""
import argparse
from contextlib import ExitStack
import json
import math
from pathlib import Path
import struct
import sys
from unittest.mock import patch
import wave

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from scripts.create_fixture import create_fixture
from static_comic import delivery
from static_comic.contracts import bytes_digest, canonical
from static_comic.media import run


def probe(destination):
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=False)
    results = []
    for extended, name in ((False, '标准 路径'), (True, '扩展 路径')):
        episode = root/name
        board = create_fixture(episode)
        samples = 143088
        with wave.open(str(episode/'input/voice.wav'), 'wb') as audio:
            audio.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b''.join(struct.pack('<h', int(5000 * math.sin(2*math.pi*440*i/48000))) for i in range(samples)))
        board['audio'].update(duration_samples=samples, sha256=bytes_digest((episode/'input/voice.wav').read_bytes()))
        for i, shot in enumerate(board['shots']):
            shot['start_samples'] = i*48000
            shot['speech_interval_samples'] = [i*48000+1000, min((i+1)*48000-1000, samples)]
            if shot['transition_out']:
                shot['transition_out'].update(semantic_anchor_samples=(i+1)*48000, duration_frames=6)
        (episode/'input/storyboard.json').write_bytes(canonical(board))
        prefix = '\\\\?\\' if extended else ''
        actual_root = Path(prefix+str(episode))
        with ExitStack() as stack:
            if extended:
                for field in ('BASE', 'RENDERER', 'BROWSER'):
                    stack.enter_context(patch.object(delivery, field, Path(prefix+str(getattr(delivery, field)))))
            preview = delivery.preview(actual_root, technical=True)
            # Composition discovery uses the same real CLI/path adapter as rendering.
            compositions = run(['node', delivery.RENDERER/'node_modules/@remotion/cli/remotion-cli.js',
                'compositions', 'src/technical.tsx',
                f'--props={actual_root / "work/remotion/technical/props.json"}',
                f'--public-dir={actual_root / "work/remotion/technical/public"}',
                f'--browser-executable={delivery.BROWSER}', '--log=info'], cwd=delivery.RENDERER)
            if b'ComicVideo' not in compositions:
                raise ValueError('Composition discovery did not return ComicVideo')
            (episode/'reports/technical/compositions.log').write_bytes(compositions)
            delivery.approve(actual_root, {'stage': 'preview', 'binding_sha256': preview['binding_sha256'],
                'human': {'actor': 'TECHNICAL PROBE ONLY', 'actor_role': 'human', 'at': '2026-10-21T00:00:00Z',
                          'evidence': 'Synthetic fixture receipt; no real user approval'},
                'decision': 'APPROVED', 'checks': {'semantics': True, 'full_listening': True, 'formal_quality': False},
                'reason': 'TEST_ONLY: exercise formal-profile rendering and mux; never production acceptance'}, technical=True)
            delivery.render_visual(actual_root, technical=True)
            result = delivery.mux(actual_root, technical=True)
            assert result['production_accepted'] is False
            result = delivery.verify(actual_root, technical=True)
            assert result['production_accepted'] is False
            results.append({'extended': extended, 'python_root': str(actual_root), 'result': result,
                            'preview': preview, 'final': str(episode/'output/technical/final.mp4')})
    (root/'verification.json').write_text(json.dumps({'status': 'PASS', 'kind': 'TEST_ONLY', 'cases': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'status': 'PASS', 'kind': 'TEST_ONLY', 'cases': len(results), 'report': str(root/'verification.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps(probe(parser.parse_args().output), ensure_ascii=True))
