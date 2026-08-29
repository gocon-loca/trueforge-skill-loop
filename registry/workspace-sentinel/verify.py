"""Verification for workspace-sentinel.

Exercises the skill's own method rather than the surrounding machinery. The rules were
extracted from an operational record, so the strongest available check is a replay: encode
the policy, feed it the situations that actually occurred, and assert it reproduces the
decision that was actually taken.

A failure here means the skill does not encode the behaviour it was extracted from, so it
must not be trusted to coordinate anything.

Sanitised: no channel identifiers, no thread timestamps, no workspace references, no names.
Roles only.
"""

WATCHDOG_IDLE_MINUTES = 3
ESCALATE_AFTER_MINUTES = 15
DEFAULT_AFTER_MINUTES = 30


def watchdog(idle_minutes, liveness_signal, content_is_new):
    """Decide what a watchdog tick should emit.

    `liveness_signal` is one of "alive", "dead", or "unavailable". Unavailable is missing
    evidence, not evidence of failure [absent-signal-is-not-evidence].

    Crossing the idle threshold is necessary but not sufficient to escalate. Re-sending
    identical content because a timer elapsed again is noise [watchdog-on-new-information].
    """
    if liveness_signal == "unavailable":
        return "hold_signal_unavailable"
    if liveness_signal == "dead":
        return "escalate"
    if idle_minutes <= WATCHDOG_IDLE_MINUTES:
        return "hold"
    return "escalate" if content_is_new else "duration_update"


def blocked_decision(minutes_blocked, reversible, external_facing):
    """Escalate at 15, default at 30, unless the action cannot be taken back.

    Flagging once and then holding is not escalation [escalate-then-default].
    """
    if not reversible or external_facing:
        return "escalate_and_wait_indefinitely" if minutes_blocked >= ESCALATE_AFTER_MINUTES else "wait"
    if minutes_blocked >= DEFAULT_AFTER_MINUTES:
        return "apply_default"
    if minutes_blocked >= ESCALATE_AFTER_MINUTES:
        return "escalate_with_default"
    return "wait"


def relay(claim_checked_against_artifact, evidence_strength):
    """Never relay a claim that has not been checked, never confirm what cannot be evidenced.

    [verify-before-relaying], [never-confirm-without-evidence]
    """
    if not claim_checked_against_artifact:
        return "verify_first"
    if evidence_strength == "strong":
        return "relay_as_confirmed"
    return "relay_with_stated_uncertainty"


def directive_state(receipt_seen, effect_observed):
    """A receipt is not application [acknowledged-not-applied]."""
    if not receipt_seen:
        return "undelivered"
    return "applied" if effect_observed else "acknowledged_not_applied"


def tick_order(actions):
    """Read inbound before anything else on a tick [channel-read-first]."""
    return actions and actions[0] == "read_inbound"


# --- replay of situations that actually occurred -----------------------------------

# A liveness probe was unavailable rather than negative. Reporting it as death would have
# been a false alarm about a session that was working normally.
assert watchdog(6, "unavailable", True) == "hold_signal_unavailable", "absent is not negative"

# Idle threshold crossed, but the escalation would have repeated content sent 60 seconds
# earlier. A duration update carries new information; a repeat does not.
assert watchdog(5, "alive", False) == "duration_update", "a repeat is noise, not signal"
assert watchdog(5, "alive", True) == "escalate", "new information at threshold must escalate"
assert watchdog(2, "alive", True) == "hold", "below threshold is not an escalation trigger"

# A scanner raised an alert that proved to be its own false positive once checked against
# the artefact. Relaying it unchecked would have reported a boundary violation that did not
# happen.
assert relay(False, "strong") == "verify_first", "an unchecked claim is never relayed"
assert relay(True, "weak") == "relay_with_stated_uncertainty"
assert relay(True, "strong") == "relay_as_confirmed"

# A decision was flagged once and then held while the defect merged. Flagging once is not
# escalation.
assert blocked_decision(20, reversible=True, external_facing=False) == "escalate_with_default"
assert blocked_decision(35, reversible=True, external_facing=False) == "apply_default"
assert blocked_decision(5, reversible=True, external_facing=False) == "wait"

# Publishing cannot be taken back, so no elapsed time converts into permission.
for elapsed in (16, 35, 600, 86400):
    assert blocked_decision(elapsed, True, external_facing=True) == "escalate_and_wait_indefinitely", (
        f"an external-facing action must never default, elapsed={elapsed}"
    )
    assert blocked_decision(elapsed, reversible=False, external_facing=False) == "escalate_and_wait_indefinitely"

# A receipt file appeared while the directive it acknowledged remained unapplied.
assert directive_state(receipt_seen=True, effect_observed=False) == "acknowledged_not_applied"
assert directive_state(receipt_seen=True, effect_observed=True) == "applied"
assert directive_state(receipt_seen=False, effect_observed=False) == "undelivered"

# Status flowed outward for 28 minutes while the inbound channel went unread.
assert tick_order(["read_inbound", "watchdog", "post_status"]) is True
assert tick_order(["post_status", "read_inbound"]) is False, "writing before reading is the failure"

# The naive rules must actually differ from the refined ones, or this fixture stops
# demonstrating why the refinement exists.
assert watchdog(5, "alive", False) != watchdog(5, "alive", True), (
    "if new and repeated content escalate identically, the refinement is not encoded"
)
assert blocked_decision(35, True, True) != blocked_decision(35, True, False), (
    "if external-facing and internal defaults behave identically, the hold is not encoded"
)

print("  watchdog: absent signal held, repeat suppressed, new information escalated")
print("  relay: unchecked claim blocked, weak evidence relayed with stated uncertainty")
print("  blocked: escalates at 15, defaults at 30, external-facing never defaults")
print("  directive: receipt distinguished from application")
