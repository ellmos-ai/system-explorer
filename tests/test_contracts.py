from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from system_explorer.cli import main
from system_explorer.contracts import (
    OUTPUT_BINDING_FIELDS,
    canonical_content_hash,
    validate_contract,
    with_content_hash,
)
from system_explorer.manifests import validate_manifest
from system_explorer.resolver import (
    resolve_fleet,
    resolve_system,
    resolve_test,
    validate_manifest_target,
)


class ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_schema_documents_are_json_and_cover_all_v4_contracts(self) -> None:
        schema_dir = Path(__file__).resolve().parents[1] / "schemas"
        names = {
            "ellmos.bundle.v1.schema.json",
            "ellmos.bundles.catalog.v1.schema.json",
            "ellmos.component-registry-bindings.v1.schema.json",
            "ellmos.system.v1.schema.json",
            "ellmos.system-instance.v1.schema.json",
            "ellmos.system-test.v1.schema.json",
            "ellmos.fleet.v1.schema.json",
            "ellmos.actual-self-component-receipt.v1.schema.json",
            "ellmos.search-authority-receipt.v1.schema.json",
            "ellmos.search-routing-query.v1.schema.json",
            "ellmos.search-routing-receipt.v1.schema.json",
            "system-explorer.receipt-trust-store.v1.schema.json",
            "system-explorer.probe-receipt.v1.schema.json",
            "system-explorer.composition-rule-pin.v1.schema.json",
            "system-explorer.stack-schema-pin.v1.schema.json",
        }
        for name in names:
            value = json.loads((schema_dir / name).read_text(encoding="utf-8"))
            self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("content_hash", value["required"])
            if name in {
                "ellmos.system.v1.schema.json",
                "ellmos.system-instance.v1.schema.json",
            }:
                output_binding = value["$defs"]["output_binding"]
                self.assertFalse(output_binding["additionalProperties"])
                self.assertEqual(
                    set(output_binding["properties"]),
                    OUTPUT_BINDING_FIELDS,
                )
                self.assertEqual(
                    output_binding["properties"]["materialization"]["enum"],
                    ["resolution-only-unmaterialized"],
                )
        instance_schema = json.loads(
            (schema_dir / "ellmos.system-instance.v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        component_state = instance_schema["$defs"]["component_state"]
        self.assertFalse(component_state["additionalProperties"])
        self.assertEqual(
            set(component_state["properties"]),
            {
                "status",
                "desired_profile",
                "publisher_slot",
                "publishes",
                "peer_transfer",
                "network_path",
                "peer_verification",
                "destination_policy",
                "activation",
                "database_allowlist",
                "live_database_in_sync",
            },
        )
        ready_disabled = component_state["allOf"][2]["then"]
        self.assertEqual(
            ready_disabled["properties"]["database_allowlist"]["maxItems"],
            0,
        )
        self.assertFalse(
            ready_disabled["properties"]["live_database_in_sync"]["const"],
        )

    def test_canonical_hash_ignores_only_the_root_content_hash(self) -> None:
        value = {"schema": "example", "nested": {"content_hash": "retained"}, "z": 1}
        first = canonical_content_hash(value)
        value["content_hash"] = "0" * 64
        self.assertEqual(first, canonical_content_hash(value))
        value["nested"]["content_hash"] = "changed"
        self.assertNotEqual(first, canonical_content_hash(value))

    def test_output_binding_ownership_and_raw_log_safety(self) -> None:
        valid = self._system(output_bindings=self._valid_output_bindings())
        self.assertEqual(validate_contract(valid), [])

        raw_onedrive = deepcopy(valid)
        raw_onedrive["output_bindings"][0]["storage_uri"] = "onedrive://logs/raw.jsonl"
        raw_onedrive = with_content_hash(raw_onedrive)
        errors = validate_contract(raw_onedrive)
        self.assertTrue(any("host-local://" in error for error in errors))
        self.assertTrue(any("OneDrive or Desktop" in error for error in errors))

        memory_log = deepcopy(valid)
        memory_log["output_bindings"][0][
            "owner_ref"
        ] = "ellmos-memory-human-context-bundle"
        memory_log = with_content_hash(memory_log)
        self.assertTrue(
            any("memory bundle" in error for error in validate_contract(memory_log))
        )

        bad_decision = deepcopy(valid)
        bad_decision["output_bindings"][1]["storage_uri"] = "desktop://decision.md"
        bad_decision = with_content_hash(bad_decision)
        self.assertTrue(
            any(
                "control-center://_DECISIONS" in error
                for error in validate_contract(bad_decision)
            )
        )

        missing_backup = deepcopy(valid)
        missing_backup["output_bindings"][-1].pop("backup_uri")
        missing_backup = with_content_hash(missing_backup)
        self.assertTrue(
            any("backup_uri" in error for error in validate_contract(missing_backup))
        )

    def test_raw_runtime_log_rejects_secondary_targets_and_encoded_cloud_path(
        self,
    ) -> None:
        for field, target in (
            ("backup_uri", "onedrive://logs/raw-backup.jsonl"),
            ("desktop_shortcut", "desktop://raw-log"),
        ):
            manifest = self._system(output_bindings=self._valid_output_bindings())
            manifest["output_bindings"][0][field] = target
            errors = validate_contract(with_content_hash(manifest))
            self.assertTrue(
                any(
                    f"{field} is not allowed for raw runtime logs" in error
                    for error in errors
                )
            )

        for target in (
            "host-local://logs/%4fneDrive/raw.jsonl",
            "host-local://logs/raw.jsonl?mirror=OneDrive",
            "host-local://logs/%254fneDrive/raw.jsonl",
            "host-local://logs/raw.jsonl?mirror=%2544esktop",
        ):
            encoded = self._system(output_bindings=self._valid_output_bindings())
            encoded["output_bindings"][0]["storage_uri"] = target
            errors = validate_contract(with_content_hash(encoded))
            self.assertTrue(any("OneDrive or Desktop" in error for error in errors))

        invalid_encoding = self._system(output_bindings=self._valid_output_bindings())
        invalid_encoding["output_bindings"][0][
            "storage_uri"
        ] = "host-local://logs/%ZZ/raw.jsonl"
        errors = validate_contract(with_content_hash(invalid_encoding))
        self.assertTrue(any("must be a typed URI" in error for error in errors))

    def test_output_binding_rejects_unknown_fields_and_secret_aliases(self) -> None:
        unknown = self._system(output_bindings=self._valid_output_bindings())
        for field in ("mirror_uri", "access_token"):
            candidate = deepcopy(unknown)
            candidate["output_bindings"][0][field] = "reviewer-canary"
            errors = validate_contract(with_content_hash(candidate))
            self.assertTrue(
                any(f".{field} is unsupported" in error for error in errors)
            )
        access_token_errors = validate_contract(
            with_content_hash(
                {
                    **unknown,
                    "output_bindings": [
                        {
                            **unknown["output_bindings"][0],
                            "access_token": "SHOULD_NOT_SURVIVE",
                        }
                    ],
                }
            )
        )
        self.assertTrue(
            any(
                "access_token may not contain a secret value" in error
                for error in access_token_errors
            )
        )

        paths = self._write_fixture()
        system = self._read(paths["system"])
        system["output_bindings"][0]["access_token"] = "RESOLVER-CANARY"
        self._write(paths["system"], with_content_hash(system))
        with self.assertRaisesRegex(ValueError, "access_token"):
            resolve_system(paths["instance"], [paths["catalog"]])

        materialized = deepcopy(unknown)
        materialized["output_bindings"][0][
            "materialization"
        ] = "resolution-only-unmaterialized"
        self.assertEqual(validate_contract(with_content_hash(materialized)), [])

        invalid_materialization = deepcopy(unknown)
        invalid_materialization["output_bindings"][0][
            "materialization"
        ] = "materialized-with-side-effects"
        errors = validate_contract(with_content_hash(invalid_materialization))
        self.assertTrue(
            any(
                ".materialization must be one of resolution-only-unmaterialized"
                in error
                for error in errors
            )
        )

        secret_alias = self._system()
        secret_alias["provenance"]["clientSecret"] = "must-not-be-stored"
        errors = validate_contract(with_content_hash(secret_alias))
        self.assertTrue(
            any("clientSecret may not contain a secret value" in error for error in errors)
        )

        api_key_value = self._system()
        api_key_value["provenance"]["apiKeyValue"] = "must-not-be-stored"
        errors = validate_contract(with_content_hash(api_key_value))
        self.assertTrue(
            any("apiKeyValue may not contain a secret value" in error for error in errors)
        )

        for field in (
            "client_secret_uri",
            "api_key_path",
            "access_token_id",
            "password_provider",
            "private_key_status",
        ):
            secret_metadata_alias = self._system()
            secret_metadata_alias["provenance"][field] = "reviewer-canary"
            errors = validate_contract(with_content_hash(secret_metadata_alias))
            self.assertTrue(
                any(f"{field} may not contain a secret value" in error for error in errors)
            )

        reference_is_allowed = self._system()
        reference_is_allowed["provenance"]["client_secret_ref"] = "vault://secret-id"
        self.assertEqual(validate_contract(with_content_hash(reference_is_allowed)), [])

    def test_generic_bindings_reject_secrets_and_absolute_secret_paths(self) -> None:
        for field, value, expected in (
            ("access_token", "SHOULD_NOT_SURVIVE", "a secret value"),
            (
                "credential_path",
                r"C:\Users\agent\.ssh\id_ed25519",
                "an absolute secret path",
            ),
            ("secret_file", "/etc/private/credential", "an absolute secret path"),
        ):
            manifest = self._system(
                bindings=[
                    {
                        "source": "module:a",
                        "target": "module:b",
                        field: value,
                    }
                ]
            )
            errors = validate_contract(with_content_hash(manifest))
            self.assertTrue(
                any(f".{field} may not contain {expected}" in error for error in errors)
            )

        logical_reference = self._system(
            bindings=[
                {
                    "source": "module:a",
                    "target": "module:b",
                    "secret_ref": "vault://logical-secret-id",
                }
            ]
        )
        self.assertEqual(validate_contract(with_content_hash(logical_reference)), [])

        paths = self._write_fixture()
        system = self._read(paths["system"])
        system["bindings"] = [
            {
                "source": "module:a",
                "target": "module:b",
                "access_token": "RESOLVER-CANARY",
            }
        ]
        self._write(paths["system"], with_content_hash(system))
        with self.assertRaisesRegex(ValueError, "access_token"):
            resolve_system(paths["instance"], [paths["catalog"]])

    def test_automation_summary_requires_redacted_non_raw_content(self) -> None:
        manifest = self._system(output_bindings=self._valid_output_bindings())
        summary = next(
            item
            for item in manifest["output_bindings"]
            if item["kind"] == "automation_summary"
        )
        summary["raw_content_allowed"] = True
        errors = validate_contract(with_content_hash(manifest))
        self.assertTrue(
            any(
                "raw_content_allowed must be false for automation summaries" in error
                for error in errors
            )
        )

    def test_resolver_is_deterministic_and_applies_profiles_and_statuses(self) -> None:
        paths = self._write_fixture()
        first = resolve_system(paths["instance"], [paths["catalog"]])
        second = resolve_system(paths["instance"], [paths["catalog"]])
        self.assertEqual(first, second)
        self.assertEqual(first["content_hash"], canonical_content_hash(first))
        self.assertEqual(first["functions"], ["system.map"])
        self.assertEqual(
            [item["id"] for item in first["bundles"]],
            ["ellmos-core-discovery-bundle"],
        )
        components = first["bundles"][0]["components"]
        self.assertEqual([item["ref"] for item in components], ["module:mapper"])
        self.assertEqual(first["runtime_actions"], [])
        self.assertEqual(first["target_mutations"], [])
        self.assertFalse((self.root / "unexpected-output.json").exists())

    def test_resolver_preserves_complete_component_states_for_equal_hosts(self) -> None:
        for host, slot in (("host-a", "workstation"), ("host-b", "laptop")):
            component_states = {
                "module:mapper": {
                    "status": "registered",
                    "desired_profile": "trusted-peer-paths",
                    "publisher_slot": slot,
                    "publishes": "signed-path-metadata-only",
                    "peer_transfer": "sftp-over-ssh",
                    "network_path": "direct-or-tailscale",
                    "peer_verification": "signed-registry-and-pinned-host-key",
                    "destination_policy": "normalized-allowlisted-no-overwrite",
                },
                "module:optional-ui": {
                    "status": "registered",
                    "desired_profile": "database-ready-disabled",
                    "activation": "ready-disabled",
                    "database_allowlist": [],
                    "live_database_in_sync": False,
                },
            }
            paths = self._write_fixture(
                suppress_optional=False,
                host_id=host,
                component_states=component_states,
            )
            result = resolve_system(paths["instance"], [paths["catalog"]])
            components = {
                item["ref"]: item
                for item in result["bundles"][0]["components"]
            }
            self.assertEqual(
                components["module:mapper"]["component_state"],
                component_states["module:mapper"],
            )
            self.assertEqual(
                components["module:optional-ui"]["component_state"],
                component_states["module:optional-ui"],
            )
            self.assertEqual(result["runtime_actions"], [])
            self.assertEqual(result["target_mutations"], [])

    def test_component_states_reject_malformed_peer_and_database_shapes(self) -> None:
        paths = self._write_fixture()
        instance = self._read(paths["instance"])
        candidates = (
            (
                {"publisher_slot": "workstation"},
                "complete trusted-peer state together",
            ),
            (
                {
                    "activation": "ready-disabled",
                    "database_allowlist": ["database:unexpected"],
                    "live_database_in_sync": False,
                },
                "ready-disabled requires database_allowlist=[]",
            ),
            (
                {
                    "activation": "ready-disabled",
                    "database_allowlist": [],
                    "live_database_in_sync": True,
                },
                "ready-disabled requires live_database_in_sync=false",
            ),
            (
                {
                    "activation": "ready-disabled",
                    "database_allowlist": "database-id",
                    "live_database_in_sync": False,
                },
                "database_allowlist must be an array of non-empty strings",
            ),
            (
                {"desired_profile": "", "unexpected": "value"},
                "unexpected is unsupported",
            ),
        )
        for state, expected in candidates:
            candidate = deepcopy(instance)
            candidate["component_states"] = {"module:mapper": state}
            errors = validate_contract(with_content_hash(candidate))
            self.assertTrue(any(expected in error for error in errors), errors)

    def test_resolver_rejects_bad_pins_escaping_paths_and_cycles(self) -> None:
        paths = self._write_fixture()
        instance = self._read(paths["instance"])
        instance["system_ref"]["version"] = "9.9.9"
        self._write(paths["instance"], with_content_hash(instance))
        with self.assertRaisesRegex(ValueError, "version pin"):
            resolve_system(paths["instance"], [paths["catalog"]])

        paths = self._write_fixture()
        instance = self._read(paths["instance"])
        instance["system_ref"]["path"] = "../outside.json"
        self._write(paths["instance"], with_content_hash(instance))
        with self.assertRaisesRegex(ValueError, "escapes its manifest root"):
            resolve_system(paths["instance"], [paths["catalog"]])

        paths = self._write_fixture(fallback_cycle=True)
        with self.assertRaisesRegex(ValueError, "fallback cycle"):
            resolve_system(paths["instance"], [paths["catalog"]])

        paths = self._write_fixture()
        system = self._read(paths["system"])
        system["bindings"] = [
            {"source": "module:a", "target": "module:b"},
            {"source": "module:b", "target": "module:a"},
        ]
        self._write(paths["system"], with_content_hash(system))
        with self.assertRaisesRegex(ValueError, "system binding cycle"):
            resolve_system(paths["instance"], [paths["catalog"]])

    def test_test_overlay_suppresses_only_resolved_refs_without_writeback(self) -> None:
        paths = self._write_fixture(suppress_optional=False)
        instance = self._read(paths["instance"])
        test = self._common("ellmos.system-test.v1", "mapper-negative-test")
        test.update(
            {
                "base_system_ref": {
                    "path": paths["instance"].name,
                    "content_hash": instance["content_hash"],
                },
                "base_hash": instance["content_hash"],
                "mode": "resolution-only",
                "suppressions": [
                    {"ref": "module:optional-ui", "reason": "negative path"}
                ],
                "expected_functions": ["system.map"],
                "expected_absent_functions": ["system.ui"],
                "tolerated_gaps": [],
                "writeback_to_base": False,
            }
        )
        test_path = self.root / "system-test.json"
        self._write(test_path, with_content_hash(test))

        result = resolve_test(test_path, [paths["catalog"]])
        self.assertEqual(result["functions"], ["system.map"])
        self.assertEqual(result["runtime_actions"], [])
        self.assertFalse(result["writeback_to_base"])
        self.assertEqual(self._read(paths["instance"]), instance)

    def test_test_overlay_accounts_for_and_suppresses_subsystem_functions(self) -> None:
        paths = self._write_fixture(suppress_optional=False)
        bundle = self._read(paths["bundle"])
        child = self._system(
            bundle_refs=[{"ref": bundle["id"], "version": bundle["version"]}],
            profiles={
                "default": {
                    "include": [bundle["id"]],
                    "exclude": [],
                    "overrides": {},
                }
            },
        )
        child["id"] = "child-system"
        child = with_content_hash(child)
        child_path = self.root / "child-system.json"
        self._write(child_path, child)
        system = self._read(paths["system"])
        system["subsystem_refs"] = [
            {
                "path": child_path.name,
                "content_hash": child["content_hash"],
                "profile": "default",
                "role": "child-service",
            }
        ]
        self._write(paths["system"], with_content_hash(system))
        instance = self._read(paths["instance"])
        test = self._common("ellmos.system-test.v1", "subsystem-negative-test")
        test.update(
            {
                "base_system_ref": {
                    "path": paths["instance"].name,
                    "content_hash": instance["content_hash"],
                },
                "base_hash": instance["content_hash"],
                "mode": "resolution-only",
                "suppressions": [],
                "expected_functions": ["system.map"],
                "expected_absent_functions": ["system.ui"],
                "tolerated_gaps": [],
                "writeback_to_base": False,
            }
        )
        test_path = self.root / "subsystem-test.json"
        self._write(test_path, with_content_hash(test))

        with self.assertRaisesRegex(ValueError, "expected-absent functions"):
            resolve_test(test_path, [paths["catalog"]])

        test["suppressions"] = [
            {"ref": "module:optional-ui", "reason": "negative child path"}
        ]
        self._write(test_path, with_content_hash(test))
        result = resolve_test(test_path, [paths["catalog"]])
        self.assertNotIn("system.ui", result["functions"])
        self.assertNotIn(
            "module:optional-ui",
            {
                (
                    component["ref"]
                    if isinstance(component["ref"], str)
                    else component["ref"]["ref"]
                )
                for subsystem in result["subsystems"]
                for bundle in subsystem["resolution"]["bundles"]
                for component in bundle["components"]
            },
        )

    def test_cli_writes_only_to_explicit_output_atomically(self) -> None:
        paths = self._write_fixture()
        output = self.root / "out" / "resolution.json"
        code = main(
            [
                "system-resolve",
                str(paths["instance"]),
                "--catalog",
                str(paths["catalog"]),
                "--output",
                str(output),
            ]
        )
        self.assertEqual(code, 0)
        value = self._read(output)
        self.assertEqual(value["content_hash"], canonical_content_hash(value))
        self.assertEqual(list(self.root.rglob(f".{output.name}.*.tmp")), [])

    def test_manifest_tree_validation_is_sorted_and_deterministic(self) -> None:
        self._write_fixture()
        first = validate_manifest_target(self.root)
        second = validate_manifest_target(self.root)
        self.assertEqual(first, second)
        self.assertTrue(first["valid"])
        paths = [item["path"] for item in first["results"]]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(first["invalid"], 0)

    def test_legacy_stack_v2_bundle_refs_remain_tolerantly_consumable(self) -> None:
        paths = self._write_fixture(use_stack=True)
        result = resolve_system(paths["instance"], [paths["catalog"]])
        self.assertEqual(result["stacks"][0]["id"], "legacy-stack")
        self.assertIn("bundle_refs only", result["warnings"][0])
        self.assertEqual(validate_manifest({"schema": "ellmos.stack.v2", "id": "x"}), [])

    def test_pinned_external_stack_schema_is_verified_during_resolution(self) -> None:
        paths = self._write_fixture(use_stack=True)
        schema_path = self.root / "external-stack-schema.json"
        schema_path.write_text(
            json.dumps({"schema": "ellmos.stack.v2", "version": "2.0.0", "required": ["id"]}),
            encoding="utf-8",
        )
        pin_path = self.root / "stack-schema-pin.json"
        pin_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.stack-schema-pin.v1",
                    "id": "stack-schema-fixture",
                    "target_schema": "ellmos.stack.v2",
                    "version": "2.0.0",
                    "scope": "template",
                    "source_uri": "registry://stack/schema-fixture",
                    "source_path": schema_path.name,
                    "content_hash": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        result = resolve_system(
            paths["instance"],
            [paths["catalog"]],
            stack_schema_pin_path=pin_path,
        )
        self.assertEqual(result["stack_schema_verifications"][0]["status"], "verified")
        schema_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stack schema authority is blocked"):
            resolve_system(paths["instance"], [paths["catalog"]], stack_schema_pin_path=pin_path)

    def test_legacy_stack_rejects_stale_self_declared_hash_after_mutation(self) -> None:
        paths = self._write_fixture(use_stack=True)
        stack_path = self.root / "stack.json"
        stack = self._read(stack_path)
        old_hash = canonical_content_hash(stack)
        stack["content_hash"] = old_hash
        stack["bundle_refs"] = []
        self._write(stack_path, stack)

        validation = validate_manifest_target(stack_path)
        self.assertFalse(validation["valid"])
        self.assertIn(
            "$.content_hash does not match canonical content",
            validation["errors"],
        )
        with self.assertRaisesRegex(
            ValueError,
            "referenced manifest content_hash does not match canonical content",
        ):
            resolve_system(paths["instance"], [paths["catalog"]])

    def test_subsystem_refs_require_pinned_path_profile_role_and_unique_path(self) -> None:
        valid_ref = {
            "path": "systems/child.json",
            "version": "1.0.0",
            "profile": "default",
            "role": "llm-core-system",
        }
        self.assertEqual(
            validate_contract(self._system(subsystem_refs=[valid_ref])),
            [],
        )

        candidates = (
            ({key: value for key, value in valid_ref.items() if key != "profile"}, "profile is required"),
            ({key: value for key, value in valid_ref.items() if key != "role"}, "role is required"),
            ({key: value for key, value in valid_ref.items() if key != "version"}, "requires a version"),
            ({**valid_ref, "path": "../outside.json"}, "may not escape"),
            ({**valid_ref, "id": "not-a-path-only-ref"}, "id is unsupported"),
        )
        for subsystem_ref, expected in candidates:
            errors = validate_contract(self._system(subsystem_refs=[subsystem_ref]))
            self.assertTrue(any(expected in error for error in errors), errors)

        duplicate = self._system(
            subsystem_refs=[valid_ref, {**valid_ref, "path": "systems\\child.json"}]
        )
        self.assertTrue(
            any("duplicate paths" in error for error in validate_contract(duplicate))
        )

    def test_resolver_keeps_recursive_subsystems_non_flattened_and_pinned(self) -> None:
        paths = self._write_fixture()
        bundle = self._read(paths["bundle"])
        bundle_ref = {"ref": bundle["id"], "version": bundle["version"]}

        grandchild = self._system(
            bundle_refs=[],
            profiles={
                "default": {"include": [], "exclude": [], "overrides": {}}
            },
        )
        grandchild["id"] = "grandchild-system"
        grandchild = with_content_hash(grandchild)
        grandchild_path = self.root / "grandchild-system.json"
        self._write(grandchild_path, grandchild)

        child = self._system(
            bundle_refs=[bundle_ref],
            subsystem_refs=[
                {
                    "path": grandchild_path.name,
                    "content_hash": grandchild["content_hash"],
                    "profile": "default",
                    "role": "nested-service",
                }
            ],
        )
        child["id"] = "child-system"
        child = with_content_hash(child)
        child_path = self.root / "child-system.json"
        self._write(child_path, child)

        parent = self._read(paths["system"])
        parent["subsystem_refs"] = [
            {
                "path": child_path.name,
                "content_hash": child["content_hash"],
                "profile": "default",
                "role": "llm-core-system",
            }
        ]
        self._write(paths["system"], with_content_hash(parent))

        result = resolve_system(paths["instance"], [paths["catalog"]])
        child_result = result["subsystems"][0]["resolution"]
        grandchild_result = child_result["subsystems"][0]["resolution"]
        self.assertEqual(result["functions"], ["system.map"])
        self.assertEqual(child_result["functions"], ["system.map"])
        self.assertEqual(grandchild_result["functions"], [])
        self.assertEqual([item["id"] for item in result["bundles"]], [bundle["id"]])
        self.assertEqual([item["id"] for item in child_result["bundles"]], [bundle["id"]])
        self.assertEqual(grandchild_result["bundles"], [])
        self.assertNotIn("instance", child_result)
        self.assertEqual(result["subsystems"][0]["role"], "llm-core-system")
        self.assertEqual(child_result["content_hash"], canonical_content_hash(child_result))
        self.assertEqual(result["content_hash"], canonical_content_hash(result))

        stale = self._read(paths["system"])
        stale["subsystem_refs"][0]["content_hash"] = "0" * 64
        self._write(paths["system"], with_content_hash(stale))
        with self.assertRaisesRegex(ValueError, "content_hash pin"):
            resolve_system(paths["instance"], [paths["catalog"]])

    def test_resolver_rejects_subsystem_cycles_and_duplicate_system_identities(self) -> None:
        paths = self._write_fixture()
        parent = self._read(paths["system"])
        child = self._system(
            subsystem_refs=[
                {
                    "path": paths["system"].name,
                    "version": parent["version"],
                    "profile": "default",
                    "role": "cycle-back",
                }
            ]
        )
        child["id"] = "child-system"
        child = with_content_hash(child)
        child_path = self.root / "child-cycle.json"
        self._write(child_path, child)
        parent["subsystem_refs"] = [
            {
                "path": child_path.name,
                "version": child["version"],
                "profile": "default",
                "role": "child",
            }
        ]
        self._write(paths["system"], with_content_hash(parent))
        with self.assertRaisesRegex(ValueError, "subsystem reference cycle"):
            resolve_system(paths["instance"], [paths["catalog"]])

        paths = self._write_fixture()
        first = self._system()
        first["id"] = "duplicate-child"
        first = with_content_hash(first)
        second = deepcopy(first)
        first_path = self.root / "first-child.json"
        second_path = self.root / "second-child.json"
        self._write(first_path, first)
        self._write(second_path, second)
        parent = self._read(paths["system"])
        parent["subsystem_refs"] = [
            {
                "path": item.name,
                "content_hash": first["content_hash"],
                "profile": "default",
                "role": role,
            }
            for item, role in ((first_path, "first"), (second_path, "second"))
        ]
        self._write(paths["system"], with_content_hash(parent))
        with self.assertRaisesRegex(ValueError, "duplicate resolved subsystem id"):
            resolve_system(paths["instance"], [paths["catalog"]])

    def test_output_bindings_dedupe_exact_policy_and_reject_conflicts(self) -> None:
        paths = self._write_fixture()
        instance = self._read(paths["instance"])
        runtime_binding = deepcopy(instance["output_bindings"][0])
        system = self._read(paths["system"])
        system["output_bindings"].append(runtime_binding)
        self._write(paths["system"], with_content_hash(system))

        result = resolve_system(paths["instance"], [paths["catalog"]])
        self.assertEqual(len(result["output_bindings"]), 2)
        self.assertEqual(
            sum(item["kind"] == "runtime_log" for item in result["output_bindings"]),
            1,
        )

        system["output_bindings"][-1]["retention"] = "P7D"
        self._write(paths["system"], with_content_hash(system))
        with self.assertRaisesRegex(ValueError, "conflicting output binding policy"):
            resolve_system(paths["instance"], [paths["catalog"]])

    def test_fleet_resolver_applies_host_desired_deviations(self) -> None:
        paths = self._write_fixture(suppress_optional=False)
        workstation = self._read(paths["instance"])
        laptop_path = self._laptop_instance(workstation)
        fleet_path = self._write_fleet(paths, workstation, laptop_path)

        first = resolve_fleet(fleet_path, [paths["catalog"]])
        second = resolve_fleet(fleet_path, [paths["catalog"]])
        self.assertEqual(first, second)
        self.assertEqual(first["content_hash"], canonical_content_hash(first))
        self.assertEqual(
            [member["id"] for member in first["members"]], ["laptop", "workstation"]
        )

        laptop_result, workstation_result = first["members"]
        self.assertEqual(laptop_result["host_id"], "host-b")
        self.assertEqual(laptop_result["resolution"]["functions"], ["system.map"])
        self.assertEqual(laptop_result["coverage_status"], "tolerated-gap")
        self.assertEqual(laptop_result["open_tolerated_gaps"], ["system.ui"])
        self.assertEqual(laptop_result["quarantined_bundles"], [])
        self.assertIn("system.ui", workstation_result["functions"])

        self.assertEqual(first["coverage_status"], "tolerated-gap")
        self.assertEqual(first["blocking_required_gaps"], [])
        self.assertEqual(first["quarantined_members"], [])
        coverage = {item["function"]: item for item in first["function_coverage"]}
        self.assertEqual(coverage["system.map"]["members"], ["laptop", "workstation"])
        self.assertFalse(coverage["system.map"]["single_provider"])
        self.assertEqual(coverage["system.ui"]["members"], ["workstation"])
        self.assertTrue(coverage["system.ui"]["single_provider"])

        self.assertEqual(first["dependencies"][0]["source"], "workstation")
        self.assertEqual(first["dependencies"][0]["target"], "laptop")
        self.assertEqual(first["host_bindings"], [])
        self.assertEqual(first["runtime_actions"], [])
        self.assertEqual(first["target_mutations"], [])
        self.assertEqual(self._read(paths["instance"]), workstation)

        output = self.root / "out" / "fleet-resolution.json"
        code = main(
            [
                "fleet-resolve",
                str(fleet_path),
                "--catalog",
                str(paths["catalog"]),
                "--output",
                str(output),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(self._read(output), first)
        self.assertEqual(list(self.root.rglob(f".{output.name}.*.tmp")), [])

    def test_fleet_resolver_reports_functions_from_subsystems(self) -> None:
        """Member coverage is the whole member, not just its root projection.

        `resolution["functions"]` is deliberately root-only since the nested
        composition work. A fleet asks what a member provides, so it has to
        include the subsystems -- otherwise a function that only a subsystem
        carries would read as an uncovered gap at fleet level.
        """

        paths = self._write_fixture(suppress_optional=False)
        workstation = self._read(paths["instance"])
        system = self._read(paths["system"])
        parent = deepcopy(system)
        parent.update(
            {
                "id": "parent-system",
                "bundle_refs": [],
                "profiles": {"default": {"include": [], "exclude": [], "overrides": {}}},
            }
        )
        parent["subsystem_refs"] = [
            {
                "path": paths["system"].name,
                "role": "child",
                "profile": "default",
                "content_hash": system["content_hash"],
            }
        ]
        parent_path = self.root / "parent-system.json"
        self._write(parent_path, with_content_hash(parent))

        parent_instance = deepcopy(workstation)
        parent_instance.update(
            {
                "id": "parent-instance",
                "instance_id": "parent-instance@host-c",
                "host_id": "host-c",
                "component_states": {},
                "system_ref": {
                    "ref": parent_path.name,
                    "content_hash": canonical_content_hash(parent),
                },
            }
        )
        parent_instance_path = self.root / "parent-instance.json"
        self._write(parent_instance_path, with_content_hash(parent_instance))

        fleet = self._common("ellmos.fleet.v1", "nested-fleet")
        fleet.update(
            {
                "systems": [
                    {
                        "id": "nested",
                        "path": parent_instance_path.name,
                        "content_hash": canonical_content_hash(parent_instance),
                    }
                ],
                "roles": [],
                "handoffs": [],
                "dependencies": [],
                "host_overrides": [],
            }
        )
        fleet_path = self.root / "nested-fleet.json"
        self._write(fleet_path, with_content_hash(fleet))

        result = resolve_fleet(fleet_path, [paths["catalog"]])
        member = result["members"][0]
        self.assertEqual(member["root_functions"], [])
        self.assertIn("system.map", member["functions"])
        self.assertIn("system.map", result["functions"])
        self.assertEqual(member["blocking_required_gaps"], [])
        self.assertEqual(result["coverage_status"], "covered")

    def test_fleet_resolver_rejects_host_overrides_for_unknown_hosts(self) -> None:
        paths = self._write_fixture(suppress_optional=False)
        workstation = self._read(paths["instance"])
        fleet = self._common("ellmos.fleet.v1", "test-fleet")
        fleet.update(
            {
                "systems": [
                    {
                        "id": "workstation",
                        "path": paths["instance"].name,
                        "content_hash": workstation["content_hash"],
                    }
                ],
                "roles": [],
                "handoffs": [],
                "dependencies": [],
                "host_overrides": [
                    {"host_id": "host-does-not-exist", "reason": "typo"}
                ],
            }
        )
        fleet_path = self.root / "fleet.json"
        self._write(fleet_path, with_content_hash(fleet))
        with self.assertRaisesRegex(ValueError, "unresolved hosts"):
            resolve_fleet(fleet_path, [paths["catalog"]])

    def test_fleet_resolver_rejects_duplicate_member_ids(self) -> None:
        paths = self._write_fixture(suppress_optional=False)
        workstation = self._read(paths["instance"])
        laptop_path = self._laptop_instance(workstation)
        laptop = self._read(laptop_path)
        fleet = self._common("ellmos.fleet.v1", "test-fleet")
        fleet.update(
            {
                "systems": [
                    {
                        "id": "same",
                        "path": paths["instance"].name,
                        "content_hash": workstation["content_hash"],
                    },
                    {
                        "id": "same",
                        "path": laptop_path.name,
                        "content_hash": laptop["content_hash"],
                    },
                ],
                "roles": [],
                "handoffs": [],
                "dependencies": [],
                "host_overrides": [],
            }
        )
        fleet_path = self.root / "fleet.json"
        self._write(fleet_path, with_content_hash(fleet))
        with self.assertRaisesRegex(ValueError, "duplicate fleet member id"):
            resolve_fleet(fleet_path, [paths["catalog"]])

    def _laptop_instance(self, workstation: dict[str, object]) -> Path:
        laptop = deepcopy(workstation)
        laptop.update(
            {
                "id": "laptop-instance",
                "instance_id": "test-instance@host-b",
                "host_id": "host-b",
            }
        )
        laptop_path = self.root / "laptop-instance.json"
        self._write(laptop_path, with_content_hash(laptop))
        return laptop_path

    def _write_fleet(
        self,
        paths: dict[str, Path],
        workstation: dict[str, object],
        laptop_path: Path,
    ) -> Path:
        laptop = self._read(laptop_path)
        fleet = self._common("ellmos.fleet.v1", "test-fleet")
        fleet.update(
            {
                "systems": [
                    {
                        "id": "workstation",
                        "path": paths["instance"].name,
                        "content_hash": workstation["content_hash"],
                    },
                    {
                        "id": "laptop",
                        "path": laptop_path.name,
                        "content_hash": laptop["content_hash"],
                    },
                ],
                "roles": [{"system": "workstation", "role": "development-primary"}],
                "handoffs": [
                    {"source": "workstation", "target": "laptop", "kind": "sync"}
                ],
                "dependencies": [{"source": "workstation", "target": "laptop"}],
                "host_overrides": [
                    {
                        "host_id": "host-b",
                        "reason": "Laptop intentionally omits the optional UI.",
                        "component_states": {
                            "module:optional-ui": {"status": "suppressed"}
                        },
                        "tolerated_gaps": ["system.ui"],
                    }
                ],
            }
        )
        fleet_path = self.root / "fleet.json"
        self._write(fleet_path, with_content_hash(fleet))
        return fleet_path

    def _write_fixture(
        self,
        *,
        fallback_cycle: bool = False,
        suppress_optional: bool = True,
        use_stack: bool = False,
        host_id: str = "host-a",
        component_states: dict[str, object] | None = None,
    ) -> dict[str, Path]:
        bundle_dir = self.root / "bundles" / "core"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        components = [
            {
                "type": "module",
                "ref": "module:mapper",
                "role": "mapper",
                "requirement": "required",
                "version": "1.0.0",
                "provides": ["system.map"],
                "consumes": [],
                **({"fallback": "module:optional-ui"} if fallback_cycle else {}),
            },
            {
                "type": "interface",
                "ref": "module:optional-ui",
                "role": "viewer",
                "requirement": "optional",
                "commit": "0123456789abcdef",
                "provides": ["system.ui"],
                "consumes": ["system.map"],
                "fallback": "module:mapper" if fallback_cycle else "module:mapper",
            },
        ]
        bundle = self._common(
            "ellmos.bundle.v1",
            "ellmos-core-discovery-bundle",
        )
        bundle.update(
            {
                "display_name": "Core discovery",
                "purpose": ["Resolve system composition"],
                "visibility": "private",
                "assurance_contract": "assurance://core",
                "components": components,
                "profiles": {
                    "default": {
                        "include": [],
                        "exclude": (
                            ["module:optional-ui"]
                            if suppress_optional and not fallback_cycle
                            else []
                        ),
                        "overrides": {},
                    }
                },
            }
        )
        bundle = with_content_hash(bundle)
        bundle_path = bundle_dir / "bundle.json"
        self._write(bundle_path, bundle)

        catalog = self._common("ellmos.bundles.catalog.v1", "test-catalog")
        catalog["bundles"] = [
            {
                "id": bundle["id"],
                "path": "bundles/core",
                "manifest": "bundle.json",
                "visibility": "private",
                "status": "available",
            }
        ]
        catalog_path = self.root / "catalog.json"
        self._write(catalog_path, with_content_hash(catalog))

        bundle_ref = {
            "ref": bundle["id"],
            "version": bundle["version"],
        }
        stack_refs: list[dict[str, str]] = []
        bundle_refs = [bundle_ref]
        if use_stack:
            stack = {
                "schema": "ellmos.stack.v2",
                "id": "legacy-stack",
                "version": "2.0.0",
                "bundle_refs": [bundle_ref],
            }
            stack_path = self.root / "stack.json"
            self._write(stack_path, stack)
            stack_refs = [
                {
                    "path": stack_path.name,
                    "content_hash": canonical_content_hash(stack),
                }
            ]
            bundle_refs = []

        system = self._system(
            bundle_refs=bundle_refs,
            stack_refs=stack_refs,
            profiles={
                "default": {
                    "include": [bundle["id"]],
                    "exclude": [],
                    "overrides": {},
                }
            },
            output_bindings=[
                {
                    "kind": "audit_receipt",
                    "owner_ref": "ellmos-governance-assurance-bundle",
                    "storage_uri": "governance://receipts",
                    "visibility": "private",
                    "raw_content_allowed": False,
                }
            ],
        )
        system_path = self.root / "system.json"
        self._write(system_path, system)

        instance = self._common("ellmos.system-instance.v1", "test-instance")
        instance.update(
            {
                "instance_id": f"test-instance@{host_id}",
                "system_ref": {
                    "path": system_path.name,
                    "version": system["version"],
                },
                "host_id": host_id,
                "desired_profile": "default",
                "component_states": component_states or {},
                "desired_sources": [],
                "evidence_refs": [],
                "output_bindings": [
                    {
                        "kind": "runtime_log",
                        "owner_ref": "automation-runtime",
                        "storage_uri": "host-local://logs/system-explorer",
                        "visibility": "private",
                        "retention": "P30D",
                        "raw_content_allowed": True,
                    }
                ],
            }
        )
        instance_path = self.root / "instance.json"
        self._write(instance_path, with_content_hash(instance))
        return {
            "bundle": bundle_path,
            "catalog": catalog_path,
            "system": system_path,
            "instance": instance_path,
        }

    def _system(self, **overrides: object) -> dict[str, object]:
        system = self._common("ellmos.system.v1", "test-system")
        system.update(
            {
                "purpose": ["Test composition"],
                "bundle_refs": [],
                "stack_refs": [],
                "profiles": {"default": {"include": [], "exclude": [], "overrides": {}}},
                "bindings": [],
                "output_bindings": [],
                "assurance_contract": "assurance://test",
            }
        )
        system.update(overrides)
        return with_content_hash(system)

    def _valid_output_bindings(self) -> list[dict[str, object]]:
        return [
            {
                "kind": "runtime_log",
                "owner_ref": "automation-runtime",
                "storage_uri": "host-local://logs/automation-runtime",
                "visibility": "private",
                "retention": "P30D",
                "raw_content_allowed": True,
            },
            {
                "kind": "decision_request",
                "owner_ref": "ellmos-governance-assurance-bundle",
                "storage_uri": "control-center://_DECISIONS/TO-DECIDE-USER",
                "visibility": "private",
                "raw_content_allowed": False,
            },
            {
                "kind": "automation_summary",
                "owner_ref": "ellmos-automation-control-bundle",
                "storage_uri": "user://.USR/logs/automation/24h",
                "visibility": "private",
                "raw_content_allowed": False,
            },
            {
                "kind": "audit_receipt",
                "owner_ref": "ellmos-governance-assurance-bundle",
                "storage_uri": "governance://receipts",
                "visibility": "private",
                "raw_content_allowed": False,
            },
            {
                "kind": "one_off_report",
                "owner_ref": "system-explorer",
                "storage_uri": "desktop://report.md",
                "backup_uri": "user://.USR/reports/report.md",
                "visibility": "private",
                "raw_content_allowed": False,
            },
        ]

    def _common(self, schema: str, manifest_id: str) -> dict[str, object]:
        return {
            "schema": schema,
            "id": manifest_id,
            "version": "1.0.0",
            "status": "active",
            "lifecycle": "active",
            "authority": {"owner": "test"},
            "provenance": {"source": "unit-test"},
        }

    def _write(self, path: Path, value: dict[str, object]) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _read(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
