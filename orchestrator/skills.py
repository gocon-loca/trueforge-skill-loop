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

    def detect_gap(self, task: Task) -> MethodGap | None:
        if self.trigger in task.description:
            return MethodGap(question=self.gap_question, rationale=self.gap_rationale)
        return None

    def files(self) -> dict[str, str]:
        return {"verify.py": (TEMPLATES / self.verify_template).read_text(encoding="utf-8")}

    def write_skill(self, task: Task, digest: Digest) -> str:
        rules = "\n".join(
            f"{i}. {c.method_rule} [{c.key}]"
            for i, c in enumerate(digest.grounded_citations(), start=1)
        )
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
    verify_summary=(
        "A pass means a single low-confidence link did not merge two groups that share "
        "nothing, which naive transitive closure does."
    ),
)

ALL_SKILLS = (SITE_INTERPRETATION, ENTITY_LINKING)
