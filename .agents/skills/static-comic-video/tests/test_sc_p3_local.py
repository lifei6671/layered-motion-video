"""Explicit local ASR preserves raw evidence and remains separate from service caches."""
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import numpy as np

from scripts.create_fixture import create_fixture
from speech_support import synthetic_windows
from static_comic import speech
from static_comic.contracts import canonical
from static_comic.speech_audio import transcribe_local


class LocalASRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pcm(self, rate=16000, channels=1):
        target = self.root/'work/audio/align_16k.wav'; target.parent.mkdir(parents=True)
        with wave.open(str(target), 'wb') as stream:
            stream.setframerate(rate); stream.setnchannels(channels); stream.setsampwidth(2)
            stream.writeframes(struct.pack('<hhh', -32768, 0, 32767) * channels)

    def test_locked_offline_model_receives_exact_pcm_and_retains_raw_word_times(self):
        self.pcm()
        word = SimpleNamespace(word='原声', start=np.float64(0.1), end=np.float64(0.3), probability=np.float32(0.9))
        segment = SimpleNamespace(start=np.float64(0.1), end=np.float64(0.4), text='原声。', words=[word])
        with patch('scripts.probe_models.verify_model', return_value=self.root) as verify, \
                patch('faster_whisper.WhisperModel') as model:
            model.return_value.transcribe.return_value = (iter([segment]), SimpleNamespace(language='zh'))
            result = transcribe_local(self.root, {'asr': {'revision': 'locked-test'}})
        verify.assert_called_once_with({'revision': 'locked-test'})
        self.assertTrue(model.call_args.kwargs['local_files_only'])
        values = model.return_value.transcribe.call_args.args[0]
        self.assertEqual(values.tolist(), [-1.0, 0.0, 32767/32768])
        self.assertEqual(result['provider'], 'locked_local_faster_whisper')
        self.assertEqual(result['response']['segments'][0]['words'][0]['start'], 0.1)
        self.assertIs(type(result['response']['segments'][0]['start']), float)
        self.assertIs(type(result['response']['segments'][0]['words'][0]['start']), float)
        self.assertIs(type(result['response']['segments'][0]['words'][0]['probability']), float)
        # The provider never clamps an out-of-audio result to manufacture a valid window.
        self.assertEqual(result['response']['segments'][0]['end'], 0.4)
        self.assertEqual(result['audio']['samples'], 3)

    def test_changed_model_or_wrong_pcm_fails_before_inference(self):
        self.pcm(rate=48000)
        with patch('scripts.probe_models.verify_model', return_value=self.root), \
                patch('faster_whisper.WhisperModel') as model:
            with self.assertRaisesRegex(ValueError, '16 kHz mono'):
                transcribe_local(self.root, {'asr': {}})
            model.assert_not_called()
        with patch('scripts.probe_models.verify_model', side_effect=ValueError('Changed model bytes')), \
                patch('faster_whisper.WhisperModel') as model:
            with self.assertRaisesRegex(ValueError, 'Changed model bytes'):
                transcribe_local(self.root, {'asr': {}})
            model.assert_not_called()

    def test_explicit_provider_cache_and_failure_do_not_silently_fall_back(self):
        create_fixture(self.root/'episode'); root = self.root/'episode'
        speech.prepare_audio(root, 'input/voice.wav')
        lock = self.root/'models.json'; lock.write_bytes(canonical({'asr': {}, 'alignment': {}}))
        board = json.loads((root/'input/storyboard.json').read_bytes())
        text = (root/'input/script.txt').read_text('utf-8-sig')
        coarse = {'backend_matches': True, 'response': {'segments': [
            {'start': s['speech_interval_samples'][0]/48000,
             'end': s['speech_interval_samples'][1]/48000, 'text': text[s['script_range'][0]:s['script_range'][1]]}
            for s in board['shots']]}}
        def worker(command, **kwargs):
            request = json.loads((root/command[-1]).read_bytes())
            return SimpleNamespace(returncode=0, stdout=canonical(synthetic_windows(request['plan'])), stderr=b'')
        def align(source):
            return speech.align_project(root, url='http://127.0.0.1:13900', models_lock=lock,
                                        technical_fixture=True, asr_source=source)
        with patch('scripts.probe_models.verify_model'), \
                patch.object(speech, 'transcribe_service', return_value=coarse) as service, \
                patch.object(speech, 'transcribe_local', side_effect=ValueError('local inference failed')) as local, \
                patch.object(speech.subprocess, 'run', side_effect=worker):
            self.assertEqual(align('voicestudio')['status'], 'PASS')
            previous = (root/'work/alignment/aligned.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'local inference failed'): align('local')
            self.assertEqual((root/'work/alignment/aligned.json').read_bytes(), previous)
            self.assertEqual(service.call_count, 1)
            local.side_effect = None; local.return_value = coarse
            self.assertEqual(align('local')['status'], 'PASS')
            self.assertEqual(align('local')['status'], 'PASS')
            self.assertEqual(local.call_count, 2)
            self.assertEqual(service.call_count, 1)


if __name__ == '__main__':
    unittest.main()
