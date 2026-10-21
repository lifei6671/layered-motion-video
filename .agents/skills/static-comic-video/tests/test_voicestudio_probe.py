import io
from unittest.mock import patch
from urllib.error import URLError
import unittest

from test_model_lock import script

probe = script("probe_voicestudio")


class VoiceStudioProbeTests(unittest.TestCase):
    def test_discovery_does_not_claim_inference_or_alignment(self):
        bodies = [b'{"status":"ok"}', b'{"paths":{},"components":{}}',
                  b'{"active":"whisperx","backends":[{"id":"whisperx"}]}',
                  b'{"ready":false,"missing":"model"}']
        with patch.object(probe, "urlopen", side_effect=[io.BytesIO(b) for b in bodies]) as request:
            result = probe.inspect_service("http://127.0.0.1:13900")
        self.assertEqual(result["status"], "PASS")  # Only HTTP discovery passed.
        self.assertFalse(result["checks"]["/dictation/readiness?purpose=transcribe"]["response"]["ready"])
        self.assertEqual(result["transcription_smoke"], "NOT_RUN")
        self.assertEqual(result["confirmed_text_alignment_acceptance"], "NOT_RUN")
        self.assertEqual(request.call_count, 4)

    def test_offline_service_is_not_success(self):
        with patch.object(probe, "urlopen", side_effect=URLError("offline")):
            self.assertEqual(probe.inspect_service("http://127.0.0.1:13900")["status"], "FAIL")

    def test_remote_url_rejected_before_request(self):
        with patch.object(probe, "urlopen") as request:
            with self.assertRaises(ValueError):
                probe.inspect_service("https://example.com")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
