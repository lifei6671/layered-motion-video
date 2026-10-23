from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from static_comic.contracts import read_json
from static_comic.media import file_hash, run
from static_comic.sfx_library import normalize_asset
from static_comic.sfx_mix import mix, pcm


def wav(path, values, rate=48000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as audio:
        audio.setframerate(rate); audio.setnchannels(values.shape[1]); audio.setsampwidth(2)
        audio.writeframes(values.astype('<i2').tobytes())


class SfxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sc-k4 音频 ')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        values = np.full((4800, 2), 1000)
        values[-1] = [2000, -2000]
        self.master = self.root/'work/audio/master_48k.wav'
        wav(self.master, values)
        pulse = np.zeros((512, 2)); pulse[0] = [8000, -8000]
        self.source = self.root/'assets/sfx/pulse.wav'
        wav(self.source, pulse)
        license_file = self.root/'assets/sfx/LICENSE.txt'
        license_file.write_text('Locally synthesized numeric test pulse; technical tests only.', encoding='utf-8')
        self.asset = {'asset_id': 'pulse', 'path': 'assets/sfx/pulse.wav', 'sha256': file_hash(self.source),
                      'source_kind': 'local_created', 'source_uri': 'local:test_sfx.py', 'author': 'test fixture',
                      'license': 'test-only', 'usage_scope': 'technical fixtures only',
                      'license_evidence': {'path': 'assets/sfx/LICENSE.txt', 'sha256': file_hash(license_file)},
                      'review_status': 'TECHNICAL_ONLY', 'sample_rate': 48000, 'channels': 2,
                      'duration_samples': 512, 'tags': ['keyword', 'scene', 'transition', 'narrative']}
        self.policy = {'max_concurrent': 2, 'peak_ceiling_dbfs': -1, 'sfx_peak_ceiling_dbfs': -6}

    def normalized(self):
        return normalize_asset(self.root, self.asset, technical=True)

    def event(self, normalized=None):
        info = normalized or self.normalized()
        return {'id': 'sfx-1', 'kind': 'keyword', 'asset_id': 'pulse', 'asset_sha256': self.asset['sha256'],
                'normalized_path': info['normalized_path'], 'normalized_sha256': info['normalized_sha256'],
                'start_sample': 1601, 'source_trim_samples': 0, 'play_samples': info['samples'],
                'gain_db': -6, 'fade_in_samples': 0, 'fade_out_samples': 96}

    def test_normalize_44100_mono_reports_samples_format_and_cache(self):
        values = (np.sin(np.arange(4410)*.1)*2000).reshape(-1, 1)
        wav(self.source, values, 44100)
        self.asset.update(sha256=file_hash(self.source), sample_rate=44100, channels=1, duration_samples=4410)
        info = self.normalized()
        self.assertEqual((info['sample_rate'], info['channels'], info['samples']), (48000, 2, 4800))
        self.assertEqual(info['source_samples'], 4410)
        self.assertEqual(info['resample_error_samples'], 0)
        self.assertEqual(self.normalized(), info)
        self.assertEqual(read_json((self.root/'reports/cache/sfx-normalize.json').read_bytes())['status'], 'HIT')
        self.assertEqual(normalize_asset(self.root, self.asset, technical=True, write=False), info)

    def test_exact_pulse_start_full_narration_and_no_mutation(self):
        master_hash = file_hash(self.master)
        event = self.event()
        result = mix(self.root, [event], self.policy)
        stem = pcm(self.root/result['stem_path'])
        self.assertEqual(np.flatnonzero(np.any(stem != 0, axis=1)).tolist(), [1601])
        self.assertEqual(len(stem), 4800)
        np.testing.assert_array_equal(pcm(self.root/result['mix_path']), pcm(self.master)+stem)
        self.assertEqual(file_hash(self.master), master_hash)
        self.assertEqual(result['mix']['clipped_samples'], 0)
        self.assertTrue(result['narration_sum_verified'])
        self.assertIn('adelay=1601S:all=1', str(result['commands']))
        self.assertNotIn('-shortest', str(result['commands']))

    def test_all_four_kinds_and_cache_gain_invalidation(self):
        event = self.event()
        events = [{**event, 'id': f'sfx-{i}', 'kind': kind, 'start_sample': 600*i}
                  for i, kind in enumerate(('keyword', 'scene', 'transition', 'narrative'))]
        first = mix(self.root, events, self.policy)
        self.assertEqual(len(first['events']), 4)
        self.assertEqual(mix(self.root, events, self.policy), first)
        cache = self.root/'reports/cache/sfx-mix.json'
        self.assertEqual(read_json(cache.read_bytes())['status'], 'HIT')
        self.assertEqual(mix(self.root, events, self.policy, write=False), first)
        events[0]['gain_db'] = -12
        changed = mix(self.root, events, self.policy)
        self.assertNotEqual(changed['mix_sha256'], first['mix_sha256'])
        self.assertEqual(read_json(cache.read_bytes())['status'], 'REBUILT')

    def test_empty_events_bypass_exact_master(self):
        result = mix(self.root, [], {})
        self.assertEqual(result['status'], 'BYPASS')
        self.assertEqual(result['mix_path'], 'work/audio/master_48k.wav')
        self.assertFalse((self.root/'work/audio/mix_48k.wav').exists())

    def test_trim_fades_and_exact_end_boundary(self):
        values = np.full((512, 2), 4000)
        values[:64] = 12000
        wav(self.source, values)
        self.asset['sha256'] = file_hash(self.source)
        event = {**self.event(), 'start_sample': 4480, 'source_trim_samples': 64,
                 'play_samples': 320, 'fade_in_samples': 16, 'fade_out_samples': 32}
        report = mix(self.root, [event], self.policy)
        stem = pcm(self.root/report['stem_path'])
        self.assertTrue(np.all(stem[:4481] == 0))
        self.assertLess(stem[-1, 0], stem[-32, 0])
        self.assertGreater(stem[-1, 0], 0)
        self.assertEqual(report['event_windows'][0]['last_nonzero_sample'], 4799)
        self.assertTrue(report['outside_event_windows_silent'])
        self.assertLess(float(stem.max()), 4001/32768)

    def test_invalid_times_gains_fades_and_tails_fail(self):
        event = self.event()
        changes = [{'start_sample': -1}, {'start_sample': True}, {'start_sample': 4799},
                   {'source_trim_samples': -1}, {'source_trim_samples': 512}, {'play_samples': 0},
                   {'gain_db': float('nan')}, {'gain_db': float('inf')}, {'gain_db': '-6;anull'},
                   {'fade_in_samples': 512, 'fade_out_samples': 1}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                mix(self.root, [{**event, **change}], self.policy)

    def test_concurrent_budget_and_peak_limits_fail(self):
        event = self.event()
        with self.assertRaisesRegex(ValueError, 'concurrent'):
            mix(self.root, [{**event, 'id': str(i)} for i in range(3)], self.policy)
        with self.assertRaisesRegex(ValueError, 'stem length/peak'):
            mix(self.root, [{**event, 'gain_db': 12}], self.policy)
        wav(self.master, np.full((4800, 2), 28000))
        with self.assertRaisesRegex(ValueError, 'Mix peak'):
            mix(self.root, [event], self.policy)

    def test_license_hash_path_and_production_gate_fail(self):
        for change in ({'license': ''}, {'sha256': '0'*64}, {'path': '../pulse.wav'},
                       {'review_status': 'CANDIDATE'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize_asset(self.root, {**self.asset, **change}, technical=True)
        with self.assertRaisesRegex(ValueError, 'not approved'):
            normalize_asset(self.root, self.asset)
        self.normalized()
        (self.root/'assets/sfx/LICENSE.txt').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'license evidence'):
            self.normalized()

    def test_corrupt_audio_and_source_metadata_fail(self):
        with self.assertRaisesRegex(ValueError, 'manifest duration'):
            normalize_asset(self.root, {**self.asset, 'duration_samples': 513}, technical=True)
        self.source.write_bytes(b'not an audio file')
        self.asset['sha256'] = file_hash(self.source)
        with self.assertRaises(ValueError):
            self.normalized()

    def test_nan_audio_is_rejected_before_integer_conversion(self):
        raw = self.root/'nan.f32'
        raw.write_bytes(np.full((512, 2), np.nan, dtype='<f4').tobytes())
        run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'f32le', '-ar', '48000', '-ac', '2',
             '-i', raw, '-c:a', 'pcm_f32le', self.source])
        self.asset['sha256'] = file_hash(self.source)
        with self.assertRaisesRegex(ValueError, 'invalid source samples'):
            self.normalized()

    def test_normalized_tampering_and_missing_readonly_cache_fail(self):
        info = normalize_asset(self.root, self.asset, technical=True, write=False)
        self.assertEqual(info['samples'], 512)
        self.assertFalse((self.root/'work/cache').exists())
        self.assertFalse((self.root/info['normalized_path']).exists())
        event = self.event()
        with self.assertRaisesRegex(ValueError, 'cache unavailable'):
            mix(self.root, [event], self.policy, write=False)
        path = self.root/event['normalized_path']
        path.write_bytes(path.read_bytes()+b'tamper')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            mix(self.root, [event], self.policy)


if __name__ == '__main__':
    unittest.main()
