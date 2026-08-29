import json
import tempfile
import unittest
from pathlib import Path

from pipeline.collectors import (
    ConfigError, check_target_allowed, evaluate_drift, get_collector,
    load_config, resolve_collector_id, validate_collector,
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


class ConsumerValidationTests(unittest.TestCase):
    """Every consumer validates, because these take a plain dict and can be called directly.

    Enforcing the invariant only in load_config left it assumed rather than enforced: a
    caller that skipped the loader got a ZeroDivisionError from inside evaluate_drift
    instead of a configuration error at the boundary. Found in review of PR #3.
    """

    DRIFT = {"min_records": 1, "max_missing_field_ratio": 0.25, "min_mean_field_length": 8}

    def test_evaluate_drift_rejects_empty_required_fields(self):
        """The reported case. Previously raised ZeroDivisionError."""
        with self.assertRaises(ConfigError):
            evaluate_drift({"required_fields": [], "drift": self.DRIFT}, [{"a": "b"}])

    def test_evaluate_drift_rejects_missing_keys(self):
        with self.assertRaises(ConfigError):
            evaluate_drift({"required_fields": ["url"]}, [{"url": "x"}])

    def test_check_target_allowed_rejects_malformed_collector(self):
        with self.assertRaises(ConfigError):
            check_target_allowed({"target_policy": {}}, "https://example.com")

    def test_resolve_collector_id_rejects_malformed_collector(self):
        with self.assertRaises(ConfigError):
            resolve_collector_id({"collector_id_env": "X"}, environ={"X": "c_abc"})

    def test_null_collector_is_a_config_error_not_a_type_error(self):
        """A validator that rejects by crashing gives a worse message than one that rejects."""
        with self.assertRaises(ConfigError):
            load_config(write({"version": 1, "collectors": {"x": None}}))

    def test_non_dict_collector_is_a_config_error(self):
        for bad in ("a string", ["a", "list"], 42):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    validate_collector(bad, name="x")

    def test_malformed_drift_block_is_a_config_error(self):
        collector = {
            "collector_id_env": "X", "required_fields": ["url"],
            "target_policy": {}, "drift": {"min_records": 1},
        }
        with self.assertRaises(ConfigError):
            validate_collector(collector, name="x")


if __name__ == "__main__":
    unittest.main()
