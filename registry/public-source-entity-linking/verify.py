"""Verification for public-source-entity-linking.

Exercises the skill's own method rules rather than the surrounding pipeline. The claim
under test is [transitive-closure-collapse]: taking transitive closure over pairwise
matches lets a single false positive merge groups that share nothing, and the error
compounds rather than averaging out.

A failure here means the skill does not encode the method it cites, so it must not be
trusted to build a graph that anyone reads as fact.
"""

# Two genuinely separate organisations, plus one wrong pairwise match linking them.
# Every other match is correct.
PAIRWISE_MATCHES = [
    ("acme-1", "acme-2", 0.97),
    ("acme-2", "acme-3", 0.95),
    ("globex-1", "globex-2", 0.96),
    ("globex-2", "globex-3", 0.94),
    ("acme-3", "globex-1", 0.51),  # the false positive: one weak link, two real groups
]

CONFIDENCE_FLOOR = 0.90
TRUE_GROUPS = [{"acme-1", "acme-2", "acme-3"}, {"globex-1", "globex-2", "globex-3"}]


def cluster(matches):
    """Naive transitive closure: any path joins a cluster. The method warned against."""
    clusters = []
    for left, right, _score in matches:
        touching = [c for c in clusters if left in c or right in c]
        merged = {left, right}
        for c in touching:
            merged |= c
            clusters.remove(c)
        clusters.append(merged)
    return clusters


def cluster_verified(matches, floor):
    """Rule [transitive-closure-collapse]: a link below the floor cannot join clusters.

    Rule [linkage-uncertainty]: the score is carried into the decision rather than being
    discarded by treating every match as a boolean edge.
    """
    return cluster([m for m in matches if m[2] >= floor])


naive = cluster(PAIRWISE_MATCHES)
assert len(naive) == 1, (
    f"expected naive closure to collapse both groups into one, got {naive}; if it no "
    f"longer does, this fixture stops demonstrating why the rule exists"
)

guarded = cluster_verified(PAIRWISE_MATCHES, CONFIDENCE_FLOOR)
assert sorted(map(sorted, guarded)) == sorted(map(sorted, TRUE_GROUPS)), (
    f"verified merge must preserve the two real groups, got {guarded}"
)

print(f"  naive transitive closure collapsed {len(TRUE_GROUPS)} groups into {len(naive)}")
print(f"  verified merge preserved {len(guarded)} groups: {sorted(map(sorted, guarded))}")
