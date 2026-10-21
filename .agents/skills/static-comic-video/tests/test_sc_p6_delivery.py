"""SC-P6 invalidation matrix. Renderer doubles test orchestration, not media quality.

Real Remotion/FFmpeg and full decoded media are independently exercised by P5.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from static_comic import delivery
from static_comic.cache import publish
from static_comic.contracts import canonical, digest
from static_comic.media import file_hash
from scripts.create_fixture import create_fixture
from test_sc_p5 import decision


class DeliveryCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'episode'
        create_fixture(self.root)
        self.commands = []
        self.fail_kind = None
        runtime = {'sources': {'renderer/static-comic/src/index.tsx': 'test-code'}, 'installed': {},
                   'tools': {n: {'sha256': n} for n in ('node', 'browser', 'ffmpeg')}}
        self.runtime = runtime
        for target, kwargs in (( 'runtime', {'return_value': runtime}),
                               ('run', {'side_effect': self.run_command}),
                               ('verify_media', {'return_value': {'status': 'PASS', 'TEST_DOUBLE': True}})):
            context = patch.object(delivery, target, **kwargs)
            context.start(); self.addCleanup(context.stop)
        self.pre = delivery.preview(self.root, True)
        delivery.approve(self.root, decision(self.pre['binding_sha256']), True)
        delivery.render_visual(self.root, True)
        delivery.mux(self.root, True)

    def run_command(self, command, **kwargs):
        if command[2:3] == ['bundle']:
            directory = Path(next(s.split('=',1)[1] for s in command if s.startswith('--out-dir=')))
            directory.mkdir(); (directory/'index.html').write_text('TEST BUNDLE')
            kind = 'bundle'
        elif command[2:3] == ['render']:
            target = Path(command[5]); target.parent.mkdir(parents=True, exist_ok=True)
            props = json.loads((self.root/'work/remotion/technical/props.json').read_bytes())
            target.write_bytes(canonical({'TEST_RENDER': props, 'scale': command[command.index('--image-format=png')+1]}))
            kind = 'render'
        else:
            Path(command[-1]).write_bytes(canonical({'TEST_MUX': [file_hash(command[i+1])
                                                                    for i,s in enumerate(command) if s == '-i']}))
            kind = 'mux'
        self.commands.append(kind)
        if self.fail_kind == kind:
            raise ValueError('injected '+kind+' failure after partial output')
        return b''

    def edit_board(self, change):
        board = json.loads((self.root/'input/storyboard.json').read_bytes())
        change(board)
        publish(self.root, {'input/storyboard.json': canonical(board)})

    def cache_status(self, stage):
        return json.loads((self.root/f'reports/cache/{stage}.json').read_bytes())['status']

    def test_identical_rerun_hits_all_stages_and_preserves_binding(self):
        before = len(self.commands)
        pre = delivery.preview(self.root, True)
        self.assertEqual(pre['binding_sha256'], self.pre['binding_sha256'])
        delivery.render_visual(self.root, True); delivery.mux(self.root, True)
        self.assertEqual(len(self.commands), before)
        for name in ('audio','image-authorization','timeline','staging','image-shot-001','remotion-build',
                     'visual-preview','visual-final','mux-preview','mux-final'):
            self.assertEqual(self.cache_status(name), 'HIT', name)

    def test_explanation_only_reuses_visual_but_requires_new_approval(self):
        self.edit_board(lambda b: b['shots'][0]['transition_out'].update(intent='changed explanation'))
        before = len(self.commands)
        pre = delivery.preview(self.root, True)
        self.assertEqual(len(self.commands), before)

        self.assertNotEqual(pre['binding_sha256'], self.pre['binding_sha256'])
        with self.assertRaisesRegex(ValueError, 'explicit'):
            delivery.render_visual(self.root, True)
        delivery.approve(self.root, decision(pre['binding_sha256']), True)
        delivery.render_visual(self.root, True)
        self.assertEqual(len(self.commands), before)

    def test_imported_schema_change_rebuilds_bundle_and_visual(self):
        self.runtime['sources']['schemas/contracts.json'] = 'changed-imported-schema'
        before = len(self.commands)
        delivery.preview(self.root, True)
        self.assertEqual(self.commands[before:before+2], ['bundle','render'])
        self.assertEqual(self.cache_status('remotion-build'), 'REBUILT')
        self.assertEqual(self.cache_status('visual-preview'), 'REBUILT')

    def test_voice_same_timeline_reuses_visual_and_remuxes(self):
        source = self.root/'input/voice.wav'
        with wave.open(str(source), 'rb') as stream:
            params = stream.getparams(); frames = bytearray(stream.readframes(stream.getnframes()))
        frames[100:102] = b'\x10\x00'
        with wave.open(str(source), 'wb') as stream:
            stream.setparams(params); stream.writeframes(frames)
        self.edit_board(lambda b: b['audio'].update(sha256=file_hash(source)))
        before = len(self.commands)
        pre = delivery.preview(self.root, True)
        self.assertEqual(self.commands[before:], ['mux'])
        self.assertEqual(self.cache_status('image-authorization'), 'HIT')
        self.assertNotEqual(pre['binding_sha256'], self.pre['binding_sha256'])
        with self.assertRaises(ValueError): delivery.render_visual(self.root, True)
        delivery.approve(self.root, decision(pre['binding_sha256']), True)
        delivery.render_visual(self.root, True); delivery.mux(self.root, True)
        self.assertEqual(self.commands[before:], ['mux','mux'])

    def test_motion_and_transition_execution_change_rebuild_entire_visual(self):
        changes = [lambda b: b['shots'][0]['motion'].update(scale_to=1.15),
                   lambda b: b['shots'][0]['transition_out'].update(type='wipe_from_left'),
                   lambda b: b['shots'][0]['transition_out'].update(placement='center_on_anchor'),
                   lambda b: b['shots'][0]['transition_out'].update(duration_frames=14),
                   lambda b: b['shots'][1].update(start_samples=b['shots'][1]['start_samples']+1600,
                                                 boundary_reason='TEST changed boundary')]
        for change in changes:
            self.edit_board(change)
            before = len(self.commands)
            delivery.preview(self.root, True)
            self.assertIn('render', self.commands[before:])
            self.assertEqual(self.cache_status('visual-preview'), 'REBUILT')
            with self.assertRaises(ValueError): delivery.render_visual(self.root, True)

    def test_voice_duration_changes_total_frames_and_renders(self):
        path = self.root/'input/voice.wav'
        with wave.open(str(path), 'rb') as stream:
            params = stream.getparams(); frames = stream.readframes(stream.getnframes())
        with wave.open(str(path), 'wb') as stream:
            stream.setparams(params); stream.writeframes(frames+b'\0'*(1600*params.nchannels*2))
        self.edit_board(lambda b: b['audio'].update(sha256=file_hash(path),
                                                   duration_samples=b['audio']['duration_samples']+1600))
        before = len(self.commands)
        delivery.preview(self.root, True)
        props = json.loads((self.root/'work/remotion/technical/props.json').read_bytes())
        self.assertEqual(props['video']['total_frames'], 361)
        self.assertEqual(self.commands[before:], ['render', 'mux'])

    def test_missing_image_or_corrupt_staging_retains_old_final(self):
        final = self.root/'output/technical/final.mp4'; old = final.read_bytes()
        board = json.loads((self.root/'input/storyboard.json').read_bytes())
        path = self.root/board['shots'][0]['image']; data = path.read_bytes(); path.unlink()
        with self.assertRaises(ValueError): delivery.preview(self.root, True)
        self.assertEqual(final.read_bytes(), old)
        path.write_bytes(data)
        staging = json.loads((self.root/'work/remotion/technical/staging-manifest.json').read_bytes())
        path = self.root/'work/remotion/technical/public'/staging['images'][0]['staged_image']
        path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Corrupt staged'): delivery.preview(self.root, True)
        self.assertEqual(final.read_bytes(), old)

    def test_missing_or_corrupt_published_visual_forces_render(self):
        path = self.root/'work/remotion/technical/visual.mp4'
        for corrupt in ('missing', 'bytes'):
            if corrupt == 'missing': path.unlink()
            else: path.write_bytes(b'bad')
            before = len(self.commands)
            delivery.render_visual(self.root, True)
            self.assertEqual(self.commands[before:], ['render'])
            self.assertEqual(self.cache_status('visual-final'), 'REBUILT')

    def test_render_failure_retains_preview_final_and_approval_retry_succeeds(self):
        names = ('preview/technical/preview.mp4', 'output/technical/final.mp4', 'review/technical/approval.json')
        old = {n: (self.root/n).read_bytes() for n in names}
        self.edit_board(lambda b: b['shots'][0]['transition_out'].update(duration_frames=14))
        self.fail_kind = 'render'
        with self.assertRaisesRegex(ValueError, 'injected'):
            delivery.preview(self.root, True)
        self.assertEqual({n: (self.root/n).read_bytes() for n in names}, old)
        status = delivery.status(self.root, True)
        self.assertEqual(status['status'], 'FAILED')
        self.assertFalse(status['current_success'])
        self.assertTrue(status['retained_previous']['render']['files_verified'])
        self.fail_kind = None
        delivery.preview(self.root, True)
        self.assertEqual(delivery.status(self.root, True)['status'], 'PREVIEW_AUDIO_MUXED')

    def test_mux_failure_preserves_final_and_approval(self):
        # Force a new mux key without changing or invalidating current review inputs.
        original = delivery.versions
        final = self.root/'output/technical/final.mp4'
        approval = self.root/'review/technical/approval.json'
        old = final.read_bytes(), approval.read_bytes()
        self.fail_kind = 'mux'
        with patch.object(delivery, 'versions', side_effect=lambda *a,**kw: {**original(*a,**kw), 'new': True}):
            with self.assertRaisesRegex(ValueError, 'injected'):
                delivery.mux(self.root, True)
        self.assertEqual((final.read_bytes(), approval.read_bytes()), old)
        self.assertEqual(delivery.status(self.root, True)['status'], 'FAILED')
        self.fail_kind = None
        self.assertEqual(delivery.mux(self.root, True)['status'], 'OUTPUT_VERIFIED')


if __name__ == '__main__':
    unittest.main()
