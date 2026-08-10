from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from system_explorer.provider_hooks import (
    ProviderHookAdapter,
    ProviderHookError,
    ProviderHookPolicy,
)
from system_explorer.store import Store


class ProviderHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_hook_is_disabled_by_default_and_drops_raw_content(self) -> None:
        with Store(self.root / "disabled.db") as store:
            adapter = ProviderHookAdapter(
                "codex",
                "codex.native-hook.v1",
                store=store,
            )
            result = adapter.ingest(
                {
                    "event_kind": "call",
                    "timestamp": "2026-08-10T10:00:00Z",
                    "source_sha256": "a" * 64,
                    "prompt": "DO_NOT_LEAK_THIS_PROMPT",
                }
            )
            self.assertEqual(result["status"], "disabled")
            self.assertFalse(result["stored"])
            self.assertNotIn("DO_NOT_LEAK_THIS_PROMPT", json.dumps(result))
            self.assertEqual(store.evidence(), [])

    def test_enabled_hook_requires_consent_and_authorization(self) -> None:
        policies = (
            ProviderHookPolicy(enabled=True, authorized=True),
            ProviderHookPolicy(enabled=True, consent_granted=True),
        )
        for index, policy in enumerate(policies):
            with self.subTest(index=index), Store(self.root / f"gate-{index}.db") as store:
                adapter = ProviderHookAdapter(
                    "claude-code",
                    "claude-code.native-hook.v1",
                    policy=policy,
                    store=store,
                )
                with self.assertRaisesRegex(ProviderHookError, "consent and authorization"):
                    adapter.on_call(
                        timestamp="2026-08-10T10:00:00Z",
                        source_sha256="b" * 64,
                    )
                self.assertEqual(store.evidence(), [])

    def test_deactivation_stops_future_capture(self) -> None:
        policy = ProviderHookPolicy(
            enabled=True,
            consent_granted=True,
            authorized=True,
        )
        with Store(self.root / "deactivated.db") as store:
            adapter = ProviderHookAdapter(
                "codex",
                "codex.native-hook.v1",
                policy=policy,
                store=store,
            )
            accepted = adapter.on_call(
                timestamp="2026-08-10T10:00:00Z",
                source_sha256="f" * 64,
            )
            self.assertEqual(accepted["status"], "accepted")
            adapter.deactivate()
            disabled = adapter.ingest(
                {
                    "event_kind": "call",
                    "timestamp": "2026-08-10T10:00:01Z",
                    "source_sha256": "e" * 64,
                    "prompt": "MUST_NOT_BE_READ",
                }
            )
            self.assertEqual(disabled["status"], "disabled")
            self.assertFalse(disabled["stored"])
            self.assertEqual(len(store.evidence()), 1)
            self.assertNotIn("MUST_NOT_BE_READ", json.dumps(disabled))

    def test_call_result_and_error_remain_distinct_and_content_minimal(self) -> None:
        policy = ProviderHookPolicy(
            enabled=True,
            consent_granted=True,
            authorized=True,
            retention="P7D",
        )
        with Store(self.root / "accepted.db") as store:
            adapter = ProviderHookAdapter(
                "codex",
                "codex.native-hook.v1",
                policy=policy,
                store=store,
            )
            call = adapter.on_call(
                timestamp="2026-08-10T10:00:00Z",
                source_sha256="c" * 64,
                call_id="call-1",
            )
            result = adapter.on_result(
                timestamp="2026-08-10T10:00:01Z",
                source_sha256="d" * 64,
                readback_status="success",
                call_id="call-1",
                uncertain=False,
            )
            error = adapter.on_error(
                timestamp="2026-08-10T10:00:02Z",
                source_sha256="e" * 64,
                error_code="timeout",
                call_id="call-2",
            )

            self.assertEqual(call["event_kind"], "call")
            self.assertEqual(call["outcome"], "pending")
            self.assertEqual(call["readback_status"], "not-applicable")
            self.assertEqual(result["event_kind"], "result")
            self.assertEqual(result["outcome"], "success")
            self.assertFalse(result["uncertain"])
            self.assertEqual(error["event_kind"], "error")
            self.assertEqual(error["outcome"], "error")
            self.assertEqual(error["error_status"], "timeout")
            self.assertEqual({call["retention"], result["retention"], error["retention"]}, {"P7D"})
            self.assertEqual(len(store.evidence()), 3)
            for item in store.evidence():
                self.assertEqual(item["source_kind"], "provider-hook-event")
                self.assertTrue(item["metadata"]["redacted"])
                self.assertNotIn("prompt", item["metadata"])
                self.assertNotIn("response", item["metadata"])

    def test_malformed_or_sensitive_events_fail_without_storage_or_leak(self) -> None:
        policy = ProviderHookPolicy(enabled=True, consent_granted=True, authorized=True)
        cases = (
            ({"event_kind": "call", "timestamp": "2026-08-10T10:00:00Z", "source_sha256": "F" * 64}, "source_sha256"),
            ({"event_kind": "unknown", "timestamp": "2026-08-10T10:00:00Z", "source_sha256": "a" * 64}, "event_kind"),
            ({"event_kind": "result", "timestamp": "not-a-time", "source_sha256": "a" * 64}, "timestamp"),
            ({"event_kind": "call", "timestamp": "2026-08-10T10:00:00Z", "source_sha256": "a" * 64, "response": "PRIVATE_RESPONSE"}, "prohibited"),
        )
        with Store(self.root / "malformed.db") as store:
            adapter = ProviderHookAdapter(
                "generic",
                "generic.native-hook.v1",
                policy=policy,
                store=store,
            )
            for event, expected in cases:
                with self.subTest(expected=expected):
                    with self.assertRaises(ProviderHookError) as raised:
                        adapter.ingest(event)
                    self.assertNotIn("PRIVATE_RESPONSE", str(raised.exception))
            self.assertEqual(store.evidence(), [])


if __name__ == "__main__":
    unittest.main()
