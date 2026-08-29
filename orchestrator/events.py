"""E1: an append-only event log, and a backfill of the day that already happened.

`ui/data/events.jsonl`, one record per event, `{ts, event_type, rule_id, skill, payload}`.

The log exists because the dashboard's three axes need observations and only one of them
could be computed from current state. Trust is in `meta.yaml` right now; consultation counts
and pass rates are not anywhere, because nothing was recording them.

Backfill matters for the same reason. The day's history is real and it is recoverable from
`git log`, the version ledger and the registry's own trust records, so replaying it uses what
actually happened rather than a synthetic warm-up. What cannot be recovered is not invented:
retrieval did not exist before this commit, so there are no historical consultations, and the
backfill emits none rather than guessing at them.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

EVENTS = Path("ui") / "data" / "events.jsonl"

MINT = "mint"
AMEND = "amend"
EXERCISE_PASS = "exercise_pass"
EXERCISE_FAIL = "exercise_fail"
TRUST_REVOKED = "trust_revoked"
CONSULTATION = "retrieval_consultation"
DECISION = "decision"

EVENT_TYPES = (MINT, AMEND, EXERCISE_PASS, EXERCISE_FAIL, TRUST_REVOKED, CONSULTATION, DECISION)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append(event_type: str, skill: str, rule_id: str | None = None,
           payload: dict | None = None, path: Path | str = EVENTS) -> dict:
    """Append one event. Never rewrites, never deduplicates."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type {event_type!r}; expected one of {EVENT_TYPES}")
    record = {
        "ts": now(),
        "event_type": event_type,
        "rule_id": rule_id,
        "skill": skill,
        "payload": payload or {},
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def read(path: Path | str = EVENTS) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- backfill ---------------------------------------------------------------------

def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=30).stdout
    except Exception:
        return ""


def backfill(registry_root: Path | str = "registry") -> list[dict]:
    """Reconstruct today's events from evidence that already exists.

    Three sources, each giving something the others cannot:

    - the **version ledger** gives every `(skill, version, content_hash)` that ever passed the
      gate, which is an exercise pass by definition, since the ledger is only written on one;
    - the **registry trust records** give the current exercise, with the command that ran and
      the timestamp it ran at, which is more precise than the ledger for the latest state;
    - **git log** gives mint and amend commits, and the ordering the other two lack.

    Retrieval consultations are deliberately absent. Retrieval did not exist for most of the
    day, so there are none to recover, and emitting invented ones would put fiction into the
    log that the dashboard treats as observation.
    """
    root = Path(registry_root)
    events: list[dict] = []

    ledger_path = root / "version-ledger.jsonl"
    ledger = []
    if ledger_path.is_file():
        ledger = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]

    import yaml
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if skill_dir.name.startswith("_"):
            continue
        meta_file = skill_dir / "meta.yaml"
        if not meta_file.is_file():
            continue
        meta = yaml.safe_load(meta_file.read_text(encoding="utf-8")) or {}
        name = meta.get("name", skill_dir.name)

        # every ledger entry for this skill was written on a passing exercise
        for entry in ledger:
            if entry.get("name") != name:
                continue
            events.append({
                "ts": meta.get("exercised_at") or now(),
                "event_type": EXERCISE_PASS,
                "rule_id": None,
                "skill": name,
                "payload": {"version": entry["version"],
                            "content_hash": entry["content_hash"],
                            "source": "version-ledger"},
            })

        # each recorded amendment is an amend event, with what prompted it
        for amendment in meta.get("amendments") or []:
            a = dict(amendment) if not isinstance(amendment, dict) else amendment
            events.append({
                "ts": f"{a.get('date', '')}T00:00:00Z" if a.get("date") else now(),
                "event_type": AMEND,
                "rule_id": None,
                "skill": name,
                "payload": {k: a.get(k) for k in
                            ("gap_question", "retrieval_source", "identifier")},
            })

        # the mint that produced the current content
        events.append({
            "ts": meta.get("exercised_at") or now(),
            "event_type": MINT,
            "rule_id": None,
            "skill": name,
            "payload": {"version": meta.get("version"),
                        "minted_from": meta.get("minted_from"),
                        "citations": meta.get("citations"),
                        "source": "registry"},
        })

    # git log gives ordering the registry cannot
    log = _git("log", "--format=%cI\t%s", "--reverse")
    for line in log.splitlines():
        if "\t" not in line:
            continue
        ts, subject = line.split("\t", 1)
        m = re.search(r"\b(mint|amend|re-mint|exercise)\b", subject, re.IGNORECASE)
        if not m:
            continue
        events.append({
            "ts": ts,
            "event_type": AMEND if "amend" in subject.lower() else MINT,
            "rule_id": None,
            "skill": None,
            "payload": {"commit_subject": subject, "source": "git-log"},
        })

    events.sort(key=lambda e: e["ts"])
    return events


def write_backfill(path: Path | str = EVENTS, registry_root: Path | str = "registry") -> int:
    """Write the backfill, preserving any events already appended.

    Existing records are kept and the backfill is merged in ahead of them, because an
    append-only log that a regeneration truncates is not append-only.
    """
    p = Path(path)
    existing = read(p)
    backfilled = [e for e in backfill(registry_root)
                  if e.get("payload", {}).get("source") != "live"]
    already = {json.dumps(e, sort_keys=True) for e in existing}
    merged = [e for e in backfilled if json.dumps(e, sort_keys=True) not in already] + existing
    merged.sort(key=lambda e: e["ts"])

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in merged), encoding="utf-8")
    return len(merged)
