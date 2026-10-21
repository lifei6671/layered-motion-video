"""Provider/worker failures must be retriable; no model or service called by these tests."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.create_fixture import create_fixture
from speech_support import synthetic_windows
from static_comic import speech
from static_comic.contracts import canonical
from static_comic.speech_audio import prepare_audio


class AlignmentCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'episode'; create_fixture(self.root)
        prepare_audio(self.root, 'input/voice.wav')
        self.lock = Path(self.tmp.name)/'lock.json'
        self.lock.write_bytes(canonical({'asr': {}, 'alignment': {}, 'device': 'cpu'}))
        board = json.loads((self.root/'input/storyboard.json').read_bytes())
        text = (self.root/'input/script.txt').read_text(encoding='utf-8-sig')
        self.coarse = {'backend_matches': True, 'response': {'segments': [
            {'start': s['speech_interval_samples'][0]/48000, 'end': s['speech_interval_samples'][1]/48000,
             'text': text[s['script_range'][0]:s['script_range'][1]]} for s in board['shots']]}}
        context = patch('scripts.probe_models.verify_model'); context.start(); self.addCleanup(context.stop)

    def align(self):
        return speech.align_project(self.root, url='http://127.0.0.1:13900', models_lock=self.lock,
                                    technical_fixture=True)

    def worker(self, command, **kwargs):
        request = json.loads((self.root/command[-1]).read_bytes())
        return SimpleNamespace(returncode=0, stdout=canonical(synthetic_windows(request['plan'])), stderr=b'')

    def test_changed_service_backend_is_not_cached_then_retry_and_hit(self):
        with patch.object(speech, 'transcribe_service', side_effect=[{'backend_matches': False}, self.coarse]) as service, \
                patch.object(speech.subprocess, 'run', side_effect=self.worker) as worker:
            with self.assertRaisesRegex(ValueError, 'backend changed'): self.align()
            good = self.align(); again = self.align()
        self.assertEqual(good, again)
        self.assertEqual(good['status'], 'PASS')
        self.assertEqual(service.call_count, 2)
        self.assertEqual(worker.call_count, 1)

    def test_worker_failure_preserves_aligned_and_retry_uses_coarse_cache(self):
        old = b'old valid generation placeholder'
        (self.root/'work/alignment').mkdir(parents=True, exist_ok=True)
        (self.root/'work/alignment/aligned.json').write_bytes(old)
        with patch.object(speech, 'transcribe_service', return_value=self.coarse) as service:
            with patch.object(speech.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout=b'', stderr=b'failed')):
                with self.assertRaisesRegex(ValueError, 'alignment failed'): self.align()
            self.assertEqual((self.root/'work/alignment/aligned.json').read_bytes(), old)
            with patch.object(speech.subprocess, 'run', side_effect=self.worker):
                self.assertEqual(self.align()['status'], 'PASS')
        self.assertEqual(service.call_count, 1)


if __name__ == '__main__':
    unittest.main()
