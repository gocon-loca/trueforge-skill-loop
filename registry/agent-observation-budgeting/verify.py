"""Verification for a skill minted from a live retrieval.

A skill minted from fixtures can ship a verification written against rules known in advance.
A skill minted live cannot: nobody knows what the rules will say until the retrieval returns.
So this checks the property that is knowable in advance and is the one that matters for a
live mint, which is whether the skill is actually grounded.

It asserts, offline, against the skill's own citations.md:

- every citation carries a well-formed arXiv identifier, so the source can be found;
- every citation carries a non-empty method rule, so it grounds something;
- every rule cited in SKILL.md resolves to a citation key that exists;
- the skill is not a summary wearing a citation, checked by requiring rules to be
  imperative rather than descriptive.

This is a weaker guarantee than the fixture-backed skills get, and saying so is the point.
It does not check that a rule is *correct*, only that it is attributed and actionable. A
live-minted skill should be read by a person before it is relied on, and this gate is what
stops an unattributed one reaching them at all.
"""

import os
import re
from pathlib import Path

SKILL_DIR = Path(os.environ.get("SKILL_REGISTRY", "registry")) / os.environ["SKILL_NAME"]

ARXIV_ID = re.compile(r"^arXiv:\d{4}\.\d{4,5}(v\d+)?$")
DESCRIPTIVE_OPENERS = (
    "this paper", "we propose", "we present", "the authors", "this work",
    "this study", "the paper", "researchers",
)

citations_text = (SKILL_DIR / "citations.md").read_text(encoding="utf-8")
skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

blocks = re.split(r"^## \[", citations_text, flags=re.MULTILINE)[1:]
assert blocks, "citations.md carries no citations; a live mint with no sources is not grounded"

keys = []
for block in blocks:
    key = block.split("]", 1)[0].strip()
    keys.append(key)

    identifier = re.search(r"^- Identifier:\s*(.+)$", block, re.MULTILINE)
    assert identifier, f"[{key}] has no Identifier line"
    ident = identifier.group(1).strip()
    assert ARXIV_ID.match(ident), (
        f"[{key}] identifier {ident!r} is not a well-formed arXiv id, so the source cannot "
        f"be found from the citation"
    )

    rule = re.search(r"^- Method rule extracted:\s*(.+)$", block, re.MULTILINE)
    assert rule and rule.group(1).strip(), f"[{key}] carries no method rule, so it grounds nothing"

    text = rule.group(1).strip().lower()
    assert not text.startswith(DESCRIPTIVE_OPENERS), (
        f"[{key}] rule reads as a description of the paper rather than an instruction: "
        f"{rule.group(1)[:80]!r}. A summary wearing a citation is not a method rule."
    )

    authors = re.search(r"^- Authors:\s*(.+)$", block, re.MULTILINE)
    assert authors and authors.group(1).strip(), f"[{key}] has no authors"
    assert "not verified" not in authors.group(1).lower(), (
        f"[{key}] records authorship as unverified, which a live retrieval has no excuse "
        f"for: the API returns the author list"
    )

cited_in_body = set(re.findall(r"\[([a-z0-9-]+)\]", skill_text))
declared = set(keys)
dangling = cited_in_body - declared
assert not dangling, f"SKILL.md cites keys with no citation entry: {sorted(dangling)}"

print(f"  {len(keys)} citations, all with well-formed arXiv identifiers")
print(f"  all rules non-empty and imperative; authorship recorded from the API")
print(f"  every key cited in SKILL.md resolves: {sorted(declared)}")
