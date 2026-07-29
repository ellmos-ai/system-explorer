from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from system_explorer.cli import main
from system_explorer.contracts import (
    canonical_content_hash,
    validate_contract,
    with_content_hash,
)
from system_explorer.manifests import validate_manifest
from system_explorer.resolver import (
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
            "ellmos.system.v1.schema.json",
            "ellmos.system-instance.v1.schema.json",
            "ellmos.system-test.v1.schema.json",
            "ellmos.fleet.v1.schema.json",
        }
        for name in names:
            value = json.loads((schema_dir / name).read_text(encoding="utf-8"))
            self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("content_hash", value["required"])

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

    def _write_fixture(
        self,
        *,
        fallback_cycle: bool = False,
        suppress_optional: bool = True,
        use_stack: bool = False,
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
                "instance_id": "test-instance@host-a",
                "system_ref": {
                    "path": system_path.name,
                    "version": system["version"],
                },
                "host_id": "host-a",
                "desired_profile": "default",
                "component_states": {},
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
