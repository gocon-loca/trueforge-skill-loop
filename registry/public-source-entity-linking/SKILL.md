---
name: public-source-entity-linking
description: Link entities across independent public sources without letting one weak match merge unrelated groups. Load before building a graph whose edges assert that two records describe the same organisation or person.
---

# Public source entity linking

## When this applies

Before building any graph whose edges claim two records refer to the same real entity, and again whenever a new source is added to an existing graph.

## Method

1. Do not take transitive closure over pairwise matches. One false positive chains records that share nothing into a single cluster, and the error compounds rather than averaging out. Require a verified merge step before joining clusters. [transitive-closure-collapse]
2. Carry linkage uncertainty into the downstream conclusion rather than collapsing matches to boolean edges. A graph built from hard edges reports a confidence it never earned. [linkage-uncertainty]
3. Block candidates on a cheap key before pairwise comparison, so comparison cost stays tractable and unrelated records are never compared in the first place. [blocking-before-comparison]

## Constraints

Public sources only. Do not link on private contact data. An edge asserts a factual claim about real organisations, so an unverified merge is a published error, not a tuning parameter.

## Verification

```sh
make verify-skill SKILL=public-source-entity-linking
```

A pass means a single low-confidence link did not merge two groups that share nothing, which naive transitive closure does.
