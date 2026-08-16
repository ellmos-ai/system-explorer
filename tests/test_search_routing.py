from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

from system_explorer.actual_self import (
    import_actual_self_receipt,
    validate_actual_self_receipt,
)
from system_explorer.cli import main
from system_explorer.contracts import with_content_hash
from system_explorer.receipt_trust import (
    load_receipt_trust_store,
    signed_content_hash,
    signed_payload_bytes,
)
from system_explorer.resolution_bridge import import_resolution
from system_explorer.search_authority import (
    import_search_authority_receipt,
    resolve_authority_receipts,
)
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
        self.producer_key = Ed25519PrivateKey.generate()
        self.authority_key = Ed25519PrivateKey.generate()
        self._write_public_key("producer.pem", self.producer_key)
        self._write_public_key("authority.pem", self.authority_key)
        producer_key_sha256 = hashlib.sha256(
            (self.root / "producer.pem").read_bytes()
        ).hexdigest()
        authority_key_sha256 = hashlib.sha256(
            (self.root / "authority.pem").read_bytes()
        ).hexdigest()
        trust_value = with_content_hash(
            {
                "schema": "system-explorer.receipt-trust-store.v1",
                "version": "1.0.0",
                "signers": [
                    {
                        "signer_id": "signer:controlcenter-test-host",
                        "algorithm": "ed25519",
                        "public_key_path": "producer.pem",
                        "public_key_sha256": producer_key_sha256,
                        "allowed_receipt_schemas": [
                            "ellmos.actual-self-component-receipt.v1"
                        ],
                        "allowed_actor_refs": [
                            "access_surface:controlcenter"
                        ],
                        "allowed_adapter_ids": [
                            "controlcenter.native-list-tools.v1"
                        ],
                        "allowed_host_ids": ["TEST-HOST"],
                        "allowed_authority_types": [],
                        "allowed_delegation_refs": [],
                        "max_ttl_seconds": 10800,
                    },
                    {
                        "signer_id": "signer:decision-resolver-test-host",
                        "algorithm": "ed25519",
                        "public_key_path": "authority.pem",
                        "public_key_sha256": authority_key_sha256,
                        "allowed_receipt_schemas": [
                            "ellmos.search-authority-receipt.v1"
                        ],
                        "allowed_actor_refs": [
                            "module:policy-decision-resolver"
                        ],
                        "allowed_adapter_ids": [
                            "policy-decision-resolver.native.v1"
                        ],
                        "allowed_host_ids": ["TEST-HOST"],
                        "allowed_authority_types": [
                            "direct-user-decision",
                            "policy-decision",
                            "delegated-avatar-decision",
                        ],
                        "allowed_delegation_refs": [
                            "decision:D-20260730-001"
                        ],
                        "max_ttl_seconds": 10800,
                    },
                ],
            }
        )
        self.trust_path = self._write("receipt-trust.json", trust_value)
        self.trust_file_sha256 = hashlib.sha256(
            self.trust_path.read_bytes()
        ).hexdigest()
        self.trust_store = load_receipt_trust_store(
            {
                "_base": str(self.root),
                "receipt_trust_store": self.trust_path.name,
                "receipt_trust_store_sha256": self.trust_file_sha256,
            }
        )
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
            trust_store=self.trust_store,
        )
        query = self._query(
            mode="tool-search",
            capabilities=["function.required"],
            exact_refs=["module:required-provider"],
        )

        result = resolve_search_route(
            query,
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )

        self.assertEqual(result["selected_ref"], "module:required-provider")
        self.assertEqual(result["candidate_method"], "exact-reference")
        self.assertTrue(result["identity_verified"])
        self.assertTrue(result["availability_verified"])
        self.assertFalse(result["executable"])
        self.assertEqual(result["verification_receipt"], [imported["evidence_id"]])

    def test_blocked_bundle_quarantine_cannot_import_or_execute_provider(
        self,
    ) -> None:
        blocked = deepcopy(self.resolution)
        component = self._component(blocked, "module:required-provider")
        component["activation_quarantine"] = {
            "reason": "bundle-has-required-declared-only-components",
            "declared_desired_status": component["desired_status"],
            "declared_provides": list(component["provides"]),
        }
        component["desired_status"] = "unavailable"
        component["provides"] = []
        blocked["functions"] = [
            function
            for function in blocked["functions"]
            if function != "function.required"
        ]
        blocked["component_registry"]["activation"] = {
            "fixture-core-bundle": {
                "state": "blocked",
                "required_unresolved": ["module:planned"],
                "recommended_unresolved": [],
                "optional_unresolved": [],
                "quarantined": True,
            }
        }
        blocked["component_registry"]["activation_enforcement"] = (
            "blocked-evidence-only"
        )
        blocked = with_content_hash(blocked)
        receipt_path = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-quarantined",
        )

        with self.assertRaisesRegex(ValueError, "is not provided"):
            import_actual_self_receipt(
                receipt_path,
                blocked,
                self.store,
                evaluated_at=OBSERVED_AT,
                trust_store=self.trust_store,
            )

        with self.assertRaisesRegex(ValueError, "not in the resolution"):
            resolve_search_route(
                self._query(
                    mode="tool-search",
                    capabilities=["function.required"],
                    exact_refs=["module:required-provider"],
                    execution_requested=True,
                ),
                blocked,
                self.store,
                trust_store=self.trust_store,
            )

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
            trust_store=self.trust_store,
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
        wrong_host = self._sign(
            wrong_host,
            self.producer_key,
            "signer:controlcenter-test-host",
        )
        wrong_host_path = self._write("wrong-host.json", wrong_host)
        with self.assertRaisesRegex(ValueError, "scope does not match"):
            import_actual_self_receipt(
                wrong_host_path,
                self.resolution,
                self.store,
                evaluated_at=OBSERVED_AT,
                trust_store=self.trust_store,
            )

        wrong_registry = self._receipt_value(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        wrong_registry["registry_binding"]["registry_content_hash"] = "e" * 64
        wrong_registry = self._sign(
            wrong_registry,
            self.producer_key,
            "signer:controlcenter-test-host",
        )
        wrong_registry_path = self._write("wrong-registry.json", wrong_registry)
        with self.assertRaisesRegex(ValueError, "registry_content_hash mismatch"):
            import_actual_self_receipt(
                wrong_registry_path,
                self.resolution,
                self.store,
                evaluated_at=OBSERVED_AT,
                trust_store=self.trust_store,
            )

    def test_shared_receipt_validator_rejects_untyped_refs_and_uppercase_hashes(self) -> None:
        untyped = self._receipt_value(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        untyped["component_ref"] = "required-provider"
        untyped = self._sign(
            untyped,
            self.producer_key,
            "signer:controlcenter-test-host",
        )
        with self.assertRaisesRegex(ValueError, "stable typed reference"):
            validate_actual_self_receipt(
                untyped,
                self.resolution,
                evaluated_at=OBSERVED_AT,
                trust_store=self.trust_store,
            )

        uppercase = self._receipt_value(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        uppercase["registry_binding"]["registry_content_hash"] = "A" * 64
        uppercase = self._sign(
            uppercase,
            self.producer_key,
            "signer:controlcenter-test-host",
        )
        with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
            validate_actual_self_receipt(
                uppercase,
                self.resolution,
                evaluated_at=OBSERVED_AT,
                trust_store=self.trust_store,
            )

    def test_expired_receipt_is_rejected(self) -> None:
        receipt = self._receipt_value(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        receipt["expires_at"] = "2026-07-30T20:30:00Z"
        receipt = self._sign(
            receipt,
            self.producer_key,
            "signer:controlcenter-test-host",
        )
        path = self._write("expired.json", receipt)

        with self.assertRaisesRegex(ValueError, "expired"):
            import_actual_self_receipt(
                path,
                self.resolution,
                self.store,
                evaluated_at="2026-07-30T21:00:00Z",
                trust_store=self.trust_store,
            )

    def test_expiry_is_bound_to_each_function_edge_not_latest_carrier(self) -> None:
        first = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-required",
            expires_at="2026-07-30T20:30:00Z",
        )
        import_actual_self_receipt(
            first,
            self.resolution,
            self.store,
            evaluated_at=OBSERVED_AT,
            trust_store=self.trust_store,
        )
        second = self._receipt(
            "module:required-provider",
            "module",
            ["function.shared"],
            suffix="-shared",
            expires_at=EXPIRES_AT,
        )
        import_actual_self_receipt(
            second,
            self.resolution,
            self.store,
            evaluated_at=OBSERVED_AT,
            trust_store=self.trust_store,
        )

        result = resolve_search_route(
            self._query(
                mode="tool-search",
                capabilities=["function.required"],
                exact_refs=["module:required-provider"],
                observed_at="2026-07-30T21:00:00Z",
            ),
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )

        self.assertIsNone(result["selected_ref"])
        self.assertEqual(result["result_status"], "declared-not-observed")
        candidate = next(
            item
            for item in result["candidates"]
            if item["ref"] == "module:required-provider"
        )
        self.assertIn(
            "actual-self-receipt-expired",
            candidate["rejection_reasons"],
        )

    def test_untrusted_or_tampered_producer_receipt_is_rejected(self) -> None:
        untrusted_key = Ed25519PrivateKey.generate()
        untrusted = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-untrusted",
            private_key=untrusted_key,
            signer_id="signer:forged",
        )
        with self.assertRaisesRegex(ValueError, "not in the configured trust store"):
            import_actual_self_receipt(
                untrusted,
                self.resolution,
                self.store,
                evaluated_at=OBSERVED_AT,
                trust_store=self.trust_store,
            )

    def test_store_metadata_flags_cannot_spoof_receipt_signatures(self) -> None:
        evidence_id = self.store.add_evidence(
            uri="actual-self://TEST-HOST/module%3Arequired-provider",
            source_kind="actual-self-native-receipt",
            sha256="a" * 64,
            effective_at="2026-07-30T19:55:00Z",
            metadata={
                "signature_verified": True,
                "receipt_id": "receipt-forged",
                "producer_signer_id": "signer:controlcenter-test-host",
                "trust_store_content_hash": self.trust_store.content_hash,
            },
        )
        carrier_id = self.store.add_node(
            "carrier",
            "module:required-provider",
            scope=self.resolution["instance"]["instance_id"],
            metadata={
                "origin_system": "TEST-HOST",
                "actual_self": True,
            },
        )
        self.store.register_component_identity_claim(
            carrier_id=carrier_id,
            component_ref="module:required-provider",
            evidence_id=evidence_id,
            source_kind="actual-self-native-receipt",
            source_id="required-provider",
        )
        self.store.add_edge(
            carrier_id,
            "carries",
            "function:function.required",
            mode="actual",
            status="observed",
            evidence_id=evidence_id,
            metadata={
                "receipt_id": "receipt-forged",
                "probe_id": "forged",
                "readback_sha256": "b" * 64,
                "producer_signer_id": "signer:controlcenter-test-host",
                "signature_verified": True,
                "trust_store_content_hash": self.trust_store.content_hash,
                "expires_at": EXPIRES_AT,
            },
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
            trust_store=self.trust_store,
        )
        self.assertIsNone(result["selected_ref"])
        self.assertIn(
            "actual-self-receipt-reverification-failed",
            result["candidates"][0]["rejection_reasons"],
        )

        self.store.add_evidence(
            uri="search-authority://TEST-HOST/authority%3Aforged-store",
            source_kind="search-authority-receipt",
            sha256="c" * 64,
            effective_at="2026-07-30T19:00:00Z",
            metadata={
                "signature_verified": True,
                "receipt_ref": "authority:forged-store",
                "issued_at": "2026-07-30T19:00:00Z",
                "expires_at": EXPIRES_AT,
                "host_id": "TEST-HOST",
                "authority_type": "delegated-avatar-decision",
                "decision_ref": "decision:FORGED",
                "delegation_ref": "decision:D-20260730-001",
                "confidence": 1.0,
                "minimum_confidence": 0.0,
                "scope": {
                    "query_modes": ["tool-search"],
                    "system_instance_ids": [
                        self.resolution["instance"]["instance_id"]
                    ],
                    "host_ids": ["TEST-HOST"],
                    "component_refs": ["module:required-provider"],
                    "capabilities": ["function.required"],
                },
                "conflicts": [],
            },
        )
        self.store.commit()
        gate_results = resolve_search_route(
            self._query(
                mode="tool-search",
                capabilities=["function.required"],
                authority_receipt_refs=["authority:forged-store"],
                execution_requested=True,
            ),
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )
        self.assertFalse(gate_results["executable"])
        self.assertEqual(
            gate_results["authority_gates"][0]["status"],
            "blocked",
        )
        self.assertIn(
            "authority-receipt-reverification-failed",
            gate_results["authority_gates"][0]["reasons"],
        )

        tampered = json.loads(
            self._receipt(
                "module:required-provider",
                "module",
                ["function.required"],
                suffix="-tampered",
            ).read_text(encoding="utf-8")
        )
        tampered["functions"][0]["readback_sha256"] = "9" * 64
        tampered_path = self._write("tampered.json", tampered)
        with self.assertRaisesRegex(
            ValueError,
            "content_hash mismatch|signature verification failed",
        ):
            import_actual_self_receipt(
                tampered_path,
                self.resolution,
                self.store,
                evaluated_at=OBSERVED_AT,
                trust_store=self.trust_store,
            )

    def test_producer_receipt_ttl_is_bounded_by_trust_policy(self) -> None:
        path = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-long-ttl",
            expires_at="2026-07-31T01:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "max_ttl_seconds"):
            import_actual_self_receipt(
                path,
                self.resolution,
                self.store,
                evaluated_at=OBSERVED_AT,
                trust_store=self.trust_store,
            )

    def test_trust_store_requires_external_config_fingerprint(self) -> None:
        with self.assertRaisesRegex(ValueError, "configured SHA-256 pin"):
            load_receipt_trust_store(
                {
                    "_base": str(self.root),
                    "receipt_trust_store": self.trust_path.name,
                    "receipt_trust_store_sha256": "0" * 64,
                }
            )
        with self.assertRaisesRegex(ValueError, "must pin"):
            load_receipt_trust_store(
                {
                    "_base": str(self.root),
                    "receipt_trust_store": self.trust_path.name,
                }
            )

    def test_public_key_swap_does_not_bypass_trust_store_pin(self) -> None:
        key_path = self.root / "producer.pem"
        original = key_path.read_bytes()
        attacker = Ed25519PrivateKey.generate()
        key_path.write_bytes(
            attacker.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        forged = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-key-swap",
            private_key=attacker,
            signer_id="signer:controlcenter-test-host",
        )
        try:
            with self.assertRaisesRegex(ValueError, "public key.*SHA-256 pin"):
                import_actual_self_receipt(
                    forged,
                    self.resolution,
                    self.store,
                    evaluated_at=OBSERVED_AT,
                    trust_store=self.trust_store,
                )
        finally:
            key_path.write_bytes(original)

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
                trust_store=self.trust_store,
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

        result = resolve_search_route(
            query,
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )

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

        result = resolve_search_route(
            query,
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )

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
            trust_store=self.trust_store,
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
        authority_path, authority_ref = self._authority_receipt()
        import_search_authority_receipt(
            authority_path,
            self.store,
            evaluated_at=OBSERVED_AT,
            expected_host_id="TEST-HOST",
            trust_store=self.trust_store,
        )
        query = self._query(
            mode="tool-search",
            capabilities=["function.required"],
            exact_refs=["module:required-provider"],
            authority_receipt_refs=[authority_ref],
            execution_requested=True,
        )

        result = resolve_search_route(
            query,
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )

        self.assertTrue(result["executable"])
        self.assertEqual(result["authority_gates"][0]["status"], "passed")
        self.assertEqual(
            result["authority_gates"][0]["decision_ref"],
            "decision:avatar-routing-001",
        )

    def test_authority_evidence_requires_local_hash_source_and_no_partial_import(self) -> None:
        cases = ("missing", "hash-mismatch", "external")
        for case in cases:
            with self.subTest(case=case):
                authority_path, _ = self._authority_receipt(
                    suffix=f"-evidence-{case}"
                )
                value = json.loads(authority_path.read_text(encoding="utf-8"))
                ref = value["evidence"][0]["ref"]
                if case == "missing":
                    self.store.db.execute(
                        "DELETE FROM evidence WHERE uri = ?", (ref,)
                    )
                    self.store.commit()
                elif case == "hash-mismatch":
                    value["evidence"][0]["sha256"] = "9" * 64
                    authority_path = self._write(
                        f"authority-evidence-{case}.json",
                        self._sign(value, self.authority_key, value["issuer"]["signer_id"]),
                    )
                else:
                    row = self.store.db.execute(
                        "SELECT id, metadata_json FROM evidence WHERE uri = ?",
                        (ref,),
                    ).fetchone()
                    metadata = json.loads(row["metadata_json"])
                    metadata["external"] = True
                    self.store.db.execute(
                        "UPDATE evidence SET metadata_json = ? WHERE id = ?",
                        (json.dumps(metadata), row["id"]),
                    )
                    self.store.commit()
                before = self.store.evidence()
                before_commits = self.store.commit_count
                with self.assertRaisesRegex(ValueError, r"evidence\[0\]"):
                    import_search_authority_receipt(
                        authority_path,
                        self.store,
                        evaluated_at=OBSERVED_AT,
                        expected_host_id="TEST-HOST",
                        trust_store=self.trust_store,
                    )
                self.assertEqual(self.store.evidence(), before)
                self.assertEqual(self.store.commit_count, before_commits)

    def test_authority_resolver_rechecks_local_evidence_after_import(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        authority_path, authority_ref = self._authority_receipt(
            suffix="-reverification"
        )
        import_search_authority_receipt(
            authority_path,
            self.store,
            evaluated_at=OBSERVED_AT,
            expected_host_id="TEST-HOST",
            trust_store=self.trust_store,
        )
        value = json.loads(authority_path.read_text(encoding="utf-8"))
        self.store.db.execute(
            "DELETE FROM evidence WHERE uri = ?",
            (value["evidence"][0]["ref"],),
        )
        self.store.commit()
        gates = resolve_authority_receipts(
            self.store,
            [authority_ref],
            query_mode="tool-search",
            scope=self.resolution["instance"]["instance_id"],
            component_ref="module:required-provider",
            capabilities=["function.required"],
            observed_at=OBSERVED_AT,
            trust_store=self.trust_store,
            expected_host_id="TEST-HOST",
        )
        self.assertEqual(gates[0]["status"], "blocked")
        self.assertEqual(
            gates[0]["reasons"],
            ["authority-receipt-reverification-failed"],
        )

    def test_avatar_gate_fails_closed_on_low_confidence_conflict_or_scope(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        variants = [
            {"confidence": 0.7},
            {
                "conflicts": [
                    {
                        "ref": "decision:conflicting-user-choice",
                        "sha256": "8" * 64,
                    }
                ]
            },
            {"component_refs": ["module:other-provider"]},
        ]

        for index, override in enumerate(variants):
            with self.subTest(override=override):
                authority_path, authority_ref = self._authority_receipt(
                    suffix=str(index),
                    **override,
                )
                import_search_authority_receipt(
                    authority_path,
                    self.store,
                    evaluated_at=OBSERVED_AT,
                    expected_host_id="TEST-HOST",
                    trust_store=self.trust_store,
                )
                query = self._query(
                    mode="tool-search",
                    capabilities=["function.required"],
                    exact_refs=["module:required-provider"],
                    authority_receipt_refs=[authority_ref],
                    execution_requested=True,
                )
                result = resolve_search_route(
                    query,
                    self.resolution,
                    self.store,
                    trust_store=self.trust_store,
                )
                self.assertFalse(result["executable"])
                self.assertEqual(result["authority_gates"][0]["status"], "blocked")

    def test_forged_delegation_or_missing_authority_receipt_fails_closed(self) -> None:
        forged_path, _ = self._authority_receipt(
            suffix="-forged",
            delegation_ref="decision:FORGED-NOT-D-20260730-001",
        )
        with self.assertRaisesRegex(ValueError, "delegation ref is not allowed"):
            import_search_authority_receipt(
                forged_path,
                self.store,
                evaluated_at=OBSERVED_AT,
                expected_host_id="TEST-HOST",
                trust_store=self.trust_store,
            )

        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        result = resolve_search_route(
            self._query(
                mode="tool-search",
                capabilities=["function.required"],
                exact_refs=["module:required-provider"],
                authority_receipt_refs=["authority:not-imported"],
                execution_requested=True,
            ),
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )
        self.assertFalse(result["executable"])
        self.assertEqual(result["authority_gates"][0]["status"], "blocked")
        self.assertEqual(
            result["authority_gates"][0]["reasons"],
            ["authority-receipt-not-found"],
        )

    def test_authority_receipt_cannot_be_reused_across_hosts(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        trust_value = json.loads(self.trust_path.read_text(encoding="utf-8"))
        trust_value.pop("content_hash")
        authority_signer = next(
            signer
            for signer in trust_value["signers"]
            if signer["signer_id"] == "signer:decision-resolver-test-host"
        )
        authority_signer["allowed_host_ids"] = ["TEST-HOST", "FOREIGN-HOST"]
        multi_host_path = self._write(
            "multi-host-receipt-trust.json",
            with_content_hash(trust_value),
        )
        multi_host_store = load_receipt_trust_store(
            {
                "_base": str(self.root),
                "receipt_trust_store": multi_host_path.name,
                "receipt_trust_store_sha256": hashlib.sha256(
                    multi_host_path.read_bytes()
                ).hexdigest(),
            }
        )
        authority_path, authority_ref = self._authority_receipt(
            suffix="-foreign-host",
            issuer_host_id="FOREIGN-HOST",
        )
        import_search_authority_receipt(
            authority_path,
            self.store,
            evaluated_at=OBSERVED_AT,
            expected_host_id="FOREIGN-HOST",
            trust_store=multi_host_store,
        )

        result = resolve_search_route(
            self._query(
                mode="tool-search",
                capabilities=["function.required"],
                exact_refs=["module:required-provider"],
                authority_receipt_refs=[authority_ref],
                execution_requested=True,
            ),
            self.resolution,
            self.store,
            trust_store=multi_host_store,
        )

        self.assertFalse(result["executable"])
        self.assertEqual(result["authority_gates"][0]["status"], "blocked")
        self.assertEqual(
            result["authority_gates"][0]["reasons"],
            ["authority-receipt-reverification-failed"],
        )

    def test_authority_revision_order_uses_parsed_utc_not_iso_text(self) -> None:
        self._import_receipt(
            "module:required-provider",
            "module",
            ["function.required"],
        )
        receipt_ref = "authority:offset-conflict"
        first_path, _ = self._authority_receipt(
            suffix="-offset-a",
            receipt_ref=receipt_ref,
            issued_at="2026-07-30T19:00:00Z",
            expires_at="2026-07-30T22:00:00Z",
            confidence=0.96,
        )
        second_path, _ = self._authority_receipt(
            suffix="-offset-b",
            receipt_ref=receipt_ref,
            issued_at="2026-07-30T21:00:00+02:00",
            expires_at="2026-07-31T00:00:00+02:00",
            confidence=0.95,
        )
        for path in (first_path, second_path):
            import_search_authority_receipt(
                path,
                self.store,
                evaluated_at=OBSERVED_AT,
                expected_host_id="TEST-HOST",
                trust_store=self.trust_store,
            )

        result = resolve_search_route(
            self._query(
                mode="tool-search",
                capabilities=["function.required"],
                exact_refs=["module:required-provider"],
                authority_receipt_refs=[receipt_ref],
                execution_requested=True,
            ),
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )

        self.assertFalse(result["executable"])
        self.assertEqual(
            result["authority_gates"][0]["reasons"],
            ["authority-receipt-revision-conflict"],
        )

    def test_cli_end_to_end_and_forged_receipts_fail_closed(self) -> None:
        config_path = self._write(
            "cli-config.json",
            {
                "schema": "system-explorer.config.v1",
                "database": str(self.root / "cli.db"),
                "receipt_trust_store": self.trust_path.name,
                "receipt_trust_store_sha256": self.trust_file_sha256,
                "roots": [],
            },
        )
        actual_path = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-cli",
        )
        authority_path, authority_ref = self._authority_receipt(suffix="-cli")
        with Store(self.root / "cli.db") as cli_store:
            authority_value = json.loads(
                authority_path.read_text(encoding="utf-8")
            )
            for evidence in [
                *authority_value["evidence"],
                *authority_value["conflicts"],
            ]:
                cli_store.add_evidence(
                    uri=evidence["ref"],
                    source_kind="document:decision",
                    sha256=evidence["sha256"],
                    locator=evidence["ref"],
                    metadata={"evidence_ref": evidence["ref"]},
                )
            cli_store.commit()
        query_path = self._write(
            "cli-query.json",
            self._query(
                mode="tool-search",
                capabilities=["function.required"],
                exact_refs=["module:required-provider"],
                authority_receipt_refs=[authority_ref],
                execution_requested=True,
            ),
        )
        output_path = self.root / "cli-search-receipt.json"

        result = main(
            [
                "search-route",
                str(query_path),
                "--resolution",
                str(self.resolution_path),
                "--actual-self",
                str(actual_path),
                "--authority-receipt",
                str(authority_path),
                "--config",
                str(config_path),
                "--output",
                str(output_path),
            ]
        )

        self.assertEqual(result, 0)
        output = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertTrue(output["executable"])
        self.assertEqual(output["selected_ref"], "module:required-provider")

        arbitrary = self._receipt_value(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-arbitrary",
        )
        arbitrary_path = self._write("arbitrary-unsigned.json", arbitrary)
        self.assertNotEqual(
            main(
                [
                    "import-actual-self",
                    str(arbitrary_path),
                    "--resolution",
                    str(self.resolution_path),
                    "--config",
                    str(config_path),
                    "--evaluated-at",
                    OBSERVED_AT,
                ]
            ),
            0,
        )

        with Store(self.root / "cli.db") as cli_store:
            before_repeat = {
                "evidence": sorted(item["id"] for item in cli_store.evidence()),
                "nodes": sorted(item["id"] for item in cli_store.nodes()),
                "edges": [
                    row[0]
                    for row in cli_store.db.execute(
                        "SELECT id FROM edges ORDER BY id"
                    )
                ],
            }
        self.assertEqual(result, 0)
        self.assertEqual(
            main(
                [
                    "search-route",
                    str(query_path),
                    "--resolution",
                    str(self.resolution_path),
                    "--actual-self",
                    str(actual_path),
                    "--authority-receipt",
                    str(authority_path),
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_path),
                ]
            ),
            0,
        )
        with Store(self.root / "cli.db") as cli_store:
            after_repeat = {
                "evidence": sorted(item["id"] for item in cli_store.evidence()),
                "nodes": sorted(item["id"] for item in cli_store.nodes()),
                "edges": [
                    row[0]
                    for row in cli_store.db.execute(
                        "SELECT id FROM edges ORDER BY id"
                    )
                ],
            }
        self.assertEqual(after_repeat, before_repeat)

    def test_cli_search_route_rolls_back_all_prior_imports_on_later_failure(self) -> None:
        config_path = self._write(
            "cli-atomic-config.json",
            {
                "schema": "system-explorer.config.v1",
                "database": str(self.root / "cli-atomic.db"),
                "receipt_trust_store": self.trust_path.name,
                "receipt_trust_store_sha256": self.trust_file_sha256,
                "roots": [],
            },
        )
        actual_path = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-atomic",
        )
        authority_path, authority_ref = self._authority_receipt(
            suffix="-atomic-invalid",
            delegation_ref="decision:FORGED",
        )
        authority_value = json.loads(authority_path.read_text(encoding="utf-8"))
        with Store(self.root / "cli-atomic.db") as cli_store:
            for evidence in [
                *authority_value["evidence"],
                *authority_value["conflicts"],
            ]:
                cli_store.add_evidence(
                    uri=evidence["ref"],
                    source_kind="document:decision",
                    sha256=evidence["sha256"],
                    locator=evidence["ref"],
                    metadata={"evidence_ref": evidence["ref"]},
                )
            cli_store.commit()
        query_path = self._write(
            "cli-atomic-query.json",
            self._query(
                mode="tool-search",
                capabilities=["function.required"],
                exact_refs=["module:required-provider"],
                authority_receipt_refs=[authority_ref],
                execution_requested=True,
            ),
        )
        output_path = self.root / "cli-atomic-search-receipt.json"
        with Store(self.root / "cli-atomic.db") as cli_store:
            before = {
                table: [
                    tuple(row)
                    for row in cli_store.db.execute(
                        f"SELECT * FROM {table} ORDER BY 1"
                    )
                ]
                for table in (
                    "evidence",
                    "nodes",
                    "edges",
                    "component_identity_claims",
                )
            }

        result = main(
            [
                "search-route",
                str(query_path),
                "--resolution",
                str(self.resolution_path),
                "--actual-self",
                str(actual_path),
                "--authority-receipt",
                str(authority_path),
                "--config",
                str(config_path),
                "--output",
                str(output_path),
            ]
        )
        self.assertNotEqual(result, 0)
        self.assertFalse(output_path.exists())
        with Store(self.root / "cli-atomic.db") as cli_store:
            after = {
                table: [
                    tuple(row)
                    for row in cli_store.db.execute(
                        f"SELECT * FROM {table} ORDER BY 1"
                    )
                ]
                for table in (
                    "evidence",
                    "nodes",
                    "edges",
                    "component_identity_claims",
                )
            }
        self.assertEqual(after, before)

        forged_path, _ = self._authority_receipt(
            suffix="-cli-forged",
            delegation_ref="decision:FORGED",
        )
        self.assertNotEqual(
            main(
                [
                    "import-search-authority",
                    str(forged_path),
                    "--resolution",
                    str(self.resolution_path),
                    "--config",
                    str(config_path),
                    "--evaluated-at",
                    OBSERVED_AT,
                ]
            ),
            0,
        )

    def test_public_search_receipt_schemas_validate_real_values(self) -> None:
        schema_root = Path(__file__).resolve().parents[1] / "schemas"
        schema_names = [
            "ellmos.actual-self-component-receipt.v1.schema.json",
            "ellmos.search-authority-receipt.v1.schema.json",
            "ellmos.search-routing-query.v1.schema.json",
            "ellmos.search-routing-receipt.v1.schema.json",
            "system-explorer.receipt-trust-store.v1.schema.json",
        ]
        schemas = {
            name: json.loads((schema_root / name).read_text(encoding="utf-8"))
            for name in schema_names
        }
        for schema in schemas.values():
            Draft202012Validator.check_schema(schema)

        actual_path = self._receipt(
            "module:required-provider",
            "module",
            ["function.required"],
            suffix="-schema",
        )
        actual = json.loads(actual_path.read_text(encoding="utf-8"))
        authority_path, authority_ref = self._authority_receipt(suffix="-schema")
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        query = self._query(
            mode="tool-search",
            capabilities=["function.required"],
            exact_refs=["module:required-provider"],
            authority_receipt_refs=[authority_ref],
            execution_requested=True,
        )
        import_actual_self_receipt(
            actual_path,
            self.resolution,
            self.store,
            evaluated_at=OBSERVED_AT,
            trust_store=self.trust_store,
        )
        import_search_authority_receipt(
            authority_path,
            self.store,
            evaluated_at=OBSERVED_AT,
            expected_host_id="TEST-HOST",
            trust_store=self.trust_store,
        )
        receipt = resolve_search_route(
            query,
            self.resolution,
            self.store,
            trust_store=self.trust_store,
        )
        trust_value = json.loads(self.trust_path.read_text(encoding="utf-8"))
        values = [actual, authority, query, receipt, trust_value]
        for name, value in zip(schema_names, values):
            errors = sorted(
                Draft202012Validator(schemas[name]).iter_errors(value),
                key=lambda error: list(error.path),
            )
            self.assertEqual(
                errors,
                [],
                msg=f"{name}: {[error.message for error in errors]}",
            )

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
        *,
        suffix: str = "",
        observed_at: str = "2026-07-30T19:55:00Z",
        expires_at: str = EXPIRES_AT,
        private_key: Ed25519PrivateKey | None = None,
        signer_id: str = "signer:controlcenter-test-host",
    ) -> Path:
        value = self._receipt_value(
            component_ref,
            component_type,
            functions,
            suffix=suffix,
            observed_at=observed_at,
            expires_at=expires_at,
            signer_id=signer_id,
        )
        return self._write(
            component_ref.replace(":", "-") + suffix + ".actual.json",
            self._sign(value, private_key or self.producer_key, signer_id),
        )

    def _receipt_value(
        self,
        component_ref: str,
        component_type: str,
        functions: list[str],
        *,
        suffix: str = "",
        observed_at: str = "2026-07-30T19:55:00Z",
        expires_at: str = EXPIRES_AT,
        signer_id: str = "signer:controlcenter-test-host",
    ) -> dict:
        component = self._component(self.resolution, component_ref)
        return {
            "schema": "ellmos.actual-self-component-receipt.v1",
            "receipt_id": (
                "receipt-" + component_ref.replace(":", "-") + suffix
            ),
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
                "adapter_id": "controlcenter.native-list-tools.v1",
                "signer_id": signer_id,
                "host_id": "TEST-HOST",
                "probe_kind": "native-runtime-readback",
            },
            "observed_at": observed_at,
            "expires_at": expires_at,
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
            trust_store=self.trust_store,
        )

    def _query(
        self,
        *,
        mode: str,
        capabilities: list[str],
        exact_refs: list[str] | None = None,
        ranked_candidates: list[dict] | None = None,
        authority_receipt_refs: list[str] | None = None,
        execution_requested: bool = False,
        observed_at: str = OBSERVED_AT,
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
                "authority_receipt_refs": authority_receipt_refs or [],
                "execution_requested": execution_requested,
                "observed_at": observed_at,
            }
        )

    def _authority_receipt(
        self,
        *,
        suffix: str = "",
        confidence: float = 0.96,
        conflicts: list[dict] | None = None,
        component_refs: list[str] | None = None,
        delegation_ref: str = "decision:D-20260730-001",
        private_key: Ed25519PrivateKey | None = None,
        signer_id: str = "signer:decision-resolver-test-host",
        receipt_ref: str | None = None,
        issued_at: str = "2026-07-30T19:00:00Z",
        expires_at: str = EXPIRES_AT,
        issuer_host_id: str = "TEST-HOST",
    ) -> tuple[Path, str]:
        receipt_ref = receipt_ref or "authority:avatar-routing-001" + suffix
        value = {
            "schema": "ellmos.search-authority-receipt.v1",
            "receipt_ref": receipt_ref,
            "authority_type": "delegated-avatar-decision",
            "decision_ref": "decision:avatar-routing-001",
            "delegation_ref": delegation_ref,
            "decision_kind": "predicted",
            "confidence": confidence,
            "minimum_confidence": 0.9,
            "issuer": {
                "ref": "module:policy-decision-resolver",
                "adapter_id": "policy-decision-resolver.native.v1",
                "signer_id": signer_id,
                "host_id": issuer_host_id,
            },
            "scope": {
                "query_modes": ["tool-search"],
                "system_instance_ids": [
                    self.resolution["instance"]["instance_id"]
                ],
                "host_ids": [issuer_host_id],
                "component_refs": component_refs
                or ["module:required-provider"],
                "capabilities": ["function.required"],
            },
            "evidence": [
                {
                    "ref": "evidence:tom-lm-prediction-001",
                    "sha256": "7" * 64,
                },
                {
                    "ref": "evidence:D-20260730-001",
                    "sha256": "6" * 64,
                },
            ],
            "issued_at": issued_at,
            "expires_at": expires_at,
            "conflicts": conflicts or [],
        }
        for evidence in [*value["evidence"], *value["conflicts"]]:
            self.store.add_evidence(
                uri=evidence["ref"],
                source_kind="document:decision",
                sha256=evidence["sha256"],
                locator=evidence["ref"],
                metadata={"evidence_ref": evidence["ref"]},
            )
        self.store.commit()
        path = self._write(
            "authority" + suffix + ".json",
            self._sign(value, private_key or self.authority_key, signer_id),
        )
        return path, receipt_ref

    def _sign(
        self,
        value: dict,
        private_key: Ed25519PrivateKey,
        signer_id: str,
    ) -> dict:
        value = deepcopy(value)
        value["content_hash"] = signed_content_hash(value)
        signature = private_key.sign(signed_payload_bytes(value))
        value["signature"] = {
            "algorithm": "ed25519",
            "signer_id": signer_id,
            "value": base64.b64encode(signature).decode("ascii"),
        }
        return value

    def _write_public_key(
        self,
        name: str,
        private_key: Ed25519PrivateKey,
    ) -> None:
        (self.root / name).write_bytes(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

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
