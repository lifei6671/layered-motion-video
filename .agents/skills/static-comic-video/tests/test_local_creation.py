"""Local production needs actual content approval, not commercial declarations."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import image_support
from human_support import simulated
from scripts.create_fixture import create_fixture
from static_comic import image_supply as images
from static_comic.contracts import validate
from static_comic.project import compile_project
from test_sc_p1 import approved_test_project, read, save


class LocalCreationTests(unittest.TestCase):
    def test_all_channels_compile_without_commercial_approval_or_license_paperwork(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            board = create_fixture(root)
            policy = read(root, images.POLICY)
            assignments = [{"source_mode": mode, "channel": "synthetic-" + mode} for mode in
                           ("agent_generate", "third_party_retrieve", "manual_generate")]
            policy.update(mode="mixed", default_channel=None, allowed_channels=assignments,
                          shots={s["id"]: a for s, a in zip(board["shots"], assignments)})
            save(root, images.POLICY, policy)
            original_brief = image_support.make_brief
            original_submission = image_support.make_submission
            original_decision = image_support.decision_for

            def brief(board):
                value = original_brief(board)
                del value['publication_scope']
                return value

            def submission(root, req, index):
                value = original_submission(root, req, index)
                del value['license_evidence']
                if index == 0:
                    del value['license']
                else:
                    value['license'] = {'publication_allowed': False}
                value['references'] = [{'source_uri': 'https://example.invalid/reference',
                                        'sha256': 'a' * 64, 'version': 'test-only',
                                        'derivation_allowed': False}]
                return value

            def decision(root):
                value = original_decision(root)
                for index, item in enumerate(value['items']):
                    for key in ('publication_rights', 'attribution_ready'):
                        if index == 0:
                            del item['checks'][key]
                        else:
                            item['checks'][key] = False
                return simulated('images', value)

            with patch.object(image_support, 'make_brief', brief), \
                    patch.object(image_support, 'make_submission', submission), \
                    patch.object(image_support, 'decision_for', decision):
                approved_test_project(root)
            self.assertEqual(images.verify(root)['status'], 'PASS')
            self.assertEqual(compile_project(root)['status'], 'PASS')
            images.report(root)  # Missing publication scope is also valid in the report.
            assets = read(root, images.MANIFEST)['assets']
            self.assertNotIn('license', assets[0])
            self.assertEqual(assets[1]['license'], {'publication_allowed': False})
            self.assertNotIn('publication_scope', images.requests(root)['brief'])
            records = images.supply(root)['records']
            self.assertFalse(records[1]['review']['item']['checks']['publication_rights'])
            self.assertNotIn('publication_rights', records[0]['review']['item']['checks'])
            self.assertFalse(records[2]['candidate']['submission']['references'][0]['derivation_allowed'])

    def test_optional_metadata_still_has_a_valid_shape(self):
        validate('license', {})
        validate('license', {'publication_allowed': False})
        with self.assertRaises(ValueError):
            validate('license', {'publication_allowed': 'yes'})
        checks = {name: True for name in images.VISUAL_CHECKS}
        validate('imageChecks', checks)
        del checks['motion_safe']
        with self.assertRaises(ValueError):
            validate('imageChecks', checks)
