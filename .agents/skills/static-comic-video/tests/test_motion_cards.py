"""SC-M：动态卡片的原文证据、时间窗、密度和回退测试。"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from static_comic.contracts import bytes_digest, canonical, read_json
from static_comic.motion_cards import compile_cards, empty_plan, propose_rules


class MotionCardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.text = "开头😀\r\n价格是166元。再想想。"
        self.script = b"\xef\xbb\xbf" + self.text.encode("utf-8")
        self.write("input/script.txt", self.script)
        self.shots = [
            {"id": "SHOT-001", "script_range": [0, len(self.text)], "timing_source": "technical_fixture"},
        ]
        self.execution = [
            {"id": "SHOT-001", "start_frame": 0, "end_frame": 180, "transition_out": None},
        ]

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else canonical(content))

    def event(self, **changes):
        start = self.text.index("166元")
        return {"id": "MC-1", "shot_id": "SHOT-001", "recipe": "talkcraft-number-slab",
                "script_range": [start, start + 4], "text": "166元", "style": "paper",
                "source": "manual", "start_frame": 40, "end_frame": 102, **changes}

    def plan(self, *events):
        data = empty_plan(self.script)
        data["events"] = list(events)
        self.write("input/motion_cards.json", data)
        return data

    def compile(self, events=None):
        return compile_cards(self.root, {"shots": self.shots}, self.execution,
                             events or [], script_bytes=self.script)

    def test_absent_plan_is_legacy_noop_and_does_not_write(self):
        result = self.compile()
        self.assertEqual(result["events"], [])
        self.assertFalse(result["present"])
        self.assertEqual(result["outputs"], {})
        self.assertEqual(list((self.root / "input").iterdir()), [self.root / "input/script.txt"])

    def test_exact_bom_unicode_numeric_and_immutable_frames(self):
        self.plan(self.event())
        before = (self.root / "input/motion_cards.json").read_bytes()
        result = self.compile()
        self.assertEqual(result["events"][0]["text"], "166元")
        self.assertEqual(result["events"][0]["start_frame"], 40)
        self.assertEqual(result["events"][0]["end_frame"], 102)
        self.assertEqual((self.root / "input/motion_cards.json").read_bytes(), before)
        self.assertIn("work/timeline/technical/motion_cards.lock.json", result["outputs"])
        self.assertTrue(result["input_hashes"]["input/motion_cards.json"])

    def test_numeric_fact_cannot_be_fabricated_or_shifted(self):
        base = self.event()
        for change in ({"text": "188元"}, {"script_range": [0, 4]},
                       {"recipe": "talkcraft-number-slab", "text": "价格"},
                       {"label": "不存在的消费数据"}):
            with self.subTest(change=change):
                self.plan({**base, **change})
                with self.assertRaisesRegex(ValueError, "text differs|numeric token|grounded"):
                    self.compile()

    def test_boundaries_transition_overlap_and_emphasis_conflict(self):
        self.plan(self.event())
        self.execution[0]["transition_out"] = {"pre_frames": 85}
        with self.assertRaisesRegex(ValueError, "stable window"):
            self.compile()
        self.execution[0]["transition_out"] = None
        with self.assertRaisesRegex(ValueError, "overlaps keyword"):
            self.compile([{"start_frame": 50, "end_frame": 90}])

    def test_overlapping_and_duplicate_cards_are_rejected(self):
        self.plan(self.event(), {**self.event(), "id": "MC-2", "start_frame": 90, "end_frame": 150})
        with self.assertRaisesRegex(ValueError, "one dynamic card per shot"):
            self.compile()

    def test_changed_script_hash_expires_selected_plan(self):
        self.plan(self.event())
        with self.assertRaisesRegex(ValueError, "MOTION_PLAN_STALE"):
            compile_cards(self.root, {"shots": self.shots}, self.execution, [], script_bytes=b"changed")

    def test_source_grounded_text_still_must_fit_readable_width(self):
        self.text = "这是非常非常非常非常非常非常非常非常长的说明。"
        self.script = self.text.encode("utf-8")
        self.write("input/script.txt", self.script)
        self.shots[0]["script_range"] = [0, len(self.text)]
        start = self.text.index("非常")
        word = "非常" * 8
        self.plan({"id": "MC-TOO-LONG", "shot_id": "SHOT-001",
                   "recipe": "talkcraft-ink-underline", "script_range": [start, start+len(word)],
                   "text": word, "style": "paper", "source": "manual",
                   "start_frame": 40, "end_frame": 102})
        with self.assertRaisesRegex(ValueError, "readable width budget"):
            self.compile()

    def test_wrong_type_unknown_recipe_and_injection_are_rejected(self):
        for change in ({"recipe": "javascript"}, {"text": "<script>"}, {"id": "x"},
                       {"style": "linear-gradient(red,blue)"}):
            with self.subTest(change=change):
                self.plan({**self.event(), **change})
                with self.assertRaises(ValueError):
                    self.compile()

    def test_rules_do_not_invent_timing_without_alignment(self):
        compiled = {"timeline": {"shots": [{"source": self.shots[0], "execution": self.execution[0]}]},
                    "artifact_kind": "technical_fixture"}
        self.assertEqual(propose_rules(self.root, compiled)["status"], "UNAVAILABLE")
        self.assertFalse((self.root / "work/motion/technical/proposals.json").exists())

    def test_rules_emit_unselected_grounded_proposal_when_alignment_is_verified(self):
        compiled = {"timeline": {"shots": [{"source": self.shots[0], "execution": self.execution[0]}]},
                    "artifact_kind": "technical_fixture"}
        self.write("work/alignment/aligned.json", {"fixture": True})
        with patch("static_comic.motion_cards.speech_samples", return_value=[80000, 96000]):
            result = propose_rules(self.root, compiled)
        self.assertEqual(result["status"], "PROPOSED")
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["selected_plan_changed"])
        candidate = read_json((self.root / result["path"]).read_bytes())
        self.assertEqual(candidate["events"][0]["text"], "166元")
        self.assertFalse((self.root / "input/motion_cards.json").exists())


    def test_explicit_chapter_semantics_propose_a_grounded_title(self):
        self.text = "第一章我们来理解原因。"
        self.script = self.text.encode("utf-8")
        self.write("input/script.txt", self.script)
        self.shots[0]["script_range"] = [0, len(self.text)]
        compiled = {"timeline": {"shots": [{"source": self.shots[0], "execution": self.execution[0]}]},
                    "artifact_kind": "technical_fixture"}
        self.write("work/alignment/aligned.json", {"fixture": True})
        with patch("static_comic.motion_cards.speech_samples", return_value=[96000, 110000]):
            result = propose_rules(self.root, compiled)
        self.assertEqual(result["count"], 1)
        candidate = read_json((self.root / result["path"]).read_bytes())["events"][0]
        self.assertEqual(candidate["recipe"], "talkcraft-chapter-card")
        self.assertEqual(candidate["text"], "第一章")
        self.assertEqual(candidate["source"], "rules")

    def test_concept_semantics_propose_ink_only_from_exact_phrase(self):
        self.text = "所谓沉没成本，是之前花的钱。"
        self.script = self.text.encode("utf-8")
        self.write("input/script.txt", self.script)
        self.shots[0]["script_range"] = [0, len(self.text)]
        compiled = {"timeline": {"shots": [{"source": self.shots[0], "execution": self.execution[0]}]},
                    "artifact_kind": "technical_fixture"}
        self.write("work/alignment/aligned.json", {"fixture": True})
        with patch("static_comic.motion_cards.speech_samples", return_value=[96000, 112000]):
            result = propose_rules(self.root, compiled)
        self.assertEqual(result["count"], 1)
        candidate = read_json((self.root / result["path"]).read_bytes())["events"][0]
        self.assertEqual(candidate["recipe"], "talkcraft-ink-underline")
        self.assertEqual(candidate["text"], "沉没成本")
        self.assertEqual(self.text[slice(*candidate["script_range"])], "沉没成本")


if __name__ == "__main__":
    unittest.main()
