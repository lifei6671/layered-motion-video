"""Targeted regressions. All confirmations use a disposable TEST-ONLY authority."""
import copy
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_support import simulated
from image_support import HUMAN, decision_for, make_submission
import test_sc_p3a as p3a
from static_comic import cache, human_review, image_supply as images
from static_comic.contracts import digest, validate
from static_comic.media import run
from static_comic.paths import process_args, process_path, resolve_path
from static_comic.project import check_human


class ConfirmationTests(unittest.TestCase):
    def test_shared_confirmation_schema(self):
        cases = json.loads((Path(__file__).resolve().parents[1]/'fixtures/human-confirmation-contract-cases.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                if case['valid']:
                    validate(case['kind'], case['value'])
                    with self.assertRaises(ValueError):
                        check_human(case['value']['human'], scope='policy')
                else:
                    with self.assertRaises(ValueError): validate(case['kind'], case['value'])

    def test_plain_forged_and_tampered_receipts_fail(self):
        with self.assertRaisesRegex(ValueError, 'local human confirmation'):
            check_human(HUMAN, scope='policy', expected={'payload_sha256': 'a'*64})
        decision = simulated('policy', {'human': HUMAN, 'payload_sha256': 'a'*64})
        check_human(decision['human'], scope='policy', expected={'payload_sha256': 'a'*64})
        for field in ('actor', 'at', 'evidence'):
            bad = copy.deepcopy(decision['human']); bad[field] += 'tamper'
            with self.assertRaisesRegex(ValueError, 'signature'):
                check_human(bad, scope='policy')
        with self.assertRaisesRegex(ValueError, 'stale'):
            check_human(decision['human'], scope='policy', expected={'payload_sha256': 'b'*64})
        with self.assertRaises(ValueError):
            check_human(decision['human'], scope='plan')

    def test_pipe_or_cancel_cannot_issue_receipt_or_key(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(human_review, 'KEY_PATH', Path(tmp)/'key'):
            proposal = {'payload_sha256': 'a'*64, 'human': HUMAN}
            with patch('sys.stdin.isatty', return_value=False), self.assertRaisesRegex(ValueError, 'interactive'):
                human_review.interactive('policy', proposal)
            with patch('sys.stdin.isatty', return_value=True), patch('sys.stdout', StringIO()) as out:
                with patch.object(out, 'isatty', return_value=True), patch('builtins.input', return_value='NO'):
                    with self.assertRaisesRegex(ValueError, 'cancelled'):
                        human_review.interactive('policy', proposal)
            self.assertFalse((Path(tmp)/'key').exists())

    def test_another_account_key_cannot_verify(self):
        decision = simulated('plan', {'human': HUMAN, 'payload_sha256': 'a'*64})
        with tempfile.TemporaryDirectory() as tmp, patch.object(human_review, 'KEY_PATH', Path(tmp)/'key'):
            (Path(tmp)/'key').write_bytes(b'x'*32)
            with self.assertRaisesRegex(ValueError, 'signature'):
                check_human(decision['human'], scope='plan')


class PolicyAndPublicationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = p3a.ImageSupplyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def test_single_and_mixed_repeat_query_is_read_only_and_approved(self):
        for mixed in (False, True):
            req = self.fixture.prepare(mixed)
            before = (self.root/images.POLICY).read_bytes()
            for _ in range(2):
                result = images.policy_options(self.root)
                self.assertEqual(result['status'], 'APPROVED')
                self.assertNotIn('question', result)
                self.assertEqual(len(result['shots']), 3)
                self.assertEqual(result['payload_sha256'], images.read_doc(self.root, images.POLICY, 'policy')['confirmation']['payload_sha256'])
            self.assertEqual((self.root/images.POLICY).read_bytes(), before)
            images.dispatch(self.root, req['shots'][0]['shot_id'], unavailable='Observed tool unavailable')
            result = images.policy_options(self.root)
            self.assertEqual(result['status'], 'APPROVED')
            self.assertIn('UNAVAILABLE', [c['status'] for c in result['channels']])

    def test_changed_policy_and_forged_confirmation_require_review(self):
        self.fixture.prepare()
        policy = images.read_doc(self.root, images.POLICY, 'policy')
        for change in ('channel', 'human'):
            bad = copy.deepcopy(policy)
            if change == 'channel': bad['default_channel'] = 'changed'
            else: bad['confirmation']['human'] = HUMAN
            images.write_docs(self.root, {images.POLICY: bad})
            self.assertEqual(images.policy_options(self.root)['status'], 'REVIEW_REQUIRED')

    def test_forged_image_review_and_repeated_old_receipt_blocked(self):
        self.fixture.acquire()
        decision = decision_for(self.root)
        forged = copy.deepcopy(decision); forged['human'] = HUMAN
        with self.assertRaisesRegex(ValueError, 'local human confirmation'):
            images.review(self.root, forged)
        images.review(self.root, decision)
        before = (self.root/images.APPROVALS).read_bytes()
        with self.assertRaisesRegex(ValueError, 'stale candidate'):
            images.review(self.root, decision)
        self.assertEqual((self.root/images.APPROVALS).read_bytes(), before)
        self.assertEqual(images.verify(self.root)['status'], 'PASS')

    def test_recomputed_public_hashes_cannot_change_signed_source_or_license(self):
        req = self.fixture.acquire()
        images.review(self.root, decision_for(self.root))
        supply = images.supply(self.root)
        manifest = images.read_doc(self.root, images.MANIFEST, 'manifest')
        approvals = images.read_doc(self.root, images.APPROVALS, 'approvals')
        for field in ('license', 'author', 'source_uri'):
            state, assets, receipts = copy.deepcopy((supply, manifest, approvals))
            record = state['records'][0]
            if field == 'license': record['candidate']['submission'][field]['usage_scope'] = 'CHANGED AFTER SIGNING'
            else: record['candidate']['submission'][field] = 'https://example.invalid/changed'
            asset = images.asset_for(req, record, record['review']['human'])
            assets['assets'][0] = asset
            receipts['receipts'][0].update(asset_sha256=digest(asset), supply_sha256=digest(record))
            images.write_docs(self.root, {images.SUPPLY: state, images.MANIFEST: assets, images.APPROVALS: receipts})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'acquisition record changed'):
                images.verify(self.root)
        images.write_docs(self.root, {images.SUPPLY: supply, images.MANIFEST: manifest, images.APPROVALS: approvals})
        self.assertEqual(images.verify(self.root)['status'], 'PASS')
        original = supply['records'][0]['review']['item']['record_sha256']
        history = self.root/f'review/images/events/{original}.json'
        original_bytes = history.read_bytes()
        bad = json.loads(original_bytes); bad['reason'] += ' tamper'
        images.write_docs(self.root, {f'review/images/events/{original}.json': bad})
        with self.assertRaisesRegex(ValueError, 'acquisition record changed'):
            images.verify(self.root)
        history.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing'):
            images.verify(self.root)
        history.write_bytes(original_bytes)
        self.assertEqual(images.verify(self.root)['status'], 'PASS')

    def test_batch_preflight_failure_preserves_other_approved_shot(self):
        self.fixture.acquire()
        images.review(self.root, decision_for(self.root, ['SHOT-001']))
        before = {name: (self.root/name).read_bytes() for name in (images.SUPPLY, images.APPROVALS, images.MANIFEST)}
        decision = decision_for(self.root, ['SHOT-002', 'SHOT-003'])
        decision['items'][-1]['checks']['narrative'] = False
        with self.assertRaisesRegex(ValueError, 'visual checks'):
            images.review(self.root, simulated('images', decision))
        for name, data in before.items(): self.assertEqual((self.root/name).read_bytes(), data)
        self.assertEqual(images.report(self.root)['shots'][0]['status'], 'APPROVED')

    def test_mid_publication_failure_rolls_back_then_retry_and_cache_gate(self):
        req = self.fixture.acquire()
        images.review(self.root, decision_for(self.root))
        before_asset = (self.root/'assets/images/shot_0001.png').read_bytes()
        # Acquire different pixels without overwriting the approved formal input.
        from PIL import Image
        source = self.root/'work/images/new.png'
        Image.new('RGB', (320, 180), 'red').save(source)
        submission = make_submission(self.root, req, 0); submission['file'] = 'work/images/new.png'
        images.ingest(self.root, submission)
        decision = decision_for(self.root, ['SHOT-001'])
        names = (images.SUPPLY, images.MANIFEST, images.APPROVALS, 'assets/images/shot_0001.png')
        before = {name: (self.root/name).read_bytes() for name in names}
        original = cache.os.replace
        def fail(src, dst):
            if str(src).endswith('.tmp') and Path(dst).name == 'image_approvals.json':
                raise OSError('injected publish failure')
            return original(src, dst)
        with patch.object(cache.os, 'replace', side_effect=fail), self.assertRaisesRegex(OSError, 'injected'):
            images.review(self.root, decision)
        for name, raw in before.items(): self.assertEqual((self.root/name).read_bytes(), raw)
        self.assertEqual(images.report(self.root)['shots'][1]['status'], 'APPROVED')
        # report changes the pending record; obtain the new exact review target.
        images.review(self.root, decision_for(self.root, ['SHOT-001']))
        self.assertNotEqual((self.root/'assets/images/shot_0001.png').read_bytes(), before_asset)
        self.assertEqual(images.verify(self.root)['status'], 'PASS')
        (self.root/'assets/images/shot_0001.png').write_bytes(before_asset)
        with self.assertRaisesRegex(ValueError, 'formal image bytes changed'):
            images.verify(self.root)

    def test_failed_rollback_retains_original_backup(self):
        cache.publish(self.root, {'a': b'old-a', 'b': b'old-b'})
        original = cache.os.replace
        def fail(src, dst):
            if Path(dst).name == 'b' or str(src).endswith('.bak'):
                raise OSError('injected persistent failure')
            return original(src, dst)
        with patch.object(cache.os, 'replace', side_effect=fail), self.assertRaisesRegex(ValueError, 'rollback incomplete'):
            cache.publish(self.root, {'a': b'new-a', 'b': b'new-b'})
        backups = list(self.root.glob('.a.*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'old-a')
        os.replace(backups[0], self.root/'a')
        cache.publish(self.root, {'a': b'new-a', 'b': b'new-b'})
        self.assertEqual((self.root/'a').read_bytes(), b'new-a')


class WindowsBoundaryTests(unittest.TestCase):
    def test_all_path_argument_forms_and_unsafe_namespaces(self):
        normal = 'D:\\中文 空格\\file.json'
        extended = '\\\\?\\' + normal
        argv, cwd = process_args(['node', extended, '--props='+extended, '--public-dir='+extended,
                                  '--browser-executable='+extended, '--out-dir='+extended], extended)
        self.assertEqual(cwd, normal)
        self.assertTrue(all('\\\\?\\' not in v for v in argv))
        self.assertEqual(process_path(normal), normal)
        self.assertEqual(process_args(['-select_streams', 'a:0', '-map', '0:v:0'])[0], ['-select_streams', 'a:0', '-map', '0:v:0'])
        for path in ('\\\\server\\share\\x', '\\\\?\\UNC\\server\\x', '\\\\.\\C:', 'D:relative', '\\\\?\\GLOBALROOT\\x'):
            with self.subTest(path=path), self.assertRaises(ValueError): process_path(path)

    @unittest.skipUnless(os.name == 'nt', 'Windows Studio path boundary')
    def test_studio_uses_same_adapter_without_launching_server(self):
        from static_comic import delivery
        with tempfile.TemporaryDirectory(prefix='Studio 中文 ') as tmp:
            root = Path('\\\\?\\'+tmp)
            with patch.object(delivery, 'snapshot'), patch.object(delivery, 'RENDERER', Path('\\\\?\\'+str(delivery.RENDERER))), patch.object(delivery.subprocess, 'Popen') as start:
                start.return_value.pid = 123
                result = delivery.studio(root, True)
                self.assertEqual(result['status'], 'STUDIO_STARTING')
                args, kwargs = start.call_args
                self.assertFalse(any('\\\\?\\' in str(v) for v in args[0]))
                self.assertFalse(str(kwargs['cwd']).startswith('\\\\?\\'))
                self.assertFalse(kwargs.get('shell', False))

    @unittest.skipUnless(os.name == 'nt', 'Windows extended-path integration')
    def test_real_node_unicode_space_script_cwd_and_json(self):
        with tempfile.TemporaryDirectory(prefix='中文 Node 路径 ') as tmp:
            root = Path(tmp)
            script = root/'入口 脚本.mjs'; data = root/'参数 中文.json'
            data.write_text('{"value":42}', encoding='utf-8')
            script.write_text("import fs from 'node:fs'; console.log(JSON.stringify({cwd:process.cwd(),data:JSON.parse(fs.readFileSync(process.argv[2],'utf8'))}));", encoding='utf-8')
            for prefix in ('', '\\\\?\\'):
                result = json.loads(run(['node', prefix+str(script), prefix+str(data)], cwd=prefix+tmp))
                self.assertEqual(result['data']['value'], 42)
                self.assertEqual(Path(result['cwd']), root)
                with self.assertRaises(ValueError): resolve_path(prefix+tmp, '../escape')
