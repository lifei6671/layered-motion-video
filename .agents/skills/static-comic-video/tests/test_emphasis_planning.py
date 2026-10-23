"""Planning regressions use declared synthetic clocks, never production alignment."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from scripts.create_fixture import create_fixture
from static_comic.contracts import bytes_digest, canonical, read_json
from static_comic.emphasis import DEFAULT_POLICY, empty_plan, validate_plan
from static_comic.emphasis_cli import merge_candidates, propose
from static_comic.emphasis_layout import choose_layout
from static_comic.emphasis_timing import speech_samples, stable_window
from static_comic.emphasis_vision import POSITIONS, observe
from static_comic.project import compile_project
from static_comic.speech_text import reading_map


def synthetic_alignment(text):
    """Unit-test-only explicit sample evidence, not an alignment approximation."""
    reading = reading_map(text, [])
    return {"reading_map": reading, "characters": [
        {"source": "acoustic_aligned", "samples": [48000 + i*3200, 48000 + i*3200+1600]}
        for i in range(len(reading["text"]))]}


class EmphasisSpeechPlanningTests(unittest.TestCase):
    def test_repeat_words_use_each_exact_codepoint_range(self):
        aligned = synthetic_alignment("重复，重复")
        self.assertEqual(speech_samples(aligned, [0, 2]), [48000, 52800])
        self.assertEqual(speech_samples(aligned, [3, 5]), [54400, 59200])

    def test_whole_percentage_token_resolves_all_reading_characters(self):
        aligned = synthetic_alignment("增长300%！")
        selected = [i for i, value in enumerate(aligned["reading_map"]["source_ranges"]) if value == [2, 6]]
        self.assertGreater(len(selected), 1)
        self.assertEqual(speech_samples(aligned, [2, 6]),
                         [aligned["characters"][selected[0]]["samples"][0],
                          aligned["characters"][selected[-1]]["samples"][1]])
        for selected_range in ([2, 3], [2, 5], [3, 6], [5, 6]):
            with self.subTest(selected_range=selected_range):
                with self.assertRaisesRegex(ValueError, "partial"):
                    speech_samples(aligned, selected_range)

    def test_bom_crlf_non_bmp_and_emoji_do_not_shift_spoken_source_ranges(self):
        raw = b"\xef\xbb\xbf" + "重复😀\r\n重复𠮷".encode("utf-8")
        text = raw.decode("utf-8-sig")
        aligned = synthetic_alignment(text)
        self.assertEqual(aligned["reading_map"]["source_ranges"], [[0, 1], [1, 2], [5, 6], [6, 7], [7, 8]])
        self.assertEqual(speech_samples(aligned, [5, 7]), [54400, 59200])
        self.assertEqual(speech_samples(aligned, [7, 8]), [60800, 62400])
        for span in ([2, 3], [3, 5]):
            with self.assertRaisesRegex(ValueError, "missing"):
                speech_samples(aligned, span)

    def test_missing_low_score_and_coarse_evidence_never_gets_invented_timing(self):
        with self.assertRaisesRegex(ValueError, "TIMING_UNCERTAIN"):
            speech_samples(None, [0, 2])
        for source in ("low_score", "interpolated", "manual_window", "coarse"):
            aligned = synthetic_alignment("重要")
            aligned["characters"][1]["source"] = source
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "TIMING_UNCERTAIN"):
                    speech_samples(aligned, [0, 2])
        aligned = synthetic_alignment("重要")
        aligned["characters"][1]["samples"] = None
        with self.assertRaisesRegex(ValueError, "TIMING_UNCERTAIN"):
            speech_samples(aligned, [0, 2])

    def test_non_monotonic_or_empty_character_intervals_are_rejected(self):
        for samples in ([48000, 48000], [40000, 42000], [-1, 100]):
            aligned = synthetic_alignment("重要")
            aligned["characters"][1]["samples"] = samples
            with self.subTest(samples=samples):
                with self.assertRaisesRegex(ValueError, "TIMING_UNCERTAIN"):
                    speech_samples(aligned, [0, 2])

    def test_stable_window_removes_both_transition_overlaps(self):
        timing = [{"start_frame": 0, "end_frame": 100, "transition_out": {"pre_frames": 4, "post_frames": 8}},
                  {"start_frame": 100, "end_frame": 200, "transition_out": {"pre_frames": 6, "post_frames": 6}},
                  {"start_frame": 200, "end_frame": 300, "transition_out": None}]
        self.assertEqual(stable_window(0, timing), (0, 96))
        self.assertEqual(stable_window(1, timing), (108, 194))
        self.assertEqual(stable_window(2, timing), (206, 300))

    def test_negative_sound_anchor_is_rejected_at_candidate_boundary(self):
        plan = empty_plan(b"test", ["SHOT-001"])
        plan["audio_events"] = [{"id": "SE-1", "kind": "scene", "sfx_asset_id": "asset",
            "anchor": {"type": "shot_start", "shot_id": "SHOT-001", "offset_samples": -1},
            "gain_db": -12, "fade_in_samples": 0, "fade_out_samples": 0, "pinned": False, "source": "rules"}]
        with self.assertRaisesRegex(ValueError, "anchor"):
            validate_plan(plan, script_bytes=b"test", shot_ids=["SHOT-001"])


class EmphasisLayoutPlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Installed system font is read for transient measurement only, not copied
        # into any product, manifest, fixture repository or staged public folder.
        path = Path("C:/Windows/Fonts/arial.ttf")
        if not path.is_file():
            raise unittest.SkipTest("UNAVAILABLE: installed Arial font for metrics")
        cls.font = path.read_bytes()

    def setUp(self):
        self.event = {"id": "VE-1", "text": "300%", "preset": "number_tick", "font_size": 72,
                      "pinned": False, "layout": {"preset": "upper_right"}}
        self.policy = deepcopy(DEFAULT_POLICY["visual"])
        self.observation = {"emotion": "neutral", "subjects": [[.4, .88, .6, .95]],
                            "embedded_text": [], "unusable": [], "regions": {
                                name: [{"edge": 0, "luma": 230, "contrast": 0}] for name in POSITIONS}}
        self.geometry = {"prepared_size": [1920, 1080], "frames": [
            {"global_frame": frame, "crop": [0, 0, 1920, 1080]} for frame in range(60)]}

    def choose(self):
        return choose_layout(self.event, self.font, self.observation, self.geometry, self.policy)

    def test_finite_safe_region_checks_every_motion_frame(self):
        layout, detail = self.choose()
        self.assertIsNotNone(layout)
        self.assertEqual(detail["position"], "upper_right")
        self.assertEqual(detail["frames_checked"], 60)

    def test_busy_regions_and_full_subject_leave_no_safe_position(self):
        for region in self.observation["regions"].values():
            region[0]["edge"] = 99
        layout, detail = self.choose()
        self.assertIsNone(layout)
        self.assertEqual(detail["reason_code"], "NO_SAFE_REGION")
        self.assertIn("VISUAL_BUSY", {entry["reason"] for entry in detail["attempts"]})
        self.setUp()
        self.observation["subjects"] = [[0, 0, 1, 1]]
        layout, detail = self.choose()
        self.assertIsNone(layout)
        self.assertIn("COLLISION", {entry["reason"] for entry in detail["attempts"]})

    def test_embedded_text_and_unusable_boxes_are_collision_obstacles(self):
        for kind in ("embedded_text", "unusable"):
            with self.subTest(kind=kind):
                self.setUp()
                self.observation[kind] = [[0, 0, 1, 1]]
                layout, detail = self.choose()
                self.assertIsNone(layout)
                self.assertIn("COLLISION", {entry["reason"] for entry in detail["attempts"]})

    def test_last_motion_frame_collision_rejects_previously_safe_fixed_location(self):
        self.event.update(pinned=True, layout={"preset": "upper_right", "x": .6, "y": .14})
        self.observation["subjects"] = [[.83, .10, .86, .13]]
        self.assertIsNotNone(self.choose()[0])
        self.geometry["frames"][-1]["crop"] = [800, 0, 1120, 630]
        layout, detail = self.choose()
        self.assertIsNone(layout)
        self.assertEqual(detail["attempts"], [{"position": "fixed", "reason": "COLLISION", "global_frame": 59}])

    def test_pinned_position_never_moves_to_another_safe_candidate(self):
        self.event.update(pinned=True, layout={"preset": "upper_right", "x": .01, "y": .01})
        layout, detail = self.choose()
        self.assertIsNone(layout)
        self.assertEqual(detail["attempts"], [{"position": "fixed", "reason": "SAFE_INSETS"}])
        self.event["pinned"] = False
        self.assertIsNotNone(self.choose()[0])

    def test_quiet_or_unverified_subject_supports_zero_text(self):
        self.observation["emotion"] = "quiet"
        self.assertEqual(self.choose(), (None, {"reason_code": "QUIET_NARRATIVE"}))
        self.observation["emotion"] = "neutral"
        self.observation["subjects"] = []
        layout, detail = self.choose()
        self.assertIsNone(layout)
        self.assertEqual(detail["reason_code"], "UNVERIFIED")

    def test_long_text_does_not_shrink_below_readable_font_to_force_a_fit(self):
        self.event["text"] = "300% " * 40
        layout, detail = self.choose()
        self.assertIsNone(layout)
        self.assertEqual(detail["detail"], "Text exceeds max_width")


class EmphasisObservationPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shot = {"id": "SHOT-001", "start_frame": 0, "end_frame": 9,
                     "image_sha256": "a"*64, "staged_image": "images/technical.png",
                     "motion": {"type": "hold"}}
        self.geometry = {"prepared_size": [480, 270], "subject_bbox_prepared": [200, 200, 260, 250],
                         "frames": [{"global_frame": i, "crop": [0, 0, 480, 270]} for i in range(9)]}
        image = BytesIO()
        Image.new("RGB", (480, 270), "white").save(image, format="PNG")
        self.prepared = {self.shot["staged_image"]: image.getvalue()}

    def observe(self, **kwargs):
        return observe(self.root, [self.shot], [self.geometry], self.prepared, technical=True, **kwargs)

    def supplied(self, entry, **changes):
        value = {"shot_id": "SHOT-001", "evidence_sha256": entry["evidence_sha256"],
                 "viewed_frames": [s["global_frame"] for s in entry["samples"]],
                 "subjects": [], "embedded_text": [], "unusable": [], "emotion": "neutral",
                 "reason": "Declared test observations, not real human approval"}
        value.update(changes)
        path = self.root / "input/emphasis_observations.json"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(canonical({"schema_version": "1.0", "provider": "human", "shots": [value]}))

    def test_rules_emit_real_frame_pngs_without_claiming_model_vision(self):
        result, outputs = self.observe(candidate_frames={"SHOT-001": [3, 100]})
        shot = result["shots"][0]
        self.assertEqual([s["global_frame"] for s in shot["samples"]], [0, 2, 3, 4, 6, 8])
        self.assertEqual(shot["model_status"], "UNAVAILABLE")
        self.assertEqual(shot["status"], "HEURISTIC")
        for sample in shot["samples"]:
            data = outputs[sample["path"]]
            self.assertEqual(bytes_digest(data), sample["sha256"])
            with Image.open(BytesIO(data)) as image:
                self.assertEqual(image.size, (480, 270))

    def test_stale_image_motion_or_unviewed_frame_observations_fail(self):
        entry = self.observe()[0]["shots"][0]
        self.supplied(entry)
        self.assertEqual(self.observe()[0]["shots"][0]["provider"], "human")
        self.shot["image_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "stale/unviewed"):
            self.observe()
        self.shot["image_sha256"] = "a"*64
        self.shot["motion"]["type"] = "zoom_in"
        with self.assertRaisesRegex(ValueError, "stale/unviewed"):
            self.observe()
        self.shot["motion"]["type"] = "hold"
        self.supplied(entry, viewed_frames=[0, 8])
        with self.assertRaisesRegex(ValueError, "stale/unviewed"):
            self.observe()

    def test_authored_observation_keeps_source_subject_and_quiet(self):
        entry = self.observe()[0]["shots"][0]
        self.supplied(entry, subjects=[[.1, .1, .2, .2]], emotion="quiet")
        shot = self.observe()[0]["shots"][0]
        self.assertEqual(len(shot["subjects"]), 2)
        self.assertEqual(shot["emotion"], "quiet")


class EmphasisCandidatePlanningTests(unittest.TestCase):
    def test_merge_preserves_fixed_events_manual_skip_silence_and_input_objects(self):
        current = empty_plan(b"test", ["SHOT-001", "SHOT-002"])
        candidate = deepcopy(current)
        current["shot_decisions"][0].update(text_decision="skip", reason="Explicit manual skip")
        current["shot_decisions"][1].update(sfx_decision="silence", reason="Explicit silence")
        for key in ("visual_events", "audio_events"):
            current[key] = [{"id": key+"-fixed", "pinned": True, "payload": "user"},
                            {"id": key+"-old", "pinned": False}]
            candidate[key] = [{"id": key+"-fixed", "pinned": False, "payload": "agent"},
                              {"id": key+"-new", "pinned": False}]
        before = deepcopy(current)
        merged = merge_candidates(current, candidate)
        self.assertEqual(current, before)
        self.assertEqual(merged["shot_decisions"][0]["text_decision"], "skip")
        self.assertEqual(merged["shot_decisions"][1]["sfx_decision"], "silence")
        for key in ("visual_events", "audio_events"):
            self.assertEqual(merged[key][0]["payload"], "user")
            self.assertEqual([e["id"] for e in merged[key]], [key+"-fixed", key+"-new"])

    def test_real_technical_fixture_zero_events_observations_and_unavailable_agent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            create_fixture(root)
            policy = deepcopy(DEFAULT_POLICY)
            policy["mode"] = "auto"
            policy["audio"]["enabled"] = True
            (root / "input/emphasis_policy.json").write_bytes(canonical(policy))
            compiled = compile_project(root, technical_fixture=True, write=True)
            self.assertEqual(compiled["emphasis"]["visual"], [])
            self.assertEqual(compiled["emphasis"]["sfx"], [])
            self.assertEqual(len(compiled["emphasis"]["observations"]["shots"]), 3)
            self.assertEqual(propose(root, compiled, provider="agent", technical=True)["status"], "UNAVAILABLE")
            proposed = propose(root, compiled, provider="rules", technical=True)
            self.assertEqual(proposed["status"], "PROPOSED")
            self.assertFalse((root / "input/emphasis_plan.json").exists())
            self.assertTrue((root / proposed["path"]).is_file())

    def test_quiet_rule_and_sfx_tags_are_usable_in_candidate_proposal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "input").mkdir()
            script = "安静300%。突然发现300%。".encode()
            text = script.decode()
            parts = [text[:7], text[7:]]
            shots = [{"id": "SHOT-001", "script_range": [0, 7]},
                     {"id": "SHOT-002", "script_range": [7, len(text)]}]
            (root / "input/storyboard.json").write_bytes(canonical({"shots": shots}))
            (root / "input/script.txt").write_bytes(script)
            policy = deepcopy(DEFAULT_POLICY)
            policy.update(mode="mixed")
            policy["visual"]["enabled"] = True
            policy["audio"]["enabled"] = True
            (root / "input/emphasis_policy.json").write_bytes(canonical(policy))
            asset_dir = root / "assets/sfx"
            asset_dir.mkdir(parents=True)
            (asset_dir / "fixture.wav").write_bytes(b"only a contract fixture; not audio decoding")
            (asset_dir / "LICENSE.txt").write_bytes(b"Technical tests only")
            asset = {"asset_id": "technical-narrative", "path": "assets/sfx/fixture.wav",
                "sha256": bytes_digest((asset_dir / "fixture.wav").read_bytes()), "source_kind": "local_created",
                "source_uri": "technical-fixture", "author": "test", "license": "test-only", "usage_scope": "tests",
                "license_evidence": {"path": "assets/sfx/LICENSE.txt", "sha256": bytes_digest(b"Technical tests only")},
                "review_status": "TECHNICAL_ONLY", "sample_rate": 48000, "channels": 2, "duration_samples": 100,
                "tags": ["narrative"]}
            (asset_dir / "manifest.json").write_bytes(canonical({"schema_version": "1.0", "assets": [asset]}))
            observations = [{"emotion": "neutral", "regions": {p: [{"edge": 0}] for p in POSITIONS}}
                            for _ in parts]
            result = propose(root, {"emphasis": {"observations": {"shots": observations}}}, provider="rules", technical=True)
            plan = read_json((root / result["path"]).read_bytes())
            self.assertEqual(plan["shot_decisions"][0]["text_decision"], "skip")
            self.assertEqual(plan["shot_decisions"][0]["sfx_decision"], "silence")
            self.assertEqual(plan["audio_events"][0]["kind"], "narrative")
            self.assertEqual(plan["visual_events"][0]["text"], "300%")


if __name__ == "__main__":
    unittest.main()
