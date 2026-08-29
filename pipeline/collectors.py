#!/usr/bin/env python3
"""Versioned Bright Data collector configuration, and the drift check it declares.

Scraper behaviour lives in `config/collectors.json` rather than in ad hoc command
invocations, so a target list or a required field is reviewable in a diff and travels with
the branch that changed it.

Drift is the reason this is config and not constants. A site that changes its markup keeps
returning HTTP 200 while the records it yields quietly lose fields, so the failure is not
an exception, it is a silent decline in what the scrape captures. Detecting that is what
`evaluate_drift` does. Repairing it is the registry's job: a drifted collector revokes the
trust of the skill that reads it, and the skill re-earns trust through the exercise gate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("config/collectors.json")
SUPPORTED_VERSION = 1


class ConfigError(ValueError):
    """The collector configuration is missing, malformed, or self-contradictory."""


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"No collector configuration at {path}")
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path} is not valid JSON: {error}") from error

    version = config.get("version")
    if version != SUPPORTED_VERSION:
        raise ConfigError(f"Unsupported collector config version {version!r}, expected {SUPPORTED_VERSION}")

    collectors = config.get("collectors")
    if not isinstance(collectors, dict) or not collectors:
        raise ConfigError("Collector config declares no collectors")

    for name, collector in collectors.items():
        validate_collector(collector, name=name)
    return config


def validate_collector(collector: Any, name: str = "<collector>") -> dict[str, Any]:
    """Reject a collector that cannot be used safely, and say why.

    Called by `load_config` and again by every function that consumes a collector. The
    second call is not redundant: these are public functions taking a plain dict, so a
    caller can reach them without passing through the loader. An invariant enforced only
    at the front door is not enforced, it is assumed, and the failure then surfaces as a
    ZeroDivisionError or an AttributeError from deep inside rather than as a clear
    configuration error at the boundary.
    """
    if not isinstance(collector, dict):
        raise ConfigError(f"Collector {name!r} must be an object, got {type(collector).__name__}")
    for field in ("collector_id_env", "required_fields", "target_policy", "drift"):
        if field not in collector:
            raise ConfigError(f"Collector {name!r} is missing required key {field!r}")
    if not isinstance(collector["required_fields"], list) or not collector["required_fields"]:
        raise ConfigError(f"Collector {name!r} declares no required fields, so drift is undetectable")
    if not isinstance(collector["target_policy"], dict):
        raise ConfigError(f"Collector {name!r} has a malformed target_policy")
    drift = collector["drift"]
    if not isinstance(drift, dict):
        raise ConfigError(f"Collector {name!r} has a malformed drift block")
    for key in ("min_records", "max_missing_field_ratio", "min_mean_field_length"):
        if key not in drift:
            raise ConfigError(f"Collector {name!r} drift block is missing {key!r}")
    return collector


def get_collector(name: str, path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    collectors = load_config(path)["collectors"]
    if name not in collectors:
        raise ConfigError(f"Unknown collector {name!r}. Declared: {sorted(collectors)}")
    return collectors[name]


def resolve_collector_id(collector: dict[str, Any], environ: dict[str, str] | None = None) -> str:
    """Read the collector id from the environment. Identifiers are never committed."""
    validate_collector(collector)
    env = os.environ if environ is None else environ
    key = collector["collector_id_env"]
    value = (env.get(key) or "").strip()
    if not value:
        raise ConfigError(f"{key} is not set. Copy .env.example to .env and fill it in.")
    return value


def check_target_allowed(collector: dict[str, Any], url: str) -> None:
    """Reject a target the policy forbids, before any request is made."""
    validate_collector(collector)
    policy = collector["target_policy"]
    lowered = url.lower()
    for denied in policy.get("denied_hosts", []):
        if f"//{denied}/" in lowered or lowered.endswith(f"//{denied}") or f".{denied}/" in lowered:
            raise ConfigError(f"Target {url} is on the denied-host list ({denied})")
    if policy.get("deny_authenticated_pages", True) and "@" in lowered.split("//", 1)[-1].split("/", 1)[0]:
        raise ConfigError(f"Target {url} carries inline credentials")


def evaluate_drift(collector: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    """Return the drift signals this scrape triggered. Empty means the shape held.

    A non-empty result means the source changed shape, not that the request failed.
    """
    validate_collector(collector)
    rules = collector["drift"]
    required = collector["required_fields"]
    signals: list[str] = []

    if len(records) < rules["min_records"]:
        signals.append(f"record count {len(records)} below minimum {rules['min_records']}")
    if not records:
        return signals

    missing = sum(
        1
        for record in records
        for field in required
        if not str(record.get(field) or "").strip()
    )
    ratio = missing / (len(records) * len(required))
    if ratio > rules["max_missing_field_ratio"]:
        signals.append(f"missing-field ratio {ratio:.2f} above {rules['max_missing_field_ratio']}")

    lengths = [len(str(record.get(field) or "")) for record in records for field in required]
    mean_length = sum(lengths) / len(lengths)
    if mean_length < rules["min_mean_field_length"]:
        signals.append(f"mean field length {mean_length:.1f} below {rules['min_mean_field_length']}")

    return signals
