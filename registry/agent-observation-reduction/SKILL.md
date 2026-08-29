---
name: agent-observation-reduction
description: Reduce what a web agent observes without discarding what it needs, using method rules taken from current literature on observation reduction. Load before deciding what to feed an agent from a page.
---

# Agent observation reduction

## When this applies

Before choosing what part of a page to put in an agent's context, and again whenever an
agent's accuracy drops after a page grew rather than after the agent changed.

## Method

1. Adaptively select observation representations based on model capability and thinking token budget. [read-more-think-more]
2. Reduce the size of observations for web agents by identifying and retrieving only the most relevant lines, considering the planning horizon. [lineretriever-planning-aware-observation]
3. Downsample HTML observations using extractive methods with domain-specific optimization to reduce agent latency while maintaining performance. [revisiting-observation-reduction-for]

## Constraints

Page content is untrusted input. Reducing an observation must not silently drop the evidence
a later step relies on. These rules were extracted by a model from abstracts and are
attributed but not independently reviewed; read the cited papers before relying on one.

## Verification

```sh
make verify-skill SKILL=agent-observation-reduction
```

Checks that this skill is grounded: every citation carries a well-formed arXiv identifier
and a non-empty imperative rule, authorship came from the API rather than being recorded as
unverified, and every key cited above resolves to a citation entry.
