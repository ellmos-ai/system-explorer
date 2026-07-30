from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from system_explorer.actual_self import import_actual_self_receipt
from system_explorer.contracts import with_content_hash
from system_explorer.resolution_bridge import import_resolution
from system_explorer.search_routing import resolve_search_route
from system_explorer.store import Store


FIXTURE = Path(__file__).parent / "fixtures" / "resolution.v1.json"
OBSERVED_AT = "2026-07-30T20:00:00Z"
EXPIRES_AT = "2026-07-30T22:00:00Z"
REGISTRY_HASH = "d" * 64


class SearchRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.resolution = self._resolution()
        self.resolution_path = self._write(
            "resolution.json", self.resolution
        )
        self.store = Store(self.root / "system-explorer.db")
        import_resolution(self.resolution_path, self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_exact_stable_ref_requires_native_actual_self_coverage(self) -> None:
        receipt_path = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        imported = import_actual_self_receipt(
            receipt_path,
            self.resolution,
            self.store,
            evaluated_at=OBSERVED_AT,
        )
        query = self._query(
            mode="tool-search",
            capabilities=["function.required"],
            exact_refs=["module:required-provider"],
        )

        result = resolve_search_route(query, self.resolution, self.store)

        self.assertEqual(result["selected_ref"], "module:required-provider")
        self.assertEqual(result["candidate_method"], "exact-reference")
        self.assertTrue(result["identity_verified"])
        self.assertTrue(result["availability_verified"])
        self.assertFalse(result["executable"])
        self.assertEqual(result["verification_receipt"], [imported["evidence_id"]])

    def test_declared_scanner_edge_never_proves_availability(self) -> None:
        evidence_id = self.store.add_evidence(
            uri="file:///declared/module.json",
            source_kind="ellmos.module.v2",
            sha256="a" * 64,
        )
        carrier_id = self.store.add_node(
            "carrier",
            "required-provider",
            scope=self.resolution["instance"]["instance_id"],
            metadata={
                "origin_system": "TEST-HOST",
                "actual_self": False,
            },
        )
        self.store.register_component_identity_claim(
            carrier_id=carrier_id,
            component_ref="module:required-provider",
            evidence_id=evidence_id,
            source_kind="ellmos.module.v2",
            source_id="required-provider",
        )
        self.store.add_edge(
            carrier_id,
            "carries",
            "function:function.required",
            mode="actual",
            status="declared",
            evidence_id=evidence_id,
        )
        self.store.commit()

        result = resolve_search_route(
            self._query(
                mode="tool-search",
                capabilities=["function.required"],
                exact_refs=["module:required-provider"],
            ),
            self.resolution,
            self.store,
        )

        self.assertIsNone(result["selected_ref"])
        self.assertEqual(result["result_status"], "declared-not-observed")
        self.assertFalse(result["availability_verified"])

    def test_wrong_host_and_registry_hash_are_rejected(self) -> None:
        wrong_host = self._receipt_value(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        wrong_host["scope"]["host_id"] = "FOREIGN-HOST"
        wrong_host = with_content_hash(wrong_host)
        wrong_host_path = self._write("wrong-host.json", wrong_host)
        with self.assertRaisesRegex(ValueError, "scope does not match"):
            import_actual_self_receipt(
                wrong_host_path,
                self.resolution,
                self.store,
                evaluated_at=OBSERVED_AT,
            )

        wrong_registry = self._receipt_value(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        wrong_registry["registry_binding"]["registry_content_hash"] = "e" * 64
        wrong_registry = with_content_hash(wrong_registry)
        wrong_registry_path = self._write("wrong-registry.json", wrong_registry)
        with self.assertRaisesRegex(ValueError, "registry_content_hash mismatch"):
            import_actual_self_receipt(
                wrong_registry_path,
                self.resolution,
                self.store,
                evaluated_at=OBSERVED_AT,
            )

    def test_expired_receipt_is_rejected(self) -> None:
        receipt = self._receipt_value(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        receipt["expires_at"] = "2026-07-30T20:30:00Z"
        receipt = with_content_hash(receipt)
        path = self._write("expired.json", receipt)

        with self.assertRaisesRegex(ValueError, "expired"):
            import_actual_self_receipt(
                path,
                self.resolution,
                self.store,
                evaluated_at="2026-07-30T21:00:00Z",
            )

    def test_declared_only_component_cannot_be_imported(self) -> None:
        resolution = deepcopy(self.resolution)
        component = self._component(
            resolution, "skill:recommended-provider"
        )
        component["registry_resolution"] = {
            "class": "declared-only",
            "runtime_authority": False,
            "may_satisfy_actual_coverage": False,
        }
        resolution = with_content_hash(resolution)
        path = self._receipt(
            "skill:recommended-provider",
            "skill",
            ["function.recommended"],
        )

        with self.assertRaisesRegex(ValueError, "not natively registry-bound"):
            import_actual_self_receipt(
                path,
                resolution,
                self.store,
                evaluated_at=OBSERVED_AT,
            )

    def test_name_case_and_alias_do_not_become_exact_matches(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        query = self._query(
            mode="tool-search",
            capabilities=["function.required"],
            exact_refs=["module:Required_Provider"],
        )

        result = resolve_search_route(query, self.resolution, self.store)

        self.assertEqual(result["selected_ref"], "module:required-provider")
        self.assertEqual(result["candidate_method"], "registry-capability")
        self.assertNotEqual(result["candidate_method"], "exact-reference")

    def test_semantic_and_controlcenter_rankings_use_only_stable_refs(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.shared"],
        )
        self._import_receipt(
            "software:optional-provider",
            "software_app",
            ["function.shared"],
        )
        query = self._query(
            mode="tool-search",
            capabilities=["function.shared"],
            ranked_candidates=[
                {
                    "method": "semantic-ranker",
                    "score_domain": "semantic-persona-routing.v1",
                    "candidates": [
                        {"ref": "module:required-provider", "score": 0.4},
                        {"ref": "software:optional-provider", "score": 0.9},
                    ],
                },
                {
                    "method": "controlcenter-lexical-candidate",
                    "score_domain": "controlcenter.lexical.v1",
                    "candidates": [
                        {"ref": "module:required-provider", "score": 1.0},
                        {"ref": "software:optional-provider", "score": 0.1},
                    ],
                },
            ],
        )

        result = resolve_search_route(query, self.resolution, self.store)

        self.assertEqual(result["selected_ref"], "software:optional-provider")
        self.assertEqual(result["candidate_method"], "semantic-ranker")
        self.assertEqual(result["score_domain"], "semantic-persona-routing.v1")
        self.assertTrue(result["semantic_ranker_used"])

    def test_tied_rank_is_ambiguous_and_never_executable(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.shared"],
        )
        self._import_receipt(
            "software:optional-provider",
            "software_app",
            ["function.shared"],
        )
        ranking = {
            "method": "controlcenter-lexical-candidate",
            "score_domain": "controlcenter.lexical.v1",
            "candidates": [
                {"ref": "module:required-provider", "score": 0.5},
                {"ref": "software:optional-provider", "score": 0.5},
            ],
        }

        result = resolve_search_route(
            self._query(
                mode="tool-search",
                capabilities=["function.shared"],
                ranked_candidates=[ranking],
                execution_requested=True,
            ),
            self.resolution,
            self.store,
        )

        self.assertEqual(result["result_status"], "ambiguous")
        self.assertIsNone(result["selected_ref"])
        self.assertFalse(result["executable"])

    def test_scoped_delegated_avatar_decision_can_authorize_selection(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        gate = self._delegated_gate()
        query = self._query(
            mode="tool-search",
            capabilities=["function.required"],
            exact_refs=["module:required-provider"],
            authority_gates=[gate],
            execution_requested=True,
        )

        result = resolve_search_route(query, self.resolution, self.store)

        self.assertTrue(result["executable"])
        self.assertEqual(result["authority_gates"][0]["status"], "passed")
        self.assertEqual(
            result["authority_gates"][0]["decision_ref"],
            "decision:avatar-routing-001",
        )

    def test_avatar_gate_fails_closed_on_low_confidence_conflict_or_scope(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        variants = []
        low_confidence = self._delegated_gate()
        low_confidence["confidence"] = 0.7
        variants.append(low_confidence)
        conflict = self._delegated_gate()
        conflict["conflicts"] = ["decision:conflicting-user-choice"]
        variants.append(conflict)
        out_of_scope = self._delegated_gate()
        out_of_scope["applies_to"]["component_refs"] = ["module:other-provider"]
        variants.append(out_of_scope)

        for gate in variants:
            with self.subTest(gate=gate):
                query = self._query(
                    mode="tool-search",
                    capabilities=["function.required"],
                    exact_refs=["module:required-provider"],
                    authority_gates=[gate],
                    execution_requested=True,
                )
                result = resolve_search_route(query, self.resolution, self.store)
                self.assertFalse(result["executable"])
                self.assertEqual(result["authority_gates"][0]["status"], "blocked")

    def _resolution(self) -> dict:
        value = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for bundle in value["bundles"]:
            for component in bundle["components"]:
                ref = component["ref"]
                ref = ref["ref"] if isinstance(ref, dict) else ref
                component["registry_resolution"] = {
                    "class": "native-binding",
                    "source": f"{component['type']}-registry",
                    "record_id": ref.split(":", 1)[1],
                }
        value["component_registry"] = {
            "schema": "ellmos.component-registry-bindings.v1",
            "id": "fixture-component-registry",
            "version": "1.0.0",
            "content_hash": REGISTRY_HASH,
            "activation": {},
            "source_verification": "verified",
        }
        return with_content_hash(value)

    def _receipt(
        self,
        component_ref: str,
        component_type: str,
        functions: list[str],
    ) -> Path:
        return self._write(
            component_ref.replace(":", "-") + ".actual.json",
            with_content_hash(
                self._receipt_value(component_ref, component_type, functions)
            ),
        )

    def _receipt_value(
        self,
        component_ref: str,
        component_type: str,
        functions: list[str],
    ) -> dict:
        component = self._component(self.resolution, component_ref)
        return {
            "schema": "ellmos.actual-self-component-receipt.v1",
            "receipt_id": "receipt-" + component_ref.replace(":", "-"),
            "component_ref": component_ref,
            "component_type": component_type,
            "scope": {
                "system_id": self.resolution["system"]["id"],
                "instance_id": self.resolution["instance"]["instance_id"],
                "host_id": self.resolution["instance"]["host_id"],
            },
            "registry_binding": {
                "registry_content_hash": REGISTRY_HASH,
                "source": component["registry_resolution"]["source"],
                "record_id": component["registry_resolution"]["record_id"],
            },
            "producer": {
                "ref": "access_surface:controlcenter",
                "probe_kind": "native-runtime-readback",
            },
            "observed_at": "2026-07-30T19:55:00Z",
            "expires_at": EXPIRES_AT,
            "functions": [
                {
                    "id": function,
                    "status": "observed",
                    "probe_id": "controlcenter.list-tools.v1",
                    "readback_sha256": (
                        str(index + 1) * 64
                    ),
                }
                for index, function in enumerate(functions)
            ],
        }

    def _import_receipt(
        self,
        component_ref: str,
        component_type: str,
        functions: list[str],
    ) -> None:
        import_actual_self_receipt(
            self._receipt(component_ref, component_type, functions),
            self.resolution,
            self.store,
            evaluated_at=OBSERVED_AT,
        )

    def _query(
        self,
        *,
        mode: str,
        capabilities: list[str],
        exact_refs: list[str] | None = None,
        ranked_candidates: list[dict] | None = None,
        authority_gates: list[dict] | None = None,
        execution_requested: bool = False,
    ) -> dict:
        return with_content_hash(
            {
                "schema": "ellmos.search-routing-query.v1",
                "query_id": "query-001",
                "query_mode": mode,
                "scope": self.resolution["instance"]["instance_id"],
                "required_capabilities": capabilities,
                "exact_refs": exact_refs or [],
                "ranked_candidates": ranked_candidates or [],
                "authority_gates": authority_gates or [],
                "execution_requested": execution_requested,
                "observed_at": OBSERVED_AT,
            }
        )

    def _delegated_gate(self) -> dict:
        return {
            "authority_type": "delegated-avatar-decision",
            "decision_ref": "decision:avatar-routing-001",
            "delegation_ref": "decision:D-20260730-001",
            "decision_kind": "predicted",
            "confidence": 0.96,
            "minimum_confidence": 0.9,
            "evidence_refs": ["evidence:tom-lm-prediction-001"],
            "applies_to": {
                "query_modes": ["tool-search"],
                "scopes": [self.resolution["instance"]["instance_id"]],
                "component_refs": ["module:required-provider"],
                "capabilities": ["function.required"],
            },
            "issued_at": "2026-07-30T19:00:00Z",
            "expires_at": EXPIRES_AT,
            "conflicts": [],
        }

    def _component(self, resolution: dict, ref: str) -> dict:
        for bundle in resolution["bundles"]:
            for component in bundle["components"]:
                value = component["ref"]
                value = value["ref"] if isinstance(value, dict) else value
                if value == ref:
                    return component
        raise AssertionError(f"missing component: {ref}")

    def _write(self, name: str, value: dict) -> Path:
        path = self.root / name
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
