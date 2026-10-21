"""Exercise Remotion/FFmpeg caching and failure recovery with technical fixtures."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.create_delivery_demo import create_clock_probe
from static_comic import delivery
from static_comic.contracts import canonical
from static_comic.media import file_hash


def run_probe(output):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Probe output must be new or empty')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sc-p6-real-') as temporary:
        root = Path(temporary)/'episode'
        started = time.monotonic(); create_clock_probe(root)
        cold = time.monotonic()-started
        final = root/'output/technical/final.mp4'
        approval = root/'review/technical/approval.json'
        original = {'final': file_hash(final), 'approval': file_hash(approval)}
        pre_binding = delivery.inspect(root, True)['binding_sha256']
        started = time.monotonic()
        pre = delivery.preview(root, True)
        delivery.render_visual(root, True); delivery.mux(root, True)
        warm = time.monotonic()-started
        hits = {p.stem: json.loads(p.read_bytes()) for p in (root/'reports/cache').glob('*.json')}
        assert all(v['status'] == 'HIT' for v in hits.values()), hits
        assert original == {'final': file_hash(final), 'approval': file_hash(approval)}
        assert pre['binding_sha256'] == pre_binding
        old_version = delivery.versions
        real_run = delivery.run
        injected = []
        def fail_mux(command, **kwargs):
            if '-c:a' not in command:
                return real_run(command, **kwargs)
            Path(command[-1]).write_bytes(b'INJECTED PARTIAL MUX')
            injected.append(command)
            raise ValueError('Injected mid-mux failure')
        with patch.object(delivery, 'versions', side_effect=lambda *a,**kw: {**old_version(*a,**kw), 'probe': 1}), \
                patch.object(delivery, 'run', side_effect=fail_mux):
            try:
                delivery.mux(root, True)
            except ValueError as error:
                assert 'Injected mid-mux' in str(error)
            else:
                raise AssertionError('Fault injection did not fail')
        failure = delivery.status(root, True)
        assert len(injected) == 1 and injected[0][-1].endswith('audible.mp4')
        assert failure['status'] == 'FAILED' and failure['current_success'] is False
        assert original == {'final': file_hash(final), 'approval': file_hash(approval)}
        recovered = delivery.mux(root, True)
        assert recovered['status'] == 'OUTPUT_VERIFIED'
        (root/'work/remotion/technical/visual.mp4').unlink()
        delivery.render_visual(root, True)
        missing = json.loads((root/'reports/cache/visual-final.json').read_bytes())
        assert missing['status'] == 'REBUILT' and missing['reason'] == 'published_visual_missing_or_corrupt'
        delivery.mux(root, True)
        verified = delivery.verify(root, True)
        assert not verified['production_accepted']
        shutil.copyfile(final, output/'technical-final.mp4')
        shutil.copyfile(root/'reports/technical/validation.json', output/'validation.json')
        result = {'status': 'PASS', 'scope': 'SYNTHETIC TECHNICAL PROBE ONLY',
                  'cold_seconds': cold, 'warm_seconds': warm, 'identical_rerun_hits': hits,
                  'unchanged_final_and_approval_sha256': original, 'failure': failure,
                  'injected_mux_command': injected[0],
                  'retry': recovered, 'deleted_visual_rebuild': missing, 'final': verified,
                  'output_sha256': file_hash(output/'technical-final.mp4'),
                  'human_acceptance': 'NOT_RUN', 'note': 'Warm timing includes hashing and full media decode; no performance SLA.'}
        (output/'result.json').write_bytes(canonical(result))
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = run_probe(args.output)
    print(json.dumps({'status': result['status'], 'cold_seconds': result['cold_seconds'],
                      'warm_seconds': result['warm_seconds']}, ensure_ascii=False))
