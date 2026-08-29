"""Look up the registry for a task description. One lookup, every candidate, scored.

    make retrieve TASK="scrape a competitor site for structured facts"

Returns every skill with its score rather than only those above a threshold. A caller
choosing between using an existing skill, amending one, minting, and reaching for a raw tool
needs to see that the best score was poor, and a filtered list hides exactly that.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from orchestrator.retrieval import SkillIndex

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", nargs="*", help="the task description to look up")
    parser.add_argument("--registry", default=str(REPO / "registry"))
    parser.add_argument("--json", action="store_true", help="emit decision-record JSON")
    args = parser.parse_args(argv)

    task = " ".join(args.task).strip()
    if not task:
        parser.error('a task description is required, e.g. TASK="link records across sources"')

    index = SkillIndex(args.registry).build()
    if not index.signatures:
        print(f"no skills in {args.registry}", file=sys.stderr)
        return 1

    candidates = index.search(task)

    if args.json:
        print(json.dumps({
            "task": task,
            "candidates": [c.as_record() for c in candidates],
            "ledger_entries": len(index.ledger()),
        }, indent=2))
        return 0

    print(f'task: "{task}"')
    print(f"{len(index.signatures)} skills indexed, "
          f"{len(index.ledger())} version-ledger entries read\n")
    print(f"  {'score':>6}  {'body':>6}  {'sig':>6}  {'trust':>5}  skill")
    print(f"  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*5}  {'-'*40}")
    for c in candidates:
        comp = c.components
        print(f"  {c.score:6.3f}  {comp['body']:6.3f}  {comp['signature']:6.3f}  "
              f"{'yes' if c.signature.exercised else 'no ':>5}  "
              f"{c.signature.name} v{c.signature.version}")
        if c.matched_terms:
            print(f"          matched: {', '.join(c.matched_terms)}")

    best = candidates[0]
    print()
    if best.score < 0.10:
        print(f"  best score {best.score:.3f} is low. Nothing here answers this task; "
              f"the decision is mint or raw-tool, not use-existing.")
    else:
        print(f"  best: {best.signature.name} at {best.score:.3f}. "
              f"Whether that is use-existing or amend is the Q2 decision, "
              f"and this score is what the record should carry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
