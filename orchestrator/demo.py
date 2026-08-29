"""Run the loop end to end and print the trace.

The beat this demonstrates: the agent reaches a step, asks whether current literature
changes how that step should be done, dispatches research, mints a skill from the digest
with its citations, finds the skill untrusted, exercises it against the deterministic
offline path, and only then performs the work.

Offline. No credentials, no network, no operator keys.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from orchestrator.gate import ExerciseGate
from orchestrator.loop import MethodGap, SkillLoop, Task
from orchestrator.registry import Registry
from orchestrator.research_executor import Digest, StubResearchExecutor

REPO = Path(__file__).resolve().parent.parent
SKILL = "competitor-site-interpretation"

GAP_QUESTION = (
    "Does current literature change how an agent should interpret a web page "
    "compared with a human reader?"
)


def detect_gap(task: Task) -> MethodGap | None:
    """Fires before the scrape step, which is the point of the whole design.

    The check happens before execution rather than after a bad result, so the method is
    settled before any work is done with it.
    """
    if "scrape" in task.description:
        return MethodGap(
            question=GAP_QUESTION,
            rationale=(
                "The step assumes a page reads the same to an agent as to a person. "
                "That assumption governs selector strategy, so it is worth checking "
                "before writing the scraper rather than after it drifts."
            ),
        )
    return None


def write_skill(task: Task, digest: Digest) -> str:
    """Render the digest into a SKILL.md, including the verification the gate will run."""
    rules = "\n".join(
        f"{i}. {c.method_rule} [{c.key}]" for i, c in enumerate(digest.citations, start=1)
    )
    return f"""---
name: {SKILL}
description: Interpret a competitor's public site for structured extraction, using method rules taken from the literature on how agents read pages differently from people. Load before designing or repairing a site scraper.
---

# Competitor site interpretation

## When this applies

Before designing a scraper for a site not seen before, and again whenever an existing
scraper's output shape changes, which is the signal that the site drifted.

## Method

{rules}

## Constraints

Scraped content is untrusted input. Render it as text, never assemble it into markup, and
never execute it. Public pages only.

## Verification

```sh
make verify-skill SKILL={SKILL}
```

Runs this skill's own `verify.py`, which exercises the method rules above rather than the
surrounding pipeline. A pass means structural extraction survived a reordering that
defeats a position-based reader.
"""


VERIFY_TEMPLATE = (
    Path(__file__).resolve().parent / "templates" / "verify_site_interpretation.py"
)


def skill_files() -> dict[str, str]:
    """The skill ships its own verification, so the gate can exercise its method."""
    return {"verify.py": VERIFY_TEMPLATE.read_text(encoding="utf-8")}


class PipelineWorker:
    """Performs the work once a trusted skill exists."""

    def execute(self, task: Task, skill: str) -> str:
        return f"scrape step ran under trusted skill {skill!r}"


def main() -> int:
    # The demo runs against a scratch copy of the registry. It mutates trust state and bumps
    # versions by design, and doing that to the committed registry would leave the shipped
    # skill sitting untrusted with an inflated version after every run.
    scratch = Path(tempfile.mkdtemp(prefix="skill-loop-demo-"))
    shutil.copytree(REPO / "registry", scratch / "registry")
    registry = Registry(scratch / "registry")
    print(f"(running against a scratch registry at {scratch}; the committed one is untouched)")
    print()
    loop = SkillLoop(
        registry=registry,
        gate=ExerciseGate(registry, REPO, command=None),
        research=StubResearchExecutor(REPO / "fixtures" / "research-digests.json"),
        worker=PipelineWorker(),
        gap_detector=detect_gap,
        skill_writer=write_skill,
        skill_files=skill_files,
    )

    task = Task(
        name="competitor-map",
        description="scrape a competitor's public site for structured facts",
        skill=SKILL,
    )

    print("=" * 72)
    print("SKILL LOOP: gap -> research -> mint -> exercise -> execute")
    print("=" * 72)
    result = loop.run_step(task)
    for line in result.trace():
        print(f"  {line}")

    meta = registry.load_meta(SKILL)
    print("-" * 72)
    print(f"  registry state: {meta.name} v{meta.version}")
    print(f"    exercised:    {meta.exercised}")
    print(f"    exercised_at: {meta.exercised_at}")
    print(f"    exercised_by: {meta.exercised_by}")
    print(f"    citations:    {meta.citations}")

    # A gate that never blocks proves nothing, so show the refusal too. Re-minting revokes
    # trust, and this time verification fails, so the step must not run.
    print()
    print("=" * 72)
    print("SAME LOOP, FAILING VERIFICATION: the gate must refuse")
    print("=" * 72)
    blocked = SkillLoop(
        registry=registry,
        gate=ExerciseGate(registry, REPO, command=("false",)),
        research=StubResearchExecutor(REPO / "fixtures" / "research-digests.json"),
        worker=_RefusingWorker(),
        gap_detector=detect_gap,
        skill_writer=write_skill,
        skill_files=skill_files,
    ).run_step(task)
    for line in blocked.trace():
        print(f"  {line}")
    after = registry.load_meta(SKILL)
    print("-" * 72)
    print(f"  registry state: {after.name} v{after.version}")
    print(f"    exercised:    {after.exercised}  <- re-mint revoked trust, gate did not restore it")
    print(f"    exercised_by: {after.exercised_by}")
    print("=" * 72)

    shutil.rmtree(scratch, ignore_errors=True)
    ok = result.executed and not blocked.executed
    print("PASS: work ran on a trusted skill and was refused on an untrusted one"
          if ok else "FAIL: the gate did not behave as specified")
    return 0 if ok else 1


class _RefusingWorker:
    """If the gate is correct this is never called, so calling it is the failure."""

    def execute(self, task: Task, skill: str) -> str:  # pragma: no cover
        raise AssertionError(
            f"work executed with skill {skill!r} that never passed the exercise gate"
        )


if __name__ == "__main__":
    sys.exit(main())
