from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from system_explorer.composition_rules import (
    PIN_SCHEMA as RULE_PIN_SCHEMA,
    SCHEMA as RULE_SCHEMA,
    evaluate_cardinality,
    load_pinned_composition_rules,
)
from system_explorer.contracts import canonical_content_hash
from system_explorer.probe_receipts import import_probe_receipt
from system_explorer.stack_schema import (
    PIN_SCHEMA as STACK_PIN_SCHEMA,
    verify_pinned_stack_schema,
)
from system_explorer.store import Store


class ExternalContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_json(self, name: str, value: dict[str, object]) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return path

    def test_cardinality_rules_are_scope_aware_and_fail_closed(self) -> None:
        rules = {
            "schema": RULE_SCHEMA,
            "id": "composition-fixture",
            "version": "1.0.0",
            "scope": "template",
            "rules": [
                {
                    "scope": "dev",
                    "provider": "provider-a",
                    "function": "search",
                    "exact": 1,
                },
                {
                    "scope": "dev",
                    "provider": "provider-b",
                    "function": "index",
                    "min": 1,
                    "max": 2,
                },
            ],
        }
        rules["content_hash"] = canonical_content_hash(rules)
        source = self._write_json("rules.json", rules)
        pin = {
            "schema": RULE_PIN_SCHEMA,
            "id": "pin-composition-fixture",
            "version": "1.0.0",
            "scope": "template",
            "content_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_uri": "registry://composition/fixture",
        }
        loaded = load_pinned_composition_rules(source, pin, now=datetime(2026, 8, 13, tzinfo=timezone.utc))
        report = evaluate_cardinality(
            loaded,
            desired=[
                {"scope": "dev", "provider": "provider-a", "function": "search", "identity": "wanted"},
                {"scope": "dev", "provider": "provider-b", "function": "index", "identity": "wanted-index"},
            ],
            actual=[
                {"scope": "dev", "provider": "provider-a", "function": "search", "identity": "observed"},
                {"scope": "dev", "provider": "provider-b", "function": "index", "identity": "observed-index"},
            ],
            now=datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        self.assertEqual("verified", report["status"])
        conflict = evaluate_cardinality(
            loaded,
            actual=[
                {"scope": "dev", "provider": "provider-a", "function": "search", "identity": "one"},
                {"scope": "dev", "provider": "provider-a", "function": "search", "identity": "two"},
            ],
            now=datetime(2026, 8, 13, tzinfo=timezone.utc),
        )
        self.assertEqual("conflict", conflict["status"])
        self.assertEqual("blocked", evaluate_cardinality(None)["status"])

    def test_probe_receipt_import_is_referential_and_idempotent(self) -> None:
        source_hash = "a" * 64
        receipt: dict[str, object] = {
            "schema": "system-explorer.probe-receipt.v1",
            "receipt_id": "receipt-fixture-001",
            "version": "1.0.0",
            "source": {"id": "runner-source", "uri": "runner://fixture", "sha256": source_hash},
            "runner": {"id": "runner-fixture"},
            "task": {"id": "task-fixture"},
            "experiment": {"id": "experiment-fixture"},
            "repetitions": 2,
            "steps": [{"index": 1, "name": "entry", "status": "success"}],
            "outcome": {"status": "uncertain", "reason": "synthetic fixture"},
            "metrics": {"success_rate": 0.5, "steps_to_target": 1},
            "observed_at": "2026-08-13T10:00:00Z",
            "source_hash": source_hash,
        }
        receipt["content_hash"] = canonical_content_hash(receipt)
        path = self._write_json("receipt.json", receipt)
        with Store(self.root / "evidence.db") as store:
            first = import_probe_receipt(
                path,
                store,
                expected_source_sha256=source_hash,
                expected_runner_id="runner-fixture",
                expected_task_id="task-fixture",
                expected_experiment_id="experiment-fixture",
            )
            second = import_probe_receipt(path, store)
            rows = store.probe_receipts()
            evidence = store.evidence()
        self.assertEqual("imported", first["status"])
        self.assertEqual("unchanged", second["status"])
        self.assertEqual(1, len(rows))
        self.assertFalse(first["coverage_claim"])
        self.assertFalse(first["actual_self_claim"])
        self.assertNotIn("synthetic fixture", json.dumps(evidence))

        tampered = dict(receipt)
        tampered["source_hash"] = "b" * 64
        tampered["content_hash"] = canonical_content_hash(tampered)
        tampered_path = self._write_json("tampered.json", tampered)
        with Store(self.root / "tampered.db") as store:
            with self.assertRaisesRegex(ValueError, "source.sha256"):
                import_probe_receipt(tampered_path, store, expected_source_sha256=source_hash)

    def test_external_stack_schema_pin_reports_drift_and_success(self) -> None:
        schema_path = self._write_json(
            "stack-schema.json",
            {"schema": "ellmos.stack.v2", "version": "2.1.0", "required": ["id", "bundle_refs"]},
        )
        stack_path = self._write_json(
            "stack.json",
            {"schema": "ellmos.stack.v2", "id": "stack-fixture", "version": "2.1.0", "bundle_refs": []},
        )
        pin = {
            "schema": STACK_PIN_SCHEMA,
            "id": "stack-pin-fixture",
            "target_schema": "ellmos.stack.v2",
            "version": "2.1.0",
            "scope": "template",
            "source_uri": "registry://stack/fixture",
            "source_path": schema_path.name,
            "content_hash": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        }
        pin_path = self._write_json("stack-pin.json", pin)
        verified = verify_pinned_stack_schema(stack_path, pin_path)
        self.assertEqual("verified", verified["status"])
        schema_path.write_text("{}", encoding="utf-8")
        drifted = verify_pinned_stack_schema(stack_path, pin_path)
        self.assertEqual("blocked", drifted["status"])
        self.assertEqual("stack-schema-source-hash-mismatch", drifted["reason"])


if __name__ == "__main__":
    unittest.main()
