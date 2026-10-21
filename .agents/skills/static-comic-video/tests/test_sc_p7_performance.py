"""Exercise the real Windows observer; no model inference or production approval."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/measure_performance.ps1"


@unittest.skipUnless(os.name == "nt" and shutil.which("pwsh"), "Windows PowerShell 7 required")
class PerformanceProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="SC P7 性能 ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_job(self, code, arguments=(), timeout=30):
        command = self.root / "command.json"
        command.write_text(json.dumps({"argv": [sys.executable, "-c", code, *arguments],
            "cwd": str(self.root), "label": "test", "cache_expectation": "none"}), encoding="utf-8")
        argv = ["pwsh", "-NoProfile", "-File", str(SCRIPT), "-CommandFile", str(command),
                "-OutputDirectory", str(self.root / "measurement"), "-IntervalSeconds", "0.25",
                "-TimeoutSeconds", str(timeout)]
        result = subprocess.run(argv, capture_output=True, timeout=timeout + 30)
        report = self.root / "measurement/measurement.json"
        return result, json.loads(report.read_text(encoding="utf-8-sig")) if report.exists() else None

    def test_process_tree_and_literal_arguments(self):
        literal = '中文 space & $(not_a_command) "quotes"'
        code = ("import subprocess,sys,time; sys.stdout.reconfigure(encoding='utf-8'); "
                "p=subprocess.Popen([sys.executable,'-c','import time; data=bytearray(32000000); time.sleep(3)']); "
                "print(sys.argv[1],flush=True); p.wait()")
        result, report = self.run_job(code, [literal])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["measurement_status"], "PASS")
        self.assertTrue(report["host"])
        self.assertGreaterEqual(max(row["tree_process_count"] for row in report["samples"]), 2)
        self.assertGreater(report["sampled_peak_tree_working_set_bytes"], 32000000)
        self.assertEqual(report["sampled_peak_browser_process_count"], 0)
        self.assertFalse(report["cache_verified"])
        self.assertEqual((self.root / "measurement/stdout.log").read_text(encoding="utf-8").strip(), literal)

    def test_child_failure_is_not_pass_and_existing_report_is_preserved(self):
        result, report = self.run_job("raise SystemExit(7)")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(report["status"], "FAIL")
        before = (self.root / "measurement/measurement.json").read_bytes()
        result, _ = self.run_job("print('must not run')")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "measurement/measurement.json").read_bytes(), before)

    def test_timeout_records_failure(self):
        result, report = self.run_job("import time; time.sleep(30)", timeout=2)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(report["status"], "TIMEOUT")
        self.assertLess(report["wall_seconds"], 15)

    def test_parent_exit_with_live_child_pipe_still_times_out(self):
        result, report = self.run_job(
            "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(0.75)",
            timeout=2)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(report["status"], "TIMEOUT")
        self.assertLess(report["wall_seconds"], 15)


if __name__ == "__main__":
    unittest.main()
