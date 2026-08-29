"""Run the loop end to end over every declared skill, and print the trace.

The beat: the agent reaches a step, asks whether current literature changes how that step
should be done, dispatches research, mints a skill from the digest with its citations,
finds it untrusted, exercises it against the skill's own verification, and only then does
the work.

It runs twice, over two method gaps that fail in different ways, then shows the refusal.
Offline throughout. No credentials, no network, no operator keys.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from orchestrator.gate import ExerciseGate
from orchestrator.loop import SkillLoop, Task
from orchestrator.registry import Registry
from orchestrator.research_executor import StubResearchExecutor
from orchestrator.skills import ALL_SKILLS, SkillSpec

REPO = Path(__file__).resolve().parent.parent
DIGESTS = REPO / "fixtures" / "research-digests.json"

TASKS = {
    "competitor-site-interpretation": Task(
        name="competitor-map/acquire",
        description="scrape a competitor's public site for structured facts",
        skill="competitor-site-interpretation",
    ),
    "public-source-entity-linking": Task(
        name="competitor-map/connect",
        description="link records across public sources into an interconnection graph",
        skill="public-source-entity-linking",
    ),
}


class PipelineWorker:
    def execute(self, task: Task, skill: str) -> str:
        return f"{task.name} ran under trusted skill {skill!r}"


class RefusingWorker:
    """If the gate is correct this is never called, so calling it is the failure."""

    def execute(self, task: Task, skill: str) -> str:  # pragma: no cover
        raise AssertionError(
            f"work executed with skill {skill!r} that never passed the exercise gate"
        )


def build_loop(spec: SkillSpec, registry: Registry, worker, command) -> SkillLoop:
    return SkillLoop(
        registry=registry,
        gate=ExerciseGate(registry, REPO, command=command),
        research=StubResearchExecutor(DIGESTS),
        worker=worker,
        gap_detector=spec.detect_gap,
        skill_writer=spec.write_skill,
        skill_files=spec.files,
    )


def run_one(spec: SkillSpec, registry: Registry) -> bool:
    print("=" * 78)
    print(f"GAP {spec.name}")
    print("=" * 78)
    result = build_loop(spec, registry, PipelineWorker(), None).run_step(TASKS[spec.name])
    for line in result.trace():
        print(f"  {line}")
    meta = registry.load_meta(spec.name)
    print(f"  -> v{meta.version} exercised={meta.exercised} "
          f"by={meta.exercised_by!r} citations={meta.citations}")
    print()
    return result.executed


def main() -> int:
    # A scratch copy: the demo bumps versions and revokes trust by design, and doing that
    # to the committed registry would leave the shipped skills untrusted after every run.
    scratch = Path(tempfile.mkdtemp(prefix="skill-loop-demo-"))
    shutil.copytree(REPO / "registry", scratch / "registry")
    registry = Registry(scratch / "registry")
    print(f"(scratch registry at {scratch}; the committed one is untouched)\n")

    try:
        executed = [run_one(spec, registry) for spec in ALL_SKILLS]

        print("=" * 78)
        print("THE GATE MUST ALSO REFUSE")
        print("=" * 78)
        spec = ALL_SKILLS[0]
        blocked = build_loop(
            spec, registry, RefusingWorker(), ("false",)
        ).run_step(TASKS[spec.name])
        for line in blocked.trace():
            print(f"  {line}")
        after = registry.load_meta(spec.name)
        print(f"  -> exercised={after.exercised} by={after.exercised_by!r}")
        print()

        ok = all(executed) and not blocked.executed
        print("=" * 78)
        print(
            f"PASS: {len(executed)} skills minted from different method gaps, each "
            f"exercised by its own verification, and work refused on an untrusted skill"
            if ok else "FAIL: the loop did not behave as specified"
        )
        return 0 if ok else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
