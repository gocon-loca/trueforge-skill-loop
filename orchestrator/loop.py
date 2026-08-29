"""The core loop: work -> method-gap check -> research -> mint -> exercise -> execute.

The loop's contract is that no work is performed with a skill that has not passed the
exercise gate, and that research recursion is capped so a gap cannot fan out indefinitely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from orchestrator.gate import ExerciseGate, ExerciseResult
from orchestrator.registry import Registry, UngroundedSkillError
from orchestrator.research_executor import Digest, ResearchExecutor

MAX_RESEARCH_DEPTH = 2


@dataclass(frozen=True)
class Task:
    name: str
    description: str
    skill: str


@dataclass(frozen=True)
class MethodGap:
    """A claim that current literature may change how a step should be done."""

    question: str
    rationale: str


@dataclass
class StepResult:
    task: Task
    gap: MethodGap | None = None
    digest: Digest | None = None
    minted: bool = False
    exercise: ExerciseResult | None = None
    executed: bool = False
    output: object | None = None
    notes: list[str] = field(default_factory=list)

    def trace(self) -> list[str]:
        """Human-readable account of the loop, used by the demo and by the PR evidence."""
        line = [f"task: {self.task.name}"]
        line.append(f"gap: {self.gap.question}" if self.gap else "gap: none, skill is current")
        if self.digest:
            line.append(f"research: {len(self.digest.citations)} citations via {self.digest.source}")
        if self.minted:
            line.append(f"mint: {self.task.skill} written untrusted")
        if self.exercise:
            line.append(self.exercise.summary())
        line.append(f"execute: {'ran' if self.executed else 'blocked'}")
        return line + self.notes


class WorkExecutor(Protocol):
    """Performs the actual work once a trusted skill is available."""

    def execute(self, task: Task, skill: str) -> object: ...


GapDetector = Callable[[Task], MethodGap | None]


class SkillLoop:
    def __init__(
        self,
        registry: Registry,
        gate: ExerciseGate,
        research: ResearchExecutor,
        worker: WorkExecutor,
        gap_detector: GapDetector,
        skill_writer: Callable[[Task, Digest], str],
        skill_files: Callable[[], dict[str, str]] | None = None,
        max_depth: int = MAX_RESEARCH_DEPTH,
    ) -> None:
        self.registry = registry
        self.gate = gate
        self.research = research
        self.worker = worker
        self.gap_detector = gap_detector
        self.skill_writer = skill_writer
        self.skill_files = skill_files
        self.max_depth = max_depth

    def run_step(self, task: Task, depth: int = 0) -> StepResult:
        result = StepResult(task=task)

        # 1. METHOD-GAP CHECK, before executing.
        gap = self.gap_detector(task) if depth < self.max_depth else None
        if gap is None and depth >= self.max_depth:
            result.notes.append(
                f"recursion cap reached at depth {depth}; gap check skipped by policy"
            )
        result.gap = gap

        # 2-4. RESEARCH and MINT, only when a gap fired.
        if gap is not None:
            digest = self.research.run(gap.question)
            result.digest = digest
            try:
                self.registry.mint(
                    task.skill,
                    digest,
                    self.skill_writer(task, digest),
                    extra_files=self.skill_files() if self.skill_files else None,
                )
                result.minted = True
            except UngroundedSkillError as exc:
                # Finding 6. A refused mint used to fall through and run the work with
                # whatever previous version happened to be trusted. A gap that fired and
                # could not be grounded means this step has no current method, so it stops.
                result.notes.append(f"mint refused: {exc}")
                result.notes.append(
                    "execution blocked: a method gap fired but research could not ground a "
                    "skill, so the previously trusted version is stale for this step"
                )
                return result

        # 5. EXERCISE GATE. A freshly minted skill is untrusted until this passes.
        #
        # An already-trusted skill is not re-exercised here, which is deliberate: trust is
        # earned once per version and re-earned on every re-mint. What makes that safe is
        # not this branch but require_trusted below, which rejects a skill whose files no
        # longer match the hash recorded when it passed. Skipping the run is an
        # optimisation; it is not what decides whether the skill may be used.
        if result.minted or not self._is_trusted(task.skill):
            result.exercise = self.gate.exercise(task.skill)

        # 6. EXECUTE, only with a trusted skill.
        #
        # Findings 2 and 3. Checking trust and then executing leaves a window: a re-mint
        # between the two means work runs under content that never passed. The check
        # therefore records what it approved, and the approval is re-confirmed against
        # disk immediately before the work runs.
        #
        # This closes the in-process window. It is not a distributed lock: another process
        # editing the registry between the confirmation and the call can still change the
        # files underneath. That is out of scope for a single-process orchestrator, and it
        # is recorded here rather than implied away.
        try:
            approved = self.registry.require_trusted(task.skill)
            approved_hash = self.registry.content_hash(task.skill)

            # Confirm again immediately before running. require_trusted already checks the
            # files against the hash recorded at exercise time; this closes the remaining
            # window between that check and the call below.
            current = self.registry.load_meta(task.skill)
            changed = (
                not current.exercised
                or current.version != approved.version
                or self.registry.content_hash(task.skill) != approved_hash
            )
        except Exception as exc:
            # Finding: the recheck could itself raise, and the exception escaped run_step
            # instead of blocking the step. A failed check is a blocked step.
            result.notes.append(f"execution blocked: {exc}")
            return result

        if changed:
            result.notes.append(
                "execution blocked: the skill changed between the trust check and the "
                "run, so what was approved is not what would execute"
            )
            return result

        result.output = self.worker.execute(task, task.skill)
        result.executed = True
        return result

    def _is_trusted(self, skill: str) -> bool:
        try:
            return self.registry.is_trusted(skill)
        except Exception:
            return False
