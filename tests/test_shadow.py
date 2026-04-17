from __future__ import annotations

import json
import logging
import unittest

from app.shadow import (
    DeviceShadowSync,
    deep_merge,
    shadow_document_base,
    shadow_topics,
)


class ShadowTopicTests(unittest.TestCase):
    def test_classic_base(self) -> None:
        self.assertEqual(
            shadow_document_base("my-thing", ""),
            "$aws/things/my-thing/shadow",
        )

    def test_named_base(self) -> None:
        self.assertEqual(
            shadow_document_base("my-thing", "config"),
            "$aws/things/my-thing/shadow/name/config",
        )

    def test_topics_include_delta(self) -> None:
        t = shadow_topics("t1", "")
        self.assertIn("update/delta", t["update_delta"])
        self.assertTrue(t["get"].endswith("/get"))


class DeepMergeTests(unittest.TestCase):
    def test_nested_merge(self) -> None:
        dst: dict = {"feature_flags": {"a": True}, "thresholds": {"x": 1.0}}
        deep_merge(dst, {"feature_flags": {"b": False}, "thresholds": {"x": 2.0}})
        self.assertEqual(dst["feature_flags"]["a"], True)
        self.assertEqual(dst["feature_flags"]["b"], False)
        self.assertEqual(dst["thresholds"]["x"], 2.0)


class DeviceShadowSyncTests(unittest.TestCase):
    def test_delta_updates_interval_and_publishes_reported(self) -> None:
        log = logging.getLogger("test_shadow")
        log.addHandler(logging.NullHandler())
        published: list[tuple[str, dict]] = []

        def pub(topic: str, body: dict) -> None:
            published.append((topic, body))

        sync = DeviceShadowSync(
            thing_name="thing-1",
            shadow_name="",
            default_interval_seconds=3,
            logger=log,
        )
        sync.attach(lambda t, h: None, pub)
        topics = sync.topics
        sync._on_delta(
            topics["update_delta"],
            json.dumps({"state": {"sampling_interval_seconds": 12}}).encode(),
        )
        self.assertEqual(sync.get_runtime().sampling_interval_seconds, 12)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0][0], topics["update"])
        reported = published[0][1]["state"]["reported"]
        self.assertEqual(reported["sampling_interval_seconds"], 12)


if __name__ == "__main__":
    unittest.main()
