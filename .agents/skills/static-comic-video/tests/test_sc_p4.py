from human_support import simulated
"""P4 behavior contracts, with explicit synthetic image/speech/user evidence."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.create_fixture import create_fixture
from static_comic import transitions as tr
from static_comic.contracts import canonical, digest
from static_comic.project import compile_project, load_project
from static_comic.speech import apply_alignment
from test_sc_p1 import approved_test_project
from transition_support import proposal_for, decision_for


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        create_fixture(self.root)
        approved_test_project(self.root, semantic=False)

    def submit(self, proposal=None):
        return tr.propose(self.root, proposal or proposal_for(self.root))

    def accept(self):
        tr.confirm(self.root, decision_for(self.root))
        return tr.apply(self.root)

    def test_forged_tampered_and_duplicate_semantic_confirmation(self):
        self.submit()
        decision = decision_for(self.root)
        bad = copy.deepcopy(decision)
        from image_support import HUMAN
        bad['human'] = HUMAN
        with self.assertRaisesRegex(ValueError, 'local human confirmation'):
            tr.confirm(self.root, bad)
        bad = copy.deepcopy(decision); bad['items'][0]['reason'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'signature'):
            tr.confirm(self.root, bad)
        first = tr.confirm(self.root, decision)
        self.assertEqual(tr.confirm(self.root, decision), first)
        rejected = decision_for(self.root, decision='REJECTED')
        tr.confirm(self.root, rejected)
        with self.assertRaisesRegex(ValueError, 'Older confirmation'):
            tr.confirm(self.root, decision)  # Original signed A, never re-signed.
        value = tr.read_doc(self.root, tr.CANDIDATES, 'transitionCandidates')
        with self.assertRaisesRegex(ValueError, 'rejected'):
            tr.approved(self.root, value)
        tr.confirm(self.root, decision_for(self.root))  # Newly confirmed A2.
        tr.apply(self.root)
        self.assertEqual(tr.verify(self.root)['status'], 'PASS')

    def test_all_cuts_require_reasons_and_confirmed_plan(self):
        old = (self.root / "input/storyboard.json").read_bytes()
        value = self.submit()
        self.assertEqual(value["status"], "READY_FOR_REVIEW")
        self.assertEqual((self.root / "input/storyboard.json").read_bytes(), old)
        with self.assertRaises(ValueError):
            compile_project(self.root, write=False)
        self.accept()
        result = compile_project(self.root, write=False)
        self.assertEqual(result["total_frames"], 360)
        self.assertEqual({s["transition_out"]["type"] for s in result["props"]["shots"][:-1]}, {"cut"})
        self.assertEqual(tr.verify(self.root)["status"], "PASS")

    def test_initial_null_transitions_can_reach_planner_but_need_confirmation(self):
        from speech_support import seed_alignment
        board = json.loads((self.root / "input/storyboard.json").read_bytes())
        for shot in board["shots"]:
            shot["transition_out"] = None
        (self.root / "input/storyboard.json").write_bytes(canonical(board))
        self.assertEqual(seed_alignment(self.root, False)["status"], "PASS")
        self.assertEqual(self.submit()["status"], "READY_FOR_REVIEW")
        with self.assertRaises(ValueError):
            compile_project(self.root, write=False)
        self.assertTrue(all(s["transition_out"] is None for s in
                            json.loads((self.root / "input/storyboard.json").read_bytes())["shots"]))
        self.accept()
        self.assertEqual(compile_project(self.root, write=False)["total_frames"], 360)

    def test_candidates_are_recomputed_not_trusted(self):
        self.submit()
        value = tr.read_doc(self.root, tr.CANDIDATES, "transitionCandidates")
        value["items"][0]["transition"]["intent"] = "Unreviewed changed intent"
        tr.write_docs(self.root, {tr.CANDIDATES: value})
        with self.assertRaisesRegex(ValueError, "edited or are stale"):
            tr.confirm(self.root, decision_for(self.root))

    def test_input_anchor_and_narration_cannot_be_edited_under_old_context(self):
        proposal = proposal_for(self.root)
        request = tr.read_doc(self.root, tr.INPUT, "plannerInput")
        request["boundaries"][0]["anchors"][0]["sample"] += 12000
        request["boundaries"][0]["to_text"] = "伪造的旁白文本"
        proposal["input_sha256"] = digest(request)
        tr.write_docs(self.root, {tr.INPUT: request})
        with self.assertRaisesRegex(ValueError, "input evidence was edited"):
            self.submit(proposal)

    def test_missing_view_and_generic_evidence_are_boundary_issues(self):
        proposal = proposal_for(self.root)
        proposal["boundaries"][0]["viewed_images"] = []
        proposal["boundaries"][0]["observations"]["before"] = "图一"
        result = self.submit(proposal)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["items"][1]["issues"], [])
        self.assertIn("ORIGINALS_NOT_VIEWED", [i["code"] for i in result["items"][0]["issues"]])
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            tr.confirm(self.root, decision_for(self.root))

    def test_conflict_wrong_quote_direction_and_black_reason(self):
        proposal = proposal_for(self.root)
        b = proposal["boundaries"][0]
        b.update(type="wipe_from_left", duration_frames=12, direction="from_right", image_text_conflict=True)
        b["evidence"][0]["quote"] = "not the narration"
        codes = [i["code"] for i in self.submit(proposal)["items"][0]["issues"]]
        self.assertTrue({"IMAGE_TEXT_CONFLICT", "TEXT_EVIDENCE_MISMATCH", "DIRECTION_UNCLEAR"} <= set(codes))
        b.update(type="fade_black", duration_frames=2)
        codes = [i["code"] for i in self.submit(proposal)["items"][0]["issues"]]
        self.assertIn("BLACK_INTERVAL_UNEXPLAINED", codes)
        self.assertIn("INVALID_EFFECT_DURATION", codes)

    def test_untrusted_execution_fields_and_enum_rejected(self):
        for key, value in (("react", "<Script/>"), ("pre_frames", 12), ("type", "random_wipe"), ("duration_frames", 2.5)):
            proposal = proposal_for(self.root)
            proposal["boundaries"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.submit(proposal)

    def test_pending_images_never_enter_planner(self):
        path = self.root / "review/image_approvals.json"
        path.write_bytes(canonical({"schema_version": "1.0", "receipts": []}))
        with self.assertRaisesRegex(ValueError, "approval missing"):
            tr.prepare(self.root)
        self.assertFalse((self.root / tr.INPUT).exists())

    def test_missing_timing_produces_review_items(self):
        (self.root / "work/alignment/aligned.json").unlink()
        proposal = proposal_for(self.root)
        result = self.submit(proposal)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(all("TIME_EVIDENCE_REQUIRED" in [x["code"] for x in i["issues"]] for i in result["items"]))

    def test_capacity_failure_does_not_shorten_effect_or_write_board(self):
        proposal = proposal_for(self.root)
        proposal["boundaries"][0].update(type="fade", duration_frames=500)
        before = (self.root / "input/storyboard.json").read_bytes()
        result = self.submit(proposal)
        self.assertIn("EFFECT_CAPACITY", [i["code"] for i in result["items"][0]["issues"]])
        self.assertEqual(result["items"][0]["transition"]["duration_frames"], 500)
        self.assertEqual((self.root / "input/storyboard.json").read_bytes(), before)

    def test_partial_and_rejected_approval_cannot_execute(self):
        self.submit()
        tr.confirm(self.root, decision_for(self.root, indices=[0]))
        with self.assertRaisesRegex(ValueError, "Every boundary"):
            tr.apply(self.root)
        tr.confirm(self.root, decision_for(self.root, indices=[1], decision="REJECTED"))
        with self.assertRaisesRegex(ValueError, "rejected"):
            tr.apply(self.root)
        tr.confirm(self.root, decision_for(self.root, indices=[1]))
        tr.apply(self.root)
        tr.confirm(self.root, decision_for(self.root, indices=[0], decision="REJECTED"))
        with self.assertRaisesRegex(ValueError, "rejected"):
            compile_project(self.root, write=False)

    def test_three_placements_compile_using_existing_budget(self):
        for placement in ("start_at_anchor", "end_at_anchor", "center_on_anchor"):
            proposal = proposal_for(self.root)
            proposal["boundaries"][0].update(type="fade", duration_frames=11, placement=placement)
            self.submit(proposal)
            self.accept()
            result = compile_project(self.root, write=False)
            effect = result["props"]["shots"][0]["transition_out"]
            self.assertEqual(effect["placement"], placement)
            self.assertEqual(effect["pre_frames"] + effect["post_frames"], 11)
            self.assertEqual(result["total_frames"], 360)

    def test_transition_replay_preserves_audio_raw_evidence_and_old_record(self):
        old = tr.read_json((self.root / "work/alignment/aligned.json").read_bytes())
        old_raw = tr.read_evidence(self.root, old["raw_ref"])
        self.submit()
        self.accept()
        new = tr.read_json((self.root / "work/alignment/aligned.json").read_bytes())
        raw = tr.read_evidence(self.root, new["raw_ref"])
        self.assertEqual(raw["replay_of"], old["raw_ref"])
        for key in ("audio", "windows", "coarse_ref", "plan"):
            self.assertEqual(raw[key], old_raw[key])
        self.assertEqual(old_raw, tr.read_evidence(self.root, old["raw_ref"]))
        docs, hashes, _ = load_project(self.root)
        self.assertEqual(apply_alignment(self.root, docs, hashes, technical_fixture=False)["audio"], docs["storyboard"]["audio"])

    def test_current_image_evidence_and_narration_invalidates_semantics(self):
        self.submit()
        self.accept()
        path = self.root / "assets/images/shot_0001.png"
        old = path.read_bytes()
        path.write_bytes(b"new bytes")
        with self.assertRaisesRegex(ValueError, "formal image bytes changed"):
            tr.verify(self.root)
        path.write_bytes(old)
        (self.root / "input/script.txt").write_bytes(b"new narration")
        with self.assertRaisesRegex(ValueError, "Original script bytes changed"):
            tr.verify(self.root)

    def test_report_shows_pairs_and_timing_but_does_not_approve(self):
        self.submit()
        result = tr.report(self.root)
        text = (self.root / result["report"]).read_text(encoding="utf-8")
        for value in ("SHOT-001", "SHOT-002", "pause_samples", "compiled_window_preview", "semantic_anchor_frame"):
            self.assertIn(value, text)
        self.assertFalse((self.root / tr.REVIEWS).exists())

    def test_cli_unknown_input_fails_as_json(self):
        p = subprocess.run([sys.executable, "-m", "static_comic", "transitions", "propose", "--project", str(self.root)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(json.loads(p.stderr)["status"], "FAIL")

    def test_confirmed_boundary_override_survives_transition_only_replay(self):
        from static_comic.speech import binding, evaluate, store_evidence
        from static_comic.speech_text import make_plan
        from image_support import HUMAN
        docs, hashes, _ = load_project(self.root)
        board = docs["storyboard"]
        old = tr.read_json((self.root / "work/alignment/aligned.json").read_bytes())
        entry = {"kind": "boundary", "from_shot_id": "SHOT-001", "to_shot_id": "SHOT-002",
                 "sample": old["boundaries"][1]["sample"], "reason": "Synthetic exact boundary confirmation", "human": HUMAN}
        override = {"schema_version": "1.0", "script_sha256": hashes["input/script.txt"],
                    "audio_sha256": hashes[board["audio"]["source"]],
                    "storyboard_sha256": hashes["input/storyboard.json"], "entries": [entry]}
        tr.write_docs(self.root, {"input/overrides.json": override})
        docs, hashes, _ = load_project(self.root)
        raw = tr.read_evidence(self.root, old["raw_ref"])
        script = (self.root / "input/script.txt").read_bytes().decode("utf-8-sig")
        plan = make_plan(script, board, tr.read_evidence(self.root, raw["coarse_ref"]), [entry], raw["audio"]["master"]["samples"])
        raw.update(binding=binding(board, hashes, False), plan=plan)
        result = evaluate(board, plan, raw["windows"], [entry], raw["audio"]["master"]["samples"])
        tr.write_docs(self.root, {"work/alignment/aligned.json": {"version": tr.VERSION, "binding": raw["binding"],
                      "raw_ref": store_evidence(self.root, raw), **result}})
        self.submit()
        self.accept()
        new_override = tr.read_doc(self.root, "input/overrides.json", "overrides")
        self.assertEqual(new_override["entries"], [entry])
        self.assertNotEqual(new_override["storyboard_sha256"], override["storyboard_sha256"])
        self.assertEqual(compile_project(self.root, write=False)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
