from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

import app as webapp
from cover_document import normalize_document
from document_store import get_document, save_document, delete_document, list_documents
from font_catalog import default_local_font_id
from scene_models import SceneError


def fixture():
    layer = {"id": "title", "name": "中文标题", "type": "text", "frame": {"x": 300, "y": 480, "width": 1320, "height": 170, "rotation": 0},
             "visible": True, "locked": False, "opacity": 1, "text": "中文标题", "fontId": default_local_font_id(), "fontSize": 88, "fontWeight": 400,
             "align": "center", "lineHeight": 1.15, "letterSpacing": 4, "color": "#ffffff", "stroke": "#0f1216", "strokeWidth": 4,
             "shadow": {"enabled": True, "color": "#000000", "opacity": .8, "blur": 24, "x": 8, "y": 8},
             "assetId": "", "fit": "cover", "focusY": 50, "darkness": 0, "radius": 0}
    return {"schemaVersion": 3, "kind": "cover-document", "id": None, "revision": 0, "name": "测试文档", "width": 1920, "height": 1080,
            "background": "#102030", "layers": [layer], "updatedAt": None}


class CoverDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_roundtrip_uses_pixels_and_retains_complete_styles(self):
        original = fixture()
        saved = save_document(self.root, original, check_font=lambda _: True)
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved, get_document(self.root, saved["id"]))
        self.assertEqual(saved["layers"], original["layers"])
        self.assertIsNone(original["id"])
        self.assertFalse((self.root / "designs").exists())

    def test_revision_conflict_serializes_two_writers(self):
        saved = save_document(self.root, fixture())
        def write(i):
            doc = deepcopy(saved)
            doc["name"] = str(i)
            try:
                return save_document(self.root, doc, ident=doc["id"])["revision"]
            except SceneError:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(write, (1, 2)))
        self.assertCountEqual(results, [2, "conflict"])
        self.assertEqual(get_document(self.root, saved["id"])["revision"], 2)

    def test_invalid_boundaries_are_rejected_before_writing(self):
        cases = [lambda d: d.update(width=True), lambda d: d["layers"][0]["frame"].update(x=float("nan")),
                 lambda d: d["layers"].append(deepcopy(d["layers"][0])), lambda d: d["layers"][0].update(color="url(evil)"),
                 lambda d: d["layers"][0].update(type="script"), lambda d: d["layers"][0].update(visible=1),
                 lambda d: d["layers"][0].update(type="image", assetId="../../private.png"), lambda d: d.update(schemaVersion=99),
                 lambda d: d.update(name="坏\ud83d"), lambda d: d["layers"][0].update(name="  ")]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                doc = fixture()
                mutate(doc)
                with self.assertRaises(SceneError):
                    save_document(self.root, doc)
        self.assertFalse((self.root / "documents").exists())

    def test_missing_font_or_asset_cannot_silently_save(self):
        with self.assertRaisesRegex(SceneError, "字体不存在"):
            save_document(self.root, fixture(), check_font=lambda _: False)
        doc = fixture()
        doc["layers"][0].update(type="image", assetId="a" * 64 + ".png")
        with self.assertRaisesRegex(SceneError, "图片不存在"):
            save_document(self.root, doc)

    def test_api_save_reopen_conflict_copy_and_old_endpoints(self):
        with patch.object(webapp, "DATA_DIR", self.root):
            client = webapp.app.test_client()
            response = client.post("/api/cover-documents", json=fixture())
            self.assertEqual(response.status_code, 201, response.get_json())
            doc = response.get_json()["document"]
            self.assertEqual(client.get("/api/cover-documents/" + doc["id"]).get_json()["document"], doc)
            self.assertEqual(len(client.get("/api/cover-documents").get_json()["documents"]), 1)
            first = client.put("/api/cover-documents/" + doc["id"], json=doc)
            self.assertEqual(first.status_code, 200)
            conflict = client.put("/api/cover-documents/" + doc["id"], json=doc)
            self.assertEqual(conflict.status_code, 409)
            doc.update(id=None, revision=0)
            self.assertEqual(client.post("/api/cover-documents", json=doc).status_code, 201)
            self.assertEqual(client.get("/api/designs").get_json(), {"designs": []})
            self.assertEqual(client.get("/legacy").status_code, 200)
            self.assertEqual(client.get("/fabric-legacy").status_code, 200)

    def test_migration_freezes_assets_and_preserves_preset_bytes(self):
        from PIL import Image
        preset = {"settings": {"title": "旧封面", "subtitle": "保留配置", "ratio": "16:9"}, "assets": {"background": {"file": "background.png", "name": "背景"}}}
        old = json.dumps(preset, ensure_ascii=False).encode("utf8")
        preset_file = self.root / "preset.json"
        preset_file.write_bytes(old)
        Image.new("RGB", (320, 180), "#102030").save(self.root / "background.png")
        with patch.object(webapp, "DATA_DIR", self.root), patch.object(webapp, "PRESET_FILE", preset_file):
            scene = webapp.app.test_client().get("/api/cover-migration/legacy").get_json()["scene"]
        self.assertEqual(scene["assets"]["background"]["source"], "managed")
        self.assertEqual(preset_file.read_bytes(), old)
        self.assertTrue((self.root / "designs/assets" / scene["assets"]["background"]["id"]).exists())

    def test_export_blocks_missing_glyphs_and_rejects_invalid_format(self):
        client = webapp.app.test_client()
        doc = fixture()
        self.assertEqual(client.post("/api/cover-export?format=gif", json=doc).status_code, 400)
        with patch("react_editor.missing_characters", return_value=["缺"]):
            response = client.post("/api/cover-export", json=doc)
        self.assertEqual(response.status_code, 400)
        self.assertIn("缺少字符", response.get_json()["error"])

    def test_migrated_extreme_spacing_and_nonuniform_text_scale_are_valid(self):
        doc = fixture()
        doc["layers"][0].update(letterSpacing=400, textScaleY=2, glow=False, fit="fill")
        self.assertEqual(normalize_document(doc)["layers"][0]["letterSpacing"], 400)
        self.assertEqual(save_document(self.root, doc)["layers"][0]["textScaleY"], 2)

    def test_shape_image_fills_and_circle_contract(self):
        doc = fixture()
        layer = doc["layers"][0]
        layer.update(type="rect", assetId="builtin:noir")
        self.assertEqual(save_document(self.root, doc)["layers"][0]["assetId"], "builtin:noir")
        layer.update(type="ellipse")
        self.assertEqual(normalize_document(doc)["layers"][0]["type"], "ellipse")
        layer.update(type="image", imageShape="circle")
        with self.assertRaisesRegex(SceneError, "宽高须一致"):
            normalize_document(doc)
        layer["frame"].update(width=300, height=300)
        self.assertEqual(normalize_document(doc)["layers"][0]["imageShape"], "circle")
        layer.update(type="text", assetId="builtin:noir")
        with self.assertRaisesRegex(SceneError, "文字图层不支持"):
            normalize_document(doc)
        layer.update(type="rect", assetId="a" * 64 + ".png")
        with self.assertRaisesRegex(SceneError, "图片不存在"):
            save_document(self.root, doc)

    def test_template_storage_is_independent_and_delete_preserves_shared_assets(self):
        from PIL import Image
        from scene_store import put_asset
        import io
        image = io.BytesIO()
        Image.new("RGB", (20, 20), "red").save(image, "PNG")
        asset = {"id": put_asset(self.root, image.getvalue(), ".png")}
        doc = fixture()
        doc["layers"][0].update(type="rect", assetId=asset["id"])
        saved = save_document(self.root, doc)
        template = save_document(self.root, doc, collection="templates")
        self.assertEqual(get_document(self.root, template["id"], collection="templates")["layers"], saved["layers"])
        self.assertEqual(len(list_documents(self.root)), 1)
        for revision in (None, True, saved["revision"] + 1):
            with self.assertRaisesRegex(SceneError, "版本已更新"):
                delete_document(self.root, saved["id"], revision)
        delete_document(self.root, saved["id"], saved["revision"])
        self.assertEqual(list_documents(self.root), [])
        self.assertTrue((self.root / "designs/assets" / asset["id"]).is_file())
        self.assertEqual(len(list_documents(self.root, collection="templates")), 1)
        delete_document(self.root, template["id"], 1, collection="templates")
        self.assertEqual(list_documents(self.root, collection="templates"), [])

    def test_template_and_delete_http_contracts(self):
        with patch.object(webapp, "DATA_DIR", self.root):
            client = webapp.app.test_client()
            template_response = client.post("/api/cover-templates", json=fixture())
            self.assertEqual(template_response.status_code, 201, template_response.get_json())
            template = template_response.get_json()["document"]
            url = "/api/cover-templates/" + template["id"]
            self.assertEqual(client.get(url).get_json()["document"], template)
            self.assertEqual(len(client.get("/api/cover-templates").get_json()["templates"]), 1)
            self.assertEqual(client.get("/api/cover-documents").get_json()["documents"], [])
            self.assertEqual(client.delete(url, json={"revision": 2}).status_code, 409)
            self.assertEqual(client.delete(url, json={"revision": 1}).status_code, 200)
            self.assertEqual(client.get("/api/cover-templates").get_json()["templates"], [])
            design = client.post("/api/cover-documents", json=fixture()).get_json()["document"]
            self.assertEqual(client.delete("/api/cover-documents/" + design["id"], json={"revision": 1}).status_code, 200)
            self.assertEqual(client.get("/api/cover-documents").get_json()["documents"], [])


if __name__ == "__main__":
    unittest.main()
