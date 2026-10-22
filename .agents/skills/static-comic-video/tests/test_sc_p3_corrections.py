"""Synthetic ASR mistakes; these receipts never approve production audio."""
import copy
from pathlib import Path
import tempfile
import unittest

from scripts.create_fixture import create_fixture
from static_comic.contracts import digest
from static_comic.project import load_project
from static_comic.speech import evaluate
from static_comic.speech_text import check_overrides, make_plan
from speech_support import synthetic_windows


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.board = create_fixture(self.root)
        _, self.hashes, _ = load_project(self.root)
        self.script = (self.root / 'input/script.txt').read_bytes().decode('utf-8-sig')
        self.samples = self.board['audio']['duration_samples']
        self.coarse = {'backend_matches': True, 'response': {'segments': [
            {'start': i * 4 + .1, 'end': i * 4 + 3.8, 'text': self.script[a:b]}
            for i, (a, b) in enumerate(s['script_range'] for s in self.board['shots'])]}}
        self.coarse['response']['segments'][0]['text'] += '的'
        plan = make_plan(self.script, self.board, self.coarse, [], self.samples)
        self.anomaly = next(a for a in plan['anomalies'] if a['kind'] == 'extra_speech')
        self.entry = {'kind': 'asr_correction', 'script_range': self.anomaly['script_range'],
                      'coarse_sha256': digest(self.coarse), **self.anomaly['detail'],
                      'reason': 'Synthetic listener confirms ASR added a word',
                      'human': {'actor': 'SYNTHETIC TEST ONLY', 'actor_role': 'human',
                                'at': '2026-10-22T00:00:00Z', 'evidence': 'Not production approval'}}

    def checked(self, entries):
        document = {'schema_version': '1.0', 'script_sha256': self.hashes['input/script.txt'],
                    'audio_sha256': self.hashes['input/voice.wav'],
                    'storyboard_sha256': self.hashes['input/storyboard.json'], 'entries': entries}
        return check_overrides(document, self.board, self.script, self.hashes, self.samples)

    def test_exact_correction_preserves_raw_asr_and_creates_no_timestamps(self):
        before = copy.deepcopy(self.coarse)
        entries = self.checked([self.entry])
        plan = make_plan(self.script, self.board, self.coarse, entries, self.samples)
        self.assertFalse(plan['anomalies'])
        self.assertEqual(self.coarse, before)
        self.assertIn('的', plan['asr_normalized'])
        self.assertEqual(plan['resolved_asr_anomalies'][0]['anomaly'], self.anomaly)
        result = evaluate(self.board, plan, synthetic_windows(plan), entries, self.samples)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertTrue(any(a['kind'] == 'unconfirmed_timing' for a in result['anomalies']))

    def test_correction_with_confirmed_window_can_be_replayed(self):
        window = {'kind': 'window', 'script_range': self.board['shots'][0]['script_range'],
                  'samples': [4800, 182400], 'reason': 'Synthetic known window', 'human': self.entry['human']}
        entries = self.checked([self.entry, window])
        plan = make_plan(self.script, self.board, self.coarse, entries, self.samples)
        raw = synthetic_windows(plan)
        result = evaluate(self.board, plan, raw, entries, self.samples)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(evaluate(self.board, make_plan(self.script, self.board, self.coarse,
                         entries, self.samples), raw, entries, self.samples), result)

    def test_wrong_hash_or_text_or_range_does_not_hide_anomaly(self):
        for field, value in [('coarse_sha256', '0' * 64), ('recognized', '多'),
                             ('expected', '错'), ('script_range', [0, 1])]:
            entry = {**self.entry, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                make_plan(self.script, self.board, self.coarse, self.checked([entry]), self.samples)

    def test_unreviewed_differences_still_block(self):
        self.coarse['response']['segments'][-1]['text'] += '加读'
        self.entry['coarse_sha256'] = digest(self.coarse)
        plan = make_plan(self.script, self.board, self.coarse, self.checked([self.entry]), self.samples)
        self.assertTrue(any(a['detail']['recognized'] == '加读' for a in plan['anomalies']))

    def test_human_and_unique_valid_range_are_required(self):
        bad = copy.deepcopy(self.entry)
        del bad['human']
        reverse = {**self.entry, 'script_range': [2, 1]}
        for entries in ([bad], [self.entry, self.entry], [reverse]):
            with self.assertRaises(ValueError):
                self.checked(entries)
