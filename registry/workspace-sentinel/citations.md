# Citations

Every method rule this skill encodes traces to a source here.

## [channel-read-first]

- Title: Directive queued to the shared inbox, unread for 28 minutes while status flowed outward
- Authors: companion session, operational record
- Venue and year: companion.jsonl, kind=gap, 2026
- Identifier: companion.jsonl@12:52:30 and @13:12:59
- Method rule extracted: Read the inbound channel before doing anything else on a tick. A coordination agent that writes status outward while never reading inbound has wired half a channel and will report itself healthy while directives sit unread.

## [receipt-before-processing]

- Title: Acknowledge on receipt, then answer, so the sender knows the message landed before the work is done
- Authors: companion session, operational record
- Venue and year: companion.jsonl, kind=receipt, 2026
- Identifier: companion.jsonl@14:07:07
- Method rule extracted: Acknowledge an inbound message the moment it is seen, before processing it. Silence between arrival and completed work is indistinguishable from not having received it.

## [acknowledged-not-applied]

- Title: A receipt appeared while the directive it acknowledged remained unapplied
- Authors: companion session, operational record
- Venue and year: companion.jsonl, kind=watchdog, 2026
- Identifier: companion.jsonl@13:58:16
- Method rule extracted: A delivery receipt is not application. Track directives to the observable effect they were supposed to cause, and treat acknowledged-but-not-applied as still open.

## [watchdog-on-new-information]

- Title: Idle threshold tripped and escalation was deliberately withheld because the content would have been identical
- Authors: companion session, operational record
- Venue and year: companion.jsonl, kind=watchdog, 2026
- Identifier: companion.jsonl@14:04:41
- Method rule extracted: Escalate on new information, not on a timer alone. Re-sending identical content because a threshold elapsed again is noise, and it trains the recipient to ignore the channel. Send a duration update instead of a repeat.

## [absent-signal-is-not-evidence]

- Title: A liveness signal was unavailable rather than negative, and was not treated as evidence of death
- Authors: companion session, operational record
- Venue and year: companion.jsonl, kind=watchdog, 2026
- Identifier: companion.jsonl@13:58:16
- Method rule extracted: Distinguish a signal that is absent from a signal that is negative. An unavailable liveness probe is missing evidence, not evidence of failure, and must not be reported as one.

## [verify-before-relaying]

- Title: A scanner alert was checked against the filesystem before being relayed, and proved to be its own false positive
- Authors: companion session, operational record
- Venue and year: companion.jsonl, kind=false_positive, 2026
- Identifier: companion.jsonl@13:13:51
- Method rule extracted: Verify a claim against the underlying artefact before relaying it. A case-insensitive pattern matched a lowercase commit hash and would have been reported as a boundary violation had it been passed on unchecked.

## [never-confirm-without-evidence]

- Title: An earlier conclusion was publicly corrected when its evidence turned out to be weaker than presented
- Authors: companion session, operational record
- Venue and year: companion.jsonl, kind=self_correction, 2026
- Identifier: companion.jsonl@13:58:16 and @14:01:48
- Method rule extracted: Never confirm what cannot be evidenced, and state the strength of the evidence alongside the claim. Where a conclusion survives but its basis was overstated, correct the basis rather than leaving the conclusion propped on it.

## [escalate-then-default]

- Title: Holding a merged defect after flagging it once was recorded as the wrong call
- Authors: companion session, operational record
- Venue and year: companion.jsonl, kind=escalation and kind=policy_change, 2026
- Identifier: companion.jsonl@13:23:46 and @13:25:44
- Method rule extracted: Flagging once and then holding is not escalation. Escalate a blocked decision with a stated default at 15 minutes, and apply the default at 30 unless the action is irreversible or external-facing, which waits indefinitely.
