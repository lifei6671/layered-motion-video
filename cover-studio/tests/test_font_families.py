"""目录代表字体家族，文件代表样式、字重和格式的回归测试。"""

import shutil
import tempfile
import unittest
from pathlib import Path

import app as webapp
import font_catalog
from font_catalog import default_font_id, get_font_by_id
from font_variants import describe_variant


class FontFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.system_font = get_font_by_id(default_font_id("title"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = font_catalog.FONT_DIR
        font_catalog.FONT_DIR = Path(self.temp.name)

    def tearDown(self):
        font_catalog.FONT_DIR = self.old_dir
        self.temp.cleanup()

    def _font_file(self, folder, filename):
        destination = Path(self.temp.name) / folder
        destination.mkdir(parents=True, exist_ok=True)
        file = destination / filename
        shutil.copyfile(self.system_font, file)
        return file

    def test_directory_is_family_and_files_are_variants(self):
        self._font_file("霞鹜文楷", "LXGWWenKai-Light.ttf")
        self._font_file("霞鹜文楷", "LXGWWenKai-Regular.ttf")
        self._font_file("霞鹜文楷", "LXGWWenKai-Medium.ttf")
        self._font_file("霞鹜文楷", "LXGWWenKaiMono-Regular.ttf")
        self._font_file("猫啃", "MaokenAssortedSans-Lite.otf")
        self._font_file("猫啃", "MaokenAssortedSans-Lite.ttf")
        self._font_file("猫啃", "MaokenAssortedSans.otf")
        self._font_file("猫啃", "MaokenAssortedSans.ttf")
        self._font_file("直放文件", "Loose-Regular.ttf")
        loose = Path(self.temp.name) / "standalone-Regular.ttf"
        shutil.copyfile(self.system_font, loose)

        fonts = font_catalog.list_local_fonts()
        self.assertEqual(len(fonts), 10)
        self.assertEqual({x["family"] for x in fonts}, {"霞鹜文楷", "猫啃", "直放文件", "根目录字体"})
        self.assertEqual(
            [(x["weight"], x["monospace"]) for x in fonts if x["family"] == "霞鹜文楷"],
            [(300, False), (400, False), (500, False), (400, True)],
        )
        grouped = font_catalog.public_catalog()
        self.assertEqual(grouped["local_count"], 10)
        self.assertEqual({f["id"]: f["count"] for f in grouped["families"]}, {
            "霞鹜文楷": 4, "猫啃": 4, "直放文件": 1, "根目录字体": 1,
        })
        maoken = [x for x in grouped["fonts"] if x["source"] == "local" and x["family"] == "猫啃"]
        self.assertEqual(len(maoken), 4)
        self.assertEqual({x["format"] for x in maoken}, {"TTF", "OTF"})
        self.assertEqual(len({x["id"] for x in maoken}), 4)
        self.assertTrue(any(x["variant"].endswith("OTF") for x in maoken))

    def test_variant_weight_from_filename(self):
        matrix = [
            ("DouyinSansBold.ttf", 700, False),
            ("SourceHanSerifCN-ExtraLight-3.otf", 250, False),
            ("Source_Han_Sans_SC_Normal_Normal.otf", 350, False),
            ("LXGWWenKaiMono-Regular.ttf", 400, True),
            ("Source_Han_Sans_SC_SemiBold_7.otf", 600, False),
            ("Source_Han_Sans_SC_Heavy_Heavy.otf", 900, False),
        ]
        for name, weight, mono in matrix:
            with self.subTest(name=name):
                spec = describe_variant(Path(name))
                self.assertEqual(spec["weight"], weight)
                self.assertEqual(spec["monospace"], mono)

    def test_default_prefers_regular_and_otf(self):
        self._font_file("A", "Alpha-Light.ttf")
        preferred = self._font_file("A", "Alpha-Regular.otf")
        self._font_file("A", "Alpha-Regular.ttf")
        self._font_file("A", "Alpha-Bold.otf")
        self.assertEqual(get_font_by_id(font_catalog.default_local_font_id()), str(preferred.resolve()))

    def test_catalog_ids_remain_stable_after_new_variants(self):
        regular = self._font_file("A", "Alpha-Regular.ttf")
        stored = font_catalog.list_local_fonts()[0]["id"]
        self._font_file("A", "Alpha-Bold.otf")
        self.assertEqual(next(f["id"] for f in font_catalog.list_local_fonts() if f["path"] == str(regular.resolve())), stored)
        client = webapp.app.test_client()
        fields = {
            "title": "复利思维",
            "subtitle": "存款百万不是结束而是开始",
            "account": "",
            "ratio": "3:4",
            "title_font_mode": "local",
            "subtitle_font_mode": "local",
            "title_font_id": stored,
            "subtitle_font_id": stored,
        }
        result = client.post("/api/render", data=fields)
        self.assertEqual(result.status_code, 200, result.get_json(silent=True))
        self.assertEqual(result.data[:4], bytes([137, 80, 78, 71]))

    def test_woff_is_selectable_and_renders_from_font_family(self):
        import io

        from fontTools.ttLib import TTFont
        from PIL import Image
        from renderer import CoverError, render_cover

        folder = Path(self.temp.name) / "WebFontFamily"
        folder.mkdir()
        web_font = folder / "WebFont-Regular.woff"
        font = TTFont(self.system_font)
        try:
            font.flavor = "woff"
            font.save(web_font)
        finally:
            font.close()

        entries = font_catalog.list_local_fonts()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["format"], "WOFF")
        family = font_catalog.public_catalog()["families"][0]
        self.assertEqual(family["name"], "WebFontFamily")
        self.assertEqual(family["count"], 1)
        self.assertEqual(get_font_by_id(entries[0]["id"]), str(web_font.resolve()))

        cover, _ = render_cover(
            title="复利思维",
            subtitle="存款百万不是结束而是开始",
            account="",
            ratio="3:4",
            title_font=web_font,
            subtitle_font=web_font,
        )
        self.assertEqual(cover.size, (1080, 1440))
        client = webapp.app.test_client()
        response = client.get("/api/font-preview", query_string={"id": entries[0]["id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Image.open(io.BytesIO(response.data)).size, (600, 104))

        web_font.write_bytes(b"bad compressed font")
        from renderer import open_font
        with self.assertRaisesRegex(CoverError, "WOFF"):
            open_font(web_font, 48)

    def test_large_font_can_be_indexed(self):
        folder = Path(self.temp.name) / "LargeFamily"
        folder.mkdir()
        file = folder / "Huge-Regular.ttf"
        with file.open("wb") as out:
            out.truncate(28 * 1024 * 1024)
        index = font_catalog.list_local_fonts()
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["family"], "LargeFamily")
        self.assertEqual(index[0]["weight"], 400)


if __name__ == "__main__":
    unittest.main()
