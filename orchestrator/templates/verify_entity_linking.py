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
from pathlib import Path

# The fixture ships inside the skill directory, so `exercised_hash` covers it. A
# known-answer fixture kept outside that directory is load-bearing for the gate and outside
# the trust binding: the expected answer could be edited while the skill stayed trusted.
SKILL_DIR = Path(os.environ.get("SKILL_REGISTRY", "registry")) / os.environ["SKILL_NAME"]
FIXTURE = SKILL_DIR / "fixture.json"

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
    """The method, with all three rules inside it.

    [blocking-before-comparison] candidates are blocked before any pair is considered, so a
    cross-block pair is never compared. This is part of the method rather than a statistic
    computed beside it: an earlier version asserted a comparison count from a helper the
    method never called, which tested the helper.
    [transitive-closure-collapse] a link below the floor may not join clusters.
    [linkage-uncertainty] the score is carried into the decision rather than discarded.

    Returns the clusters and the number of pairs actually compared.
    """
    ids = [r["id"] for r in records]
    block_of = {r["id"]: r["block"] for r in records}

    considered = 0
    edges = []
    for m in matches:
        if block_of[m["left"]] != block_of[m["right"]]:
            continue          # blocked out: never compared
        considered += 1
        if m["confidence"] >= floor:
            edges.append((m["left"], m["right"]))
    return union_find(ids, edges), considered


def link_without_blocking(records, matches, floor):
    """Mutant: compares every pair regardless of block. Violates
    [blocking-before-comparison]."""
    ids = [r["id"] for r in records]
    considered = 0
    edges = []
    for m in matches:
        considered += 1
        if m["confidence"] >= floor:
            edges.append((m["left"], m["right"]))
    return union_find(ids, edges), considered


# --- mutants: each violates one cited rule and must be caught ----------------------

def mutant_naive_closure(records, matches):
    """Ignores the floor: the rule [transitive-closure-collapse] forbids exactly this."""
    ids = [r["id"] for r in records]
    return union_find(ids, [(m["left"], m["right"]) for m in matches])


def mutant_guessed_threshold(records, matches):
    """Substitutes a guessed cutoff for the calibrated floor, which is what
    [linkage-uncertainty] warns against: the score stops being carried into the decision and
    becomes a boolean above a number somebody picked.

    Deliberately 0.60 rather than 0.40. At 0.40 every sub-floor link is admitted and the
    result is identical to naive closure, so the two mutants would be the same mutant and
    catching one would say nothing about the other. At 0.60 exactly one wrong link is
    admitted, giving an outcome distinct from both the correct answer and naive closure.
    """
    ids = [r["id"] for r in records]
    edges = [(m["left"], m["right"]) for m in matches if m["confidence"] > 0.60]
    return union_find(ids, edges)


# --- 1. the method reproduces the independently stated answer ----------------------

clusters, compared = link_verified(records, matches, CONFIDENCE_FLOOR)
actual = normalise(clusters)
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

guessed = normalise(mutant_guessed_threshold(records, matches))
assert guessed != want, (
    "the guessed-threshold mutant produced the correct answer, so this fixture cannot "
    "detect a calibrated floor being replaced by a guess"
)
assert guessed != naive, (
    f"the guessed-threshold mutant and the naive-closure mutant produced the same result "
    f"({guessed}), so they are one mutant wearing two names and catching them both "
    f"establishes only one thing"
)

# --- 3. blocking is applied, and the saving is the stated one ----------------------

# the count comes from the method itself, not from a helper beside it
_, unblocked_compared = link_without_blocking(records, matches, CONFIDENCE_FLOOR)
assert compared < unblocked_compared, (
    f"the method compared {compared} pairs and the unblocked mutant compared "
    f"{unblocked_compared}; blocking is not reducing anything"
)
cross_block = sum(
    1 for m in matches
    if {r["id"]: r["block"] for r in records}[m["left"]]
    != {r["id"]: r["block"] for r in records}[m["right"]]
)
assert unblocked_compared - compared == cross_block, (
    f"the method should skip exactly the {cross_block} cross-block pairs, "
    f"skipped {unblocked_compared - compared}"
)
assert cross_block > 0, "no cross-block pairs in the fixture, so blocking is untested"

print(f"  known answer reproduced: {len(actual)} clusters, matching the registration field")
print(f"  naive closure caught: collapses to {len(naive)} cluster(s), not {len(want)}")
print(f"  guessed-threshold mutant caught: {len(guessed)} cluster(s), distinct from both")
print(f"  blocking inside the method: {compared} pairs compared, {cross_block} skipped")
