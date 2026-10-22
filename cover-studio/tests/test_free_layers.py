"""扩展图层：兼容性、素材安全、组合约束及设计持久化。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import unittest

from PIL import Image

from free_layer_models import normalize_extras, ExtraLayerError
from scene_models import normalize_scene, from_legacy_preset, SceneError
from scene_store import save_scene, get_scene, put_asset
import app


def fixture_bytes():
    output = io.BytesIO()
    Image.new("RGB", (180, 220), (44, 109, 143)).save(output, "PNG")
    return output.getvalue()


class ExtraLayersTest(unittest.TestCase):
    @classmethod
    def example_scene(cls):
        return from_legacy_preset({
            "title": "复利思维", "subtitle": "时间就是复利", "account": "@封面工坊",
        }, {}, title_font_id="test-title", subtitle_font_id="test-subtitle")

    @staticmethod
    def shape(ident: str, index: int, kind: str = "rect", group=None):
        result = {
            "id": "custom-" + ident * 12, "name": "图层 " + ident,
            "type": kind, "zIndex": 50 + index, "locked": False,
            "visible": True, "groupId": group,
            "frame": {"x": 5 + index, "y": 20 + index, "width": 20, "height": 15, "angle": 0},
        }
        if kind == "text":
            result.update(text="理解复利", fontId="test-title", style={"fontSize": 58, "fill": "#efdfc8"})
        elif kind == "rect":
            result["style"] = {"fill": "#123456", "opacity": .7}
        elif kind == "ellipse":
            result["style"] = {"fill": "#ffaa11"}
        return result

    def test_old_scenes_have_empty_extras(self):
        legacy = self.example_scene()
        legacy.pop("extras", None)
        normalized = normalize_scene(legacy)
        self.assertEqual(normalized["schemaVersion"], 2)
        self.assertEqual(normalized["extras"], {"layers": [], "groups": []})

    def test_add_group_and_reopen_exactly(self):
        scene = self.example_scene()
        gid = "group-" + "9" * 12
        rect = self.shape("a", 0, group=gid)
        label = self.shape("b", 1, kind="text", group=gid)
        ellipse = self.shape("c", 2, kind="ellipse")
        scene["extras"] = {
            "layers": [rect, label, ellipse],
            "groups": [{"id": gid, "name": "对比图形", "members": [rect["id"], label["id"]],
                        "visible": True, "locked": False}],
        }
        with TemporaryDirectory() as directory:
            saved = save_scene(Path(directory), scene)
            restored = get_scene(Path(directory), saved["id"])
            self.assertEqual(restored["extras"], normalize_extras(scene["extras"]))
            self.assertEqual(len(restored["extras"]["layers"]), 3)
            self.assertEqual(restored["extras"]["groups"][0]["name"], "对比图形")
            clone = save_scene(Path(directory), restored)
            self.assertEqual(clone["extras"], restored["extras"])

    def test_ratio_frames_inherit_and_survive_persistence(self):
        scene = self.example_scene()
        rect = self.shape("a", 0, kind="rect")
        base = deepcopy(rect["frame"])
        current = dict(base, x=55, y=12, width=35, height=19, angle=18)
        portrait = dict(base, x=10, y=51, width=27, height=16, angle=-7)
        rect["ratioFrames"] = {"3:4": current, "9:16": portrait}
        scene["extras"]["layers"].append(rect)
        normalized = normalize_scene(scene)
        saved_layer = normalized["extras"]["layers"][0]
        self.assertEqual(saved_layer["frame"], base)
        self.assertEqual(set(saved_layer["ratioFrames"]), {"3:4", "9:16"})
        self.assertEqual(saved_layer["ratioFrames"]["3:4"]["angle"], 18)
        with TemporaryDirectory() as directory:
            saved = save_scene(Path(directory), normalized)
            loaded = get_scene(Path(directory), saved["id"])
            self.assertEqual(loaded["extras"]["layers"][0]["ratioFrames"], saved_layer["ratioFrames"])
            self.assertEqual(loaded["extras"]["layers"][0]["frame"], base)

    def test_old_extra_layer_without_ratio_frames_is_compatible(self):
        scene = self.example_scene()
        layer = self.shape("b", 0)
        layer.pop("ratioFrames", None)
        scene["extras"]["layers"].append(layer)
        normalized = normalize_scene(scene)
        self.assertEqual(normalized["extras"]["layers"][0]["ratioFrames"], {})
        self.assertEqual(normalized["extras"]["layers"][0]["frame"], layer["frame"])

    def test_free_text_has_ratio_specific_vertical_scale(self):
        scene = self.example_scene()
        layer = self.shape("e", 0, kind="text")
        scale_frame = dict(layer["frame"], x=30, y=21, scaleY=1.65)
        layer["ratioFrames"] = {"16:9": scale_frame}
        scene["extras"]["layers"].append(layer)
        normalized = normalize_scene(scene)
        output = normalized["extras"]["layers"][0]
        self.assertNotIn("scaleY", output["frame"])
        self.assertEqual(output["ratioFrames"]["16:9"]["scaleY"], 1.65)
        for bad in (0, .1, 5, float("nan"), "1.4"):
            invalid = deepcopy(scene)
            invalid["extras"]["layers"][0]["ratioFrames"]["16:9"]["scaleY"] = bad
            with self.subTest(bad=bad):
                with self.assertRaises(SceneError):
                    normalize_scene(invalid)
        shape = deepcopy(scene)
        shape["extras"]["layers"][0]["type"] = "ellipse"
        shape["extras"]["layers"][0].pop("fontId")
        shape["extras"]["layers"][0].pop("text")
        shape["extras"]["layers"][0]["style"] = {"fill": "#ffffff"}
        with self.assertRaises(SceneError):
            normalize_scene(shape)

    def test_invalid_ratio_frames_are_rejected(self):
        original = self.example_scene()
        layer = self.shape("c", 0)
        for cases in (
            {"5:6": dict(layer["frame"])},
            {"3:4": {"x": 10}},
            {"16:9": dict(layer["frame"], width=200)},
            {"3:4": dict(layer["frame"], x=97)},
            {"3:4": dict(layer["frame"], angle=float("nan"))},
            ["3:4"],
            {"3:4": None},
        ):
            scene = deepcopy(original)
            item = deepcopy(layer)
            item["ratioFrames"] = cases
            scene["extras"]["layers"] = [item]
            with self.subTest(case=str(cases)[:50]):
                with self.assertRaises(SceneError):
                    normalize_scene(scene)

    def test_invalid_group_members_and_style_are_rejected(self):
        base = self.example_scene()
        a, b = self.shape("a", 0), self.shape("b", 1)
        gid = "group-" + "e" * 12
        problems = [
            {"layers": [a, a], "groups": []},
            {"layers": [a, b], "groups": [{"id": gid, "members": [a["id"], b["id"]]}]},
            {"layers": [a, {**b, "groupId": gid}], "groups": []},
            {"layers": [{**a, "frame": {**a["frame"], "x": 92}}], "groups": []},
            {"layers": [{**a, "style": {"fill": "javascript:alert(1)"}}], "groups": []},
            {"layers": [{**a, "zIndex": True}], "groups": []},
        ]
        for sample in problems:
            scene = deepcopy(base)
            scene["extras"] = sample
            with self.subTest(case=str(sample)[:80]):
                with self.assertRaises(SceneError):
                    normalize_scene(scene)

    def test_managed_free_image_upload_and_invalid_reference(self):
        data = fixture_bytes()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            previous_data, previous_preset = app.DATA_DIR, app.PRESET_FILE
            try:
                app.DATA_DIR, app.PRESET_FILE = root, root / "preset.json"
                client = app.app.test_client()
                res = client.post("/api/designs/assets", data={
                    "kind": "layer", "file": (io.BytesIO(data), "shape.png")
                }, content_type="multipart/form-data")
                self.assertEqual(res.status_code, 201)
                asset_id = res.get_json()["asset"]["id"]
                scene = self.example_scene()
                from font_catalog import default_font_id
                scene["fontRefs"] = {
                    "title": default_font_id("title"),
                    "subtitle": default_font_id("subtitle"),
                }
                record = self.shape("d", 4, kind="image")
                record["assetId"] = asset_id
                scene["extras"]["layers"].append(record)
                created = client.post("/api/designs", json=scene)
                self.assertEqual(created.status_code, 201, created.get_json())
                stored = created.get_json()["design"]
                self.assertEqual(stored["extras"]["layers"][0]["assetId"], asset_id)
                download = client.get("/api/designs/assets/" + asset_id)
                self.assertEqual(download.data, data)
                download.close()
                wrong = deepcopy(scene)
                wrong["extras"]["layers"][0]["assetId"] = "0" * 64 + ".png"
                res = client.post("/api/designs", json=wrong)
                self.assertEqual(res.status_code, 404)
                self.assertIn("不存在", res.get_json()["error"])
            finally:
                app.DATA_DIR, app.PRESET_FILE = previous_data, previous_preset


if __name__ == "__main__":
    unittest.main()
