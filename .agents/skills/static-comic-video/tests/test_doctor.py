import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from static_comic.doctor import local_cli, model_probe, path_probe, run


class DoctorTests(unittest.TestCase):
    def test_unicode_and_failure_propagation(self):
        self.assertEqual(path_probe()["status"], "PASS")

    def test_missing_local_cli_never_starts_download(self):
        with tempfile.TemporaryDirectory() as folder, patch("static_comic.doctor.run") as execute:
            result = local_cli("node", Path(folder))
        self.assertEqual(result["status"], "UNAVAILABLE")
        execute.assert_not_called()

    def test_missing_executable_and_timeout_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(run([str(Path(folder) / "missing.exe")], folder)["status"], "UNAVAILABLE")
            result = run([sys.executable, "-c", "import time; time.sleep(3)"], folder, timeout=0.05)
            self.assertEqual(result["status"], "UNAVAILABLE")

    def test_model_probe_is_explicit_and_offline(self):
        self.assertEqual(model_probe(None)["status"], "NOT_RUN")
        with patch("static_comic.doctor.run", return_value={"status": "PASS"}) as execute:
            model_probe(Path("models.json"))
        self.assertEqual(execute.call_args.kwargs["env"]["HF_HUB_OFFLINE"], "1")

    def test_argument_is_literal(self):
        payload = '中文 空格 & | %PATH% " value'
        result = run([sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1]))", payload], Path.cwd())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(json.loads(result["stdout"]), payload)


if __name__ == "__main__":
    unittest.main()
