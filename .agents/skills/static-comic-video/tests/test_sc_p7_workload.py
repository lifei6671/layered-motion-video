import json
from pathlib import Path
import tempfile
import unittest

from scripts.benchmark_fixture import create_workload, run_benchmark
from static_comic.project import compile_project


class WorkloadTests(unittest.TestCase):
    def test_exact_duration_and_technical_isolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            for seconds in (60, 180):
                root = Path(temporary) / str(seconds)
                create_workload(root, seconds)
                result = compile_project(root, technical_fixture=True, write=False)
                self.assertEqual(result["total_frames"], seconds * 30)
                self.assertIn("TECHNICAL", result["artifact_kind"].upper())
                with self.assertRaises(ValueError):
                    compile_project(root, write=False)

    def test_existing_inputs_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "keep.txt").write_text("unchanged", encoding="utf-8")
            with self.assertRaises(ValueError):
                create_workload(root, 60)
            self.assertEqual((root / "keep.txt").read_text(encoding="utf-8"), "unchanged")

    def test_warm_requires_successful_matching_cold_workload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            create_workload(root, 60)
            with self.assertRaisesRegex(ValueError, "cold"):
                run_benchmark(root, "warm", 60)
            with self.assertRaisesRegex(ValueError, "requested"):
                run_benchmark(root, "warm", 180)


if __name__ == "__main__":
    unittest.main()
