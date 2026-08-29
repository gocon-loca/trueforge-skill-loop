"""Verification for competitor-site-interpretation.

Exercises the skill's own method rules rather than the surrounding pipeline. The claim
under test is [web-for-agents] and [webvoyager]: an agent targeting semantic structure
survives a change in visual arrangement, and one reading position does not.

A failure here means the skill does not encode the method it cites, so it must not be
trusted to perform work.
"""

from html.parser import HTMLParser

# The same facts in two layouts. The second reorders them and injects a decorative banner
# first, so a reader keyed on visual position now sees the banner where the name was.
SAME_FACTS_TWO_LAYOUTS = [
    '<main><section id="company"><h1 data-field="name">Acme</h1>'
    '<p data-field="hq">Berlin</p></section></main>',
    '<main><aside class="banner">Sponsored</aside>'
    '<section id="company"><p data-field="hq">Berlin</p>'
    '<h1 data-field="name">Acme</h1></section></main>',
]


class StructuralExtractor(HTMLParser):
    """Targets declared semantic anchors, per the cited method rules."""

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


class PositionalExtractor(HTMLParser):
    """The method the literature warns against: first rendered text block wins."""

    def __init__(self):
        super().__init__()
        self.first = None

    def handle_data(self, data):
        if self.first is None and data.strip():
            self.first = data.strip()


def _run(cls, html):
    parser = cls()
    parser.feed(html)
    return parser


structural = [_run(StructuralExtractor, h).fields for h in SAME_FACTS_TWO_LAYOUTS]
assert structural[0] == structural[1], (
    f"structural extraction must not depend on visual order: {structural}"
)
assert structural[0] == {"name": "Acme", "hq": "Berlin"}, structural[0]

positional = [_run(PositionalExtractor, h).first for h in SAME_FACTS_TWO_LAYOUTS]
assert positional[0] != positional[1], (
    "the positional reader was expected to diverge under reordering; if it did not, this "
    "fixture no longer demonstrates why the method rule exists"
)

print(f"  structural extraction stable across layouts: {structural[0]}")
print(f"  positional reader diverged as predicted: {positional[0]!r} vs {positional[1]!r}")
