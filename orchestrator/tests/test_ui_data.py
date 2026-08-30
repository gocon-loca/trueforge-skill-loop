"""E1/E2/E3: the event log, the evidence snapshot, and the null rule.

The property under test is the null rule. A dashboard that renders an invented number is
worse than one that renders little, because nobody looking at it can tell which they have.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from orchestrator import events as ev
from orchestrator import ui_data


class EventLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "events.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unknown_event_type_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            ev.append("vibes", skill="s", path=self.path)

    def test_record_carries_the_declared_schema(self) -> None:
        r = ev.append(ev.CONSULTATION, skill="s", rule_id="s#1",
                      payload={"score": 0.5}, path=self.path)
        self.assertEqual(set(r), {"ts", "event_type", "rule_id", "skill", "payload"})
        self.assertTrue(r["ts"].endswith("Z"))

    def test_is_append_only(self) -> None:
        ev.append(ev.MINT, skill="a", path=self.path)
        ev.append(ev.MINT, skill="b", path=self.path)
        self.assertEqual([e["skill"] for e in ev.read(self.path)], ["a", "b"])

    def test_reading_a_missing_log_is_empty(self) -> None:
        self.assertEqual(ev.read(Path(self._tmp.name) / "none.jsonl"), [])

    def test_backfill_does_not_invent_consultations(self) -> None:
        """Retrieval did not exist for most of the day, so there are none to recover."""
        for e in ev.backfill("registry"):
            self.assertNotEqual(e["event_type"], ev.CONSULTATION)

    def test_backfill_recovers_the_real_history(self) -> None:
        got = ev.backfill("registry")
        self.assertTrue(got, "backfill recovered nothing")
        kinds = {e["event_type"] for e in got}
        self.assertIn(ev.EXERCISE_PASS, kinds)
        self.assertIn(ev.MINT, kinds)
        self.assertEqual([e["ts"] for e in got], sorted(e["ts"] for e in got))

    def test_backfill_preserves_events_already_appended(self) -> None:
        """A regeneration that truncates an append-only log has not preserved it."""
        ev.append(ev.CONSULTATION, skill="s", payload={"source": "live"}, path=self.path)
        ev.write_backfill(self.path, "registry")
        live = [e for e in ev.read(self.path)
                if (e.get("payload") or {}).get("source") == "live"]
        self.assertEqual(len(live), 1)


class EvidenceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.events = Path(self._tmp.name) / "events.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unobserved_quantities_are_null_not_zero(self) -> None:
        """The load-bearing case. Zero is an observation; null is the absence of one."""
        data = ui_data.build("registry", self.events)      # no events at all
        self.assertTrue(data["rules"])
        for r in data["rules"]:
            self.assertIsNone(r["x"], f"{r['rule_id']} invented a retrieval score")
            self.assertIsNone(r["size"], f"{r['rule_id']} invented a consult count")

    def test_the_schema_tells_the_consumer_what_null_means(self) -> None:
        data = ui_data.build("registry", self.events)
        self.assertIn("neutral", data["schema"]["null_means"].lower())
        self.assertIn("zero is an observation", data["schema"]["null_means"].lower())

    def test_a_consultation_displaces_the_rules_of_that_skill(self) -> None:
        ev.append(ev.CONSULTATION, skill="workspace-sentinel",
                  payload={"score": 0.42}, path=self.events)
        data = ui_data.build("registry", self.events)
        moved = [r for r in data["rules"] if r["skill"] == "workspace-sentinel"]
        self.assertTrue(moved)
        for r in moved:
            self.assertEqual(r["x"], 0.42)
            self.assertEqual(r["size"], 1)
        others = [r for r in data["rules"] if r["skill"] != "workspace-sentinel"]
        for r in others:
            self.assertIsNone(r["x"], "an unconsulted skill was displaced")

    def test_pass_rate_is_null_until_an_exercise_is_observed(self) -> None:
        data = ui_data.build("registry", self.events)
        for r in data["rules"]:
            self.assertIsNone(r["y"])

    def test_every_rule_carries_its_identity_and_citations(self) -> None:
        data = ui_data.build("registry", self.events)
        for r in data["rules"]:
            self.assertRegex(r["rule_id"], r"^[a-z0-9-]+#\d+$")
            self.assertTrue(r["text"])
            self.assertIsInstance(r["citations"], list)
            self.assertIn(r["provenance"], ("research", "incident", "manual"))

    def test_counts_reconcile_with_the_rules(self) -> None:
        data = ui_data.build("registry", self.events)
        c = data["counts"]
        self.assertEqual(c["rules"], len(data["rules"]))
        self.assertEqual(c["rules_with_retrieval_observations"] + c["rules_without"],
                         c["rules"])

    def test_snapshot_is_valid_json_on_disk(self) -> None:
        out = Path(self._tmp.name) / "evidence.json"
        ui_data.write("registry", out, self.events)
        json.loads(out.read_text())


class CoverageDiscriminatesTests(unittest.TestCase):
    """Coverage must measure the skill, not the number of lookups that were run."""

    def test_raw_consult_count_is_identical_across_skills(self):
        """The defect this guards. Retrieval scores every skill on every query, so a raw
        consultation count says how many lookups ran and nothing about any skill."""
        data = ui_data.build_skillearn()
        per_skill = {r["skill"]: r["consults"] for r in data["rules"]}
        if len(per_skill) > 1 and all(per_skill.values()):
            self.assertEqual(
                len(set(per_skill.values())), 1,
                "if raw consult counts ever differ across skills, retrieval stopped scoring "
                "every candidate and coverage's rationale needs revisiting",
            )

    def test_coverage_is_not_pinned_to_one_for_every_skill(self):
        data = ui_data.build_skillearn()
        cov = {r["skill"]: r["emb"][ui_data.DIMS.index("coverage")] for r in data["rules"]}
        observed = [v for v in cov.values() if v is not None]
        if len(observed) > 1:
            self.assertGreater(
                len(set(observed)), 1,
                "coverage carries no information if every skill scores the same; it must read "
                "rank-1 selections, not consultations",
            )

    def test_a_skill_never_ranked_first_has_null_coverage_not_zero(self):
        rule = {"selected": None, "x": 0.5, "y": 1.0, "size": 40}
        emb = ui_data._embedding(rule, busiest=10)
        self.assertIsNone(emb[ui_data.DIMS.index("coverage")])
