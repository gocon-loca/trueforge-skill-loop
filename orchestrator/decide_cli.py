"""Retrieve for a task, choose an action, and append the decision with its evidence.

    make decide TASK="link records across public filings"

The action is chosen by a fixed heuristic. Per the brief, the bandit ships after logged
decisions exist rather than before, so this writes the history that a learned policy would
later need, and says plainly that the current policy is a guess.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from orchestrator.decisions import DecisionLog, choose
from orchestrator.retrieval import SkillIndex

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", nargs="*")
    parser.add_argument("--registry", default=str(REPO / "registry"))
    parser.add_argument("--log", default=str(REPO / "data" / "decisions.jsonl"))
    parser.add_argument("--dry-run", action="store_true", help="decide without recording")
    args = parser.parse_args(argv)

    task = " ".join(args.task).strip()
    if not task:
        parser.error('a task description is required')

    index = SkillIndex(args.registry).build()
    candidates = index.search(task)
    decision = choose(task, candidates)

    print(f'task:   "{task}"')
    print(f"action: {decision.action}" + (f"  ->  {decision.skill}" if decision.skill else ""))
    print(f"why:    {decision.rationale}")
    print(f"policy: {decision.decided_by} (a fixed heuristic, not a learned one)")

    if args.dry_run:
        print("\ndry run: nothing recorded")
        return 0

    log = DecisionLog(args.log)
    log.append(decision)
    counts = log.counts()
    print(f"\nrecorded to {log.path} with {len(candidates)} scored candidates")
    print("  " + ", ".join(f"{a}={n}" for a, n in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
