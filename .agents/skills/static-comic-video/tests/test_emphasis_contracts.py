"""K1 contracts, deterministic plans and local resource evidence rejection."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from static_comic.contracts import bytes_digest, canonical, validate
from static_comic.emphasis import (DEFAULT_POLICY, empty_plan, load_extension,
                                   load_policy, normalized_plan_bytes, validate_plan)


class EmphasisContractsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = b'\xef\xbb\xbf' + "重复😀300%\r\n重复".encode()
        self.shots = ["SHOT-001", "SHOT-002"]

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else canonical(value))

    def policy(self, visual=False, audio=False):
        value = deepcopy(DEFAULT_POLICY)
        value["mode"] = "mixed"
        value["visual"]["enabled"] = visual
        value["audio"]["enabled"] = audio
        self.write("input/emphasis_policy.json", value)
        return value

    def resource(self, kind="fonts"):
        data = b"TECHNICAL ONLY placeholder bytes, format validation belongs to rendering/audio probe"
        evidence = b"Technical contract test fixture. Not approved production content."
        path = f"assets/{kind}/fixture." + ("ttf" if kind == "fonts" else "wav")
        license_path = f"assets/{kind}/LICENSE.txt"
        self.write(path, data)
        self.write(license_path, evidence)
        asset = {"asset_id": "fixture", "path": path, "sha256": bytes_digest(data),
                 "source_kind": "local_created", "source_uri": "technical-fixture",
                 "author": "TEST ONLY", "license": "fixture-only", "usage_scope": "tests",
                 "license_evidence": {"path": license_path, "sha256": bytes_digest(evidence)},
                 "review_status": "TECHNICAL_ONLY"}
        if kind == "fonts":
            asset["family"] = "Technical Fixture"
        else:
            asset.update(sample_rate=48000, channels=2, duration_samples=3200, tags=["scene"])
        self.write(f"assets/{kind}/manifest.json", {"schema_version": "1.0", "assets": [asset]})
        return asset

    def load(self, **kwargs):
        return load_extension(self.root, script_bytes=self.script, shot_ids=self.shots, **kwargs)

    def test_missing_extension_keeps_old_project_without_asset_directories(self):
        result = self.load()
        self.assertEqual(result["policy"]["mode"], "disabled")
        self.assertEqual(result["fonts"], {})
        self.assertEqual(result["sfx"], {})
        self.assertEqual(list(self.root.iterdir()), [])

    def test_all_independent_switch_modes_and_on_demand_audio(self):
        for visual, audio in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(visual=visual, audio=audio):
                self.policy(visual, audio)
                if visual:
                    self.resource()
                loaded = self.load(technical=True)
                self.assertEqual(bool(loaded["fonts"]), visual)
                self.assertEqual(loaded["sfx"], {})
                self.assertEqual(len(loaded["plan"]["shot_decisions"]), 2)

    def test_partial_policy_is_normalized_deterministically(self):
        self.write("input/emphasis_policy.json", {"schema_version": "1.0", "mode": "auto",
                                                  "visual": {"enabled": False}, "audio": {"enabled": True}})
        self.assertEqual(canonical(load_policy(self.root)), canonical(load_policy(self.root)))
        self.assertEqual(load_policy(self.root)["audio"]["sample_rate"], 48000)

    def test_duplicate_unknown_nonfinite_policy_inputs_rejected(self):
        bad = [b'{"mode":"auto","mode":"disabled"}',
               canonical({**DEFAULT_POLICY, "command": "anything"}),
               b'{"x": NaN}', b'{"x": Infinity}', b'{"x": 1e999}']
        for raw in bad:
            with self.subTest(raw=raw):
                self.write("input/emphasis_policy.json", raw)
                with self.assertRaises(ValueError):
                    load_policy(self.root)

    def test_disabled_mode_rejects_enabled_channels(self):
        value = deepcopy(DEFAULT_POLICY)
        value["visual"]["enabled"] = True
        self.write("input/emphasis_policy.json", value)
        with self.assertRaisesRegex(ValueError, "disabled"):
            self.load()

    def test_visual_requires_resource_manifest(self):
        self.policy(visual=True)
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.load()

    def test_font_hash_and_license_hash_tampering_rejected(self):
        self.policy(visual=True)
        asset = self.resource()
        self.write(asset["path"], b"tampered")
        with self.assertRaisesRegex(ValueError, "fixture.*SHA256"):
            self.load(technical=True)
        self.resource()
        self.write(asset["license_evidence"]["path"], b"tampered")
        with self.assertRaisesRegex(ValueError, "fixture.*license evidence"):
            self.load(technical=True)

    def test_technical_license_never_becomes_production_approval(self):
        self.policy(visual=True)
        self.resource()
        with self.assertRaisesRegex(ValueError, "not approved"):
            self.load()

    def test_missing_license_and_path_injection_rejected(self):
        self.policy(visual=True)
        base = self.resource()
        for path in ("../fixture.ttf", "assets/sfx/fixture.ttf", "C:/fixture.ttf", "assets/fonts/../fixture.ttf"):
            with self.subTest(path=path):
                asset = {**base, "path": path}
                self.write("assets/fonts/manifest.json", {"schema_version": "1.0", "assets": [asset]})
                with self.assertRaises(ValueError):
                    self.load(technical=True)
        asset = deepcopy(base)
        del asset["license_evidence"]
        self.write("assets/fonts/manifest.json", {"schema_version": "1.0", "assets": [asset]})
        with self.assertRaisesRegex(ValueError, "license_evidence"):
            self.load(technical=True)

    def test_duplicate_resource_id_rejected(self):
        self.policy(visual=True)
        asset = self.resource()
        self.write("assets/fonts/manifest.json", {"schema_version": "1.0", "assets": [asset, asset]})
        with self.assertRaisesRegex(ValueError, "duplicate asset_id"):
            self.load(technical=True)

    def test_resource_symlink_is_rejected_even_within_project(self):
        self.policy(visual=True)
        asset = self.resource()
        link = self.root / "assets/fonts/linked.ttf"
        try:
            link.symlink_to(self.root / asset["path"])
        except OSError as error:
            self.skipTest(f"Platform cannot create symlink: {error}")
        asset["path"] = "assets/fonts/linked.ttf"
        self.write("assets/fonts/manifest.json", {"schema_version": "1.0", "assets": [asset]})
        with self.assertRaisesRegex(ValueError, "reparse point"):
            self.load(technical=True)

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_windows_junction_resource_is_rejected(self):
        self.policy(visual=True)
        asset = self.resource()
        target = self.root / "assets/fonts"
        link = target / "redirect"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        asset["path"] = "assets/fonts/redirect/fixture.ttf"
        self.write("assets/fonts/manifest.json", {"schema_version": "1.0", "assets": [asset]})
        try:
            with self.assertRaisesRegex(ValueError, "reparse point"):
                self.load(technical=True)
        finally:
            # rmdir only removes the junction, never recursively traverses it.
            link.rmdir()

    def test_sfx_assets_are_required_only_when_used(self):
        self.policy(audio=True)
        self.load()
        plan = empty_plan(self.script, self.shots)
        plan["audio_events"] = [{"id": "SE-1", "kind": "scene", "sfx_asset_id": "fixture",
                                 "anchor": {"type": "shot_start", "shot_id": "SHOT-001", "offset_samples": 0},
                                 "gain_db": -12, "fade_in_samples": 0, "fade_out_samples": 960,
                                 "pinned": False, "source": "rules"}]
        self.write("input/emphasis_plan.json", plan)
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.load(technical=True)
        self.resource("sfx")
        self.assertEqual(list(self.load(technical=True)["sfx"]), ["fixture"])

    def test_sfx_start_only_trim_defers_end_to_asset_duration(self):
        plan = empty_plan(self.script, self.shots)
        plan["audio_events"] = [{"id": "SE-trim", "kind": "scene", "sfx_asset_id": "fixture",
            "anchor": {"type": "shot_start", "shot_id": "SHOT-001", "offset_samples": 0},
            "gain_db": -12, "fade_in_samples": 0, "fade_out_samples": 0,
            "pinned": False, "source": "rules", "trim_start_sample": 240}]
        result = validate_plan(plan, script_bytes=self.script, shot_ids=self.shots)
        self.assertEqual(result["audio_events"][0]["trim_start_sample"], 240)
        self.assertNotIn("trim_end_sample", result["audio_events"][0])

    def test_sfx_end_only_trim_keeps_implicit_zero_start(self):
        plan = empty_plan(self.script, self.shots)
        plan["audio_events"] = [{"id": "SE-trim", "kind": "scene", "sfx_asset_id": "fixture",
            "anchor": {"type": "shot_start", "shot_id": "SHOT-001", "offset_samples": 0},
            "gain_db": -12, "fade_in_samples": 0, "fade_out_samples": 0,
            "pinned": False, "source": "rules", "trim_end_sample": 240}]
        result = validate_plan(plan, script_bytes=self.script, shot_ids=self.shots)
        self.assertEqual(result["audio_events"][0]["trim_end_sample"], 240)
        self.assertNotIn("trim_start_sample", result["audio_events"][0])

    def test_sfx_explicit_empty_or_reversed_trim_is_rejected(self):
        plan = empty_plan(self.script, self.shots)
        event = {"id": "SE-trim", "kind": "scene", "sfx_asset_id": "fixture",
            "anchor": {"type": "shot_start", "shot_id": "SHOT-001", "offset_samples": 0},
            "gain_db": -12, "fade_in_samples": 0, "fade_out_samples": 0,
            "pinned": False, "source": "rules", "trim_start_sample": 240}
        for end in (120, 240):
            with self.subTest(end=end):
                plan["audio_events"] = [{**event, "trim_end_sample": end}]
                with self.assertRaisesRegex(ValueError, "SE-trim: empty/reversed source trim"):
                    validate_plan(plan, script_bytes=self.script, shot_ids=self.shots)

    def event(self):
        return {"id": "VE-1", "shot_id": "SHOT-002", "script_range": [9, 11], "text": "重复",
                "semantic_type": "concept", "importance": "high", "preset": "soft_rise", "tier": 1,
                "layout": {"preset": "upper_right"}, "pinned": False, "source": "rules"}

    def test_exact_codepoint_ranges_preserve_bom_emoji_percentage_and_crlf(self):
        plan = empty_plan(self.script, self.shots)
        plan["visual_events"] = [self.event()]
        validate_plan(plan, script_bytes=self.script, shot_ids=self.shots)
        self.assertEqual(normalized_plan_bytes(plan), normalized_plan_bytes(deepcopy(plan)))
        for selected, text in (([2, 3], "😀"), ([3, 7], "300%"), ([7, 9], "\r\n重复"), ([9, 12], "重复")):
            plan["visual_events"][0].update(script_range=selected, text=text)
            if selected in ([2, 3], [3, 7]):
                validate_plan(plan, script_bytes=self.script, shot_ids=self.shots)
            else:
                with self.assertRaises(ValueError):
                    validate_plan(plan, script_bytes=self.script, shot_ids=self.shots)

    def test_shot_coverage_unknown_ids_reason_and_duplicate_events_rejected(self):
        plan = empty_plan(self.script, self.shots)
        variants = []
        bad = deepcopy(plan); bad["shot_decisions"].pop(); variants.append(bad)
        bad = deepcopy(plan); bad["shot_decisions"][1]["shot_id"] = "SHOT-001"; variants.append(bad)
        bad = deepcopy(plan); bad["shot_decisions"][0]["reason"] = " "; variants.append(bad)
        bad = deepcopy(plan); bad["shot_decisions"][0]["reason_code"] = "UNKNOWN"; variants.append(bad)
        bad = deepcopy(plan); bad["visual_events"] = [self.event(), self.event()]; variants.append(bad)
        bad = deepcopy(plan); bad["visual_events"] = [{**self.event(), "shot_id": "SHOT-099"}]; variants.append(bad)
        bad = deepcopy(plan); bad["visual_events"] = [{**self.event(), "preset": "arbitrary_code"}]; variants.append(bad)
        bad = deepcopy(plan); bad["visual_events"] = [{**self.event(), "tier": 2}]; variants.append(bad)
        bad = deepcopy(plan); bad["visual_events"] = [{**self.event(), "font_size": float("inf")}]; variants.append(bad)
        bad = deepcopy(plan); bad["visual_events"] = [{**self.event(), "script_range": [10, 9]}]; variants.append(bad)
        bad = deepcopy(plan); bad["script_sha256"] = "0" * 64; variants.append(bad)
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_plan(value, script_bytes=self.script, shot_ids=self.shots)

    def test_changed_asset_metadata_changes_extension_fingerprint(self):
        self.policy(visual=True)
        asset = self.resource()
        before = self.load(technical=True)["input_hashes"]
        asset["usage_scope"] = "changed scope"
        self.write("assets/fonts/manifest.json", {"schema_version": "1.0", "assets": [asset]})
        after = self.load(technical=True)["input_hashes"]
        self.assertNotEqual(before["fonts_sha256"], after["fonts_sha256"])
        self.assertEqual(before["plan_sha256"], after["plan_sha256"])


if __name__ == "__main__":
    unittest.main()
