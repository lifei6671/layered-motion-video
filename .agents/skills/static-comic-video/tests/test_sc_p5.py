from human_support import simulated
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from static_comic import delivery
from static_comic.contracts import canonical, read_json, validate
from test_sc_p1 import approved_test_project
from image_support import HUMAN
from scripts.create_fixture import create_fixture


def decision(binding, *, stage='preview', approved=True):
    return simulated(stage, {'stage': stage, 'binding_sha256': binding, 'human': copy.deepcopy(HUMAN),
            'decision': 'APPROVED' if approved else 'REJECTED',
            'checks': {'semantics': stage == 'preview', 'full_listening': stage == 'preview',
                       'formal_quality': stage == 'final'}, 'reason': 'SYNTHETIC TEST ONLY: explicit test decision, not user acceptance'})


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sc-p5-production-shape-')
        cls.base = Path(cls.tmp.name)/'base'; cls.base.mkdir()
        create_fixture(cls.base)
        approved_test_project(cls.base)
        cls.pre = delivery.preview(cls.base)
        cls.approval = decision(cls.pre['binding_sha256'])
        delivery.approve(cls.base, cls.approval)
        delivery.render_visual(cls.base)
        cls.final = delivery.mux(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp_case = tempfile.TemporaryDirectory(prefix='sc-p5-case-')
        self.root = Path(self.tmp_case.name)/'episode'
        shutil.copytree(self.base, self.root)

    def tearDown(self):
        self.tmp_case.cleanup()

    def edit(self, name, operation):
        path = self.root/name
        value = read_json(path.read_bytes()); operation(value)
        path.write_bytes(canonical(value)+b'\n')

    def test_forged_and_cross_stage_media_approval_is_rejected(self):
        forged = decision(self.pre['binding_sha256'])
        forged['human'] = copy.deepcopy(HUMAN)
        with self.assertRaisesRegex(ValueError, 'local human confirmation'):
            delivery.approve(self.root, forged)
        signed = decision(self.pre['binding_sha256'])
        signed['checks']['full_listening'] = False
        with self.assertRaisesRegex(ValueError, 'signature'):
            delivery.approve(self.root, signed)
        signed = decision(self.final['binding_sha256'], stage='final')
        signed['human'] = self.approval['human']
        with self.assertRaisesRegex(ValueError, 'local human confirmation'):
            delivery.approve(self.root, signed)

    def test_old_unsigned_quality_blocks_acceptance_but_can_be_reconfirmed(self):
        from static_comic.media import file_hash
        old = decision(self.final['binding_sha256'], stage='final')
        old['human'] = copy.deepcopy(HUMAN)
        path = self.root/'review/quality.json'
        path.write_bytes(canonical(old))
        old_hash = file_hash(path)
        result = delivery.mux(self.root)
        self.assertEqual(result['acceptance']['formal_quality'], 'REVIEW_REQUIRED')
        self.assertFalse(result['production_accepted'])
        self.assertEqual(file_hash(path), old_hash)
        delivery.approve(self.root, decision(result['binding_sha256'], stage='final'))
        self.assertTrue(delivery.verify(self.root)['production_accepted'])
        history = self.root/f'review/delivery-history/{old_hash}.json'
        self.assertEqual(history.read_bytes(), canonical(old))

    def test_old_signed_approval_cannot_override_later_rejection(self):
        approved = decision(self.pre['binding_sha256'])
        first = delivery.approve(self.root, approved)
        self.assertEqual(delivery.approve(self.root, approved), first)
        rejected = decision(self.pre['binding_sha256'], approved=False)
        delivery.approve(self.root, rejected)
        with self.assertRaisesRegex(ValueError, 'Older confirmation'):
            delivery.approve(self.root, approved)  # Original signature, not re-signed.
        snap, _ = delivery.snapshot(self.root)
        preview = delivery.checked_record(self.root, 'preview', snap, False)
        with self.assertRaisesRegex(ValueError, 'explicit'):
            delivery.require_approval(self.root, preview, False)
        fresh = decision(self.pre['binding_sha256'])
        delivery.approve(self.root, fresh)
        self.assertEqual(delivery.require_approval(self.root, preview, False), fresh)

    def test_real_production_entry_flow_preserves_t_and_separate_quality(self):
        self.assertEqual(self.pre['status'], 'PREVIEW_AUDIO_MUXED')
        self.assertEqual(self.final['acceptance']['formal_quality'], 'NOT_RUN')
        self.assertFalse(self.final['production_accepted'])
        report = read_json((self.root/'reports/render.json').read_bytes())
        self.assertEqual(report['validation']['total_frames'], 360)
        self.assertTrue(report['validation']['decoded_video_matches'])
        self.assertEqual(report['validation']['tail_samples'], 912)
        delivery.approve(self.root, decision(self.final['binding_sha256'], stage='final'))
        self.assertTrue(delivery.verify(self.root)['production_accepted'])

    def test_missing_or_partial_preview_approval_cannot_render(self):
        (self.root/'review/approval.json').unlink()
        with self.assertRaises(ValueError):
            delivery.render_visual(self.root)
        partial = decision(self.pre['binding_sha256']); partial['checks']['full_listening'] = False
        with self.assertRaisesRegex(ValueError, 'human checks'):
            delivery.approve(self.root, simulated("preview", partial))
        self.assertFalse((self.root/'review/approval.json').exists())

    def test_rejection_invalidates_existing_formal_media(self):
        delivery.approve(self.root, decision(self.pre['binding_sha256'], approved=False))
        with self.assertRaisesRegex(ValueError, 'explicit'):
            delivery.verify(self.root)
        with self.assertRaisesRegex(ValueError, 'explicit'):
            delivery.mux(self.root)

    def test_changed_preview_bytes_invalidate_approval(self):
        path = self.root/'preview/preview.mp4'; path.write_bytes(path.read_bytes()+b'tamper')
        with self.assertRaisesRegex(ValueError, 'media hash changed'):
            delivery.render_visual(self.root)

    def test_renderer_version_changes_invalidate_approval(self):
        original = delivery.runtime()
        with patch.object(delivery, 'runtime', return_value={**original, 'changed_version': 'test'}):
            with self.assertRaisesRegex(ValueError, 'renderer version'):
                delivery.render_visual(self.root)

    def test_license_change_invalidates_even_identical_pixels(self):
        self.edit('assets/images/manifest.json', lambda v: v['assets'][0]['license'].update(evidence='changed license'))
        with self.assertRaisesRegex(ValueError, 'approval is stale'):
            delivery.render_visual(self.root)

    def test_semantic_intent_change_invalidates_approval(self):
        self.edit('input/storyboard.json', lambda v: v['shots'][0]['transition_out'].update(intent='changed intent'))
        with self.assertRaises(ValueError):
            delivery.render_visual(self.root)

    def test_master_change_invalidates_before_mux(self):
        path=self.root/'work/audio/master_48k.wav'; data=bytearray(path.read_bytes()); data[-1]^=1;path.write_bytes(data)
        with self.assertRaises(ValueError):
            delivery.mux(self.root)

    def test_changed_formal_visual_cannot_be_muxed(self):
        path=self.root/'work/remotion/visual.mp4';path.write_bytes(path.read_bytes()+b'tamper')
        with self.assertRaisesRegex(ValueError, 'media hash changed'):
            delivery.mux(self.root)

    def test_stale_quality_receipt_is_not_formal_acceptance(self):
        stale=decision('0'*64, stage='final')
        with self.assertRaisesRegex(ValueError, 'stale media'):
            delivery.approve(self.root, stale)
        self.assertEqual(delivery.verify(self.root)['acceptance']['formal_quality'], 'NOT_RUN')

    def test_status_records_real_image_gates_and_inspection_is_not_approval(self):
        value=delivery.status(self.root)
        self.assertEqual(value['status'], 'OUTPUT_VERIFIED')
        self.assertIn('IMAGE_PLAN_APPROVED', value['passed'])
        self.assertIn('IMAGE_REVIEW_APPROVED', value['passed'])
        (self.root/'review/approval.json').unlink()
        self.assertEqual(delivery.inspect(self.root)['status'], 'PREVIEW_AUDIO_MUXED')
        self.assertFalse((self.root/'review/approval.json').exists())


class EntryTests(unittest.TestCase):
    def test_shared_delivery_contract_cases(self):
        cases = read_json((Path(__file__).resolve().parents[1]/'fixtures/delivery-contract-cases.json').read_bytes())
        for case in cases:
            with self.subTest(case=case['name']):
                if case['valid']:
                    validate(case['kind'], case['value'])
                else:
                    with self.assertRaises(ValueError):
                        validate(case['kind'], case['value'])

    def test_init_asks_channels_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'new'
            result=delivery.initialize(root)
            self.assertEqual(result['status'], 'SOURCE_POLICY_PENDING')
            self.assertEqual(len(result['options']), 4)
            self.assertEqual(delivery.status(root)['status'], 'SOURCE_POLICY_PENDING')
            with self.assertRaisesRegex(ValueError, 'empty'):
                delivery.initialize(root)
            with self.assertRaises(ValueError):
                delivery.preview(root)
            self.assertFalse((root/'preview/preview.mp4').exists())

    def test_closed_decision_schema(self):
        valid=decision('a'*64);validate('deliveryDecision',valid)
        for field, value in [('command','run arbitrary code'), ('stage','image'), ('binding_sha256','old')]:
            bad=copy.deepcopy(valid);bad[field]=value
            with self.assertRaises(ValueError):
                validate('deliveryDecision',bad)

    def test_approve_cli_requires_explicit_input_and_returns_json_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=subprocess.run([str(Path(__file__).resolve().parents[1]/'.venv/Scripts/python.exe'),
                '-m','static_comic','approve','--project',tmp],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('--input',json.loads(result.stderr)['error'])
