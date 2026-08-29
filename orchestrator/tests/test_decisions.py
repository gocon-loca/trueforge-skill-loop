"""Q2 action space: four actions, every choice recorded with the scores that informed it."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from orchestrator.decisions import (
    ACTIONS, AMEND, MINT, RAW_TOOL, USE_EXISTING, Decision, DecisionLog, choose,
)
from orchestrator.retrieval import SkillIndex


class _Sig:
    def __init__(self, name, exercised=True, version=1):
        self.name, self.exercised, self.version = name, exercised, version
        self.provenance = "research"


class _Cand:
    def __init__(self, name, score, exercised=True):
        self.signature = _Sig(name, exercised)
        self.score = score
        self.components = {"body": score, "signature": score, "trust": 1.0 if exercised else 0.0}
    def as_record(self):
        return {"skill": self.signature.name, "score": self.score,
                "components": self.components, "exercised": self.signature.exercised}


class RecordShapeTests(unittest.TestCase):
    def test_a_decision_without_candidates_is_refused(self) -> None:
        """A choice recorded without its evidence is the thing this log exists to prevent."""
        with self.assertRaises(ValueError):
            Decision("t", MINT, None, "because", candidates=())

    def test_unknown_action_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Decision("t", "improvise", None, "because", candidates=({"skill": None},))

    def test_use_existing_and_amend_must_name_a_skill(self) -> None:
        for action in (USE_EXISTING, AMEND):
            with self.subTest(action=action), self.assertRaises(ValueError):
                Decision("t", action, None, "because", candidates=({"skill": "x"},))

    def test_mint_and_raw_tool_must_not_name_a_skill(self) -> None:
        for action in (MINT, RAW_TOOL):
            with self.subTest(action=action), self.assertRaises(ValueError):
                Decision("t", action, "some-skill", "because", candidates=({"skill": "x"},))

    def test_record_carries_the_candidate_scores(self) -> None:
        d = choose("t", [_Cand("a", 0.5), _Cand("b", 0.1)])
        rec = d.as_record()
        self.assertEqual(len(rec["candidates"]), 2)
        self.assertIn("score", rec["candidates"][0])
        self.assertTrue(rec["decided_at"].endswith("Z"))


class HeuristicTests(unittest.TestCase):
    def test_strong_match_on_a_trusted_skill_is_used(self) -> None:
        self.assertEqual(choose("t", [_Cand("a", 0.5)]).action, USE_EXISTING)

    def test_strong_match_on_an_untrusted_skill_is_amended(self) -> None:
        """The skill is about the right method; its trust has lapsed. That is an amend."""
        d = choose("t", [_Cand("a", 0.5, exercised=False)])
        self.assertEqual(d.action, AMEND)
        self.assertEqual(d.skill, "a")

    def test_weak_but_related_match_is_amended(self) -> None:
        self.assertEqual(choose("t", [_Cand("a", 0.15)]).action, AMEND)

    def test_nothing_in_the_area_is_minted(self) -> None:
        self.assertEqual(choose("t", [_Cand("a", 0.02)]).action, MINT)

    def test_an_empty_registry_reaches_for_a_raw_tool(self) -> None:
        self.assertEqual(choose("t", []).action, RAW_TOOL)

    def test_every_decision_states_its_reason_with_the_number(self) -> None:
        for c in (0.5, 0.15, 0.02):
            with self.subTest(score=c):
                self.assertIn(f"{c:.3f}", choose("t", [_Cand("a", c)]).rationale)


class LogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.log = DecisionLog(Path(self._tmp.name) / "decisions.jsonl")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_appends_and_reads_back(self) -> None:
        self.log.append(choose("first", [_Cand("a", 0.5)]))
        self.log.append(choose("second", [_Cand("a", 0.01)]))
        rows = self.log.read()
        self.assertEqual([r["task"] for r in rows], ["first", "second"])

    def test_is_append_only_across_instances(self) -> None:
        self.log.append(choose("first", [_Cand("a", 0.5)]))
        DecisionLog(self.log.path).append(choose("second", [_Cand("a", 0.5)]))
        self.assertEqual(len(self.log.read()), 2)

    def test_counts_cover_every_action(self) -> None:
        counts = self.log.counts()
        self.assertEqual(set(counts), set(ACTIONS))

    def test_reading_a_missing_log_is_empty_not_an_error(self) -> None:
        self.assertEqual(DecisionLog(Path(self._tmp.name) / "none.jsonl").read(), [])


class AgainstTheRealRegistryTests(unittest.TestCase):
    def test_a_real_lookup_produces_a_recordable_decision(self) -> None:
        index = SkillIndex(Path("registry")).build()
        cands = index.search("scrape a competitor website for structured company facts")
        d = choose("scrape a competitor website for structured company facts", cands)
        self.assertEqual(d.action, USE_EXISTING)
        self.assertEqual(d.skill, "competitor-site-interpretation")
        self.assertEqual(len(d.as_record()["candidates"]), len(index.signatures))

    def test_an_unrelated_task_against_the_real_registry_mints(self) -> None:
        index = SkillIndex(Path("registry")).build()
        cands = index.search("convert a PDF invoice into a spreadsheet row")
        self.assertEqual(choose("convert a PDF invoice", cands).action, MINT)
