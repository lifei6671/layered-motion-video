"""Chat confirmation never needs a user terminal; receipts still bind scope/content."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_support import simulated
from static_comic import human_review
from static_comic.contracts import digest, validate
from static_comic.project import check_human


class ChatConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.authority = self.root / 'test-only.key'
        self.key_patch = patch.object(human_review, 'KEY_PATH', self.authority)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.proposal = {'payload_sha256': 'a' * 64}
        self.evidence = {'thread_id': 'SYNTHETIC-TEST-ONLY', 'message_id': 'test-message-1',
                         'user_message': '确认本次来源；不批准图片计划或成片。',
                         'scope': 'policy', 'decision_sha256': digest(self.proposal)}

    def test_cli_records_chat_without_tty_then_returns_existing_application_contract(self):
        (self.root / 'proposal.json').write_text(json.dumps(self.proposal), encoding='utf-8')
        (self.root / 'reply.json').write_text(json.dumps(self.evidence), encoding='utf-8')
        with patch('sys.stdin.isatty', return_value=False), redirect_stdout(StringIO()), \
                patch('builtins.input', side_effect=AssertionError('Must not ask for terminal confirmation')):
            result = human_review.main(['--project', str(self.root), '--scope', 'policy',
                                        '--input', 'proposal.json', '--conversation', 'reply.json'])
        self.assertEqual(result['status'], 'CONFIRMATION_RECORDED')
        signed = json.loads((self.root / result['input']).read_text(encoding='utf-8'))
        self.assertEqual(signed['human']['confirmation']['source'], 'conversation')
        self.assertEqual(signed['human']['confirmation']['conversation'], self.evidence)
        check_human(signed['human'], scope='policy', expected=self.proposal)
        self.assertFalse((self.root / 'input/image_source_policy.json').exists())

    def test_wrong_binding_or_incomplete_evidence_does_not_create_key(self):
        changes = [('scope', 'plan'), ('decision_sha256', 'b' * 64),
                   ('thread_id', ' '), ('user_message', ''), ('message_id', ' ')]
        for field, value in changes:
            evidence = dict(self.evidence, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                human_review.conversation('policy', self.proposal, evidence)
            self.assertFalse(self.authority.exists())
        missing = dict(self.evidence)
        del missing['user_message']
        with self.assertRaises(ValueError):
            human_review.conversation('policy', self.proposal, missing)
        self.assertFalse(self.authority.exists())

    def test_evidence_and_scope_cannot_be_changed_after_signing(self):
        signed = human_review.conversation('policy', self.proposal, self.evidence)
        for field in ('user_message', 'thread_id', 'message_id'):
            bad = deepcopy(signed['human'])
            bad['confirmation']['conversation'][field] += 'tampered'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'signature'):
                check_human(bad, scope='policy', expected=self.proposal)
        with self.assertRaises(ValueError):
            check_human(signed['human'], scope='plan', expected=self.proposal)
        with self.assertRaisesRegex(ValueError, 'stale'):
            check_human(signed['human'], scope='policy', expected={'payload_sha256': 'b' * 64})
        self.assertNotIn('human', self.proposal)

    def test_optional_message_id_and_rejection_are_preserved(self):
        decision = {'stage': 'preview', 'binding_sha256': 'c' * 64, 'decision': 'REJECTED',
                    'checks': {'semantics': False, 'full_listening': False, 'formal_quality': False},
                    'reason': '请修改镜头'}
        evidence = {'thread_id': 'SYNTHETIC-TEST-ONLY', 'user_message': '不同意这个预览，请修改镜头。',
                    'scope': 'preview', 'decision_sha256': digest(decision)}
        signed = human_review.conversation('preview', decision, evidence)
        self.assertEqual(signed['decision'], 'REJECTED')
        check_human(signed['human'], scope='preview', expected=decision)
        with self.assertRaisesRegex(ValueError, 'stage'):
            human_review.conversation('final', decision, dict(evidence, scope='final'))

    def test_old_terminal_receipts_remain_valid_and_source_shapes_are_checked(self):
        terminal = simulated('policy', self.proposal, source='local_terminal')
        check_human(terminal['human'], scope='policy', expected=self.proposal)
        missing = deepcopy(terminal['human'])
        missing['confirmation']['source'] = 'conversation'
        with self.assertRaises(ValueError):
            validate('human', missing)
        extra = deepcopy(terminal['human'])
        extra['confirmation']['conversation'] = self.evidence
        with self.assertRaises(ValueError):
            validate('human', extra)


if __name__ == '__main__':
    unittest.main()
