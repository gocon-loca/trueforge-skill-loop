"""Q2 action space: four actions, and an append-only record of every choice.

The four actions a caller has when a task arrives:

    use-existing   a trusted skill already answers this
    amend          a skill is about this method but is incomplete or wrong here
    mint           no skill covers it, and the method is worth writing down
    raw-tool       no skill covers it and none should; do the work directly

Every choice writes a record carrying **the retrieval scores that informed it**. That is the
requirement, and the reason for it is that a decision without its inputs cannot be reviewed
later: "we minted" is a fact, "we minted when the best existing candidate scored 0.03" is a
judgement someone can disagree with.

The log is append-only and separate from the version ledger. The ledger records what the
registry *is*; this records what was *decided* and on what evidence. Keeping them apart
matters because a decision can be wrong while the resulting state is internally consistent,
and a single log cannot show that.

Nothing here scores or rewards. Q3 defines reward and Q4 defines selection; this layer only
records, so that when they arrive there is a history to learn from rather than a cold start.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

USE_EXISTING = "use-existing"
AMEND = "amend"
MINT = "mint"
RAW_TOOL = "raw-tool"
ACTIONS = (USE_EXISTING, AMEND, MINT, RAW_TOOL)

DEFAULT_LOG = Path("data") / "decisions.jsonl"

# A fixed heuristic, per the brief: the bandit ships after logged decisions exist, not before.
# These thresholds are stated here rather than buried so that a later policy can be compared
# against them, and so that a reader can see the policy is a guess rather than a finding.
USE_EXISTING_FLOOR = 0.20
AMEND_FLOOR = 0.10


@dataclass(frozen=True)
class Decision:
    """One choice, with the evidence that informed it."""

    task: str
    action: str
    skill: str | None
    rationale: str
    candidates: tuple[dict, ...] = ()
    decided_at: str = ""
    decided_by: str = "heuristic-v1"

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"unknown action {self.action!r}; expected one of {ACTIONS}")
        if self.action in (USE_EXISTING, AMEND) and not self.skill:
            raise ValueError(f"action {self.action!r} requires the skill it refers to")
        if self.action in (MINT, RAW_TOOL) and self.skill:
            raise ValueError(f"action {self.action!r} names a skill {self.skill!r}")
        if not self.candidates:
            raise ValueError(
                "a decision record with no candidates records a choice without the evidence "
                "that informed it, which is the thing this log exists to prevent"
            )

    def as_record(self) -> dict:
        return {
            "decided_at": self.decided_at or datetime.now(timezone.utc)
                .isoformat().replace("+00:00", "Z"),
            "decided_by": self.decided_by,
            "task": self.task,
            "action": self.action,
            "skill": self.skill,
            "rationale": self.rationale,
            "candidates": list(self.candidates),
        }


def choose(task: str, candidates: list, policy: str = "heuristic-v1") -> Decision:
    """The fixed heuristic. Deliberately simple, and deliberately explicit about being a guess.

    `candidates` is the ranked output of `SkillIndex.search`, every skill scored.

    The policy: a strong match on a trusted skill is used; a strong match on an untrusted one
    is amended, because the skill is about the right method and its trust has lapsed; a weak
    match is amended if it is at least in the area, and minted otherwise; nothing in the area
    at all is a raw-tool decision, because minting a skill for a one-off is how a registry
    fills with entries nobody retrieves.
    """
    records = tuple(c.as_record() for c in candidates)
    if not records:
        return Decision(task, RAW_TOOL, None,
                        "registry is empty, so there is nothing to retrieve against",
                        candidates=({"skill": None, "score": 0.0},), decided_by=policy)

    best = candidates[0]
    score = best.score
    name = best.signature.name
    trusted = best.signature.exercised

    if score >= USE_EXISTING_FLOOR and trusted:
        return Decision(task, USE_EXISTING, name,
                        f"{name} scored {score:.3f}, at or above the {USE_EXISTING_FLOOR} "
                        f"floor, and is trusted",
                        records, decided_by=policy)
    if score >= USE_EXISTING_FLOOR and not trusted:
        return Decision(task, AMEND, name,
                        f"{name} scored {score:.3f} but is untrusted; it is about this "
                        f"method and has to re-earn trust before use",
                        records, decided_by=policy)
    if score >= AMEND_FLOOR:
        return Decision(task, AMEND, name,
                        f"{name} scored {score:.3f}, in the area but below the "
                        f"{USE_EXISTING_FLOOR} floor; closest existing method rather than a "
                        f"new one",
                        records, decided_by=policy)
    return Decision(task, MINT, None,
                    f"best candidate scored {score:.3f}, below the {AMEND_FLOOR} floor; "
                    f"nothing in the registry is about this method",
                    records, decided_by=policy)


class DecisionLog:
    """Append-only. Never rewritten, never deduplicated, never truncated by this code."""

    def __init__(self, path: Path | str = DEFAULT_LOG) -> None:
        self.path = Path(os.environ.get("DECISION_LOG", path))

    def append(self, decision: Decision) -> dict:
        record = decision.as_record()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def read(self) -> list[dict]:
        if not self.path.is_file():
            return []
        return [
            json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def counts(self) -> dict[str, int]:
        out = {a: 0 for a in ACTIONS}
        for r in self.read():
            if r.get("action") in out:
                out[r["action"]] += 1
        return out
