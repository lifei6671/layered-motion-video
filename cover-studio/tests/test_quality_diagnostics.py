"""场景 v2 安全区方案、人工重叠确认与字体字符预检测试。"""

from __future__ import annotations

from copy import deepcopy
import unittest

from font_catalog import default_font_id, get_font_by_id
from font_coverage import missing_characters
from quality_models import normalize_quality
from scene_models import SceneError, from_legacy_preset, normalize_scene
import app as webapp


class QualityModelsTests(unittest.TestCase):
    def setUp(self):
        self.scene = from_legacy_preset(
            {"title": "复利思维", "subtitle": "时间是复利", "account": "@封面工坊"},
            {}, title_font_id="test-title", subtitle_font_id="test-subtitle",
        )

    def test_backward_compatibility_and_profile_persistence(self):
        legacy = deepcopy(self.scene)
        legacy.pop("quality", None)
        resolved = normalize_scene(legacy)
        self.assertEqual(resolved["quality"], {
            "profilesByRatio": {}, "allowedOverlaps": [], "allowedByRatio": {},
        })
        resolved["quality"] = {
            "profilesByRatio": {
                "9:16": "vertical_video",
                "3:4": "graphic_post",
                "16:9": "landscape_video",
            },
            "allowedOverlaps": [["title", "account"]],
        }
        normal = normalize_scene(resolved)
        self.assertEqual(normal["quality"]["profilesByRatio"]["9:16"], "vertical_video")
        self.assertEqual(normal["quality"]["allowedOverlaps"], [["account", "title"]])
        self.assertEqual(normalize_scene(normal)["quality"], normal["quality"])

    def test_profile_is_compatible_with_ratio(self):
        source = deepcopy(self.scene)
        for value in (
            {"16:9": "vertical_video"},
            {"9:16": "landscape_video"},
            {"3:4": "unknown"},
            {"2:3": "general"},
            ["3:4"],
        ):
            sample = deepcopy(source)
            sample["quality"] = {"profilesByRatio": value, "allowedOverlaps": []}
            with self.subTest(value=str(value)):
                with self.assertRaises(SceneError):
                    normalize_scene(sample)

    def test_allowed_pairs_have_valid_identifiers_and_limit(self):
        scene = deepcopy(self.scene)
        examples = [
            [["title", "title"]],
            [["background", "title"]],
            [["title", "not-found"]],
            [["title", "subtitle"], ["subtitle", "title"]],
            [["title"]],
            ["title"],
            "title",
        ]
        for pair in examples:
            scene["quality"] = {"profilesByRatio": {}, "allowedOverlaps": pair}
            with self.subTest(value=str(pair)):
                with self.assertRaises(SceneError):
                    normalize_scene(scene)
        with self.assertRaises(ValueError):
            normalize_quality({"profilesByRatio":{}, "allowedOverlaps": [["a","b"]]*101}, layer_ids={"a","b"})

    def test_ratio_scoped_overlaps_and_invalid_pairs(self):
        scene = deepcopy(self.scene)
        scene["quality"] = {
            "profilesByRatio": {"9:16": "vertical_video"},
            "allowedOverlaps": [],
            "allowedByRatio": {
                "3:4": [["title", "account"]],
                "16:9": [["subtitle", "account"]],
            },
        }
        resolved = normalize_scene(scene)
        per_ratio = resolved["quality"]["allowedByRatio"]
        self.assertEqual(per_ratio["3:4"], [["account", "title"]])
        self.assertEqual(per_ratio["16:9"], [["account", "subtitle"]])
        self.assertNotIn("9:16", per_ratio)
        self.assertEqual(normalize_scene(resolved)["quality"], resolved["quality"])
        for value in (
            {"3:4": [["title", "bad-layer"]]},
            {"2:3": [["title", "subtitle"]]},
            {"3:4": [["title", "title"]]},
            {"3:4": [["title", "subtitle"], ["subtitle", "title"]]},
            {"3:4": "invalid"},
        ):
            scene["quality"]["allowedByRatio"] = value
            with self.subTest(value=str(value)):
                with self.assertRaises(SceneError):
                    normalize_scene(scene)

    def test_group_quality_references_survive_scene_validation(self):
        scene = deepcopy(self.scene)
        self.assertEqual(len(scene["extras"]["layers"]), 0)
        # 基础文字图层与基础头像始终是合法的确认对象。
        scene["quality"] = {
            "profilesByRatio": {"9:16": "vertical_video"},
            "allowedOverlaps": [["avatar", "title"]],
        }
        self.assertEqual(
            normalize_scene(scene)["quality"]["allowedOverlaps"],
            [["avatar", "title"]]
        )


class FontCoverageEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font_id = default_font_id("title")
        cls.font_file = get_font_by_id(cls.font_id)

    def test_font_cmap_detects_missing_noncharacter(self):
        self.assertTrue(self.font_file)
        missing = missing_characters(self.font_file, "\u0378")
        self.assertEqual(missing, ["\u0378"])
        self.assertEqual(missing_characters(self.font_file, "   \n"), [])

    def test_font_coverage_endpoint_validates_font_id_and_characters(self):
        response = webapp.app.test_client().post("/api/fabric-poc/font-coverage", json={
            "checks": [{"fontId": self.font_id, "text": "复利思维\u0378", "label": "title"}]
        })
        self.assertEqual(response.status_code, 200, response.get_json(silent=True))
        data = response.get_json()
        self.assertEqual(data["checkedCount"], 1)
        self.assertIn("\u0378", data["results"][0]["missing"])
        self.assertGreaterEqual(data["results"][0]["missingCount"], 1)

    def test_font_coverage_endpoint_rejects_invalid_inputs(self):
        client = webapp.app.test_client()
        examples = [
            {"checks": [{"fontId":"../../Windows/Fonts/private.ttf", "text":"abc", "label":"x"}]},
            {"checks": [{"fontId":self.font_id, "text": "a"*501, "label":"x"}]},
            {"checks": [{"fontId":self.font_id, "text": "abc", "label": ""}]},
            {"checks": [{"fontId":self.font_id, "text": "abc"}]},
            {"checks": "not-list"},
            {"checks": [{}]*41},
            {"checks": [], "unexpected": "key"},
        ]
        for entry in examples:
            with self.subTest(entry=str(entry)[:80]):
                response = client.post("/api/fabric-poc/font-coverage", json=entry)
                self.assertIn(response.status_code, (400,404))
        self.assertEqual(client.post(
            "/api/fabric-poc/font-coverage", data="invalid",
            content_type="application/json",
        ).status_code, 400)


if __name__ == "__main__":
    unittest.main()
