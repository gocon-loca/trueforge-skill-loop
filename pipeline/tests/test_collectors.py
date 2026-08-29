import json
import tempfile
import unittest
from pathlib import Path

from pipeline.collectors import (
    ConfigError, check_target_allowed, evaluate_drift, get_collector,
    load_config, resolve_collector_id,
)

VALID = {
    "version": 1,
    "collectors": {
        "sites": {
            "collector_id_env": "TEST_COLLECTOR_ID",
            "targets": [],
            "target_policy": {"denied_hosts": ["linkedin.com"], "deny_authenticated_pages": True},
            "required_fields": ["url", "title"],
            "drift": {"min_records": 1, "max_missing_field_ratio": 0.25, "min_mean_field_length": 8},
        }
    },
}


def write(config):
    directory = tempfile.mkdtemp()
    path = Path(directory) / "collectors.json"
    path.write_text(json.dumps(config))
    return path


class ConfigTests(unittest.TestCase):
    def test_loads_valid_config(self):
        self.assertEqual(load_config(write(VALID))["version"], 1)

    def test_rejects_unsupported_version(self):
        bad = json.loads(json.dumps(VALID)); bad["version"] = 99
        with self.assertRaises(ConfigError):
            load_config(write(bad))

    def test_rejects_missing_key(self):
        bad = json.loads(json.dumps(VALID)); del bad["collectors"]["sites"]["drift"]
        with self.assertRaises(ConfigError):
            load_config(write(bad))

    def test_rejects_empty_required_fields(self):
        """No required fields means drift can never be detected, so the config is unusable."""
        bad = json.loads(json.dumps(VALID)); bad["collectors"]["sites"]["required_fields"] = []
        with self.assertRaises(ConfigError):
            load_config(write(bad))

    def test_rejects_unknown_collector(self):
        with self.assertRaises(ConfigError):
            get_collector("nope", write(VALID))

    def test_missing_env_var_is_a_config_error(self):
        with self.assertRaises(ConfigError):
            resolve_collector_id(VALID["collectors"]["sites"], environ={})

    def test_blank_env_var_is_a_config_error(self):
        with self.assertRaises(ConfigError):
            resolve_collector_id(VALID["collectors"]["sites"], environ={"TEST_COLLECTOR_ID": "   "})

    def test_resolves_env_var(self):
        got = resolve_collector_id(VALID["collectors"]["sites"], environ={"TEST_COLLECTOR_ID": "c_abc"})
        self.assertEqual(got, "c_abc")


class PolicyTests(unittest.TestCase):
    def test_allows_public_target(self):
        check_target_allowed(VALID["collectors"]["sites"], "https://example.com/product")

    def test_rejects_denied_host(self):
        with self.assertRaises(ConfigError):
            check_target_allowed(VALID["collectors"]["sites"], "https://www.linkedin.com/in/someone")

    def test_rejects_inline_credentials(self):
        with self.assertRaises(ConfigError):
            check_target_allowed(VALID["collectors"]["sites"], "https://user:pw@example.com/")


class DriftTests(unittest.TestCase):
    collector = VALID["collectors"]["sites"]

    def record(self, **overrides):
        base = {"url": "https://example.com", "title": "A sufficiently long title"}
        base.update(overrides)
        return base

    def test_healthy_scrape_has_no_signals(self):
        self.assertEqual(evaluate_drift(self.collector, [self.record()]), [])

    def test_empty_scrape_signals_drift(self):
        self.assertTrue(evaluate_drift(self.collector, []))

    def test_hollowed_records_signal_drift(self):
        """A site that changes markup returns 200 with empty fields, not an error."""
        signals = evaluate_drift(self.collector, [self.record(title=""), self.record(title="")])
        self.assertTrue(any("missing-field ratio" in s for s in signals))

    def test_truncated_fields_signal_drift(self):
        signals = evaluate_drift(self.collector, [self.record(url="x", title="y")])
        self.assertTrue(any("mean field length" in s for s in signals))


if __name__ == "__main__":
    unittest.main()
