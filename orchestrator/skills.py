"""The skills this repository mints, declared rather than hardcoded in the demo.

Two entries, deliberately from different method gaps. The first is about acquiring facts
from a page; the second is about linking facts across sources. They fail in different ways,
so minting both shows the loop generalises rather than showing that one code path runs
twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.loop import MethodGap, Task
from orchestrator.research_executor import Digest

TEMPLATES = Path(__file__).resolve().parent / "templates"
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _render_rules(citations) -> list[str]:
    """One numbered rule per group of citations, not per citation.

    A citation carrying `supports` converges on another citation's rule: same prescribed
    action, different objective. Those render as one rule citing both keys, so the registry
    does not assert one method twice, and the rule text states both objectives so a later
    change cannot satisfy one while silently destroying the other.
    """
    primaries = [c for c in citations if not c.supports]
    convergent: dict[str, list] = {}
    for c in citations:
        if c.supports:
            convergent.setdefault(c.supports, []).append(c)

    out = []
    for i, c in enumerate(primaries, start=1):
        others = convergent.get(c.key, [])
        keys = " ".join(f"[{k.key}]" for k in [c, *others])
        if not others:
            out.append(f"{i}. {c.method_rule} {keys}")
            continue
        objectives = "; ".join(
            f"{k.objective or 'unstated'} ({k.key})" for k in [c, *others]
        )
        out.append(
            f"{i}. {c.method_rule} Independently prescribed for a second reason: "
            f"{' '.join(k.method_rule for k in others)} "
            f"Objectives this rule answers to: {objectives}. {keys}"
        )
    return out


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    trigger: str
    gap_question: str
    gap_rationale: str
    applies_when: str
    constraints: str
    verify_template: str
    verify_summary: str
    minted_from: str = "research"
    fixture: str | None = None

    def detect_gap(self, task: Task) -> MethodGap | None:
        if self.trigger in task.description:
            return MethodGap(question=self.gap_question, rationale=self.gap_rationale)
        return None

    def _rules(self, digest: Digest) -> list[str]:
        return _render_rules(digest.grounded_citations())

    def files(self) -> dict[str, str]:
        """Everything the gate needs, shipped inside the skill directory.

        The fixture ships here rather than staying under `fixtures/` because
        `exercised_hash` covers the skill directory only. A known-answer fixture that lives
        outside it is load-bearing for the gate and outside the trust binding, so editing
        the expected answer would leave the skill trusted against a run that no longer
        proves anything.
        """
        out = {"verify.py": (TEMPLATES / self.verify_template).read_text(encoding="utf-8")}
        if self.fixture:
            out["fixture.json"] = (FIXTURES / self.fixture).read_text(encoding="utf-8")
        return out

    def write_skill(self, task: Task, digest: Digest) -> str:
        rules = "\n".join(self._rules(digest))
        return f"""---
name: {self.name}
description: {self.description}
---

# {self.name.replace('-', ' ').capitalize()}

## When this applies

{self.applies_when}

## Method

{rules}

## Constraints

{self.constraints}

## Verification

```sh
make verify-skill SKILL={self.name}
```

{self.verify_summary}
"""


SITE_INTERPRETATION = SkillSpec(
    name="competitor-site-interpretation",
    description=(
        "Interpret a public site for structured extraction, using method rules from the "
        "literature on how agents read pages differently from people. Load before "
        "designing or repairing a site scraper."
    ),
    trigger="scrape",
    gap_question=(
        "Does current literature change how an agent should interpret a web page "
        "compared with a human reader?"
    ),
    gap_rationale=(
        "The step assumes a page reads the same to an agent as to a person. That "
        "assumption governs selector strategy, so it is worth settling before the "
        "scraper is written rather than after its output drifts."
    ),
    applies_when=(
        "Before designing a scraper for a site not seen before, and again whenever an "
        "existing scraper's output shape changes, which is the signal that the site "
        "drifted."
    ),
    constraints=(
        "Scraped content is untrusted input. Render it as text, never assemble it into "
        "markup, and never execute it. Public pages only."
    ),
    verify_template="verify_site_interpretation.py",
    fixture="site-interpretation-known-answers.json",
    verify_summary=(
        "A pass means structural extraction survived a reordering that defeats a "
        "position-based reader."
    ),
)

ENTITY_LINKING = SkillSpec(
    name="public-source-entity-linking",
    description=(
        "Link entities across independent public sources without letting one weak match "
        "merge unrelated groups. Load before building a graph whose edges assert that two "
        "records describe the same organisation or person."
    ),
    trigger="link",
    gap_question=(
        "Does current literature change how entities should be linked across independent "
        "public sources?"
    ),
    gap_rationale=(
        "The step assumes pairwise matches can be joined transitively into groups. That "
        "assumption decides whether the resulting graph is evidence or an artefact, so it "
        "is worth settling before any edge is drawn."
    ),
    applies_when=(
        "Before building any graph whose edges claim two records refer to the same real "
        "entity, and again whenever a new source is added to an existing graph."
    ),
    constraints=(
        "Public sources only. Do not link on private contact data. An edge asserts a "
        "factual claim about real organisations, so an unverified merge is a published "
        "error, not a tuning parameter."
    ),
    verify_template="verify_entity_linking.py",
    fixture="entity-linking-known-answers.json",
    verify_summary=(
        "A pass means a single low-confidence link did not merge two groups that share "
        "nothing, which naive transitive closure does."
    ),
)

WORKSPACE_SENTINEL = SkillSpec(
    name="workspace-sentinel",
    description=(
        "Coordinate a shared workspace so that reports from it can be relied on: read "
        "inbound before acting, acknowledge on receipt, watch a peer for silence, verify "
        "claims against artefacts before relaying them, and escalate on a stated clock. "
        "Load before running any agent that watches others and reports what it sees."
    ),
    trigger="coordinate",
    gap_question=(
        "What does a workspace coordination agent have to do so that its reports can be "
        "relied on?"
    ),
    gap_rationale=(
        "A coordination agent's output is consumed as fact by whoever reads it, so its "
        "failures are silent: a missed directive, an unchecked relay, or an alarm raised "
        "on an absent signal all look like normal operation. The rules are worth settling "
        "before it is trusted to watch anything."
    ),
    applies_when=(
        "Before instantiating an agent whose job is to watch other agents, relay their "
        "state to a person, and hold directives on their behalf. Also whenever such an "
        "agent has reported something that turned out not to be so, since that is the "
        "signal one of these rules is missing."
    ),
    constraints=(
        "Never relay a claim that has not been checked against the underlying artefact. "
        "Never treat an unavailable signal as a negative one. Never let elapsed time "
        "convert into permission for an action that cannot be taken back. Do not act on "
        "an operator's behalf beyond a stated default, and never at all where the action "
        "is irreversible or external-facing."
    ),
    verify_template="verify_workspace_sentinel.py",
    verify_summary=(
        "A pass means the encoded policy reproduces the decisions actually taken in the "
        "record it was extracted from, including the two cases where the refined rule "
        "differs from the naive one."
    ),
    minted_from="incident",
)

OBSERVATION_BUDGETING = SkillSpec(
    name="agent-observation-budgeting",
    description=(
        "Decide how much of an observation a running agent should carry, from its budget "
        "and its plan rather than from the page. Load before choosing what to keep when an "
        "observation will not fit."
    ),
    trigger="budget",
    gap_question="How should a running agent decide how much of an observation to carry?",
    gap_rationale=(
        "The step assumes one representation fits every model and every point in a plan. "
        "That assumption decides what the agent still has when it needs it, and its failure "
        "is silent: the agent proceeds with too little rather than erroring."
    ),
    applies_when=(
        "Before reducing an observation that a later step will read, and whenever an agent "
        "degrades on longer tasks rather than on harder ones, which is the signature of "
        "dropping what the plan needed."
    ),
    constraints=(
        "Reduction is not compression for its own sake. These rules answer to sufficiency, "
        "keeping what the plan will need, and they can conflict with a cost objective. Where "
        "they do, the conflict is real and belongs to whoever sets the budget, not to a "
        "silent default."
    ),
    verify_template="verify_live_grounding.py",
    verify_summary=(
        "Checks grounding rather than correctness: every citation carries a well-formed "
        "identifier, a non-empty imperative rule, and a stated objective. These rules came "
        "from a live retrieval, so a person should read the cited papers before relying on "
        "one."
    ),
)

ALL_SKILLS = (SITE_INTERPRETATION, ENTITY_LINKING, WORKSPACE_SENTINEL, OBSERVATION_BUDGETING)
