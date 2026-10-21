import copy
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from static_comic.media import check_video, mux_command, probe, run, verify_media


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sc-p5-音频 空格-')
        cls.root = Path(cls.tmp.name)
        cls.visual, cls.master, cls.muxed = [cls.root / n for n in ('visual.mp4', 'master.wav', 'preview.mp4')]
        cls.samples = 575088
        cls.make_audio(cls.master, cls.samples)
        cls.make_visual(cls.visual, 'red')
        run(mux_command(cls.visual, cls.master, cls.muxed))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def make_audio(path, samples):
        t = np.arange(samples) / 48000
        signal = np.stack([.3*np.sin(2*np.pi*220*t), .3*np.sin(2*np.pi*330*t)], axis=1)
        with wave.open(str(path), 'wb') as wav:
            wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(48000)
            wav.writeframes((signal*32767).astype('<i2').tobytes())

    @staticmethod
    def make_visual(path, color):
        run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'lavfi', '-i',
             f'color=c={color}:s=320x180:r=30', '-frames:v', '360', '-an', '-c:v', 'libx264',
             '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', path])

    def test_11981_master_retains_360_frames_and_head_tail_audio(self):
        result = verify_media(self.visual, self.master, frames=360, width=320, height=180, audible=self.muxed)
        self.assertEqual(result['tail_samples'], 912)
        self.assertTrue(result['decoded_video_matches'])
        self.assertEqual(result['audio']['content_windows'][-1]['end_sample'], self.samples)
        self.assertLess(result['audio']['padding_samples'], 1024)
        self.assertIn('skip_samples', str(result['audio']['first_packet']))

    def test_truncated_voice_is_rejected(self):
        short, target = self.root/'short.wav', self.root/'short.mp4'
        self.make_audio(short, self.samples-48000)
        run(mux_command(self.visual, short, target))
        with self.assertRaisesRegex(ValueError, 'effective playback'):
            verify_media(self.visual, self.master, frames=360, width=320, height=180, audible=target)

    def test_changed_video_stream_is_rejected(self):
        other, target = self.root/'other.mp4', self.root/'changed.mp4'
        self.make_visual(other, 'blue')
        run(mux_command(other, self.master, target))
        with self.assertRaisesRegex(ValueError, 'changed decoded video'):
            verify_media(self.visual, self.master, frames=360, width=320, height=180, audible=target)

    def test_silent_visual_and_exact_stream_layout_required(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            verify_media(self.muxed, self.master, frames=360, width=320, height=180)
        info = probe(self.visual)
        bad = copy.deepcopy(info); bad['streams'][0]['avg_frame_rate'] = '15/1'
        with self.assertRaisesRegex(ValueError, 'fps'):
            check_video(bad, 360, 320, 180, audible=False)

    def test_tail_must_be_less_than_one_frame(self):
        short = self.root/'too-short.wav'
        self.make_audio(short, self.samples-48000)
        with self.assertRaisesRegex(ValueError, 'less than one frame'):
            verify_media(self.visual, short, frames=360, width=320, height=180)
