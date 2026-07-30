from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from system_explorer.cli import main
from system_explorer.contracts import canonical_content_hash
from system_explorer.coverage import coverage_report
from system_explorer.function_equivalence import (
    import_function_equivalence,
    reconcile_function_equivalence_projections,
)
from system_explorer.resolution_bridge import import_resolution
from system_explorer.store import Store


FIXTURE = Path(__file__).parent / "fixtures" / "resolution.v1.json"
ACTUAL_HASH = "d" * 64
DECISION_HASH = "e" * 64
DESIRED_HASH = "c" * 64
RUNTIME_HASH = "a" * 64
DECISION_URI = "decision://fixture/D-FUNCTION-EQUIVALENCE"


class FunctionEquivalenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "state" / "evidence.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _seed(
        self,
        store: Store,
        *,
        host_id: str = "TEST-HOST",
        status: str = "observed",
        identity_hash: str = ACTUAL_HASH,
        decision_evidence: bool = True,
    ) -> None:
        import_resolution(FIXTURE, store)
        identity_evidence = store.add_evidence(
            uri="file:///fixture/provider/ellmos-module.v2.json",
            source_kind="manifest",
            sha256=identity_hash,
        )
        if decision_evidence:
            store.add_evidence(
                uri=DECISION_URI,
                source_kind="document:decision",
                sha256=DECISION_HASH,
            )
        carrier = store.add_node(
            "carrier",
            "Required provider",
            node_id="carrier:observed-required-provider",
            metadata={
                "origin_system": host_id,
                "component_ref": "module:required-provider",
                "identity_status": "verified",
                "identity_source_sha256": identity_hash,
                "identity_evidence_id": identity_evidence,
                "manifest_schema": "ellmos.module.v2",
                "manifest_version": "1.0.0",
                "identity_contract_schema": "ellmos.module.v2",
                "identity_contract_version": "1.0.0",
            },
        )
        store.add_node(
            "function",
            "actual.required",
            node_id="function:actual.required",
        )
        runtime_evidence = store.add_evidence(
            uri="probe://fixture/actual.required",
            source_kind="runtime-readback",
            sha256=RUNTIME_HASH,
        )
        store.add_edge(
            carrier,
            "carries",
            "function:actual.required",
            mode="actual",
            status=status,
            evidence_id=runtime_evidence,
        )
        store.commit()

    def _contract(
        self,
        *,
        contract_id: str = "function-equivalence:fixture",
        scope: dict[str, str] | None = None,
        actual_function: str = "actual.required",
        actual_hash: str = ACTUAL_HASH,
        desired_hash: str = DESIRED_HASH,
        decision_hash: str = DECISION_HASH,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": "system-explorer.function-equivalence.v1",
            "id": contract_id,
            "version": "1.0.0",
            "status": "active",
            "scope": scope or {"kind": "template"},
            "mappings": [
                {
                    "relation": "exact-equivalence",
                    "direction": "actual-satisfies-desired",
                    "component_ref": "module:required-provider",
                    "desired_function": "function.required",
                    "actual_function": actual_function,
                    "desired_contract": {
                        "schema": "ellmos.bundle.v1",
                        "id": "fixture-core-bundle",
                        "version": "1.0.0",
                        "content_hash": desired_hash,
                    },
                    "actual_contract": {
                        "schema": "ellmos.module.v2",
                        "version": "1.0.0",
                        "content_hash": actual_hash,
                    },
                    "authority_ref": "decision:D-FUNCTION-EQUIVALENCE",
                    "evidence": [
                        {
                            "uri": DECISION_URI,
                            "sha256": decision_hash,
                            "source_kind": "document:decision",
                            "authority_ref": (
                                "decision:D-FUNCTION-EQUIVALENCE"
                            ),
                        }
                    ],
                }
            ],
            "runtime_actions": [],
            "target_mutations": [],
        }
        value["content_hash"] = canonical_content_hash(value)
        return value

    def _write(
        self, value: dict[str, object], name: str = "equivalence.json"
    ) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _required_scope(self, store: Store) -> dict[str, object]:
        report = coverage_report(store)
        required = next(
            row
            for row in report["functions"]
            if row["function"]["name"] == "function.required"
        )
        return required["desired_by_scope"][0]

    def test_template_contract_materializes_partial_equivalence(self) -> None:
        path = self._write(self._contract())
        with Store(self.db) as store:
            self._seed(store)
            before = self._required_scope(store)
            result = import_function_equivalence(path, store)
            after = self._required_scope(store)
            synthetic = [
                edge
                for edge in store.resolved_edges("actual")
                if edge.get("metadata", {}).get(
                    "function_equivalence_projection"
                )
            ]

        self.assertEqual(before["verdict"], "uncovered")
        self.assertEqual(result["status"], "imported")
        self.assertEqual(result["materialized_edges"], 1)
        self.assertEqual(result["runtime_actions"], [])
        self.assertEqual(result["target_mutations"], [])
        self.assertEqual(after["verdict"], "partial")
        self.assertEqual(after["actual_provider_edges"], 1)
        self.assertEqual(len(synthetic), 1)
        self.assertTrue(
            synthetic[0]["metadata"]["source_actual_evidence_id"]
        )
        self.assertEqual(
            len(synthetic[0]["metadata"]["mapping_evidence_ids"]), 1
        )
        self.assertNotIn("mapping_evidence", synthetic[0]["metadata"])

    def test_declared_manifest_function_never_becomes_positive_actual(self) -> None:
        path = self._write(self._contract())
        with Store(self.db) as store:
            self._seed(store, status="declared")
            result = import_function_equivalence(path, store)
            scope = self._required_scope(store)

        self.assertEqual(result["materialized_edges"], 0)
        self.assertEqual(len(result["missing_actual"]), 1)
        self.assertEqual(scope["verdict"], "uncovered")

    def test_missing_decision_evidence_fails_closed(self) -> None:
        path = self._write(self._contract())
        with Store(self.db) as store:
            self._seed(store, decision_evidence=False)
            result = import_function_equivalence(path, store)
            scope = self._required_scope(store)

        self.assertEqual(result["materialized_edges"], 0)
        self.assertEqual(len(result["missing_evidence"]), 1)
        self.assertEqual(scope["verdict"], "uncovered")

    def test_policy_authority_with_hashed_policy_evidence_is_allowed(
        self,
    ) -> None:
        policy_uri = "policy://fixture/P-FUNCTION-EQUIVALENCE"
        policy_hash = "f" * 64
        value = self._contract()
        mapping = value["mappings"][0]
        mapping["authority_ref"] = "policy:P-FUNCTION-EQUIVALENCE"
        mapping["evidence"] = [
            {
                "uri": policy_uri,
                "sha256": policy_hash,
                "source_kind": "document:policy",
                "authority_ref": "policy:P-FUNCTION-EQUIVALENCE",
            }
        ]
        value["content_hash"] = canonical_content_hash(value)
        path = self._write(value)
        with Store(self.db) as store:
            self._seed(store)
            store.add_evidence(
                uri=policy_uri,
                source_kind="document:policy",
                sha256=policy_hash,
            )
            store.commit()
            result = import_function_equivalence(path, store)
            scope = self._required_scope(store)

        self.assertEqual(result["materialized_edges"], 1)
        self.assertEqual(scope["verdict"], "partial")

    def test_authority_and_evidence_kind_must_match(self) -> None:
        value = self._contract()
        mapping = value["mappings"][0]
        mapping["authority_ref"] = "policy:P-FUNCTION-EQUIVALENCE"
        mapping["evidence"][0]["authority_ref"] = (
            "policy:P-FUNCTION-EQUIVALENCE"
        )
        value["content_hash"] = canonical_content_hash(value)
        path = self._write(value)
        with Store(self.db) as store:
            self._seed(store)
            with self.assertRaisesRegex(
                ValueError, "evidence must include evidence matching"
            ):
                import_function_equivalence(path, store)

    def test_authority_ref_must_match_the_concrete_evidence(self) -> None:
        value = self._contract()
        mapping = value["mappings"][0]
        mapping["authority_ref"] = "decision:UNRELATED"
        value["content_hash"] = canonical_content_hash(value)
        path = self._write(value)
        with Store(self.db) as store:
            self._seed(store)
            with self.assertRaisesRegex(
                ValueError, "must bind the mapping authority_ref"
            ):
                import_function_equivalence(path, store)

    def test_spoofed_identity_evidence_kind_fails_closed(self) -> None:
        path = self._write(self._contract())
        with Store(self.db) as store:
            import_resolution(FIXTURE, store)
            identity_evidence = store.add_evidence(
                uri="file:///fixture/provider/ellmos-module.v2.json",
                source_kind="document:policy",
                sha256=ACTUAL_HASH,
            )
            store.add_evidence(
                uri=DECISION_URI,
                source_kind="document:decision",
                sha256=DECISION_HASH,
            )
            carrier = store.add_node(
                "carrier",
                "Spoofed provider",
                node_id="carrier:spoofed-provider",
                metadata={
                    "origin_system": "TEST-HOST",
                    "component_ref": "module:required-provider",
                    "identity_status": "verified",
                    "identity_source_sha256": ACTUAL_HASH,
                    "identity_evidence_id": identity_evidence,
                    "identity_contract_schema": "ellmos.module.v2",
                    "identity_contract_version": "1.0.0",
                },
            )
            store.add_node(
                "function",
                "actual.required",
                node_id="function:actual.required",
            )
            runtime_evidence = store.add_evidence(
                uri="probe://fixture/actual.required",
                source_kind="runtime-readback",
                sha256=RUNTIME_HASH,
            )
            store.add_edge(
                carrier,
                "carries",
                "function:actual.required",
                mode="actual",
                status="observed",
                evidence_id=runtime_evidence,
            )
            store.commit()
            result = import_function_equivalence(path, store)

        self.assertEqual(result["materialized_edges"], 0)
        self.assertEqual(len(result["missing_actual"]), 1)

    def test_positive_status_without_native_hashed_evidence_fails_closed(
        self,
    ) -> None:
        path = self._write(self._contract())
        with Store(self.db) as store:
            self._seed(store)
            store.db.execute(
                """
                UPDATE edges
                SET evidence_id = NULL
                WHERE target_id = 'function:actual.required'
                  AND mode = 'actual'
                """
            )
            store.commit()
            result = import_function_equivalence(path, store)

        self.assertEqual(result["materialized_edges"], 0)
        self.assertEqual(len(result["missing_actual"]), 1)

    def test_wrong_host_identity_and_host_override_fail_closed(self) -> None:
        override = {
            "kind": "host-override",
            "host_id": "OTHER-HOST",
            "reason": "Synthetic negative case",
        }
        path = self._write(self._contract(scope=override))
        with Store(self.db) as store:
            self._seed(store)
            result = import_function_equivalence(path, store)
            scope = self._required_scope(store)

        self.assertEqual(result["materialized_edges"], 0)
        self.assertEqual(len(result["missing_desired"]), 1)
        self.assertEqual(scope["verdict"], "uncovered")

    def test_contract_hash_drift_is_not_approximated(self) -> None:
        path = self._write(
            self._contract(
                desired_hash="a" * 64,
                actual_hash="b" * 64,
            )
        )
        with Store(self.db) as store:
            self._seed(store)
            result = import_function_equivalence(path, store)
            scope = self._required_scope(store)

        self.assertEqual(result["materialized_edges"], 0)
        self.assertEqual(len(result["missing_desired"]), 1)
        self.assertEqual(scope["verdict"], "uncovered")

    def test_two_authorities_for_same_target_are_a_conflict(self) -> None:
        first = self._write(self._contract(), "first.json")
        second = self._write(
            self._contract(
                contract_id="function-equivalence:second-authority"
            ),
            "second.json",
        )
        with Store(self.db) as store:
            self._seed(store)
            initial = import_function_equivalence(first, store)
            conflict = import_function_equivalence(second, store)
            scope = self._required_scope(store)

        self.assertEqual(initial["materialized_edges"], 1)
        self.assertEqual(conflict["materialized_edges"], 0)
        self.assertEqual(len(conflict["conflicts"]), 1)
        self.assertEqual(scope["verdict"], "uncovered")

    def test_reconciliation_removes_unlisted_projection(self) -> None:
        path = self._write(self._contract())
        with Store(self.db) as store:
            self._seed(store)
            imported = import_function_equivalence(path, store)
            removed = reconcile_function_equivalence_projections(
                store, set()
            )
            scope = self._required_scope(store)
            claims = store.db.execute(
                "SELECT COUNT(*) FROM function_equivalence_claims"
            ).fetchone()[0]

        self.assertEqual(imported["materialized_edges"], 1)
        self.assertEqual(
            removed["removed_projections"],
            [imported["projection_key"]],
        )
        self.assertEqual(claims, 0)
        self.assertEqual(scope["verdict"], "uncovered")

    def test_no_case_or_name_alias_is_inferred(self) -> None:
        value = self._contract()
        mapping = value["mappings"][0]
        mapping["component_ref"] = "module:REQUIRED-PROVIDER"
        value["content_hash"] = canonical_content_hash(value)
        path = self._write(value)
        with Store(self.db) as store:
            self._seed(store)
            result = import_function_equivalence(path, store)
            scope = self._required_scope(store)

        self.assertEqual(result["materialized_edges"], 0)
        self.assertEqual(scope["verdict"], "uncovered")

    def test_runtime_actions_and_untyped_decision_are_rejected(self) -> None:
        for field, replacement in (
            ("runtime_actions", [{"action": "start"}]),
            ("authority_ref", "D-UNTYPED"),
        ):
            with self.subTest(field=field):
                value = self._contract()
                if field == "authority_ref":
                    value["mappings"][0][field] = replacement
                else:
                    value[field] = replacement
                value["content_hash"] = canonical_content_hash(value)
                path = self._write(value, f"{field}.json")
                with Store(self.root / f"{field}.db") as store:
                    self._seed(store)
                    with self.assertRaises(ValueError):
                        import_function_equivalence(path, store)

    def test_identical_function_ids_are_not_an_equivalence_contract(
        self,
    ) -> None:
        value = self._contract(actual_function="function.required")
        path = self._write(value)
        with Store(self.db) as store:
            self._seed(store)
            with self.assertRaisesRegex(
                ValueError, "must not restate an identical function id"
            ):
                import_function_equivalence(path, store)

    def test_stale_revision_is_ignored_and_same_generation_conflicts(
        self,
    ) -> None:
        current = self._write(self._contract(), "current.json")
        old_time = 1_700_000_000
        os.utime(current, (old_time, old_time))
        with Store(self.db) as store:
            self._seed(store)
            first = import_function_equivalence(current, store)
            newer = self._contract()
            newer["version"] = "1.0.1"
            newer["content_hash"] = canonical_content_hash(newer)
            current.write_text(json.dumps(newer), encoding="utf-8")
            os.utime(current, (old_time + 10, old_time + 10))
            second = import_function_equivalence(current, store)
            current.write_text(
                json.dumps(self._contract()), encoding="utf-8"
            )
            os.utime(current, (old_time, old_time))
            stale = import_function_equivalence(current, store)

        self.assertEqual(first["status"], "imported")
        self.assertEqual(second["status"], "imported")
        self.assertEqual(stale["status"], "stale-ignored")

    def test_same_generation_different_hash_is_rejected(self) -> None:
        path = self._write(self._contract())
        fixed_time = 1_700_000_000
        os.utime(path, (fixed_time, fixed_time))
        with Store(self.db) as store:
            self._seed(store)
            import_function_equivalence(path, store)
            changed = self._contract()
            changed["version"] = "2.0.0"
            changed["content_hash"] = canonical_content_hash(changed)
            path.write_text(json.dumps(changed), encoding="utf-8")
            os.utime(path, (fixed_time, fixed_time))
            with self.assertRaisesRegex(
                ValueError, "generation conflicts"
            ):
                import_function_equivalence(path, store)

    def test_cli_coverage_imports_then_reconciles_equivalence(self) -> None:
        contract = self._write(self._contract())
        config = self.root / "explorer.json"
        config.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                    "system": {
                        "id": "TEST-HOST",
                        "name": "Synthetic host",
                        "kind": "workstation",
                        "level": "own-system",
                    },
                }
            ),
            encoding="utf-8",
        )
        with Store(self.db) as store:
            self._seed(store)

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "coverage",
                    "--config",
                    str(config),
                    "--equivalence",
                    str(contract),
                ]
            )
        imported = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            imported["function_equivalence_imports"][0]["stats"][
                "materialized_edges"
            ],
            1,
        )

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["coverage", "--config", str(config)])
        reconciled = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            reconciled["function_equivalence_imports"][-1][
                "reconciliation"
            ]["materialized_edges"],
            0,
        )
        required = next(
            row
            for row in reconciled["functions"]
            if row["function"]["name"] == "function.required"
        )
        self.assertEqual(
            required["desired_by_scope"][0]["verdict"], "uncovered"
        )
