"""场景 v2 文字、头像样式的兼容性、校验、版本保存。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scene_models import SceneError, default_avatar_style, default_text_style, from_legacy_preset, normalize_scene
from scene_store import get_scene, save_scene


class SceneStyleTests(unittest.TestCase):
    def setUp(self):
        self.scene = from_legacy_preset(
            {"title": "复利思维", "subtitle": "存款百万不是结束而是开始", "account": "@封面工坊"},
            {}, title_font_id="test-title", subtitle_font_id="test-subtitle",
        )

    def style(self, id):
        return next(layer["style"] for layer in self.scene["layers"] if layer["id"] == id)

    def test_existing_templates_receive_correct_default_styles(self):
        for part, color in (("title", "#fffcf4"), ("subtitle", "#f8f7f2"), ("account", "#939496")):
            self.assertEqual(self.style(part), default_text_style(part))
            self.assertEqual(self.style(part)["fill"], color)
            self.assertIsNone(self.style(part)["fontSize"])
        self.assertEqual(self.style("avatar"), default_avatar_style())
        old = deepcopy(self.scene)
        for layer in old["layers"]:
            layer.pop("style", None)
        normalized = normalize_scene(old)
        for layer in normalized["layers"]:
            if layer["id"] in ("title", "subtitle", "account", "avatar"):
                self.assertIn("style", layer)

    def test_style_settings_survive_persistence_and_copy(self):
        title = self.style("title")
        title.update(fontSize=166, charSpacing=80, lineHeight=1.4,
                     fill="#Aa33CC", stroke="#112233", strokeWidth=3, angle=-11, opacity=.8)
        title["shadow"] = {
            "enabled": True, "color": "#1A1B1C", "opacity": .54,
            "blur": 12, "offsetX": -6, "offsetY": 7,
        }
        self.style("avatar").update(opacity=.65, angle=18, scale=1.35)
        self.style("subtitle")["fill"] = "#F8F8F8"
        with TemporaryDirectory() as folder:
            root = Path(folder)
            saved = save_scene(root, self.scene)
            reopened = get_scene(root, saved["id"])
            styles = {item["id"]: item.get("style") for item in reopened["layers"]}
            self.assertEqual(styles["title"]["fill"], "#aa33cc")
            self.assertEqual(styles["title"]["shadow"]["color"], "#1a1b1c")
            self.assertEqual(styles["title"]["fontSize"], 166)
            self.assertEqual(styles["title"]["shadow"]["blur"], 12)
            self.assertEqual(styles["avatar"]["scale"], 1.35)
            self.assertEqual(styles["subtitle"]["fill"], "#f8f8f8")
            copy = save_scene(root, reopened)
            self.assertNotEqual(copy["id"], saved["id"])
            self.assertEqual(copy["layers"], reopened["layers"])

    def test_text_style_rejects_invalid_data(self):
        examples = (
            ("fontSize", 401), ("fontSize", True), ("charSpacing", -200),
            ("lineHeight", .6), ("fill", "javascript:alert(1)"), ("fill", "white"),
            ("stroke", "#123"), ("strokeWidth", -1), ("angle", float("nan")),
            ("opacity", 1.01),
        )
        for key, invalid in examples:
            with self.subTest(key=key, invalid=invalid):
                scene = deepcopy(self.scene)
                next(x for x in scene["layers"] if x["id"] == "title")["style"][key] = invalid
                with self.assertRaises(SceneError):
                    normalize_scene(scene)
        for shadow_key, invalid in (
            ("enabled", 1), ("color", "rgb(1,2,3)"), ("blur", 90),
            ("offsetX", -90), ("opacity", float("inf")),
        ):
            with self.subTest(shadow_key=shadow_key):
                scene = deepcopy(self.scene)
                next(x for x in scene["layers"] if x["id"] == "title")["style"]["shadow"][shadow_key] = invalid
                with self.assertRaises(SceneError):
                    normalize_scene(scene)

    def test_image_styles_are_validated(self):
        for key, invalid in (("opacity", -1), ("angle", 181), ("scale", 3), ("scale", "1.5")):
            scene = deepcopy(self.scene)
            next(x for x in scene["layers"] if x["id"] == "avatar")["style"][key] = invalid
            with self.subTest(key=key):
                with self.assertRaises(SceneError):
                    normalize_scene(scene)
        unknown = deepcopy(self.scene)
        next(x for x in unknown["layers"] if x["id"] == "subtitle")["style"]["rawScript"] = "?"
        with self.assertRaises(SceneError):
            normalize_scene(unknown)


if __name__ == "__main__":
    unittest.main()
