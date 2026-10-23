"""K5 incremental matrix: real PCM/FFmpeg, declared renderer/media doubles.

Synthetic character evidence and locally drawn test glyphs are never production
alignment, font licenses, image approvals or listening acceptance.
"""
from io import BytesIO
import unittest
from unittest.mock import patch
import wave

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
import numpy as np

from static_comic import delivery
from static_comic.cache import publish
from static_comic.contracts import canonical, read_json
from static_comic.media import file_hash
from static_comic.speech import read_evidence, store_evidence
from static_comic.speech_audio import prepare_audio
from speech_support import seed_alignment
import test_emphasis_integration
from test_sc_p5 import decision
from test_sfx import wav


def synthetic_font(width=600):
    """Original rectangle outlines for two codepoints; no installed font copied."""
    names = [".notdef", "repeat", "sentence"]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord("复"): "repeat", ord("句"): "sentence"})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        pen.moveTo((60, 0)); pen.lineTo((width-60, 0)); pen.lineTo((width-60, 700))
        pen.lineTo((60, 700)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (width, 60) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "TEST_ONLY Rectangle", "styleName": "Regular",
                           "uniqueFontIdentifier": f"test-rectangle-{width}",
                           "fullName": "TEST_ONLY Rectangle", "psName": "TestRectangle"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    output = BytesIO(); builder.save(output)
    return output.getvalue()


class EmphasisIncrementalTests(unittest.TestCase):
    # Reuse setup/helpers only; inherited tests would duplicate the existing
    # four-case suite, including the already-covered gain-only invalidation.
    setUp = test_emphasis_integration.EmphasisIntegrationTests.setUp
    run_command = test_emphasis_integration.EmphasisIntegrationTests.run_command
    cache_status = test_emphasis_integration.EmphasisIntegrationTests.cache_status
    save_plan = test_emphasis_integration.EmphasisIntegrationTests.save_plan

    def baseline(self):
        first = delivery.preview(self.root, True)
        delivery.approve(self.root, decision(first["binding_sha256"]), True)
        return first, len(self.commands)

    def assert_stale(self, first, second):
        self.assertNotEqual(first["binding_sha256"], second["binding_sha256"])
        with self.assertRaisesRegex(ValueError, "explicit semantic"):
            delivery.render_visual(self.root, True)

    def edit_board(self, change):
        path = self.root / "input/storyboard.json"
        board = read_json(path.read_bytes())
        change(board)
        publish(self.root, {"input/storyboard.json": canonical(board)})

    def add_visual(self):
        path = self.root / "assets/fonts/test.ttf"
        path.parent.mkdir(parents=True)
        path.write_bytes(synthetic_font())
        license_path = path.with_name("LICENSE.txt")
        license_path.write_bytes(b"Original numeric rectangle outlines from test_emphasis_incremental.py. TEST_ONLY.")
        asset = {"asset_id": "test-font", "path": "assets/fonts/test.ttf", "sha256": file_hash(path),
                 "family": "TEST_ONLY Rectangle", "source_kind": "local_created",
                 "source_uri": "local:test_emphasis_incremental.py", "author": "test generator",
                 "license": "test-only", "usage_scope": "temporary technical tests",
                 "license_evidence": {"path": "assets/fonts/LICENSE.txt", "sha256": file_hash(license_path)},
                 "review_status": "TECHNICAL_ONLY"}
        publish(self.root, {"assets/fonts/manifest.json": canonical({"schema_version": "1.0", "assets": [asset]})})
        self.policy["visual"]["enabled"] = True
        self.plan["shot_decisions"][0]["text_decision"] = "auto"
        self.plan["visual_events"] = [{"id": "VE-1", "shot_id": "SHOT-001", "script_range": [1, 3],
            "text": "复句", "semantic_type": "concept", "importance": "high", "preset": "soft_rise", "tier": 1,
            "font_asset_id": "test-font", "font_size": 48, "layout": {"preset": "upper_right"},
            "pinned": False, "source": "rules"}]
        publish(self.root, {"input/emphasis_policy.json": canonical(self.policy)})
        self.save_plan()
        # Keep real FFmpeg preparation and normal replay; only raw model results
        # are explicitly synthetic, as in the existing speech test fixtures.
        audio = prepare_audio(self.root, "input/voice.wav")
        preserved = {n: (self.root / n).read_bytes() for n in ("work/audio/master_48k.wav", "work/audio/align_16k.wav")}
        aligned = seed_alignment(self.root, technical_fixture=True)
        raw = read_evidence(self.root, aligned["raw_ref"])
        raw["audio"] = audio
        raw["TEST_ONLY"] = "Synthetic model character evidence; no speech model invoked"
        aligned["raw_ref"] = store_evidence(self.root, raw)
        publish(self.root, {**preserved, "work/alignment/aligned.json": canonical(aligned)})
        # The visual stream is a declared renderer double, so extracting real
        # pixels would be invalid. This inventory double is confined to tests.
        context = patch("static_comic.emphasis_preview.preview_evidence", side_effect=lambda _, compiled, loc: {
            loc["preview"]+"/emphasis.json": canonical({"TEST_DOUBLE": True, "events": compiled["emphasis"]})})
        context.start(); self.addCleanup(context.stop)

    def test_only_text_changes_rebuild_visual_keep_mix_and_never_run_alignment_model(self):
        self.add_visual()
        first, before = self.baseline()
        alignment = file_hash(self.root / "work/alignment/aligned.json")
        master = file_hash(self.root / "work/audio/master_48k.wav")
        self.plan["visual_events"][0].update(script_range=[1, 2], text="复")
        self.save_plan()
        with patch("static_comic.speech.align_project", side_effect=AssertionError("Model alignment must not rerun")) as model:
            second = delivery.preview(self.root, True)
        model.assert_not_called()
        self.assertEqual(self.commands[before:], ["render", "mux"])
        self.assertEqual(self.cache_status("visual-preview"), "REBUILT")
        self.assertEqual(self.cache_status("remotion-build"), "HIT")
        self.assertEqual(self.cache_status("sfx-mix"), "HIT")
        self.assertEqual(self.cache_status("sfx-normalize"), "HIT")
        self.assertEqual(file_hash(self.root / "work/alignment/aligned.json"), alignment)
        self.assertEqual(file_hash(self.root / "work/audio/master_48k.wav"), master)
        props = read_json((self.root / "work/remotion/technical/props.json").read_bytes())
        self.assertEqual(props["visual_emphasis"][0]["text"], "复")
        self.assert_stale(first, second)

    def test_font_bytes_rebuild_bundle_and_visual_keep_independent_audio(self):
        self.add_visual()
        first, before = self.baseline()
        path = self.root / "assets/fonts/test.ttf"
        path.write_bytes(synthetic_font(width=650))
        manifest = read_json((self.root / "assets/fonts/manifest.json").read_bytes())
        manifest["assets"][0]["sha256"] = file_hash(path)
        publish(self.root, {"assets/fonts/manifest.json": canonical(manifest)})
        second = delivery.preview(self.root, True)
        self.assertEqual(self.commands[before:], ["bundle", "render", "mux"])
        self.assertEqual(self.cache_status("remotion-build"), "REBUILT")
        self.assertEqual(self.cache_status("visual-preview"), "REBUILT")
        self.assertEqual(self.cache_status("sfx-mix"), "HIT")
        self.assertEqual(self.cache_status("sfx-normalize"), "HIT")
        self.assert_stale(first, second)

    def test_motion_changes_rebuild_visual_keep_unrelated_sound_and_expire_approval(self):
        first, before = self.baseline()
        self.edit_board(lambda board: board["shots"][0]["motion"].update(scale_to=1.12))
        second = delivery.preview(self.root, True)
        self.assertIn("render", self.commands[before:])
        self.assertEqual(self.cache_status("image-shot-001"), "REBUILT")
        self.assertEqual(self.cache_status("visual-preview"), "REBUILT")
        self.assertEqual(self.cache_status("sfx-mix"), "HIT")
        self.assert_stale(first, second)

    def test_narration_same_length_rebuilds_mix_preserves_visual_and_effect_asset(self):
        first, before = self.baseline()
        old_master = file_hash(self.root / "work/audio/master_48k.wav")
        source = self.root / "input/voice.wav"
        with wave.open(str(source), "rb") as stream:
            params = stream.getparams(); values = bytearray(stream.readframes(stream.getnframes()))
        values[100:102] = b"\x20\x00"
        with wave.open(str(source), "wb") as stream:
            stream.setparams(params); stream.writeframes(values)
        self.edit_board(lambda board: board["audio"].update(sha256=file_hash(source)))
        second = delivery.preview(self.root, True)
        self.assertEqual(self.commands[before:], ["mux"])
        self.assertEqual(self.cache_status("audio"), "REBUILT")
        self.assertEqual(self.cache_status("visual-preview"), "HIT")
        self.assertEqual(self.cache_status("sfx-normalize"), "HIT")
        self.assertEqual(self.cache_status("sfx-mix"), "REBUILT")
        self.assertNotEqual(file_hash(self.root / "work/audio/master_48k.wav"), old_master)
        self.assert_stale(first, second)

    def test_sound_asset_bytes_rebuild_normalization_mix_keep_visual(self):
        first, before = self.baseline()
        path = self.root / "assets/sfx/pulse.wav"
        pulse = np.zeros((512, 2)); pulse[0] = [4000, -4000]
        wav(path, pulse)
        manifest = read_json((self.root / "assets/sfx/manifest.json").read_bytes())
        manifest["assets"][0]["sha256"] = file_hash(path)
        publish(self.root, {"assets/sfx/manifest.json": canonical(manifest)})
        second = delivery.preview(self.root, True)
        self.assertEqual(self.commands[before:], ["mux"])
        self.assertEqual(self.cache_status("sfx-normalize"), "REBUILT")
        self.assertEqual(self.cache_status("sfx-mix"), "REBUILT")
        self.assertEqual(self.cache_status("visual-preview"), "HIT")
        self.assert_stale(first, second)

    def test_transition_window_changes_recompile_bound_sound_and_visual(self):
        self.plan["audio_events"][0].update(kind="transition", anchor={"type": "transition_frame",
            "from_shot_id": "SHOT-001", "point": "start", "offset_samples": 0})
        self.save_plan()
        first, before = self.baseline()
        old_start = read_json((self.root / "work/emphasis/technical/sfx.lock.json").read_bytes())["events"][0]["start_sample"]
        self.edit_board(lambda board: board["shots"][0]["transition_out"].update(duration_frames=18))
        second = delivery.preview(self.root, True)
        new_start = read_json((self.root / "work/emphasis/technical/sfx.lock.json").read_bytes())["events"][0]["start_sample"]
        self.assertEqual(old_start-new_start, 6*1600)
        self.assertIn("render", self.commands[before:])
        self.assertEqual(self.cache_status("visual-preview"), "REBUILT")
        self.assertEqual(self.cache_status("sfx-mix"), "REBUILT")
        self.assertEqual(self.cache_status("sfx-normalize"), "HIT")
        self.assert_stale(first, second)


if __name__ == "__main__":
    unittest.main()
