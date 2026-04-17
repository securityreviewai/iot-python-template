from __future__ import annotations

import logging
import unittest

from app.config import AppConfig
from app.shadow import ShadowDeviceConfig, validate_and_merge_state


class ShadowMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log = logging.getLogger("test_shadow")
        self.log.addHandler(logging.NullHandler())

    def test_clamps_sampling_interval(self) -> None:
        base = ShadowDeviceConfig(5, {}, {})
        merged = validate_and_merge_state(
            base,
            {"sampling_interval_seconds": 999_999},
            self.log,
        )
        self.assertEqual(merged.sampling_interval_seconds, 86_400)

    def test_allowlists_feature_flags(self) -> None:
        base = ShadowDeviceConfig(5, {}, {})
        merged = validate_and_merge_state(
            base,
            {
                "feature_flags": {
                    "advanced_metrics": True,
                    "unknown_flag": True,
                }
            },
            self.log,
        )
        self.assertTrue(merged.feature_flags.get("advanced_metrics"))
        self.assertNotIn("unknown_flag", merged.feature_flags)

    def test_allowlists_thresholds_and_rejects_bool(self) -> None:
        base = ShadowDeviceConfig(5, {}, {})
        merged = validate_and_merge_state(
            base,
            {"thresholds": {"cpu_temp_c_max": 72.5, "rogue": 1, "bad": True}},
            self.log,
        )
        self.assertEqual(merged.thresholds.get("cpu_temp_c_max"), 72.5)
        self.assertNotIn("rogue", merged.thresholds)
        self.assertNotIn("bad", merged.thresholds)

    def test_version_passthrough(self) -> None:
        base = ShadowDeviceConfig(5, {}, {}, shadow_version=1)
        merged = validate_and_merge_state(base, {"version": 42}, self.log)
        self.assertEqual(merged.shadow_version, 42)


class ShadowPathsTests(unittest.TestCase):
    def test_classic_base(self) -> None:
        from app.shadow import shadow_paths

        p = shadow_paths("my-thing", None)
        self.assertTrue(p["delta"].startswith("$aws/things/my-thing/shadow/"))
        self.assertIn("/update/delta", p["delta"])
        self.assertNotIn("/name/", p["delta"])

    def test_named_shadow_base(self) -> None:
        from app.shadow import shadow_paths

        p = shadow_paths("my-thing", "config")
        self.assertIn("/shadow/name/config/update/delta", p["delta"])


class ShadowFromAppConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        cfg = AppConfig(
            app_env="development",
            log_level="INFO",
            aws_region="us-east-1",
            iot_endpoint="",
            iot_client_id="c",
            iot_thing_name="t",
            iot_topic="devices/t/t",
            iot_cert_path="",
            iot_key_path="",
            iot_ca_path="",
            iot_shadow_name="",
            firmware_version="2.0.0",
            publish_interval_seconds=12,
            remote_config_url="",
            remote_config_poll_seconds=300,
            remote_config_request_timeout_seconds=10.0,
            remote_config_allow_insecure_http=False,
            remote_config_allowed_hosts_raw="",
            remote_config_bearer_token="",
            iot_jobs_enabled=True,
            iot_jobs_audit_topic="",
        )
        s = ShadowDeviceConfig.from_app_config(cfg)
        self.assertEqual(s.sampling_interval_seconds, 12)


if __name__ == "__main__":
    unittest.main()
