"""Audio integration with real PCM/FFmpeg; video execution is a declared test double."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from scripts.create_fixture import create_fixture
from static_comic import delivery
from static_comic.cache import publish
from static_comic.contracts import canonical, read_json
from static_comic.emphasis import DEFAULT_POLICY, empty_plan
from static_comic.media import file_hash
from static_comic.project import compile_project
from test_sc_p5 import decision
import test_sc_p6_delivery
from test_sfx import wav


class EmphasisIntegrationTests(unittest.TestCase):
    run_command = test_sc_p6_delivery.DeliveryCacheTests.run_command
    cache_status = test_sc_p6_delivery.DeliveryCacheTests.cache_status

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sc-k4-integration-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)/'episode'
        board = create_fixture(self.root)
        self.commands, self.fail_kind = [], None
        runtime = {'sources': {'renderer/static-comic/src/index.tsx': 'test-code'}, 'installed': {},
                   'tools': {n: {'sha256': n} for n in ('node', 'browser', 'ffmpeg')}}
        for target, kwargs in (('runtime', {'return_value': runtime}),
                               ('run', {'side_effect': self.run_command}),
                               ('verify_media', {'return_value': {'status': 'PASS', 'TEST_DOUBLE': True}})):
            context = patch.object(delivery, target, **kwargs)
            mock = context.start(); self.addCleanup(context.stop)
            if target == 'verify_media':
                self.verifier = mock
        pulse = np.zeros((512, 2)); pulse[0] = [8000, -8000]
        source = self.root/'assets/sfx/pulse.wav'
        wav(source, pulse)
        evidence = self.root/'assets/sfx/LICENSE.txt'
        evidence.write_text('Locally synthesized integration pulse. Test only.', encoding='utf-8')
        asset = {'asset_id': 'pulse', 'path': 'assets/sfx/pulse.wav', 'sha256': file_hash(source),
                 'source_kind': 'local_created', 'source_uri': 'local:test_emphasis_integration.py',
                 'author': 'test fixture', 'license': 'test-only', 'usage_scope': 'technical tests',
                 'license_evidence': {'path': 'assets/sfx/LICENSE.txt', 'sha256': file_hash(evidence)},
                 'review_status': 'TECHNICAL_ONLY', 'sample_rate': 48000, 'channels': 2,
                 'duration_samples': 512, 'tags': ['scene']}
        self.policy = deepcopy(DEFAULT_POLICY)
        self.policy['mode'] = 'mixed'; self.policy['audio']['enabled'] = True
        self.plan = empty_plan((self.root/'input/script.txt').read_bytes(), [s['id'] for s in board['shots']])
        for shot in self.plan['shot_decisions']:
            shot.update(text_decision='skip', sfx_decision='allow')
        self.plan['audio_events'] = [{'id': 'scene-1', 'kind': 'scene', 'sfx_asset_id': 'pulse',
            'anchor': {'type': 'shot_start', 'shot_id': 'SHOT-001', 'offset_samples': 1601},
            'gain_db': -6, 'fade_in_samples': 0, 'fade_out_samples': 96, 'pinned': False, 'source': 'rules'}]
        publish(self.root, {'input/emphasis_policy.json': canonical(self.policy),
                           'assets/sfx/manifest.json': canonical({'schema_version': '1.0', 'assets': [asset]})})
        self.save_plan()

    def save_plan(self):
        publish(self.root, {'input/emphasis_plan.json': canonical(self.plan)})

    def test_initial_readonly_compile_then_preview_uses_mix_and_review_evidence(self):
        compiled = compile_project(self.root, technical_fixture=True, write=False)
        self.assertEqual(compiled['emphasis']['sfx'][0]['start_sample'], 1601)
        self.assertFalse((self.root/'work/audio/sfx').exists())
        pre = delivery.preview(self.root, True)
        snap, compiled = delivery.snapshot(self.root, True)
        self.assertEqual(snap['audio_reference']['path'], 'work/audio/mix_48k.wav')
        self.assertNotIn('visual_emphasis', compiled['props'])
        record = read_json((self.root/'reports/technical/preview.json').read_bytes())
        self.assertIn('preview/technical/mix.json', record['files'])
        self.assertIn('preview/technical/emphasis.json', record['files'])
        delivery.approve(self.root, decision(pre['binding_sha256']), True)
        self.assertEqual(Path(self.verifier.call_args.args[1]), self.root/'work/audio/mix_48k.wav')

    def test_only_gain_change_hits_visual_rebuilds_mix_mux_and_invalidates_approval(self):
        first = delivery.preview(self.root, True)
        delivery.approve(self.root, decision(first['binding_sha256']), True)
        before = len(self.commands)
        self.plan['audio_events'][0]['gain_db'] = -12
        self.save_plan()
        second = delivery.preview(self.root, True)
        self.assertEqual(self.commands[before:], ['mux'])
        self.assertEqual(self.cache_status('visual-preview'), 'HIT')
        self.assertEqual(self.cache_status('remotion-build'), 'HIT')
        self.assertEqual(self.cache_status('sfx-mix'), 'REBUILT')
        self.assertEqual(self.cache_status('mux-preview'), 'REBUILT')
        self.assertNotEqual(first['binding_sha256'], second['binding_sha256'])
        with self.assertRaisesRegex(ValueError, 'explicit semantic'):
            delivery.render_visual(self.root, True)

    def test_cross_silence_tail_skips_and_fixed_conflict_requires_review(self):
        self.plan['audio_events'][0]['anchor']['offset_samples'] = 191900
        self.plan['shot_decisions'][1]['sfx_decision'] = 'silence'
        self.save_plan()
        compiled = compile_project(self.root, technical_fixture=True, write=False)
        self.assertEqual(compiled['emphasis']['sfx'], [])
        self.assertEqual(compiled['emphasis']['diagnostics'][0]['reason_code'], 'SILENCE_TAIL_CONFLICT')
        self.plan['audio_events'][0]['pinned'] = True
        self.save_plan()
        with self.assertRaisesRegex(ValueError, 'REVIEW_REQUIRED.*SILENCE_TAIL_CONFLICT'):
            compile_project(self.root, technical_fixture=True, write=False)

    def test_removing_events_bypasses_stale_mix_with_original_master(self):
        delivery.preview(self.root, True)
        self.assertTrue((self.root/'work/audio/mix_48k.wav').is_file())
        self.plan['audio_events'] = []
        self.save_plan()
        pre = delivery.preview(self.root, True)
        snap, _ = delivery.snapshot(self.root, True)
        self.assertNotIn('audio_reference', snap)
        delivery.approve(self.root, decision(pre['binding_sha256']), True)
        self.assertEqual(Path(self.verifier.call_args.args[1]), self.root/'work/audio/master_48k.wav')


if __name__ == '__main__':
    unittest.main()
