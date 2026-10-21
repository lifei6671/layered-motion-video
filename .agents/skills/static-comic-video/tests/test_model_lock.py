import importlib.util
from pathlib import Path
import tempfile
import unittest


def script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lock = script("lock_models")
probe = script("probe_models")


class ModelLockTests(unittest.TestCase):
    def test_changed_weights_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            weight = root / "model.bin"
            weight.write_bytes(b"original")
            record = lock.entry(root, "test-revision")
            self.assertEqual(probe.verify_model(record), root.resolve())
            weight.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                probe.verify_model(record)

    def test_missing_and_additional_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            weight = root / "model.bin"
            weight.write_bytes(b"original")
            record = lock.entry(root, "test-revision")
            extra = root / "config.json"
            extra.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inventory changed"):
                probe.verify_model(record)
            extra.unlink()
            weight.unlink()
            with self.assertRaisesRegex(ValueError, "inventory changed"):
                probe.verify_model(record)


if __name__ == "__main__":
    unittest.main()
