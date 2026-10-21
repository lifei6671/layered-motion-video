"""Cache identity, recovery and live authorization regressions; receipts are TEST ONLY."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from static_comic import cache, delivery
from static_comic.contracts import canonical, digest
from static_comic.media import file_hash
from static_comic.project import compile_project
from static_comic.speech_audio import prepare_audio
from scripts.create_fixture import create_fixture


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = 0

    def build(self, temp):
        self.calls += 1
        (temp/'value.txt').write_text('complete')
        return {'valid': True}

    def test_identical_inputs_hit_and_content_version_change_miss(self):
        a, _ = cache.cached(self.root, 'probe', {'input': 1, 'version': 1}, self.build)
        b, _ = cache.cached(self.root, 'probe', {'input': 1, 'version': 1}, self.build)
        self.assertEqual(a, b); self.assertEqual(self.calls, 1)
        cache.cached(self.root, 'probe', {'input': 1, 'version': 2}, self.build)
        self.assertEqual(self.calls, 2)
        report = json.loads((self.root/'reports/cache/probe.json').read_bytes())
        self.assertEqual(report['reason'], 'inputs_or_version_changed')

    def test_missing_corrupt_key_and_uncommitted_payload_never_hit(self):
        for corruption in ('missing', 'bytes', 'key', 'manifest'):
            folder, _ = cache.cached(self.root, 'probe', {}, self.build)
            if corruption == 'missing': (folder/'value.txt').unlink()
            elif corruption == 'bytes': (folder/'value.txt').write_text('partial')
            elif corruption == 'manifest': (folder/'manifest.json').unlink()
            else:
                manifest = json.loads((folder/'manifest.json').read_bytes())
                manifest['key'] = '0'*64
                (folder/'manifest.json').write_bytes(canonical(manifest))
            before = self.calls
            cache.cached(self.root, 'probe', {}, self.build)
            self.assertEqual(self.calls, before+1, corruption)

    def test_failure_does_not_cache_half_product_and_retry_completes(self):
        def fail(temp):
            (temp/'value.txt').write_text('half')
            raise ValueError('injected build failure')
        with self.assertRaisesRegex(ValueError, 'injected'):
            cache.cached(self.root, 'probe', {}, fail)
        self.assertIsNone(cache.lookup(self.root, 'probe', {})[1])
        folder, _ = cache.cached(self.root, 'probe', {}, self.build)
        self.assertEqual((folder/'value.txt').read_text(), 'complete')

    def test_malformed_manifest_result_and_inventory_rebuild(self):
        for corrupt in ('missing_result', 'list_inventory', 'changed_result'):
            folder, _ = cache.cached(self.root, 'probe', {}, self.build)
            value = json.loads((folder/'manifest.json').read_bytes())
            if corrupt == 'missing_result': del value['result']
            elif corrupt == 'list_inventory': value['files'] = ['value.txt']
            else: value['result'] = {'valid': False}
            (folder/'manifest.json').write_bytes(canonical(value))
            before = self.calls
            _, result = cache.cached(self.root, 'probe', {}, self.build)
            self.assertEqual(self.calls, before+1)
            self.assertEqual(result, {'valid': True})

    def test_publication_failure_rolls_back_existing_outputs(self):
        cache.publish(self.root, {'a': b'old-a', 'b': b'old-b'})
        real = cache.os.replace
        def replace(src, dst):
            if str(src).endswith('.tmp') and Path(dst).name == 'b':
                raise OSError('injected replace failure')
            return real(src, dst)
        with patch.object(cache.os, 'replace', side_effect=replace), self.assertRaises(OSError):
            cache.publish(self.root, {'a': b'new-a', 'b': b'new-b'})
        self.assertEqual((self.root/'a').read_bytes(), b'old-a')
        self.assertEqual((self.root/'b').read_bytes(), b'old-b')
        self.assertEqual({p.name for p in self.root.iterdir()}, {'a', 'b'})

    def test_cache_manifest_cannot_escape_entry(self):
        folder, _ = cache.cached(self.root, 'probe', {}, self.build)
        value = json.loads((folder/'manifest.json').read_bytes())
        value['files'] = {'../../outside': '0'*64}
        (folder/'manifest.json').write_bytes(canonical(value))
        self.assertIsNone(cache.lookup(self.root, 'probe', {})[1])

    def test_attempt_failure_identifies_retained_old_inputs(self):
        record = {'snapshot': {'old': True}, 'files': {'output/final.mp4': 'a'*64}}
        cache.publish(self.root, {'reports/render.json': canonical(record)})
        with self.assertRaises(ValueError):
            with cache.operation(self.root, 'mux', 'reports'):
                raise ValueError('injected')
        report = json.loads((self.root/'reports/attempt.json').read_bytes())
        self.assertEqual(report['status'], 'FAILED')
        self.assertEqual(report['retained_previous']['render']['input_digest'], digest(record['snapshot']))
        self.assertEqual(json.loads((self.root/'reports/render.json').read_bytes()), record)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'episode'
        create_fixture(self.root)

    def test_audio_hit_corruption_and_failure_preserve_master(self):
        first = prepare_audio(self.root, 'input/voice.wav')
        with patch('static_comic.speech_audio.subprocess.run', side_effect=AssertionError('decoded on hit')):
            self.assertEqual(prepare_audio(self.root, 'input/voice.wav'), first)
        master = self.root/'work/audio/master_48k.wav'
        original = master.read_bytes()
        source = self.root/'input/voice.wav'
        source.write_bytes(b'invalid audio')
        with self.assertRaisesRegex(ValueError, 'decoding failed'):
            prepare_audio(self.root, 'input/voice.wav')
        self.assertEqual(master.read_bytes(), original)

    def test_compile_hits_images_and_reprocesses_only_changed_image(self):
        compile_project(self.root, technical_fixture=True)
        with patch('static_comic.project.prepare_image', side_effect=AssertionError('reprocessed')):
            compile_project(self.root, technical_fixture=True)
        from PIL import Image
        board = json.loads((self.root/'input/storyboard.json').read_bytes())
        manifest = json.loads((self.root/'assets/images/manifest.json').read_bytes())
        path = self.root/board['shots'][0]['image']
        with Image.open(path) as image:
            image.putpixel((100,100), (255,0,0)); image.save(path)
        sha = file_hash(path)
        manifest['assets'][0]['sha256'] = sha
        board['shots'][0]['transition_out']['image_hashes'][0] = sha
        cache.publish(self.root, {'input/storyboard.json': canonical(board),
                                  'assets/images/manifest.json': canonical(manifest)})
        from static_comic.project import prepare_image
        with patch('static_comic.project.prepare_image', wraps=prepare_image) as prepare:
            compile_project(self.root, technical_fixture=True)
        self.assertEqual(prepare.call_count, 1)

    def test_validation_is_read_only_and_corrupt_staging_blocks(self):
        compile_project(self.root, technical_fixture=True, write=False)
        self.assertFalse((self.root/'work/cache').exists())
        result = compile_project(self.root, technical_fixture=True)
        staged = self.root/'work/remotion/technical/public'/result['staging']['images'][0]['staged_image']
        staged.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Corrupt staged'):
            compile_project(self.root, technical_fixture=True)


if __name__ == '__main__':
    unittest.main()
