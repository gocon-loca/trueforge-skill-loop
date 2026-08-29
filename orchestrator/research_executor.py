"""The research dispatch boundary.

The public repo ships the INTERFACE and a deterministic offline stub. The real
implementation lives on the private side and fulfils the same protocol. Nothing in this
module may import private code; see BOUNDARY.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Citation:
    """One source, and the single method rule extracted from it.

    A citation that carries no method rule is a reference, not a basis for a skill.
    """

    key: str
    title: str
    authors: str
    venue: str
    year: int
    identifier: str
    method_rule: str

    # Convergence support. Two sources can prescribe the same action for different reasons;
    # merging them as plain corroboration loses the reasons, and a later change satisfying
    # one objective can then silently destroy the other while the merged rule still reads as
    # satisfied. `objective` names what this source wants the action for. `supports` names
    # the citation key whose rule this one converges on, so the two render as one rule
    # carrying both objectives rather than as two rules or as one rule with a lost reason.
    objective: str = ""
    supports: str = ""

    def to_markdown(self) -> str:
        lines = [
            f"## [{self.key}]",
            "",
            f"- Title: {self.title}",
            f"- Authors: {self.authors}",
            f"- Venue and year: {self.venue}, {self.year}",
            f"- Identifier: {self.identifier}",
            f"- Method rule extracted: {self.method_rule}",
        ]
        if self.objective:
            lines.append(f"- Objective supported: {self.objective}")
        if self.supports:
            lines.append(f"- Converges on rule: [{self.supports}]")
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Digest:
    """The output of one research dispatch."""

    question: str
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    source: str = "stub"

    @property
    def method_rules(self) -> tuple[str, ...]:
        return tuple(c.method_rule for c in self.citations)

    def is_groundable(self) -> bool:
        """Whether this digest can ground a skill.

        Finding 4. Counting citations was not enough: a citation carrying an empty
        method_rule contributes nothing to the skill's method, so a digest of three such
        citations passed grounding while encoding no rules at all. A citation must carry
        both a rule and an identifier for the rule to be traceable to a source.
        """
        return any(
            c.method_rule.strip() and c.identifier.strip() for c in self.citations
        )

    def grounded_citations(self) -> tuple["Citation", ...]:
        return tuple(
            c for c in self.citations if c.method_rule.strip() and c.identifier.strip()
        )


@runtime_checkable
class ResearchExecutor(Protocol):
    """`run(question) -> Digest`. The only surface the orchestrator depends on."""

    def run(self, question: str) -> Digest: ...


class StubResearchExecutor:
    """Deterministic, offline, fixture-backed. No network and no credentials.

    This is what makes the loop runnable in CI and what the exercise gate runs against
    before anything touches a live source.
    """

    def __init__(self, fixture_path: Path | str) -> None:
        self._fixture_path = Path(fixture_path)

    def run(self, question: str) -> Digest:
        payload = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        entry = payload.get(question)
        if entry is None:
            return Digest(question=question, citations=(), source="stub:miss")
        citations = tuple(Citation(**c) for c in entry["citations"])
        return Digest(question=question, citations=citations, source="stub")
