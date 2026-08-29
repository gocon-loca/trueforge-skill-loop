# Citations

Every method rule this skill encodes traces to a source here.

## [transitive-closure-collapse]

- Title: Entity Resolution in Practice: Lessons from a Self-Serve Pipeline
- Authors: see arXiv record; author list not verified in this dispatch
- Venue and year: arXiv preprint, 2026
- Identifier: arXiv:2607.26298
- Method rule extracted: Do not take transitive closure over pairwise matches. One false positive chains records that share nothing into a single cluster, and the error compounds rather than averaging out. Require a verified merge step before joining clusters.

## [linkage-uncertainty]

- Title: Generalized Bayesian Record Linkage and Regression with Exact Error Propagation
- Authors: see arXiv record; author list not verified in this dispatch
- Venue and year: arXiv preprint, 2018
- Identifier: arXiv:1810.04808
- Method rule extracted: Carry linkage uncertainty into the downstream conclusion rather than collapsing matches to boolean edges. A graph built from hard edges reports a confidence it never earned.

## [blocking-before-comparison]

- Title: A Survey of Blocking and Filtering Techniques for Entity Resolution
- Authors: see arXiv record; author list not verified in this dispatch
- Venue and year: arXiv preprint, 2019
- Identifier: arXiv:1905.06167
- Method rule extracted: Block candidates on a cheap key before pairwise comparison, so comparison cost stays tractable and unrelated records are never compared in the first place.
