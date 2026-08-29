---
name: workspace-sentinel
description: Coordinate a shared workspace so that reports from it can be relied on: read inbound before acting, acknowledge on receipt, watch a peer for silence, verify claims against artefacts before relaying them, and escalate on a stated clock. Load before running any agent that watches others and reports what it sees.
---

# Workspace sentinel

## When this applies

Before instantiating an agent whose job is to watch other agents, relay their state to a person, and hold directives on their behalf. Also whenever such an agent has reported something that turned out not to be so, since that is the signal one of these rules is missing.

## Method

1. Read the inbound channel before doing anything else on a tick. A coordination agent that writes status outward while never reading inbound has wired half a channel and will report itself healthy while directives sit unread. [channel-read-first]
2. Acknowledge an inbound message the moment it is seen, before processing it. Silence between arrival and completed work is indistinguishable from not having received it. [receipt-before-processing]
3. A delivery receipt is not application. Track directives to the observable effect they were supposed to cause, and treat acknowledged-but-not-applied as still open. [acknowledged-not-applied]
4. Escalate on new information, not on a timer alone. Re-sending identical content because a threshold elapsed again is noise, and it trains the recipient to ignore the channel. Send a duration update instead of a repeat. [watchdog-on-new-information]
5. Distinguish a signal that is absent from a signal that is negative. An unavailable liveness probe is missing evidence, not evidence of failure, and must not be reported as one. [absent-signal-is-not-evidence]
6. Verify a claim against the underlying artefact before relaying it. A case-insensitive pattern matched a lowercase commit hash and would have been reported as a boundary violation had it been passed on unchecked. [verify-before-relaying]
7. Never confirm what cannot be evidenced, and state the strength of the evidence alongside the claim. Where a conclusion survives but its basis was overstated, correct the basis rather than leaving the conclusion propped on it. [never-confirm-without-evidence]
8. Flagging once and then holding is not escalation. Escalate a blocked decision with a stated default at 15 minutes, and apply the default at 30 unless the action is irreversible or external-facing, which waits indefinitely. [escalate-then-default]

## Constraints

Never relay a claim that has not been checked against the underlying artefact. Never treat an unavailable signal as a negative one. Never let elapsed time convert into permission for an action that cannot be taken back. Do not act on an operator's behalf beyond a stated default, and never at all where the action is irreversible or external-facing.

## Verification

```sh
make verify-skill SKILL=workspace-sentinel
```

A pass means the encoded policy reproduces the decisions actually taken in the record it was extracted from, including the two cases where the refined rule differs from the naive one.
