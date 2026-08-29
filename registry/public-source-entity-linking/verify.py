"""Verification for public-source-entity-linking: known answers, not a smoke test.

The earlier version of this file asserted that a naive closure collapsed two groups and a
guarded merge did not. That is a smoke test wearing a fixture: the expected answer was
authored alongside the method it checks, so it proved self-consistency. A fixture written
from the same understanding as the skill passes for the same reason the skill is wrong.

Two changes make this a known-answer check.

**The answer comes from outside the method.** Ground truth is read off a `registration`
field on each record. Two records describe the same organisation exactly when they carry the
same registration number, which is a fact stated in the data. The linking method never reads
that field; it sees only `matches`. So the expected clustering is not derivable from the
implementation under test.

**The fixture is shown to be capable of failing.** Passing a correct implementation proves
little on its own, so this also runs two mutants that violate a cited rule and asserts each
one is caught. A fixture that cannot detect a broken method is not a test, and this asserts
that it can.

What this still does not establish: accuracy on real records. It is a constructed fixture,
not a published benchmark with adjudicated labels, and it says so in its own provenance.
"""

import json
import os
from itertools import combinations
from pathlib import Path

FIXTURE = Path(os.environ.get("SKILL_FIXTURE", "fixtures/entity-linking-known-answers.json"))

data = json.loads(FIXTURE.read_text(encoding="utf-8"))
records = data["records"]
matches = data["matches"]
expected = data["expected"]

CONFIDENCE_FLOOR = 0.90


def normalise(clusters):
    return sorted(sorted(c) for c in clusters)


def union_find(ids, edges):
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for left, right in edges:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    groups = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


# --- the method under test, exactly as the skill states it -------------------------

def link_verified(records, matches, floor):
    """[transitive-closure-collapse] a link below the floor may not join clusters.
    [linkage-uncertainty] the score is carried into the decision, not discarded."""
    ids = [r["id"] for r in records]
    edges = [(m["left"], m["right"]) for m in matches if m["confidence"] >= floor]
    return union_find(ids, edges)


def comparisons_with_blocking(records):
    """[blocking-before-comparison] compare only within a block."""
    blocks = {}
    for r in records:
        blocks.setdefault(r["block"], []).append(r["id"])
    return sum(len(list(combinations(v, 2))) for v in blocks.values())


# --- mutants: each violates one cited rule and must be caught ----------------------

def mutant_naive_closure(records, matches):
    """Ignores the floor: the rule [transitive-closure-collapse] forbids exactly this."""
    ids = [r["id"] for r in records]
    return union_find(ids, [(m["left"], m["right"]) for m in matches])


def mutant_boolean_edges(records, matches):
    """Treats any match above a token threshold as equal evidence, discarding uncertainty,
    which is what [linkage-uncertainty] warns against."""
    ids = [r["id"] for r in records]
    edges = [(m["left"], m["right"]) for m in matches if m["confidence"] > 0.4]
    return union_find(ids, edges)


# --- 1. the method reproduces the independently stated answer ----------------------

actual = normalise(link_verified(records, matches, CONFIDENCE_FLOOR))
want = normalise(expected["clusters"])
assert actual == want, (
    f"method did not reproduce the known answer.\n  expected: {want}\n  actual:   {actual}"
)
assert len(actual) == expected["cluster_count"]

# ground truth really is independent: the same answer falls out of the registration field,
# which the method never reads. If these disagree the fixture is internally inconsistent.
by_registration = {}
for r in records:
    by_registration.setdefault(r["registration"], []).append(r["id"])
assert normalise(by_registration.values()) == want, (
    "the fixture's expected clusters do not match its own registration field, so the "
    "ground truth is not what it claims to be"
)

# --- 2. the fixture can detect a broken method ------------------------------------

naive = normalise(mutant_naive_closure(records, matches))
assert naive != want, (
    "the naive-closure mutant produced the correct answer, so this fixture cannot detect "
    "the failure its first cited rule is about, and passing it means nothing"
)
assert len(naive) == data["expected_under_naive_closure"]["cluster_count"], (
    f"naive closure was expected to collapse to "
    f"{data['expected_under_naive_closure']['cluster_count']} cluster(s), got {len(naive)}"
)

boolean = normalise(mutant_boolean_edges(records, matches))
assert boolean != want, (
    "the boolean-edge mutant produced the correct answer, so this fixture cannot detect "
    "uncertainty being discarded"
)

# --- 3. blocking is applied, and the saving is the stated one ----------------------

all_pairs = len(list(combinations([r["id"] for r in records], 2)))
blocked = comparisons_with_blocking(records)
assert all_pairs == data["expected_under_no_blocking"]["comparisons"], (
    f"fixture says {data['expected_under_no_blocking']['comparisons']} unblocked "
    f"comparisons, computed {all_pairs}"
)
assert blocked < all_pairs, "blocking did not reduce the comparison count"

print(f"  known answer reproduced: {len(actual)} clusters, matching the registration field")
print(f"  naive closure caught: collapses to {len(naive)} cluster(s), not {len(want)}")
print(f"  boolean-edge mutant caught: {len(boolean)} cluster(s) instead of {len(want)}")
print(f"  blocking: {blocked} comparisons instead of {all_pairs}")
