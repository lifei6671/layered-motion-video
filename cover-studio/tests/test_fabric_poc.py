"""Fabric.js 验证页和只读素材接口的安全/兼容性检查。"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import app as webapp
from font_catalog import default_font_id, get_font_by_id


class FabricPoCApiTests(unittest.TestCase):
    def test_editor_homepage_and_legacy_routes(self):
        client = webapp.app.test_client()
        current = client.get("/")
        classic = client.get("/legacy")
        bookmarked = client.get("/fabric-poc")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(classic.status_code, 200)
        self.assertEqual(bookmarked.status_code, 302)
        self.assertEqual(bookmarked.headers["Location"], "/")
        self.assertIn(b"editor.bundle.js", current.data)
        self.assertIn(b'id="root"', current.data)
        original = client.get("/fabric-legacy")
        self.assertIn(b"fabric-poc.bundle.js", original.data)
        self.assertIn(b'id="artboard"', original.data)
        self.assertIn(b'id="coverForm"', classic.data)
        self.assertNotIn(b'id="coverForm"', current.data)
        self.assertIn(b'href="/legacy"', original.data)
        self.assertIn(b'href="/"', classic.data)
        self.assertEqual(current.headers["Content-Type"].split(";")[0], "text/html")

    def test_font_url_from_whitelisted_id_only(self):
        client = webapp.app.test_client()
        for wrong in ("", "../windows/private.ttf", "local:not-a-font-id"):
            response = client.get("/api/fabric-poc/font", query_string={"id": wrong})
            self.assertEqual(response.status_code, 404)
        fid = default_font_id("title")
        font_path = get_font_by_id(fid)
        self.assertTrue(font_path)
        response = client.get("/api/fabric-poc/font", query_string={"id": fid})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), Path(font_path).stat().st_size)
        self.assertTrue(response.mimetype.startswith("font/"))

    def test_saved_image_assets_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            original_data, original_preset = webapp.DATA_DIR, webapp.PRESET_FILE
            try:
                webapp.DATA_DIR = Path(directory)
                webapp.PRESET_FILE = Path(directory) / "preset.json"
                image = Image.new("RGB", (160, 120), (114, 149, 179))
                file = io.BytesIO()
                image.save(file, "PNG")
                content = file.getvalue()
                (Path(directory) / "background.png").write_bytes(content)
                webapp.PRESET_FILE.write_text(
                    json.dumps({
                        "settings": {
                            "title": "测试模板", "subtitle": "中文封面",
                            "ratio": "3:4", "title_x": None, "title_y": None,
                        },
                        "assets": {
                            "background": {"file": "background.png", "name": "background.png"}
                        }
                    }, ensure_ascii=False),
                    encoding="utf-8",
                )
                client = webapp.app.test_client()
                resp = client.get("/api/fabric-poc/asset/background")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.mimetype, "image/png")
                self.assertEqual(resp.data, content)
                self.assertEqual(client.get("/api/fabric-poc/asset/avatar").status_code, 404)
                self.assertEqual(client.get("/api/fabric-poc/asset/private").status_code, 404)
                settings = client.get("/api/preset").get_json()["settings"]
                self.assertEqual(settings["title"], "测试模板")
                self.assertIsNone(settings["title_x"])
                # 全部操作都是 GET，原有配置字节保持不变。
                self.assertIn('"background"', webapp.PRESET_FILE.read_text(encoding="utf-8"))
            finally:
                webapp.DATA_DIR, webapp.PRESET_FILE = original_data, original_preset


if __name__ == "__main__":
    unittest.main()
