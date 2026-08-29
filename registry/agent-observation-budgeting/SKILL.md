---
name: agent-observation-budgeting
description: Decide how much of an observation a running agent should carry, from its budget and its plan rather than from the page. Load before choosing what to keep when an observation will not fit.
---

# Agent observation budgeting

## When this applies

Before reducing an observation that a later step will read, and whenever an agent degrades on longer tasks rather than on harder ones, which is the signature of dropping what the plan needed.

## Method

1. Adaptively select the observation representation from the model's capability and its thinking token budget, rather than fixing one representation for every model and every step. [read-more-think-more]
2. Retrieve only the lines the current plan needs, judged against the planning horizon rather than against the page. Reducing by relevance to the page drops lines the planner still required. [lineretriever-planning-aware-observation]

## Constraints

Reduction is not compression for its own sake. These rules answer to sufficiency, keeping what the plan will need, and they can conflict with a cost objective. Where they do, the conflict is real and belongs to whoever sets the budget, not to a silent default.

## Verification

```sh
make verify-skill SKILL=agent-observation-budgeting
```

Checks grounding rather than correctness: every citation carries a well-formed identifier, a non-empty imperative rule, and a stated objective. These rules came from a live retrieval, so a person should read the cited papers before relying on one.
