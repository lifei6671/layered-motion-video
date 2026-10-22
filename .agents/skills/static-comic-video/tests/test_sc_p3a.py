from human_support import simulated
"""Image supply contracts; all human receipts and providers here are synthetic."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from scripts.create_fixture import create_fixture
from static_comic import image_supply as images
from static_comic.contracts import canonical, digest
from static_comic.project import compile_project
from image_support import HUMAN, decision_for, make_brief, make_submission


class ImageSupplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.board = create_fixture(self.root)

    def save(self, name, value):
        images.write_docs(self.root, {name: value})

    def prepare(self, mixed=False):
        policy = images.read_doc(self.root, images.POLICY, "policy")
        if mixed:
            assignments = [{"source_mode": mode, "channel": "synthetic-" + mode} for mode in
                           ("agent_generate", "third_party_retrieve", "manual_generate")]
            policy.update(mode="mixed", default_channel=None, allowed_channels=assignments,
                          shots={s["id"]: a for s, a in zip(self.board["shots"], assignments)})
            self.save(images.POLICY, policy)
        payload = images.policy_options(self.root)["payload_sha256"]
        images.confirm(self.root, "policy", simulated("policy", {"payload_sha256": payload, "human": HUMAN}))
        result = images.plan(self.root, make_brief(self.board))
        images.confirm(self.root, "plan", simulated("plan", {"payload_sha256": result["payload_sha256"], "human": HUMAN}))
        return images.requests(self.root)

    def acquire(self, mixed=False):
        req = self.prepare(mixed)
        for i in range(3):
            images.ingest(self.root, make_submission(self.root, req, i))
        return req

    def test_policy_pending_blocks_planning_and_tools(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_POLICY_PENDING"):
            images.plan(self.root, make_brief(self.board))
        self.assertFalse((self.root / images.REQUESTS).exists())
        with self.assertRaises(ValueError):
            images.dispatch(self.root, "SHOT-001")
        self.assertEqual(images.supply(self.root)["records"], [])

    def test_measure_box_after_generation_preserves_original_request(self):
        self.board["shots"][0]["subject_bbox"] = None
        self.save("input/storyboard.json", self.board)
        req = self.acquire()
        original = (self.root / images.REQUESTS).read_bytes()
        with self.assertRaisesRegex(ValueError, "visual checks"):
            images.review(self.root, decision_for(self.root))
        self.board["shots"][0]["subject_bbox"] = [0.4, 0.4, 0.6, 0.6]
        self.save("input/storyboard.json", self.board)
        self.assertEqual(images.requests(self.root), req)
        self.assertEqual((self.root / images.REQUESTS).read_bytes(), original)
        report = images.report(self.root)
        decision = decision_for(self.root)
        self.assertEqual(report["shots"][0]["geometry_sha256"], decision["items"][0]["geometry_sha256"])
        images.review(self.root, simulated("images", decision))
        self.assertEqual(images.verify(self.root)["status"], "PASS")

    def test_old_review_geometry_rejected_before_and_after_approval(self):
        for shot in self.board["shots"]:
            shot["timing_source"] = "manual_confirmed"
            shot["transition_out"] = None
        self.save("input/storyboard.json", self.board)
        self.acquire()
        decision = decision_for(self.root)
        self.board["shots"][0]["subject_bbox"] = [0.39, 0.39, 0.61, 0.61]
        self.save("input/storyboard.json", self.board)
        with self.assertRaisesRegex(ValueError, "geometry.*stale"):
            images.review(self.root, simulated("images", decision))
        fresh = decision_for(self.root)
        images.review(self.root, fresh)
        self.board["shots"][0]["subject_bbox"] = [0.41, 0.41, 0.59, 0.59]
        self.save("input/storyboard.json", self.board)
        with self.assertRaisesRegex(ValueError, "geometry.*stale"):
            images.verify(self.root)
        with self.assertRaisesRegex(ValueError, "geometry.*stale"):
            compile_project(self.root, write=False)

    def test_missing_geometry_and_clipped_box_cannot_be_approved(self):
        self.acquire()
        decision = decision_for(self.root)
        del decision["items"][0]["geometry_sha256"]
        with self.assertRaisesRegex(ValueError, "geometry.*missing"):
            images.review(self.root, simulated("images", decision))
        self.board["shots"][0]["subject_bbox"] = [0, 0, 1, 1]
        self.save("input/storyboard.json", self.board)
        with self.assertRaisesRegex(ValueError, "visual checks"):
            images.review(self.root, decision_for(self.root))

    def test_motion_revision_reuses_acquisition_but_requires_new_visual_review(self):
        for shot in self.board["shots"]:
            shot["timing_source"] = "manual_confirmed"
            shot["transition_out"] = None
        self.save("input/storyboard.json", self.board)
        req = self.acquire()
        original = (self.root / images.REQUESTS).read_bytes()
        decision = decision_for(self.root)
        images.review(self.root, simulated("images", decision))
        decision = decision_for(self.root)
        self.board["shots"][0]["motion"].update(type="zoom_in", scale_from=1, scale_to=1.06)
        self.save("input/storyboard.json", self.board)
        self.assertEqual(images.requests(self.root), req)
        self.assertEqual((self.root / images.REQUESTS).read_bytes(), original)
        current_report = images.report(self.root)
        self.assertEqual(current_report["shots"][0]["motion"], self.board["shots"][0]["motion"])
        from html import unescape
        from ast import literal_eval
        page = unescape((self.root / "review/images/index.html").read_text(encoding="utf-8"))
        shown = literal_eval(page.split("<pre>", 1)[1].split("</pre>", 1)[0])
        self.assertEqual(shown["运镜"], self.board["shots"][0]["motion"])
        self.assertEqual(shown["原采集运镜"], req["shots"][0]["motion"])
        with self.assertRaisesRegex(ValueError, "geometry.*stale"):
            images.review(self.root, simulated("images", decision))
        with self.assertRaisesRegex(ValueError, "geometry.*stale"):
            images.verify(self.root)
        with self.assertRaisesRegex(ValueError, "geometry.*stale"):
            compile_project(self.root, write=False)
        images.review(self.root, decision_for(self.root))
        self.assertEqual(images.verify(self.root)["status"], "PASS")

    def test_motion_revision_cannot_approve_clipped_or_invalid_motion(self):
        self.acquire()
        self.board["shots"][0]["subject_bbox"] = [0.1, 0.1, 0.9, 0.9]
        self.board["shots"][0]["motion"].update(type="zoom_in", scale_from=1, scale_to=2)
        self.save("input/storyboard.json", self.board)
        with self.assertRaisesRegex(ValueError, "visual checks"):
            images.review(self.root, decision_for(self.root))
        self.board["shots"][0]["motion"]["type"] = "static"
        self.save("input/storyboard.json", self.board)
        with self.assertRaisesRegex(ValueError, "static motion"):
            images.review(self.root, decision_for(self.root))

    def test_motion_revision_does_not_unbind_cover(self):
        self.acquire()
        self.board["shots"][0]["cover_anchor"] = [0.3, 0.7]
        self.save("input/storyboard.json", self.board)
        with self.assertRaisesRegex(ValueError, "requests are stale"):
            images.requests(self.root)

    def test_new_episode_asks_channel_without_default_selection(self):
        with tempfile.TemporaryDirectory() as root:
            result = images.policy_options(root)
            self.assertEqual(result["status"], "SOURCE_POLICY_PENDING")
            self.assertFalse((Path(root) / images.POLICY).exists())
            self.assertIsNone(result["default_channel"])
            self.assertEqual(result["allowed_channels"], [])

    def test_unconfirmed_mixed_mapping_and_stale_confirmation(self):
        self.prepare(True)
        policy = images.read_doc(self.root, images.POLICY, "policy")
        policy["shots"]["SHOT-001"]["channel"] = "other"
        self.save(images.POLICY, policy)
        with self.assertRaisesRegex(ValueError, "confirmation is stale"):
            images.dispatch(self.root, "SHOT-001")

    def test_independent_complete_chinese_prompts_and_waiting(self):
        req = self.prepare()
        for item in req["shots"]:
            for text in ("统一画风", "角色一致性", "主体与构图", "灯光", "16:9", "运镜留白", "具体排除项", item["formal_path"]):
                self.assertIn(text, item["prompt"])
        result = images.dispatch(self.root, "SHOT-001")
        self.assertEqual(result["status"], "WAITING_FOR_USER")
        self.assertTrue((self.root / "assets/images/shot_0001.png").exists())
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            images.verify(self.root)

    def test_unavailable_does_not_switch_channel(self):
        req = self.prepare(True)
        result = images.dispatch(self.root, "SHOT-001", unavailable="Synthetic disconnected generator")
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(images.requests(self.root), req)

    def test_mixed_import_review_and_production_gate(self):
        self.acquire(True)
        self.assertEqual({r["status"] for r in images.supply(self.root)["records"]}, {"CANDIDATE_READY"})
        report = images.report(self.root)
        self.assertEqual({r["status"] for r in report["shots"]}, {"REVIEW_REQUIRED"})
        self.assertFalse((self.root / "work/remotion/public").exists())
        images.review(self.root, decision_for(self.root))
        self.assertEqual(images.verify(self.root)["status"], "PASS")
        assets = images.read_doc(self.root, images.MANIFEST, "manifest")["assets"]
        self.assertEqual(len({a["source_mode"] for a in assets}), 3)

    def test_approval_batch_is_exact_and_preflighted(self):
        self.acquire()
        decision = decision_for(self.root)
        decision["items"][-1]["candidate_sha256"] = "0" * 64
        before = (self.root / images.APPROVALS).read_bytes()
        with self.assertRaisesRegex(ValueError, "stale candidate"):
            images.review(self.root, simulated("images", decision))
        self.assertEqual((self.root / images.APPROVALS).read_bytes(), before)
        self.assertTrue(all(r["status"] == "CANDIDATE_READY" for r in images.supply(self.root)["records"]))

    def test_visual_approval_cannot_select_reference_only_as_final_artwork(self):
        req = self.prepare(True)
        sub = make_submission(self.root, req, 1)
        sub["usage_role"] = "reference_only"
        images.ingest(self.root, sub)
        with self.assertRaisesRegex(ValueError, "reference_only"):
            images.review(self.root, decision_for(self.root))
        self.assertEqual(images.read_doc(self.root, images.APPROVALS, "approvals")["receipts"], [])

    def test_visual_checks_still_require_explicit_acceptance(self):
        self.acquire()
        for check in images.VISUAL_CHECKS:
            decision = decision_for(self.root)
            decision["items"][0]["checks"][check] = False
            with self.subTest(check=check), self.assertRaisesRegex(ValueError, "visual checks"):
                images.review(self.root, simulated("images", decision))

    def test_reject_and_redo_invalidate_formal_image_and_approval(self):
        self.acquire()
        images.review(self.root, decision_for(self.root))
        images.review(self.root, decision_for(self.root, ["SHOT-001"], "REJECTED"))
        self.assertTrue((self.root / "assets/images/shot_0001.png").exists())
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            images.verify(self.root)
        self.assertEqual(images.supply(self.root)["records"][0]["status"], "REJECTED")

    def test_reimport_identical_bytes_still_requires_new_review(self):
        req = self.acquire()
        images.review(self.root, decision_for(self.root))
        images.ingest(self.root, make_submission(self.root, req, 0))
        with self.assertRaisesRegex(ValueError, "missing or stale"):
            images.verify(self.root)

    def test_candidate_and_license_bytes_are_rechecked(self):
        self.acquire()
        images.review(self.root, decision_for(self.root))
        candidate = images.supply(self.root)["records"][0]["candidate"]
        path = self.root / candidate["path"]
        old = path.read_bytes()
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Candidate bytes changed"):
            images.verify(self.root)
        path.write_bytes(old)
        (self.root / "work/images/test-evidence.txt").write_bytes(b"new license")
        with self.assertRaisesRegex(ValueError, "Changed provenance"):
            images.verify(self.root)

    def test_formal_file_change_and_new_visual_plan_invalidate(self):
        self.acquire()
        images.review(self.root, decision_for(self.root))
        path = self.root / "assets/images/shot_0001.png"
        old = path.read_bytes()
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "formal image bytes changed"):
            images.verify(self.root)
        path.write_bytes(old)
        self.board["shots"][0]["narrative"] = "new meaning"
        self.save("input/storyboard.json", self.board)
        with self.assertRaisesRegex(ValueError, "requests are stale"):
            images.verify(self.root)

    def test_timing_and_p4_transition_edits_do_not_change_image_request(self):
        req = self.prepare()
        self.board["shots"][0]["transition_out"] = None
        self.board["shots"][1]["start_samples"] += 100
        self.save("input/storyboard.json", self.board)
        self.assertEqual(images.requests(self.root), req)

    def test_corrupt_decoder_and_channel_mismatch_never_promote(self):
        req = self.prepare()
        sub = make_submission(self.root, req, 0)
        sub["channel"] = "unapproved"
        with self.assertRaisesRegex(ValueError, "channel differs"):
            images.ingest(self.root, sub)
        sub["channel"] = req["shots"][0]["assignment"]["channel"]
        (self.root / sub["file"]).write_bytes(b"not an image")
        with self.assertRaisesRegex(ValueError, "Cannot decode"):
            images.ingest(self.root, sub)
        self.assertEqual(images.supply(self.root)["records"], [])

    def test_jpeg_normalization_preserves_original_provenance(self):
        req = self.prepare()
        sub = make_submission(self.root, req, 0)
        sub["file"] = "work/images/source.jpg"
        Image.new("RGB", (640, 360), "red").save(self.root / sub["file"])
        images.ingest(self.root, sub)
        record = images.supply(self.root)["records"][0]
        self.assertNotEqual(record["candidate"]["sha256"], record["candidate"]["original_sha256"])
        images.review(self.root, decision_for(self.root))
        with Image.open(self.root / "assets/images/shot_0001.png") as im:
            self.assertEqual(im.format, "PNG")

    def test_missing_subject_and_clipped_subject_cannot_be_approved(self):
        self.board["shots"][0]["subject_bbox"] = None
        self.save("input/storyboard.json", self.board)
        req = self.prepare()
        images.ingest(self.root, make_submission(self.root, req, 0))
        with self.assertRaisesRegex(ValueError, "motion safety"):
            images.review(self.root, decision_for(self.root))

    def test_production_compile_requires_supply_even_with_old_approval(self):
        from test_sc_p1 import approved_test_project
        approved_test_project(self.root)
        (self.root / images.SUPPLY).unlink()
        with self.assertRaisesRegex(ValueError, "supply approval missing"):
            compile_project(self.root)
        self.assertFalse((self.root / "work/remotion/public").exists())

    def test_cli_required_input_and_unknown_shot_report_json(self):
        result = subprocess.run([sys.executable, "-m", "static_comic", "images", "plan", "--project", str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["status"], "FAIL")
        self.prepare()
        with self.assertRaisesRegex(ValueError, "Unknown shot"):
            images.dispatch(self.root, "SHOT-099")

    def test_partial_approval_report_preserves_valid_shot(self):
        req = self.prepare()
        images.ingest(self.root, make_submission(self.root, req, 0))
        images.review(self.root, decision_for(self.root))
        report = images.report(self.root)
        self.assertEqual([s["status"] for s in report["shots"]], ["APPROVED", "PLANNED", "PLANNED"])

    def test_source_change_and_rejection_invalidate_unchanged_transition_images(self):
        from test_sc_p1 import approved_test_project
        from image_support import seed_supply
        approved_test_project(self.root)
        images.review(self.root, decision_for(self.root, ["SHOT-001"], "REJECTED"))
        images.review(self.root, decision_for(self.root, ["SHOT-001"]))
        with self.assertRaisesRegex(ValueError, "transition image approval is stale"):
            compile_project(self.root, write=False)
        policy = images.read_doc(self.root, images.POLICY, "policy")
        policy["default_channel"] = "synthetic-new-source"
        policy["allowed_channels"] = [{"source_mode": "manual_generate", "channel": "synthetic-new-source"}]
        self.save(images.POLICY, policy)
        images.confirm(self.root, "policy", simulated("policy", {"payload_sha256": images.policy_options(self.root)["payload_sha256"], "human": HUMAN}))
        seed_supply(self.root, images.read_doc(self.root, "input/storyboard.json", "storyboard"))
        self.assertEqual(images.verify(self.root)["status"], "PASS")
        with self.assertRaisesRegex(ValueError, "transition image approval is stale"):
            compile_project(self.root, write=False)


if __name__ == "__main__":
    unittest.main()
