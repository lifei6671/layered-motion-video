import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

import app as webapp
from scene_models import SceneError
from web_fonts import web_font_path


class WebFontTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "fixture.ttf"
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder([".notdef", "A"])
        builder.setupCharacterMap({65: "A"})
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0)); pen.lineTo((500, 700)); pen.lineTo((900, 0)); pen.closePath()
        builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
        builder.setupHorizontalMetrics({".notdef": (1000, 0), "A": (1000, 0)})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupNameTable({"familyName": "Cover Fixture", "styleName": "Regular", "uniqueFontIdentifier": "fixture", "fullName": "Cover Fixture Regular", "psName": "CoverFixture-Regular"})
        builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
        builder.setupPost(); builder.save(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def test_conversion_preserves_source_cmap_metrics_and_reuses_cache(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        target = web_font_path(self.root, self.source)
        self.assertEqual(target.read_bytes()[:4], b"wOF2")
        mtime = target.stat().st_mtime_ns
        self.assertEqual(web_font_path(self.root, self.source), target)
        self.assertEqual(target.stat().st_mtime_ns, mtime)
        with TTFont(self.source) as original, TTFont(target) as converted:
            self.assertEqual(original.getBestCmap(), converted.getBestCmap())
            self.assertEqual(original["hmtx"].metrics, converted["hmtx"].metrics)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before)
        self.assertEqual(web_font_path(self.root, target), target)
        os.utime(self.source, ns=(self.source.stat().st_atime_ns, self.source.stat().st_mtime_ns + 10000000))
        self.assertNotEqual(web_font_path(self.root, self.source), target)

    def test_woff_and_collection_first_face_conversion(self):
        from fontTools.ttLib import TTCollection
        woff = self.root / "fixture.woff"
        with TTFont(self.source) as font:
            font.flavor = "woff"; font.save(woff)
        self.assertEqual(web_font_path(self.root, woff).read_bytes()[:4], b"wOF2")
        collection = TTCollection()
        collection.fonts = [TTFont(self.source), TTFont(self.source)]
        ttc = self.root / "fixture.ttc"
        collection.save(ttc); collection.close()
        self.assertEqual(web_font_path(self.root, ttc).read_bytes()[:4], b"wOF2")

    def test_bad_fonts_fail_explicitly_without_partial_cache(self):
        self.source.write_bytes(b"not-a-font")
        with self.assertRaisesRegex(SceneError, "转为 WOFF2 失败"):
            web_font_path(self.root, self.source)
        self.assertEqual(list((self.root / "font-web").glob("*")), [])

    def test_api_serves_indexed_woff2_and_download_with_cors(self):
        with patch.object(webapp, "DATA_DIR", self.root), patch("react_editor.get_font_by_id", side_effect=lambda fid: str(self.source) if fid == "indexed-fixture" else None):
            client = webapp.app.test_client()
            response = client.get("/api/cover-font?id=indexed-fixture&download=1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data[:4], b"wOF2")
            self.assertEqual(response.mimetype, "font/woff2")
            self.assertIn("fixture.woff2", response.headers["Content-Disposition"])
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
            response.close()
            self.assertEqual(client.get("/api/cover-font?id=../../private.ttf").status_code, 404)
