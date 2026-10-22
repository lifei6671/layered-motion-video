"""封面工坊：字体目录、像素位置、页面接口与模板持久化回归测试。"""

import io
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

import app as webapp
import font_catalog
from font_catalog import default_font_id, get_font_by_id, list_system_fonts
from renderer import (
    CoverError, SIZES, account_pixel_position, render_account_layer, render_cover,
)


def png_bytes(color=(80, 110, 150), size=(300, 400)):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, "PNG")
    return stream.getvalue()


@unittest.skipUnless(list_system_fonts(), "此环境缺少系统字体")
class CoverStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.title_font = get_font_by_id(default_font_id("title"))
        cls.subtitle_font = get_font_by_id(default_font_id("subtitle"))

    def make_cover(self, **extra):
        settings = dict(
            title="普通人的财富积累逻辑",
            subtitle="为什么真正的财富来自长期积累",
            account="@测试账号",
            ratio="3:4",
            title_font=self.title_font,
            subtitle_font=self.subtitle_font,
            background=png_bytes(),
            avatar=png_bytes((240, 190, 95)),
        )
        settings.update(extra)
        return render_cover(**settings)

    def test_supported_ratios(self):
        for ratio, size in SIZES.items():
            with self.subTest(ratio=ratio):
                image, info = self.make_cover(ratio=ratio)
                self.assertEqual(image.size, size)
                self.assertEqual((info["width"], info["height"]), size)

    def test_title_wrap_preserves_all_characters(self):
        title = "普通人的财富积累逻辑"
        _, info = self.make_cover(title=title)
        self.assertEqual(len(info["title_lines"]), 2)
        self.assertEqual("".join(info["title_lines"]), title)
        self.assertGreater(info["title_font_size"], 40)

    def test_manual_newline_and_invalid_input(self):
        _, info = self.make_cover(title="普通人\n财富逻辑")
        self.assertEqual(info["title_lines"], ["普通人", "财富逻辑"])
        for title in ("", "过长标题" * 30):
            with self.subTest(title=title):
                with self.assertRaises(CoverError):
                    self.make_cover(title=title)

    def test_background_and_avatar(self):
        image, _ = self.make_cover(glow=False, darkness=0)
        self.assertEqual(image.getpixel((8, 8)), (80, 110, 150))
        self.assertNotEqual(image.getpixel((image.width - 160, int(image.height * 0.76))), (80, 110, 150))

    def test_invalid_image(self):
        with self.assertRaises(CoverError):
            self.make_cover(background=b"not an image")

    def test_local_fonts_detect_changes_without_restart(self):
        old_dir = font_catalog.FONT_DIR
        with tempfile.TemporaryDirectory() as folder:
            try:
                font_catalog.FONT_DIR = Path(folder)
                self.assertEqual(font_catalog.list_local_fonts(), [])
                nested = Path(folder, "毛笔字体")
                nested.mkdir()
                file = nested / "书法.ttf"
                shutil.copyfile(self.title_font, file)
                first = font_catalog.list_local_fonts()
                self.assertEqual(len(first), 1)
                self.assertEqual(first[0]["source"], "local")
                self.assertTrue(first[0]["id"].startswith("local:"))
                self.assertIn("毛笔字体/", first[0]["name"])
                self.assertEqual(get_font_by_id(first[0]["id"]), str(file.resolve()))
                self.assertEqual(font_catalog.public_catalog()["local_count"], 1)

                second_file = Path(folder) / "正文.otf"
                shutil.copyfile(self.subtitle_font, second_file)
                self.assertEqual(len(font_catalog.list_local_fonts()), 2)
                second_file.unlink()
                self.assertEqual(len(font_catalog.list_local_fonts()), 1)
                file.unlink()
                self.assertIsNone(get_font_by_id(first[0]["id"]))
            finally:
                font_catalog.FONT_DIR = old_dir

    def test_local_fonts_end_to_end_save_and_reload(self):
        old_dir = font_catalog.FONT_DIR
        old_data, old_preset = webapp.DATA_DIR, webapp.PRESET_FILE
        with tempfile.TemporaryDirectory() as folder:
            try:
                font_catalog.FONT_DIR = Path(folder) / "fonts"
                font_catalog.FONT_DIR.mkdir()
                shutil.copyfile(self.title_font, font_catalog.FONT_DIR / "calligraphy.ttf")
                local_id = font_catalog.list_local_fonts()[0]["id"]
                webapp.DATA_DIR = Path(folder) / "data"
                webapp.PRESET_FILE = webapp.DATA_DIR / "preset.json"

                fields = {
                    "title": "复利思维",
                    "subtitle": "用时间打造长期收益",
                    "account": "@本地字体",
                    "account_x": "53.5",
                    "account_y": "81.2",
                    "ratio": "3:4",
                    "title_font_mode": "local",
                    "subtitle_font_mode": "local",
                    "title_font_id": local_id,
                    "subtitle_font_id": local_id,
                }
                client = webapp.app.test_client()
                response = client.post("/api/preset", data=fields)
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                stored = client.get("/api/preset").get_json()
                self.assertEqual(stored["settings"]["title_font_id"], local_id)
                self.assertEqual(stored["settings"]["account_x"], 53.5)
                self.assertEqual(stored["settings"]["account_y"], 81.2)

                fields["title"] = "认知成长"
                result = client.post("/api/render", data=fields)
                self.assertEqual(result.status_code, 200, result.status)
                self.assertEqual(result.data[:4], bytes([137, 80, 78, 71]))
                font_catalog.FONT_DIR.joinpath("calligraphy.ttf").unlink()
                stale = client.post("/api/render", data=fields)
                self.assertEqual(stale.status_code, 400)
                self.assertIn("字体", stale.get_json()["error"])
            finally:
                font_catalog.FONT_DIR = old_dir
                webapp.DATA_DIR, webapp.PRESET_FILE = old_data, old_preset

    def test_account_layer_matches_final_export_across_ratios(self):
        for ratio in SIZES:
            for x, y in [(0, 0), (7.2, 68.0), (96.5, 99.5)]:
                with self.subTest(ratio=ratio, x=x, y=y):
                    original, info = self.make_cover(ratio=ratio, account_x=x, account_y=y)
                    base, _ = self.make_cover(ratio=ratio, account_x=x, account_y=y, include_account=False)
                    layer = render_account_layer("@测试账号", ratio, self.subtitle_font)
                    position = account_pixel_position(ratio, x, y, layer.size)
                    expected = base.convert("RGBA")
                    expected.alpha_composite(layer, dest=position)
                    self.assertIsNone(ImageChops.difference(original, expected.convert("RGB")).getbbox())
                    self.assertEqual(tuple(info["account_position"]), position)
                    self.assertLessEqual(position[0] + layer.width, original.width)
                    self.assertLessEqual(position[1] + layer.height, original.height)

    def test_account_empty_and_invalid_coordinates(self):
        layer = render_account_layer("", "3:4", self.subtitle_font)
        self.assertEqual(layer.size, (1, 1))
        for x, y in [(-1, 50), (101, 50), (30, 120), (float("nan"), 50)]:
            with self.subTest(x=x, y=y):
                with self.assertRaises(CoverError):
                    self.make_cover(account_x=x, account_y=y)

    def test_http_preview_layer_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            old_data, old_preset = webapp.DATA_DIR, webapp.PRESET_FILE
            try:
                webapp.DATA_DIR = Path(folder)
                webapp.PRESET_FILE = Path(folder) / "preset.json"
                client = webapp.app.test_client()
                html = client.get("/legacy")
                self.assertEqual(html.status_code, 200)
                self.assertIn(b'id="accountDragHandle"', html.data)
                self.assertIn(b'id="refreshFonts"', html.data)
                self.assertNotIn(b'id="titleFontFile"', html.data)

                fields = {
                    "title": "复利思维",
                    "subtitle": "存款百万不是结束而是开始",
                    "account": "@测试",
                    "account_x": "42.75",
                    "account_y": "23.5",
                    "ratio": "3:4",
                    "title_font_mode": "system",
                    "subtitle_font_mode": "system",
                    "title_font_id": default_font_id("title"),
                    "subtitle_font_id": default_font_id("subtitle"),
                    "darkness": "76",
                    "focus_y": "50",
                    "glow": "true",
                }
                save_payload = {
                    **fields,
                    "background": (io.BytesIO(png_bytes()), "cover-bg.png"),
                    "avatar": (io.BytesIO(png_bytes()), "logo.png"),
                }
                stored = client.post("/api/preset", data=save_payload, content_type="multipart/form-data")
                self.assertEqual(stored.status_code, 200, stored.get_data(as_text=True))
                self.assertTrue((Path(folder) / "background.png").exists())
                self.assertTrue((Path(folder) / "avatar.png").exists())
                preset = client.get("/api/preset").get_json()
                self.assertEqual(preset["settings"]["account_x"], 42.75)
                self.assertEqual(preset["settings"]["account_y"], 23.5)
                self.assertEqual(preset["assets"]["background"], "cover-bg.png")

                base = client.post("/api/render?preview=1", data=fields)
                final = client.post("/api/render", data=fields)
                layer_resp = client.post("/api/account-layer", data=fields)
                for response in (base, final, layer_resp):
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, "image/png")
                base_image = Image.open(io.BytesIO(base.data)).convert("RGBA")
                layer_image = Image.open(io.BytesIO(layer_resp.data)).convert("RGBA")
                full_image = Image.open(io.BytesIO(final.data)).convert("RGB")
                self.assertEqual(final.headers["X-Canvas-Size"], "1080x1440")
                self.assertEqual(int(layer_resp.headers["X-Layer-Width"]), layer_image.width)
                self.assertEqual(int(layer_resp.headers["X-Layer-Height"]), layer_image.height)
                pos = account_pixel_position("3:4", 42.75, 23.5, layer_image.size)
                base_image.alpha_composite(layer_image, dest=pos)
                self.assertIsNone(ImageChops.difference(full_image, base_image.convert("RGB")).getbbox())

                invalid = client.post("/api/render", data={**fields, "account_x": "nan"})
                self.assertEqual(invalid.status_code, 400)
                injection = client.post("/api/render", data={
                    **fields,
                    "title_font_mode": "local",
                    "title_font_id": "../../Windows/Fonts/hack.ttf",
                })
                self.assertEqual(injection.status_code, 400)

                fields["background_action"] = "clear"
                cleared = client.post("/api/preset", data=fields)
                self.assertEqual(cleared.status_code, 200)
                self.assertFalse((Path(folder) / "background.png").exists())
            finally:
                webapp.DATA_DIR, webapp.PRESET_FILE = old_data, old_preset

    def test_woff2_local_font_rendering_and_character_coverage(self):
        """生成真实中文 WOFF2，验证目录发现、页面渲染、字形检查和缓存。"""
        from fontTools import subset
        from fontTools.ttLib import TTFont
        from renderer import open_font, validate_font_text

        original_dir = font_catalog.FONT_DIR
        title = "复利思维"
        subtitle = "存款百万不是结束而是开始"
        account = "@测试账号"
        with tempfile.TemporaryDirectory() as folder:
            try:
                font_catalog.FONT_DIR = Path(folder)
                font_file = Path(folder) / "毛笔标题.woff2"
                source = TTFont(self.title_font)
                try:
                    if any(ord(char) not in (source.getBestCmap() or {}) for char in title + subtitle + account):
                        self.skipTest("当前系统字体不包含测试所需字符")
                    subsetter = subset.Subsetter()
                    subsetter.populate(text=title + subtitle + account)
                    subsetter.subset(source)
                    source.flavor = "woff2"
                    source.save(font_file)
                finally:
                    source.close()

                entries = font_catalog.list_local_fonts()
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]["id"], font_catalog.default_local_font_id())
                self.assertEqual(entries[0]["path"], str(font_file.resolve()))
                self.assertEqual(font_catalog.get_font_by_id(entries[0]["id"]), str(font_file.resolve()))
                self.assertEqual(font_catalog.public_catalog()["local_count"], 1)

                face = open_font(font_file, 72)
                self.assertTrue(face.getname()[0])
                self.assertGreater(face.getbbox(title)[2], 0)
                image, metadata = self.make_cover(
                    title=title, subtitle=subtitle, account=account,
                    title_font=font_file, subtitle_font=font_file,
                )
                self.assertEqual(image.size, (1080, 1440))
                self.assertEqual("".join(metadata["title_lines"]), title)
                with self.assertRaisesRegex(CoverError, "缺少字符"):
                    validate_font_text(font_file, "普通人的积累逻辑", "大标题")

                fields = {
                    "title": title,
                    "subtitle": subtitle,
                    "account": account,
                    "ratio": "3:4",
                    "title_font_mode": "local",
                    "subtitle_font_mode": "local",
                    "title_font_id": entries[0]["id"],
                    "subtitle_font_id": entries[0]["id"],
                }
                client = webapp.app.test_client()
                image_response = client.post("/api/render", data=fields)
                self.assertEqual(image_response.status_code, 200, image_response.get_json(silent=True))
                self.assertEqual(image_response.data[:4], bytes((137, 80, 78, 71)))
                layer_response = client.post("/api/account-layer", data=fields)
                self.assertEqual(layer_response.status_code, 200)

                response = client.post("/api/render", data={**fields, "title": "普通人的积累逻辑"})
                self.assertEqual(response.status_code, 400)
                self.assertIn("缺少字符", response.get_json()["error"])

                font_file.write_bytes(b"broken woff2")
                with self.assertRaisesRegex(CoverError, "WOFF2"):
                    open_font(font_file, 72)
            finally:
                font_catalog.FONT_DIR = original_dir

    def test_real_http_static_routes(self):
        import threading
        import urllib.request
        from werkzeug.serving import make_server

        server = make_server("127.0.0.1", 0, webapp.app)
        port = server.socket.getsockname()[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for route, mimetype in (
                ("/", "text/html"),
                ("/legacy", "text/html"),
                ("/static/style.css", "text/css"),
                ("/static/app.js", "javascript"),
                ("/static/fabric-poc.css", "text/css"),
                ("/static/fabric-poc.bundle.js", "javascript"),
                ("/api/fonts", "application/json"),
                ("/api/preset", "application/json"),
            ):
                with self.subTest(route=route):
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}{route}", timeout=20) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn(mimetype, response.headers.get("Content-Type", ""))
                        self.assertTrue(response.read())
        finally:
            server.shutdown()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
