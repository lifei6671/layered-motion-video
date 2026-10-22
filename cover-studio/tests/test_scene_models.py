"""场景模型 v2：导入、画幅隔离、模板持久化、版本冲突和素材访问测试。"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from PIL import Image

import app
from font_catalog import default_font_id, get_font_by_id
from scene_models import SceneError, from_legacy_preset, normalize_scene
from scene_store import asset_path, get_scene, list_scenes, put_asset, save_scene


def fixture_image():
    im = Image.new("RGB", (320, 480), (91, 105, 140))
    output = io.BytesIO()
    im.save(output, format="PNG")
    return output.getvalue()


class SceneV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.title_id = default_font_id("title")
        cls.subtitle_id = default_font_id("subtitle")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous_data, self.previous_preset = app.DATA_DIR, app.PRESET_FILE
        app.DATA_DIR = self.root
        app.PRESET_FILE = self.root / "preset.json"

    def tearDown(self):
        app.DATA_DIR, app.PRESET_FILE = self.previous_data, self.previous_preset
        self.temp.cleanup()

    def sample(self):
        return from_legacy_preset({
            "title": "复利思维",
            "subtitle": "存款百万不是结束而是开始",
            "account": "@测试",
            "ratio": "3:4",
            "title_x": 12.5, "title_y": None,
            "subtitle_x": None, "subtitle_y": 35.7,
            "account_x": 20.0, "account_y": 55.0,
            "darkness": 66, "focus_y": 42, "glow": True,
        }, {}, title_font_id=self.title_id, subtitle_font_id=self.subtitle_id)

    def test_legacy_import_preserves_initial_coordinates_only(self):
        scene = self.sample()
        self.assertEqual(scene["schemaVersion"], 2)
        self.assertIsNone(scene["id"])
        self.assertEqual(set(scene["variants"]), {"3:4"})
        variant = scene["variants"]["3:4"]
        self.assertEqual(variant["title"], {"mode": "manual", "x": 12.5, "y": None})
        self.assertEqual(variant["subtitle"], {"mode": "manual", "x": None, "y": 35.7})
        self.assertEqual(variant["account"], {"mode": "manual", "x": 20.0, "y": 55.0})
        self.assertEqual(scene["backgroundStyle"]["darkness"], 66)
        self.assertEqual(scene["content"]["title"], "复利思维")

    def test_separate_variants_and_scene_copy(self):
        scene = self.sample()
        scene["variants"]["16:9"] = {
            "title": {"mode": "auto"},
            "subtitle": {"mode": "auto"},
            "account": {"mode": "auto"},
        }
        scene["variants"]["3:4"]["title"]["x"] = 25.1
        normalized = normalize_scene(scene)
        self.assertEqual(normalized["variants"]["16:9"]["title"]["x"], None)
        self.assertEqual(normalized["variants"]["3:4"]["title"]["x"], 25.1)
        first = save_scene(self.root, normalized, check_font=get_font_by_id)
        self.assertEqual(first["revision"], 1)
        self.assertEqual(len(first["id"]), 32)
        self.assertEqual(list_scenes(self.root)[0]["name"], first["name"])
        second = save_scene(self.root, first, check_font=get_font_by_id)
        self.assertNotEqual(second["id"], first["id"])
        first_read = get_scene(self.root, first["id"])
        self.assertEqual(first_read["revision"], 1)
        second["variants"]["16:9"]["account"] = {"mode": "manual", "x": 10, "y": 85}
        revised = save_scene(self.root, second, check_font=get_font_by_id, ident=second["id"])
        self.assertEqual(revised["revision"], 2)
        self.assertEqual(revised["variants"]["16:9"]["account"]["x"], 10.0)
        self.assertEqual(first_read["variants"]["16:9"]["account"]["mode"], "auto")
        with self.assertRaisesRegex(SceneError, "版本已更新"):
            save_scene(self.root, second, ident=second["id"])

    def test_strict_validation(self):
        scene = self.sample()
        problems = [
            ("schema", {"schemaVersion": 1}),
            ("missing title", {"content": {"title": "", "subtitle": "副标题", "account": ""}}),
            ("unknown ratio", {"activeRatio": "5:12"}),
            ("bad version", {"revision": -1}),
            ("bad asset", {"assets": {"background": {"source": "managed", "id": "../../secret.png"}}}),
            ("bad fonts", {"fontRefs": {"title": "../abs.ttf", "subtitle": "local:123"}}),
            ("bad variant", {"variants": {"16:9": {"title": {"mode": "manual", "x": 100.01}}}}),
            ("malformed layer", {"layers": [{"id": ["bad-id"]} for _ in range(5)]}),
        ]
        for label, modification in problems:
            with self.subTest(label=label):
                altered = deepcopy(scene)
                altered.update(modification)
                with self.assertRaises(SceneError):
                    normalize_scene(altered, check_font=get_font_by_id)
        with self.assertRaises(SceneError):
            asset_path(self.root, "../my.png")

    def test_asset_snapshot_legacy_and_content_addressed_upload(self):
        image = fixture_image()
        legacy = self.root / "background.png"
        legacy.write_bytes(image)
        saved = {
            "settings": {
                "title": "复利思维", "subtitle": "财富是一种习惯", "account": "@测试",
                "ratio": "3:4", "title_font_id": self.title_id, "subtitle_font_id": self.subtitle_id,
            },
            "assets": {"background": {"file": "background.png", "name": "背景.png"}},
        }
        app.PRESET_FILE.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        client = app.app.test_client()
        legacy_draft = client.get("/api/designs/legacy")
        self.assertEqual(legacy_draft.status_code, 200)
        scene = legacy_draft.get_json()
        self.assertEqual(scene["assets"]["background"]["source"], "legacy")
        created = client.post("/api/designs", json=scene)
        self.assertEqual(created.status_code, 201, created.get_json())
        new = created.get_json()["design"]
        self.assertEqual(new["assets"]["background"]["source"], "managed")
        self.assertTrue(asset_path(self.root, new["assets"]["background"]["id"]).is_file())
        self.assertEqual(asset_path(self.root, new["assets"]["background"]["id"]).read_bytes(), image)
        self.assertEqual(legacy.read_bytes(), image)
        self.assertEqual(json.loads(app.PRESET_FILE.read_text(encoding="utf-8"))["assets"], saved["assets"])
        downloaded = client.get("/api/designs/assets/" + new["assets"]["background"]["id"])
        self.assertEqual(downloaded.data, image)
        downloaded.close()
        duplicate_id = put_asset(self.root, image, ".png")
        self.assertEqual(duplicate_id, new["assets"]["background"]["id"])

    def test_browser_endpoints_revision_and_managed_upload(self):
        client = app.app.test_client()
        scene = self.sample()
        created = client.post("/api/designs", json=scene)
        self.assertEqual(created.status_code, 201, created.get_json())
        data = created.get_json()["design"]
        page = client.get("/api/designs/" + data["id"])
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.get_json()["design"]["content"], data["content"])
        data["name"] = "财经封面"
        updated = client.put("/api/designs/" + data["id"], json=data)
        self.assertEqual(updated.status_code, 200, updated.get_json())
        self.assertEqual(updated.get_json()["design"]["revision"], 2)
        conflict = client.put("/api/designs/" + data["id"], json=data)
        self.assertEqual(conflict.status_code, 409)

        image = fixture_image()
        upload = client.post("/api/designs/assets", data={
            "kind": "avatar", "file": (io.BytesIO(image), "person.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(upload.status_code, 201, upload.get_json())
        item = upload.get_json()["asset"]
        self.assertEqual(item["source"], "managed")
        content = client.get("/api/designs/assets/" + item["id"])
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content.data, image)
        content.close()
        invalid = client.post("/api/designs/assets", data={
            "kind": "avatar", "file": (io.BytesIO(b"not an image"), "bad.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(invalid.status_code, 400)
        mislabeled = client.post("/api/designs/assets", data={
            "kind": "background", "file": (io.BytesIO(image), "photo.webp"),
        }, content_type="multipart/form-data")
        self.assertEqual(mislabeled.status_code, 400)
        self.assertIn("编码", mislabeled.get_json()["error"])
        self.assertEqual(client.get("/api/designs/invalid").status_code, 400)
        self.assertEqual(client.get("/api/designs/assets/%2E%2E").status_code, 404)


if __name__ == "__main__":
    unittest.main()
