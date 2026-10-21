"""The P3A corpus is also read by the renderer's Ajv tests."""
from pathlib import Path
import unittest

from static_comic.contracts import read_json, validate


class ImageContractTests(unittest.TestCase):
    def test_shared_image_contract_cases(self):
        path = Path(__file__).resolve().parents[1] / "fixtures/image-contract-cases.json"
        for case in read_json(path.read_bytes()):
            with self.subTest(case=case["name"]):
                if case["valid"]:
                    validate(case["kind"], case["value"])
                else:
                    with self.assertRaises(ValueError):
                        validate(case["kind"], case["value"])
