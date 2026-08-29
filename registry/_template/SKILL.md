---
name: skill-name-in-kebab-case
description: One sentence on what this skill does and when an agent should load it. Written so the agent can decide relevance without opening the file.
---

# Skill Name

## When this applies

The condition that should cause an agent to load this skill. Be specific. A skill that
loads for everything is a skill that helps with nothing.

## Method

The steps, in order. Each step should be checkable. Where a step encodes a method rule
taken from the literature, cite it inline by its key in `citations.md`.

## Constraints

What this skill must not do. Include the trust boundary: what input is untrusted, and what
must never be executed or followed.

## Verification

The exact command that constitutes a passing run for this skill, and what its output must
show. This is what the exercise gate runs. A skill without a checkable verification step
cannot be exercised, and therefore cannot become trusted.
