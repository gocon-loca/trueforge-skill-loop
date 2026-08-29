"""Verification for competitor-site-interpretation: known answers, not a smoke test.

The earlier version asserted that two layouts extracted alike and a positional reader did
not. Both the extractor and its expected output were written here from the same
understanding, so it showed self-consistency: the answer was whatever the extractor produced.

Two changes make it a known-answer check.

**The answer is written before anything parses.** The fixture states the facts each page
carries, as data, and the layouts are three renderings of those same facts differing only in
arrangement and decoration. An extractor that reads a page differently from how the page was
built disagrees with the answer rather than defining it.

**The fixture is shown capable of failing.** Two mutant readers each violate a cited rule and
each must be caught. One takes the first text block, which [webvoyager] warns about since
position is not presence. One takes the most visually prominent element, which
[web-for-agents] warns about since the human-facing rendering is not the agent-facing
interface. A fixture that cannot detect a broken reader is not a test.

What this still does not establish: survival on real markup. Three hand-built pages are not a
corpus, and the fixture says so in its own provenance.
"""

import json
import os
from html.parser import HTMLParser
from pathlib import Path

# Ships inside the skill directory so `exercised_hash` covers it. A known-answer fixture
# kept outside that directory is load-bearing for the gate and outside the trust binding.
SKILL_DIR = Path(os.environ.get("SKILL_REGISTRY", "registry")) / os.environ["SKILL_NAME"]
FIXTURE = SKILL_DIR / "fixture.json"

data = json.loads(FIXTURE.read_text(encoding="utf-8"))
FACTS = data["facts"]
LAYOUTS = data["layouts"]


class StructuralExtractor(HTMLParser):
    """The method: target declared semantic anchors, per the cited rules."""

    def __init__(self):
        super().__init__()
        self.fields = {}
        self._current = None

    def handle_starttag(self, tag, attrs):
        self._current = dict(attrs).get("data-field")

    def handle_data(self, data):
        if self._current and data.strip():
            self.fields[self._current] = data.strip()

    def handle_endtag(self, tag):
        self._current = None


class PositionalReader(HTMLParser):
    """Mutant: first non-empty text block wins. Position treated as presence."""

    def __init__(self):
        super().__init__()
        self.first = None

    def handle_data(self, data):
        if self.first is None and data.strip():
            self.first = data.strip()


class SalienceReader(HTMLParser):
    """Mutant: the h1 is the name. Visual prominence treated as importance."""

    def __init__(self):
        super().__init__()
        self.heading = None
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        self._in_h1 = tag == "h1"

    def handle_data(self, data):
        if self._in_h1 and self.heading is None and data.strip():
            self.heading = data.strip()

    def handle_endtag(self, tag):
        if tag == "h1":
            self._in_h1 = False


def run(cls, html):
    parser = cls()
    parser.feed(html)
    return parser


# --- 1. the method reproduces the stated facts, on every layout --------------------

for layout in LAYOUTS:
    got = run(StructuralExtractor, layout["html"]).fields
    assert got == FACTS, (
        f"layout {layout['id']!r} did not yield the stated facts.\n"
        f"  expected: {FACTS}\n  actual:   {got}\n  ({layout['note']})"
    )

# invariance is the property the rules actually claim, so assert it directly rather than
# inferring it from three separate equalities
distinct = {json.dumps(run(StructuralExtractor, l["html"]).fields, sort_keys=True) for l in LAYOUTS}
assert len(distinct) == 1, f"extraction was not invariant across layouts: {distinct}"

# --- 2. the fixture can detect readers that are not invariant ---------------------

positional = [run(PositionalReader, l["html"]).first for l in LAYOUTS]
assert len(set(positional)) > 1, (
    "the positional reader agreed with itself across all layouts, so this fixture cannot "
    f"detect position being treated as presence; got {positional}"
)
assert FACTS["name"] in positional and any(v != FACTS["name"] for v in positional), (
    f"expected the positional reader to be right on one layout and wrong on another, "
    f"got {positional}"
)

salience = [run(SalienceReader, l["html"]).heading for l in LAYOUTS]
assert len(set(salience)) > 1, (
    "the salience reader agreed with itself across all layouts, so this fixture cannot "
    f"detect visual prominence being treated as importance; got {salience}"
)

# and the decoration a salience reader falls for must not be in the answer at all
for value in salience:
    if value is not None and value != FACTS["name"]:
        assert value not in FACTS.values(), (
            f"the decoy {value!r} is also a real fact, so catching the salience reader "
            f"proves nothing"
        )

print(f"  stated facts recovered from all {len(LAYOUTS)} layouts: {FACTS}")
print(f"  extraction invariant across arrangement and decoration")
print(f"  positional reader caught: {positional}")
print(f"  salience reader caught: {salience}")
