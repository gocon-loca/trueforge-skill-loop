"""Adversarial tests for the trust invariant.

The property under test is: `exercised: true` implies a passing run happened. These tests
try to obtain trust without a passing run, and assert that every route is closed.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from orchestrator.gate import ExerciseGate
from orchestrator.loop import MethodGap, SkillLoop, Task
from orchestrator.registry import (
    ExerciseEvidence,
    Registry,
    RegistryError,
    UngroundedSkillError,
    UntrustedSkillError,
)
from orchestrator.research_executor import Citation, Digest, StubResearchExecutor

FIXTURE_QUESTION = (
    "Does current literature change how an agent should interpret a web page "
    "compared with a human reader?"
)


def grounded_digest(n: int = 2) -> Digest:
    return Digest(
        question="q",
        citations=tuple(
            Citation(
                key=f"k{i}",
                title=f"T{i}",
                authors="A",
                venue="V",
                year=2024,
                identifier=f"arXiv:{i}",
                method_rule=f"rule {i}",
            )
            for i in range(n)
        ),
    )


class RegistryTrustTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry = Registry(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_minted_skill_lands_untrusted(self) -> None:
        meta = self.registry.mint("demo-skill", grounded_digest(), "# body")
        self.assertFalse(meta.exercised)
        self.assertIsNone(meta.exercised_at)
        self.assertIsNone(meta.exercised_by)
        self.assertEqual(meta.citations, 2)

    def test_mint_refuses_digest_with_no_citations(self) -> None:
        with self.assertRaises(UngroundedSkillError):
            self.registry.mint("demo-skill", Digest(question="q", citations=()), "# body")

    def test_mint_rejects_non_kebab_and_reserved_names(self) -> None:
        for bad in ("Demo_Skill", "demo skill", "_template", "-leading", "trailing-"):
            with self.subTest(name=bad), self.assertRaises(RegistryError):
                self.registry.mint(bad, grounded_digest(), "# body")

    def test_untrusted_skill_may_not_be_used_for_work(self) -> None:
        self.registry.mint("demo-skill", grounded_digest(), "# body")
        with self.assertRaises(UntrustedSkillError):
            self.registry.require_trusted("demo-skill")

    def test_failing_evidence_cannot_buy_trust(self) -> None:
        self.registry.mint("demo-skill", grounded_digest(), "# body")
        evidence = ExerciseEvidence.now("make exercise", passed=False)
        with self.assertRaises(RegistryError):
            self.registry.mark_exercised("demo-skill", evidence)
        self.assertFalse(self.registry.load_meta("demo-skill").exercised)

    def test_passing_evidence_writes_all_three_fields_together(self) -> None:
        self.registry.mint("demo-skill", grounded_digest(), "# body")
        at = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
        meta = self.registry.mark_exercised(
            "demo-skill", ExerciseEvidence(command="make exercise", passed=True, at=at)
        )
        self.assertTrue(meta.exercised)
        self.assertEqual(meta.exercised_at, "2026-08-29T12:00:00Z")
        self.assertEqual(meta.exercised_by, "make exercise")
        # and it survives a round trip through disk
        on_disk = yaml.safe_load((self.root / "demo-skill" / "meta.yaml").read_text())
        self.assertTrue(on_disk["exercised"])
        self.assertEqual(on_disk["exercised_by"], "make exercise")

    def test_remint_revokes_trust_and_bumps_version(self) -> None:
        self.registry.mint("demo-skill", grounded_digest(), "# body")
        self.registry.mark_exercised("demo-skill", ExerciseEvidence.now("make exercise", passed=True))
        self.assertTrue(self.registry.is_trusted("demo-skill"))

        second = self.registry.mint("demo-skill", grounded_digest(3), "# body v2")
        self.assertEqual(second.version, 2)
        self.assertFalse(second.exercised, "re-minting must revoke trust")
        self.assertIsNone(second.exercised_by)

    def test_reset_trust_clears_all_three_fields(self) -> None:
        self.registry.mint("demo-skill", grounded_digest(), "# body")
        self.registry.mark_exercised("demo-skill", ExerciseEvidence.now("make exercise", passed=True))
        meta = self.registry.reset_trust("demo-skill")
        self.assertFalse(meta.exercised)
        self.assertIsNone(meta.exercised_at)
        self.assertIsNone(meta.exercised_by)

    def test_template_is_not_listed_as_a_skill(self) -> None:
        (self.root / "_template").mkdir()
        (self.root / "_template" / "meta.yaml").write_text("name: _template\nversion: 1\n")
        self.registry.mint("demo-skill", grounded_digest(), "# body")
        self.assertEqual(self.registry.list_skills(), ["demo-skill"])


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry = Registry(self.root / "registry")
        self.registry.mint("demo-skill", grounded_digest(), "# body")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_failing_command_leaves_skill_untrusted(self) -> None:
        gate = ExerciseGate(self.registry, self.root, command=("false",))
        result = gate.exercise("demo-skill")
        self.assertFalse(result.passed)
        self.assertFalse(self.registry.is_trusted("demo-skill"))

    def test_passing_command_confers_trust(self) -> None:
        gate = ExerciseGate(self.registry, self.root, command=("true",))
        result = gate.exercise("demo-skill")
        self.assertTrue(result.passed)
        self.assertTrue(self.registry.is_trusted("demo-skill"))
        self.assertEqual(result.meta.exercised_by, "true")

    def test_timeout_is_a_failure_not_a_pass(self) -> None:
        gate = ExerciseGate(self.registry, self.root, command=("sleep", "5"), timeout=1)
        result = gate.exercise("demo-skill")
        self.assertFalse(result.passed)
        self.assertEqual(result.returncode, 124)
        self.assertFalse(self.registry.is_trusted("demo-skill"))


class _RecordingWorker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, task: Task, skill: str) -> str:
        self.calls.append(skill)
        return f"worked:{skill}"


class LoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry = Registry(self.root / "registry")
        self.worker = _RecordingWorker()
        self.task = Task(name="competitor-map", description="scrape", skill="demo-skill")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _loop(self, *, command: tuple[str, ...], gap: MethodGap | None) -> SkillLoop:
        return SkillLoop(
            registry=self.registry,
            gate=ExerciseGate(self.registry, self.root, command=command),
            research=_StaticResearch(),
            worker=self.worker,
            gap_detector=lambda _t: gap,
            skill_writer=lambda _t, _d: "# minted body",
        )

    def test_failed_gate_blocks_execution(self) -> None:
        loop = self._loop(command=("false",), gap=MethodGap("q", "r"))
        result = loop.run_step(self.task)
        self.assertTrue(result.minted)
        self.assertFalse(result.executed)
        self.assertEqual(self.worker.calls, [], "work must not run on an unexercised skill")

    def test_passing_gate_allows_execution(self) -> None:
        loop = self._loop(command=("true",), gap=MethodGap("q", "r"))
        result = loop.run_step(self.task)
        self.assertTrue(result.executed)
        self.assertEqual(self.worker.calls, ["demo-skill"])

    def test_recursion_cap_stops_gap_checks(self) -> None:
        loop = self._loop(command=("true",), gap=MethodGap("q", "r"))
        result = loop.run_step(self.task, depth=2)
        self.assertIsNone(result.gap)
        self.assertFalse(result.minted)
        self.assertTrue(any("recursion cap" in n for n in result.notes))
        self.assertFalse(result.executed, "no skill exists, so no work may run")

    def test_gate_refuses_absent_skill_without_running_the_command(self) -> None:
        marker = self.root / "ran"
        gate = ExerciseGate(
            self.registry, self.root, command=("touch", str(marker))
        )
        result = gate.exercise("never-minted")
        self.assertFalse(result.passed)
        self.assertEqual(result.returncode, 127)
        self.assertFalse(marker.exists(), "the command must not run for an absent skill")


class _StaticResearch:
    def run(self, question: str) -> Digest:
        return grounded_digest()


class StubResearchTests(unittest.TestCase):
    def test_stub_reads_the_committed_fixture(self) -> None:
        stub = StubResearchExecutor(Path("fixtures/research-digests.json"))
        digest = stub.run(FIXTURE_QUESTION)
        self.assertTrue(digest.is_groundable())
        self.assertEqual(digest.source, "stub")

    def test_unknown_question_is_ungroundable_not_an_error(self) -> None:
        stub = StubResearchExecutor(Path("fixtures/research-digests.json"))
        digest = stub.run("no such question")
        self.assertFalse(digest.is_groundable())
        self.assertEqual(digest.source, "stub:miss")


if __name__ == "__main__":
    unittest.main()
