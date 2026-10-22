"""三块文字独立拖动：默认布局兼容、位置边界及 PNG 逐像素一致性。"""

from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

import app as webapp
from font_catalog import default_font_id, get_font_by_id
from renderer import (
    CoverError, SIZES, account_pixel_position, build_text_layers, render_cover,
)


class ThreeTextLayersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.title_font = get_font_by_id(default_font_id("title"))
        cls.subtitle_font = get_font_by_id(default_font_id("subtitle"))

    @classmethod
    def defaults(cls):
        return dict(
            title="复利思维",
            subtitle="存款百万不是结束而是开始",
            account="@测试",
            ratio="3:4",
            title_font=cls.title_font,
            subtitle_font=cls.subtitle_font,
        )

    def test_pixel_perfect_layers_on_three_formats(self):
        for ratio in ("3:4", "16:9", "9:16"):
            for coordinates in ({}, {
                "title_x": 73.4, "title_y": 78.6,
                "subtitle_x": 2.3, "subtitle_y": 8.5,
                "account_x": 55.8, "account_y": 92.1,
            }):
                with self.subTest(ratio=ratio, coordinates=coordinates):
                    settings = self.defaults() | {"ratio": ratio, **coordinates}
                    original, info = render_cover(**settings)
                    base, _ = render_cover(
                        **settings, include_title=False, include_subtitle=False,
                        include_account=False,
                    )
                    layers, meta = build_text_layers(**settings)
                    expected = base.convert("RGBA")
                    for kind in ("title", "subtitle", "account"):
                        entry = layers[kind]
                        expected.alpha_composite(entry["image"], dest=entry["position"])
                        self.assertEqual(
                            list(entry["position"]),
                            list(info[kind + "_position"]),
                        )
                        self.assertGreater(entry["image"].width, 0)
                        self.assertLessEqual(entry["position"][0] + entry["image"].width, original.width)
                        self.assertLessEqual(entry["position"][1] + entry["image"].height, original.height)
                    self.assertIsNone(
                        ImageChops.difference(original, expected.convert("RGB")).getbbox()
                    )
                    self.assertEqual(meta["title_lines"], info["title_lines"])

    def test_two_line_title_and_divider_travel_as_groups(self):
        kwargs = self.defaults() | {
            "title": "普通人的财富积累逻辑", "subtitle": "普通人的生活经济规律"
        }
        auto_layers, auto = build_text_layers(**kwargs)
        moved_layers, moved = build_text_layers(
            **kwargs, title_x=70, title_y=8, subtitle_x=10, subtitle_y=70,
        )
        self.assertEqual(len(auto["title_lines"]), 2)
        self.assertEqual("".join(auto["title_lines"]), kwargs["title"])
        for kind in ("title", "subtitle", "account"):
            self.assertEqual(auto_layers[kind]["image"].tobytes(), moved_layers[kind]["image"].tobytes())
        self.assertNotEqual(auto["title_position"], moved["title_position"])
        self.assertNotEqual(auto["subtitle_position"], moved["subtitle_position"])
        self.assertEqual(auto["account_position"], moved["account_position"])
        # 小标题图层的末端仍含有灰色分隔线。
        layer = auto_layers["subtitle"]["image"]
        alpha = layer.getchannel("A")
        self.assertGreater(alpha.crop((0, max(0, layer.height - 8), layer.width, layer.height)).getbbox() is not None, 0)

    def test_auto_position_follows_title_length_and_manual_is_stable(self):
        settings = self.defaults()
        _, base = build_text_layers(**settings)
        _, longer = build_text_layers(**(settings | {"title": "普通人的财富积累逻辑"}))
        self.assertNotEqual(base["title_position"], longer["title_position"])
        _, manual = build_text_layers(
            **(settings | {"title_x": 15.0, "title_y": 12.5,
                            "subtitle_x": 62.0, "subtitle_y": 81.0})
        )
        _, manual_longer = build_text_layers(
            **(settings | {"title": "普通人的财富积累逻辑",
                            "title_x": 15.0, "title_y": 12.5,
                            "subtitle_x": 62.0, "subtitle_y": 81.0})
        )
        self.assertEqual(manual["title_position"][0], manual_longer["title_position"][0])
        self.assertEqual(manual["title_position"][1], manual_longer["title_position"][1])
        self.assertEqual(manual["subtitle_position"][1], manual_longer["subtitle_position"][1])

    def test_titles_reject_outside_coordinates(self):
        for key, value in (
            ("title_x", -0.1), ("title_y", 100.1),
            ("subtitle_x", float("nan")), ("subtitle_y", float("inf")),
        ):
            with self.subTest(name=key):
                with self.assertRaises(CoverError):
                    render_cover(**(self.defaults() | {key: value}))

    def test_preview_export_and_preset_http(self):
        with tempfile.TemporaryDirectory() as directory:
            old_data, old_preset = webapp.DATA_DIR, webapp.PRESET_FILE
            try:
                webapp.DATA_DIR = Path(directory)
                webapp.PRESET_FILE = Path(directory) / "preset.json"
                fields = {
                    "title": "复利思维",
                    "subtitle": "存款百万不是结束而是开始",
                    "account": "@测试",
                    "ratio": "3:4",
                    "title_font_mode": "system",
                    "subtitle_font_mode": "system",
                    "title_font_id": default_font_id("title"),
                    "subtitle_font_id": default_font_id("subtitle"),
                    "title_x": "64.25",
                    "title_y": "10.3",
                    "subtitle_x": "2.5",
                    "subtitle_y": "68.8",
                    "account_x": "75.9",
                    "account_y": "90.1",
                }
                client = webapp.app.test_client()
                pages = {
                    "base": client.post("/api/render?preview=all-text", data=fields),
                    "layers": client.post("/api/text-layers", data=fields),
                    "final": client.post("/api/render", data=fields),
                }
                for response in pages.values():
                    self.assertEqual(response.status_code, 200, response.get_json(silent=True) if response.mimetype != "image/png" else response.status)
                payload = pages["layers"].get_json()
                self.assertEqual(set(payload["layers"]), {"title", "subtitle", "account"})
                base = Image.open(io.BytesIO(pages["base"].data)).convert("RGBA")
                final = Image.open(io.BytesIO(pages["final"].data)).convert("RGB")
                for key in ("title", "subtitle", "account"):
                    node = payload["layers"][key]
                    ink = Image.open(io.BytesIO(base64.b64decode(node["png"]))).convert("RGBA")
                    self.assertEqual(ink.size, (node["width"], node["height"]))
                    base.alpha_composite(ink, tuple(node["position"]))
                self.assertIsNone(ImageChops.difference(base.convert("RGB"), final).getbbox())

                saved = client.post("/api/preset", data=fields)
                self.assertEqual(saved.status_code, 200, saved.get_json())
                preset = client.get("/api/preset").get_json()
                self.assertEqual(preset["settings"]["title_x"], 64.25)
                self.assertEqual(preset["settings"]["title_y"], 10.3)
                self.assertEqual(preset["settings"]["subtitle_x"], 2.5)
                self.assertEqual(preset["settings"]["subtitle_y"], 68.8)

                fields.update({"title_x": "", "title_y": "", "subtitle_x": "", "subtitle_y": ""})
                auto = client.post("/api/preset", data=fields)
                self.assertEqual(auto.status_code, 200)
                auto_preset = client.get("/api/preset").get_json()
                for key in ("title_x", "title_y", "subtitle_x", "subtitle_y"):
                    self.assertIsNone(auto_preset["settings"][key])

                legacy = client.post("/api/render?preview=1", data=fields)
                self.assertEqual(legacy.status_code, 200)
                old_layer = client.post("/api/account-layer", data=fields)
                self.assertEqual(old_layer.status_code, 200)
                legacy_img = Image.open(io.BytesIO(legacy.data)).convert("RGBA")
                legacy_layer = Image.open(io.BytesIO(old_layer.data)).convert("RGBA")
                pos = account_pixel_position(
                    fields["ratio"], float(fields["account_x"]), float(fields["account_y"]),
                    legacy_layer.size,
                )
                legacy_img.alpha_composite(legacy_layer, pos)
                full = client.post("/api/render", data=fields)
                self.assertIsNone(ImageChops.difference(
                    legacy_img.convert("RGB"),
                    Image.open(io.BytesIO(full.data)).convert("RGB"),
                ).getbbox())
            finally:
                webapp.DATA_DIR, webapp.PRESET_FILE = old_data, old_preset


if __name__ == "__main__":
    unittest.main()
