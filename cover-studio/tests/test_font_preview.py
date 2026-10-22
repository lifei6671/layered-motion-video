"""字体选择器预览回归：本机字体、WOFF2、实际字形及访问边界。"""

import io
import shutil
import tempfile
import unittest
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image

import app as webapp
import font_catalog
from font_catalog import default_font_id, get_font_by_id
from font_preview import get_font_preview_info, render_font_preview


class FontPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.title_font = get_font_by_id(default_font_id("title"))

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_dir = font_catalog.FONT_DIR
        font_catalog.FONT_DIR = Path(self.folder.name)

    def tearDown(self):
        font_catalog.FONT_DIR = self.old_dir
        self.folder.cleanup()

    def test_local_font_metadata_and_preview_png(self):
        path = Path(self.folder.name, "书法标题.ttf")
        shutil.copyfile(self.title_font, path)
        font = font_catalog.list_local_fonts()[0]
        catalog = font_catalog.public_catalog()
        local_item = next(item for item in catalog["fonts"] if item["id"] == font["id"])
        self.assertEqual(local_item["source"], "local")
        self.assertEqual(local_item["coverage"], "chinese")
        self.assertTrue(local_item["sample"])
        self.assertIn("字", local_item["label"])
        payload = render_font_preview(font["path"])
        self.assertEqual(payload[:4], bytes([137, 80, 78, 71]))
        self.assertEqual(Image.open(io.BytesIO(payload)).size, (600, 104))

        client = webapp.app.test_client()
        preview = client.get("/api/font-preview", query_string={"id": font["id"]})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.mimetype, "image/png")
        self.assertEqual(preview.data, payload)

        compact_bytes = render_font_preview(font["path"], compact=True)
        compact_image = Image.open(io.BytesIO(compact_bytes))
        self.assertEqual(compact_image.height, 96)
        self.assertGreater(compact_image.width, 80)
        self.assertLessEqual(compact_image.width, 360)
        compact_api = client.get("/api/font-preview", query_string={"id": font["id"], "compact": "1"})
        self.assertEqual(compact_api.status_code, 200)
        self.assertEqual(compact_api.data, compact_bytes)
        self.assertEqual(compact_api.headers["X-Preview-Characters"], "4")

    def test_woff2_latin_font_uses_real_latin_sample(self):
        source = TTFont(self.title_font)
        try:
            from fontTools import subset
            subsetter = subset.Subsetter()
            subsetter.populate(text="Aa Bb 123")
            subsetter.subset(source)
            source.flavor = "woff2"
            target = Path(self.folder.name, "Latin.woff2")
            source.save(target)
        finally:
            source.close()
        record = font_catalog.public_catalog()["fonts"][0]
        self.assertEqual(record["coverage"], "latin")
        self.assertEqual(record["sample"], "Aa Bb 123")
        self.assertEqual(record["label"], "仅含拉丁字形")
        result = webapp.app.test_client().get("/api/font-preview", query_string={"id": record["id"]})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(result.data)).size, (600, 104))

    def test_unavailable_font_is_rejected(self):
        client = webapp.app.test_client()
        for font_id in ("", "../../Windows/Fonts/foo.ttf", "local:deadbeefdeadbeef"):
            response = client.get("/api/font-preview", query_string={"id": font_id})
            self.assertEqual(response.status_code, 404)
        empty = Path(self.folder.name, "broken.woff2")
        empty.write_bytes(b"bad font")
        record = font_catalog.public_catalog()["fonts"][0]
        self.assertEqual(record["coverage"], "invalid")
        response = client.get("/api/font-preview", query_string={"id": record["id"]})
        self.assertEqual(response.status_code, 422)
        self.assertIn("error", response.get_json())

    def test_picker_markup_contains_search_preview_and_keyboard_targets(self):
        response = webapp.app.test_client().get("/legacy")
        self.assertEqual(response.status_code, 200)
        markup = response.get_data(as_text=True)
        for kind in ("title", "subtitle"):
            for suffix in (
                "FontPicker", "FontTrigger", "FontPreview", "FontBadge", "FontOptions", "FontSearch",
                "FontFamilyPicker", "FontFamilyTrigger", "FontFamilyPreview", "FontFamilyName",
                "FontFamilyBadge", "FontFamilyMenu", "FontFamilyOptions", "FontFamilySearch",
            ):
                self.assertIn(f'id="{kind}{suffix}"', markup)
        self.assertIn("role=\"listbox\"", markup)
        self.assertEqual(markup.count('aria-haspopup="listbox"'), 4)


if __name__ == "__main__":
    unittest.main()
