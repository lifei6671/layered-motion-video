"""Earshot provider/marker sync regressions; only isolated TEST_ONLY roots are modified."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from static_comic.contracts import canonical, read_json, validate
from static_comic.earshot_provider import (
    BANK_VERSION, SOURCE_COMMIT, local_runtime, load_bank, render,
)
from static_comic.earshot_cues import propose_card_sounds
from static_comic.emphasis import DEFAULT_POLICY, empty_plan, verify_asset, load_manifest
from static_comic.emphasis_timing import compile_events


class EarshotProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sc-a-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = "测试数字是300%。".encode("utf-8")
        self.write("input/script.txt", self.script)

    def write(self, filename, value):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else canonical(value))

    def test_pinned_runtime_and_model_free_bank_catalog(self):
        self.assertTrue(local_runtime().is_dir())
        bank = load_bank()
        self.assertEqual(bank.VERSION, BANK_VERSION)
        self.assertEqual(len(bank.list()), 252)

    def test_wav_generation_is_deterministic_and_remains_technical_only(self):
        first = render(self.root, "ui_pop/soft", uses=["keyword"], seed=7, technical_fixture=True)
        second = render(self.root, "ui_pop/soft", uses=["keyword"], seed=7, technical_fixture=True)
        self.assertEqual((first["asset_id"], first["sha256"]),
                         (second["asset_id"], second["sha256"]))
        manifest = validate("sfxManifest", read_json((self.root/"assets/sfx/manifest.json").read_bytes()))
        self.assertEqual(len(manifest["assets"]), 1)
        asset = manifest["assets"][0]
        self.assertEqual(asset["review_status"], "TECHNICAL_ONLY")
        self.assertEqual(asset["generator"]["source_commit"], SOURCE_COMMIT)
        self.assertLess(asset["cue_points"]["onset_samples"],asset["cue_points"]["peak_samples"])
        self.assertLess(asset["cue_points"]["peak_samples"],first["duration_samples"])
        with wave.open(str(self.root/first["asset_path"]), "rb") as source:
            self.assertEqual((source.getframerate(),source.getnchannels(),source.getnframes()),
                             (48000,2,first["duration_samples"]))
        verify_asset(self.root,asset,kind="sfx",technical=True)
        with self.assertRaisesRegex(ValueError, "approved"):
            verify_asset(self.root,asset,kind="sfx",technical=False)
        # Pretending the manifest was approved must never bypass the signed receipt gate.
        forged={**asset,"review_status":"APPROVED"}
        with self.assertRaisesRegex(ValueError,"signed resource approval"):
            verify_asset(self.root,forged,kind="sfx",technical=False)

    def test_production_sound_is_candidate_and_does_not_self_approve(self):
        candidate = render(self.root, "ui_pop/soft", uses=["keyword"],seed=11)
        item=read_json((self.root/"assets/sfx/manifest.json").read_bytes())["assets"][0]
        self.assertEqual(item["review_status"],"CANDIDATE")
        self.assertTrue(candidate["requires_human_review"])
        self.assertFalse((self.root/"review/emphasis_resource_approvals.json").exists())

    def test_unapproved_candidate_does_not_break_existing_selected_sound(self):
        # 当前有效技术音效与新候选共存，只验证被计划引用的音效。
        used = render(self.root,"ui_pop/soft",uses=["keyword"],seed=19,technical_fixture=True)
        pending = render(self.root,"ui_pop/soft",uses=["keyword"],seed=20)
        self.assertNotEqual(used["asset_id"],pending["asset_id"])
        library = load_manifest(self.root,"sfx",technical=True,required_ids={used["asset_id"]})
        self.assertEqual(set(library),{used["asset_id"]})
        with self.assertRaisesRegex(ValueError,"not approved"):
            load_manifest(self.root,"sfx",technical=True,required_ids={pending["asset_id"]})
        available = load_manifest(self.root,"sfx",technical=True)
        self.assertEqual(set(available),{used["asset_id"]})

    def test_manually_forged_sync_point_outside_audio_is_rejected(self):
        source=render(self.root,"ui_pop/soft",uses=["keyword"],seed=21,technical_fixture=True)
        asset=read_json((self.root/"assets/sfx/manifest.json").read_bytes())["assets"][0]
        forged=deepcopy(asset)
        forged["cue_points"]["peak_samples"]=source["duration_samples"]+1
        with self.assertRaisesRegex(ValueError,"cue points"):
            verify_asset(self.root,forged,kind="sfx",technical=True)

    def test_unsafe_or_unsupported_render_options_are_rejected(self):
        for ident,opts in [
            ("../../python",{}), ("os/system",{}),
            ("ui_pop/soft",{"duration_s":13}), ("ui_pop/soft",{"apex_s":.1}),
            ("ui_pop/soft",{"seed":-1}), ("ui_pop/soft",{"pitch":"__hack"}),
        ]:
            with self.subTest(ident=ident,options=opts):
                with self.assertRaises(ValueError):
                    render(self.root,ident,uses=["keyword"],technical_fixture=True,**opts)
        self.assertFalse((self.root/"assets/sfx/manifest.json").exists())

    def test_card_sound_proposal_is_not_automatic_approval_or_import(self):
        generated=render(self.root,"ui_pop/soft",uses=["keyword"],seed=9,technical_fixture=True)
        policy=deepcopy(DEFAULT_POLICY)
        policy["mode"]="mixed"; policy["audio"]["enabled"]=True
        self.write("input/emphasis_policy.json",policy)
        selected=empty_plan(self.script,["SHOT-001"])
        selected["shot_decisions"][0]["sfx_decision"]="allow"
        self.write("input/emphasis_plan.json",selected)
        compiled={"motion_cards":{"events":[{"id":"MC-001","recipe":"talkcraft-number-slab",
                    "shot_id":"SHOT-001","start_frame":30,"end_frame":100}]},
                "timeline":{"shots":[{"source":{"id":"SHOT-001"}}]}}
        proposed=propose_card_sounds(self.root,compiled,technical=True)
        self.assertEqual(proposed["count"],1)
        candidate=read_json((self.root/proposed["path"]).read_bytes())
        event=candidate["audio_events"][0]
        self.assertEqual(event["sfx_asset_id"],generated["asset_id"])
        self.assertEqual(event["anchor"]["type"],"motion_marker")
        self.assertEqual(event["anchor"]["marker"],"impact")
        self.assertEqual(event["sync_to"],"peak")
        self.assertEqual(read_json((self.root/"input/emphasis_plan.json").read_bytes()),selected)
        selected["shot_decisions"][0]["sfx_decision"]="silence"
        self.write("input/emphasis_plan.json",selected)
        self.assertEqual(propose_card_sounds(self.root,compiled,technical=True)["count"],0)


class EarshotSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sc-a-sync-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy=deepcopy(DEFAULT_POLICY)
        self.policy["mode"]="mixed"; self.policy["audio"]["enabled"]=True
        self.card={"id":"MC-001","shot_id":"SHOT-001","recipe":"talkcraft-number-slab",
                   "start_frame":100,"end_frame":170}
        self.asset={"asset_id":"test-asset","sha256":"a"*64,
                    "cue_points":{"onset_samples":120,"peak_samples":1704,"end_samples":6900}}
        self.event={"id":"SFX-earshot","kind":"keyword","sfx_asset_id":"test-asset",
                    "anchor":{"type":"motion_marker","motion_card_id":"MC-001",
                              "marker":"impact","offset_samples":0},
                    "sync_to":"peak","gain_db":-20,"fade_in_samples":0,
                    "fade_out_samples":400,"pinned":False,"source":"rules"}
        self.obs={"artifact_kind":"technical_fixture","shots":[
            {"shot_id":"SHOT-001","emotion":"neutral"}]}
        self.board={"audio":{"duration_samples":320000},"shots":[
            {"id":"SHOT-001","script_range":[0,3]}]}
        self.execution=[{"id":"SHOT-001","start_frame":0,"end_frame":200,
                         "transition_out":None}]
        self.ext={"policy":self.policy,
                  "plan":{"audio_events":[self.event],"visual_events":[],"excluded":[],
                          "shot_decisions":[{"shot_id":"SHOT-001","sfx_decision":"allow",
                                             "text_decision":"skip"}]},
                  "fonts":{},"sfx":{"test-asset":self.asset},"input_hashes":{}}

    def compile(self):
        with patch("static_comic.emphasis_timing.observe",return_value=(self.obs,{})),\
             patch("static_comic.sfx_library.normalize_asset",return_value={
                "samples":8451,"normalized_path":"work/audio/sfx/ok.wav",
                "normalized_sha256":"a"*64}):
            return compile_events(self.root,self.ext,self.board,self.execution,
                    [{}],{},motion_cards=[self.card],technical=True,write=False)

    def test_peak_is_aligned_to_animated_visual_impact_frame(self):
        result=self.compile()
        self.assertEqual(len(result["sfx"]),1)
        sfx=result["sfx"][0]
        self.assertEqual(sfx["motion_frame"],124)
        self.assertEqual(sfx["start_sample"]+self.asset["cue_points"]["peak_samples"],124*1600)
        self.assertEqual(sfx["sync_to"],"peak")

    def test_motion_card_moved_recompiles_matching_peak_without_script_realign(self):
        first=self.compile()["sfx"][0]["start_sample"]
        self.card["start_frame"]+=8
        result=self.compile()["sfx"][0]
        self.assertEqual(result["start_sample"]-first,8*1600)

    def test_missing_card_or_sync_point_fails_closed(self):
        self.event["anchor"]["motion_card_id"]="MC-missing"
        self.assertFalse(self.compile()["sfx"])
        self.event["anchor"]["motion_card_id"]="MC-001"
        self.asset.pop("cue_points")
        self.assertEqual(self.compile()["diagnostics"][0]["reason_code"],"SYNC_POINT_UNAVAILABLE")


if __name__=="__main__":
    unittest.main()
