"""Cover Scene v2 图层锁定、显示与层级顺序持久化测试。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scene_models import SceneError, from_legacy_preset, normalize_scene
from scene_store import get_scene, save_scene


class SceneLayerStateTests(unittest.TestCase):
    @staticmethod
    def sample():
        return from_legacy_preset({
            "title": "复利思维",
            "subtitle": "存款百万不是结束而是开始",
            "account": "@封面工坊",
            "ratio": "3:4",
        }, {}, title_font_id="test-title", subtitle_font_id="test-subtitle")

    def test_default_layers_are_stable_and_background_pinned(self):
        scene = self.sample()
        self.assertEqual(
            [part["id"] for part in scene["layers"]],
            ["background", "avatar", "title", "subtitle", "account"],
        )
        self.assertEqual([part["zIndex"] for part in scene["layers"]], [0, 10, 20, 30, 40])
        self.assertTrue(all(part["visible"] for part in scene["layers"]))
        self.assertTrue(scene["layers"][0]["locked"])

    def test_visibility_lock_and_reordering_survive_save_and_copy(self):
        scene = self.sample()
        for layer in scene["layers"]:
            if layer["id"] == "subtitle":
                layer["visible"] = False
                layer["locked"] = True
                layer["zIndex"] = 40
            elif layer["id"] == "account":
                layer["zIndex"] = 30
            elif layer["id"] == "avatar":
                layer["visible"] = False

        with TemporaryDirectory() as folder:
            root = Path(folder)
            saved = save_scene(root, scene)
            loaded = get_scene(root, saved["id"])
            props = {part["id"]: part for part in loaded["layers"]}
            self.assertFalse(props["subtitle"]["visible"])
            self.assertTrue(props["subtitle"]["locked"])
            self.assertEqual(props["subtitle"]["zIndex"], 40)
            self.assertEqual(props["account"]["zIndex"], 30)
            self.assertFalse(props["avatar"]["visible"])
            # 另存为独立设计仍保留顺序、锁定与可见性。
            cloned = save_scene(root, loaded)
            self.assertNotEqual(cloned["id"], saved["id"])
            self.assertEqual(cloned["layers"], loaded["layers"])

    def test_invalid_layer_properties_are_rejected(self):
        origin = self.sample()
        cases = [
            ("non_boolean_visible", "title", "visible", "no"),
            ("non_boolean_lock", "title", "locked", 1),
            ("invalid_z", "title", "zIndex", 1024),
            ("bool_z", "title", "zIndex", True),
            ("background_unlocked", "background", "locked", False),
            ("background_order", "background", "zIndex", 8),
            ("layer_type", "title", "type", "script"),
        ]
        for label, ident, prop, value in cases:
            with self.subTest(label=label):
                data = deepcopy(origin)
                next(item for item in data["layers"] if item["id"] == ident)[prop] = value
                with self.assertRaises(SceneError):
                    normalize_scene(data)

        same = deepcopy(origin)
        same["layers"][2]["zIndex"] = same["layers"][3]["zIndex"]
        with self.assertRaisesRegex(SceneError, "重复"):
            normalize_scene(same)

    def test_legacy_scene_without_new_fields_still_loads(self):
        legacy = self.sample()
        for layer in legacy["layers"]:
            layer.pop("visible")
        scene = normalize_scene(legacy)
        self.assertTrue(all(x["visible"] for x in scene["layers"]))


if __name__ == "__main__":
    unittest.main()
