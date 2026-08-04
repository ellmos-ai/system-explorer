from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path

from system_explorer.cli import _activation_enforcement_status, main
from system_explorer.component_registry import inspect_component_registry
from system_explorer.contracts import (
    canonical_content_hash,
    validate_contract,
    with_content_hash,
)
from system_explorer.resolver import resolve_system


class ComponentRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.contract_path = self.root / "component-contract.json"
        self.contract = with_content_hash(
            {
                "schema": "ellmos.component-registry-resolution-contract.v1",
                "id": "component-registry-resolution-v1",
                "version": "1.0.0",
            }
        )
        self._write(self.contract_path, self.contract)
        self.module_source = self.root / "modules.json"
        self._write(
            self.module_source,
            {
                "modules": [
                    {"id": "native-module"},
                ]
            },
        )
        self.crosswalk_source = self.root / "skills.crosswalk.json"
        self._write(
            self.crosswalk_source,
            {
                "skills": {
                    "skill:native": {
                        "registry_component_id": "skill:registry:native",
                        "source_path": "skills/native/SKILL.md",
                    }
                }
            },
        )
        self.skill_source = self.root / "skills.json"
        self._write(
            self.skill_source,
            {
                "components": [
                    {"id": "skill:registry:native"},
                ]
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_contract_component_type_and_registry_schema_are_supported(self) -> None:
        bundle = self._bundle(
            "contract-bundle",
            [
                self._component(
                    "contract",
                    "contract:tenant-context",
                    "required",
                )
            ],
        )
        self.assertEqual(validate_contract(bundle), [])
        registry = self._registry(
            bindings={},
            declared_only={
                "contract:tenant-context": {
                    "component_type": "contract",
                    "reason": "planned contract has no native registry record",
                }
            },
        )
        self.assertEqual(validate_contract(registry), [])
        registry_path = self.root / "bindings.json"
        bundle_path = self.root / "contract-bundle.json"
        forged = deepcopy(registry)
        forged["contract"]["ref"] = "contract:UNRELATED"
        self._write(registry_path, with_content_hash(forged))
        self._write(bundle_path, bundle)
        with self.assertRaisesRegex(ValueError, "does not match the loaded contract ID"):
            inspect_component_registry(registry_path, [bundle_path])

    def test_unknown_source_id_fails_even_with_recomputed_content_hash(self) -> None:
        registry = self._registry(
            bindings={
                "module": {
                    "module:native": {
                        "source": "registry:modules",
                        "record_id": "native-module",
                    }
                }
            }
        )
        forged = deepcopy(registry)
        forged["bindings"]["module"]["module:native"]["source"] = (
            "registry:NONEXISTENT"
        )
        forged = with_content_hash(forged)
        errors = validate_contract(forged)
        self.assertTrue(any("unknown source" in error for error in errors))

    def test_host_fields_and_unapproved_type_source_are_rejected(self) -> None:
        registry = self._registry(bindings={})
        host_bound = deepcopy(registry)
        host_bound["authority"]["host_id"] = "TEST-HOST"
        host_bound["provenance"]["observed_on"] = "TEST-HOST"
        errors = validate_contract(with_content_hash(host_bound))
        self.assertTrue(any("$.authority.host_id is unsupported" in item for item in errors))
        self.assertTrue(
            any("$.provenance.observed_on is unsupported" in item for item in errors)
        )

        wrong_source = deepcopy(registry)
        wrong_source["bindings"] = {
            "policy_document": {
                "policy:wrong-source": {
                    "source": "registry:modules",
                    "record_id": "native-module",
                }
            }
        }
        errors = validate_contract(with_content_hash(wrong_source))
        self.assertTrue(
            any("no approved native source kind" in item for item in errors)
        )

    def test_native_source_record_and_skill_crosswalk_are_both_verified(self) -> None:
        registry_path = self.root / "bindings.json"
        registry = self._registry(
            bindings={
                "module": {
                    "module:native": {
                        "source": "registry:modules",
                        "record_id": "native-module",
                    }
                },
                "skill": {
                    "skill:native": {
                        "source": "registry:skills",
                        "record_id": "skill:registry:native",
                        "crosswalk_source": "crosswalk:skills",
                        "crosswalk_record_id": "skill:native",
                    }
                },
            }
        )
        self._write(registry_path, registry)
        bundle_path = self.root / "bundle.json"
        self._write(
            bundle_path,
            self._bundle(
                "native-bundle",
                [
                    self._component("module", "module:native", "required"),
                    self._component("skill", "skill:native", "recommended"),
                ],
            ),
        )
        report, code = inspect_component_registry(
            registry_path,
            [bundle_path],
            source_paths={
                "registry:modules": self.module_source,
                "registry:skills": self.skill_source,
                "crosswalk:skills": self.crosswalk_source,
            },
            activation_bundle_ids=["native-bundle"],
            observed_on="TEST-HOST",
            observed_at="2026-07-30T00:00:00Z",
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "verified")
        self.assertTrue(report["source_verification_complete"])
        self.assertEqual(report["observed_on"], "TEST-HOST")

        altered = json.loads(self.crosswalk_source.read_text(encoding="utf-8"))
        altered["skills"]["skill:native"]["registry_component_id"] = "wrong"
        self._write(self.crosswalk_source, altered)
        report, code = inspect_component_registry(
            registry_path,
            [bundle_path],
            source_paths={
                "registry:modules": self.module_source,
                "registry:skills": self.skill_source,
                "crosswalk:skills": self.crosswalk_source,
            },
        )
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "source-verification-failed")
        self.assertTrue(
            any("crosswalk:skills: source sha256 mismatch" in item for item in report["source_errors"])
        )
        self.assertTrue(
            any("registry_component_id" in item for item in report["source_errors"])
        )

    def test_declared_only_severity_is_occurrence_local(self) -> None:
        registry_path = self.root / "bindings.json"
        self._write(
            registry_path,
            self._registry(
                bindings={},
                declared_only={
                    "module:planned": {
                        "component_type": "module",
                        "reason": "not registered yet",
                    }
                },
            ),
        )
        required_path = self.root / "required.json"
        optional_path = self.root / "optional.json"
        self._write(
            required_path,
            self._bundle(
                "required-bundle",
                [self._component("module", "module:planned", "required")],
            ),
        )
        self._write(
            optional_path,
            self._bundle(
                "optional-bundle",
                [self._component("module", "module:planned", "optional")],
            ),
        )
        report, code = inspect_component_registry(
            registry_path,
            [required_path, optional_path],
            activation_bundle_ids=["required-bundle", "optional-bundle"],
        )
        self.assertEqual(code, 3)
        self.assertEqual(report["activation"]["required-bundle"]["state"], "blocked")
        self.assertEqual(
            report["activation"]["optional-bundle"]["state"],
            "resolved-with-optional-gaps",
        )
        self.assertEqual(
            report["activation"]["optional-bundle"]["required_unresolved"],
            [],
        )

    def test_cli_writes_explicit_native_receipt(self) -> None:
        registry_path = self.root / "bindings.json"
        self._write(
            registry_path,
            self._registry(
                bindings={
                    "module": {
                        "module:native": {
                            "source": "registry:modules",
                            "record_id": "native-module",
                        }
                    }
                }
            ),
        )
        bundle_path = self.root / "bundle.json"
        self._write(
            bundle_path,
            self._bundle(
                "native-bundle",
                [self._component("module", "module:native", "required")],
            ),
        )
        output = self.root / "receipt.json"
        code = main(
            [
                "component-registry-check",
                str(registry_path),
                "--bundle",
                str(bundle_path),
                "--source-path",
                f"registry:modules={self.module_source}",
                "--source-path",
                f"registry:skills={self.skill_source}",
                "--source-path",
                f"crosswalk:skills={self.crosswalk_source}",
                "--activation-check",
                "native-bundle",
                "--observed-on",
                "TEST-HOST",
                "--observed-at",
                "2026-07-30T00:00:00Z",
                "--output",
                str(output),
            ]
        )
        self.assertEqual(code, 0)
        receipt = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "verified")
        self.assertEqual(receipt["observed_on"], "TEST-HOST")

    def test_system_resolver_consumes_registry_and_fails_closed(self) -> None:
        bundle_path, catalog_path, system_path, instance_path = (
            self._system_fixture("optional")
        )
        registry_path = self.root / "bindings.json"
        self._write(
            registry_path,
            self._registry(
                bindings={},
                declared_only={
                    "module:planned": {
                        "component_type": "module",
                        "reason": "not registered yet",
                    }
                },
            ),
        )
        result = resolve_system(
            instance_path,
            [catalog_path],
            registry_bindings_path=registry_path,
        )
        component = result["bundles"][0]["components"][0]
        self.assertEqual(component["desired_status"], "unavailable")
        self.assertEqual(
            component["registry_resolution"]["class"],
            "declared-only",
        )
        self.assertEqual(
            result["component_registry"]["activation"]["fixture-bundle"]["state"],
            "resolved-with-optional-gaps",
        )

        required = json.loads(bundle_path.read_text(encoding="utf-8"))
        required["components"][0]["requirement"] = "required"
        self._write(bundle_path, with_content_hash(required))
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        self._write(catalog_path, with_content_hash(catalog))
        with self.assertRaisesRegex(ValueError, "activation blocked"):
            resolve_system(
                instance_path,
                [catalog_path],
                registry_bindings_path=registry_path,
            )

    def test_blocked_evidence_view_quarantines_the_entire_bundle(
        self,
    ) -> None:
        bundle_path, catalog_path, _, instance_path = self._system_fixture(
            "required"
        )
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle["components"].append(
            self._component("module", "module:native", "required")
        )
        self._write(bundle_path, with_content_hash(bundle))
        registry_path = self.root / "bindings.json"
        self._write(
            registry_path,
            self._registry(
                bindings={
                    "module": {
                        "module:native": {
                            "source": "registry:modules",
                            "record_id": "native-module",
                        }
                    }
                },
                declared_only={
                    "module:planned": {
                        "component_type": "module",
                        "reason": "not registered yet",
                    }
                },
            ),
        )

        result = resolve_system(
            instance_path,
            [catalog_path],
            registry_bindings_path=registry_path,
            registry_source_paths={"registry:modules": self.module_source},
            emit_blocked_resolution=True,
        )

        components = {
            item["ref"]["ref"]: item
            for item in result["bundles"][0]["components"]
        }
        registry = result["component_registry"]
        self.assertEqual(components["module:planned"]["desired_status"], "unavailable")
        self.assertEqual(components["module:native"]["desired_status"], "unavailable")
        self.assertEqual(components["module:native"]["provides"], [])
        quarantine = components["module:native"]["activation_quarantine"]
        self.assertEqual(quarantine["declared_desired_status"], "configured")
        self.assertEqual(quarantine["declared_provides"], ["function.module:native"])
        self.assertEqual(result["functions"], [])
        self.assertEqual(
            registry["activation"]["fixture-bundle"]["state"],
            "blocked",
        )
        self.assertTrue(
            registry["activation"]["fixture-bundle"]["quarantined"]
        )
        self.assertEqual(
            registry["activation_enforcement"],
            "blocked-evidence-only",
        )
        self.assertEqual(registry["source_verification"], "verified")
        self.assertTrue(
            any("operational resolution" in warning for warning in result["warnings"])
        )

        output = self.root / "preserved-resolution.json"
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = main(
                [
                    "system-resolve",
                    str(instance_path),
                    "--catalog",
                    str(catalog_path),
                    "--registry-bindings",
                    str(registry_path),
                    "--registry-source-path",
                    f"registry:modules={self.module_source}",
                    "--emit-blocked-resolution",
                    "--output",
                    str(output),
                ]
            )
        self.assertEqual(code, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["activation_status"], "blocked-evidence-only")
        written = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(written["content_hash"], result["content_hash"])

        child_only = {
            "component_registry": {"source_verification": "verified"},
            "subsystems": [
                {
                    "resolution": {
                        "component_registry": {
                            "activation_enforcement": "blocked-evidence-only"
                        },
                        "subsystems": [],
                    }
                }
            ],
        }
        self.assertEqual(
            _activation_enforcement_status(child_only),
            "blocked-evidence-only",
        )

    def test_system_resolver_requires_native_source_record_readback(self) -> None:
        _, catalog_path, _, instance_path = self._system_fixture(
            "required",
            component_ref="module:native",
        )
        registry_path = self.root / "bindings.json"
        registry = self._registry(
            bindings={
                "module": {
                    "module:native": {
                        "source": "registry:modules",
                        "record_id": "native-module",
                    }
                }
            }
        )
        self._write(registry_path, registry)
        with self.assertRaisesRegex(ValueError, "source path was not supplied"):
            resolve_system(
                instance_path,
                [catalog_path],
                registry_bindings_path=registry_path,
            )
        result = resolve_system(
            instance_path,
            [catalog_path],
            registry_bindings_path=registry_path,
            registry_source_paths={"registry:modules": self.module_source},
        )
        component = result["bundles"][0]["components"][0]
        self.assertEqual(
            component["registry_resolution"]["class"],
            "native-binding",
        )
        self.assertEqual(
            result["component_registry"]["source_verification"],
            "verified",
        )

        forged = deepcopy(registry)
        forged["bindings"]["module"]["module:native"]["record_id"] = "NONEXISTENT"
        self._write(registry_path, with_content_hash(forged))
        with self.assertRaisesRegex(ValueError, "record_id 'NONEXISTENT' is missing"):
            resolve_system(
                instance_path,
                [catalog_path],
                registry_bindings_path=registry_path,
                registry_source_paths={"registry:modules": self.module_source},
            )

        self._write(
            self.module_source,
            {
                "modules": [
                    {"id": "native-module"},
                    {"id": "native-module", "role": "conflicting-duplicate"},
                ]
            },
        )
        duplicate_registry = deepcopy(registry)
        duplicate_registry["sources"]["registry:modules"]["sha256"] = (
            self._file_hash(self.module_source)
        )
        self._write(registry_path, with_content_hash(duplicate_registry))
        with self.assertRaisesRegex(ValueError, "duplicate record IDs"):
            resolve_system(
                instance_path,
                [catalog_path],
                registry_bindings_path=registry_path,
                registry_source_paths={"registry:modules": self.module_source},
            )

    def test_system_resolver_applies_registry_gate_to_nested_subsystems(self) -> None:
        _, catalog_path, system_path, instance_path = self._system_fixture(
            "required",
            component_ref="module:native",
        )
        parent = json.loads(system_path.read_text(encoding="utf-8"))
        child = deepcopy(parent)
        child["id"] = "fixture-child-system"
        child = with_content_hash(child)
        child_path = self.root / "child-system.json"
        self._write(child_path, child)
        parent["subsystem_refs"] = [
            {
                "path": child_path.name,
                "content_hash": child["content_hash"],
                "profile": "default",
                "role": "child-service",
            }
        ]
        self._write(system_path, with_content_hash(parent))
        registry_path = self.root / "bindings.json"
        self._write(
            registry_path,
            self._registry(
                bindings={
                    "module": {
                        "module:native": {
                            "source": "registry:modules",
                            "record_id": "native-module",
                        }
                    }
                }
            ),
        )

        result = resolve_system(
            instance_path,
            [catalog_path],
            registry_bindings_path=registry_path,
            registry_source_paths={"registry:modules": self.module_source},
        )
        child_result = result["subsystems"][0]["resolution"]
        self.assertEqual(
            child_result["bundles"][0]["components"][0]["registry_resolution"][
                "class"
            ],
            "native-binding",
        )
        self.assertEqual(
            child_result["component_registry"]["source_verification"],
            "verified",
        )
        self.assertEqual(
            child_result["content_hash"],
            canonical_content_hash(child_result),
        )

    def _registry(
        self,
        *,
        bindings: dict[str, object],
        declared_only: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return with_content_hash(
            {
                "schema": "ellmos.component-registry-bindings.v1",
                "id": "test-component-registry",
                "version": "1.0.0",
                "status": "registered",
                "lifecycle": "draft",
                "authority": {
                    "kind": "external-registry-reference",
                    "runtime_authority": False,
                },
                "provenance": {
                    "source_plan": "plan:unit-test",
                    "repository": "system-explorer",
                },
                "contract": {
                    "ref": "contract:component-registry-resolution-v1",
                    "path": self.contract_path.name,
                    "content_hash": self.contract["content_hash"],
                },
                "sources": {
                    "registry:modules": {
                        "kind": "module-registry",
                        "uri": "test://modules",
                        "record_collection": "modules",
                        "record_id_field": "id",
                        "sha256": self._file_hash(self.module_source),
                    },
                    "registry:skills": {
                        "kind": "skill-registry",
                        "uri": "test://skills",
                        "record_collection": "components",
                        "record_id_field": "id",
                        "sha256": self._file_hash(self.skill_source),
                    },
                    "crosswalk:skills": {
                        "kind": "skill-crosswalk",
                        "uri": f"repo://{self.crosswalk_source.name}",
                        "record_collection": "skills",
                        "record_id_field": "registry_component_id",
                        "sha256": self._file_hash(self.crosswalk_source),
                    },
                },
                "bindings": bindings,
                "declared_only": declared_only or {},
                "declared_only_policy": {
                    "resolution_class": "declared-only",
                    "runtime_authority": False,
                    "activation_status": "blocked-until-native-registry-record",
                    "may_satisfy_actual_coverage": False,
                },
            }
        )

    def _bundle(
        self,
        bundle_id: str,
        components: list[dict[str, object]],
    ) -> dict[str, object]:
        return with_content_hash(
            {
                **self._common("ellmos.bundle.v1", bundle_id),
                "display_name": bundle_id,
                "purpose": ["unit test"],
                "visibility": "private",
                "assurance_contract": "contract://test",
                "components": components,
                "profiles": {
                    "default": {
                        "include": [],
                        "exclude": [],
                        "overrides": {},
                    }
                },
            }
        )

    def _component(
        self,
        component_type: str,
        ref: str,
        requirement: str,
    ) -> dict[str, object]:
        return {
            "type": component_type,
            "ref": {
                "ref": ref,
                "version": "registry-current",
            },
            "role": "unit-test",
            "requirement": requirement,
            "provides": [f"function.{ref}"],
            "consumes": [],
        }

    def _system_fixture(
        self,
        requirement: str,
        *,
        component_ref: str = "module:planned",
    ) -> tuple[Path, Path, Path, Path]:
        bundle_dir = self.root / "bundles" / "fixture"
        bundle_dir.mkdir(parents=True)
        bundle_path = bundle_dir / "bundle.json"
        bundle = self._bundle(
            "fixture-bundle",
            [self._component("module", component_ref, requirement)],
        )
        self._write(bundle_path, bundle)
        catalog_path = self.root / "catalog.json"
        catalog = with_content_hash(
            {
                **self._common("ellmos.bundles.catalog.v1", "fixture-catalog"),
                "bundles": [
                    {
                        "id": "fixture-bundle",
                        "path": "bundles/fixture",
                        "manifest": "bundle.json",
                        "visibility": "private",
                        "status": "available",
                    }
                ],
            }
        )
        self._write(catalog_path, catalog)
        system_path = self.root / "system.json"
        system = with_content_hash(
            {
                **self._common("ellmos.system.v1", "fixture-system"),
                "purpose": ["unit test"],
                "bundle_refs": [
                    {
                        "ref": "fixture-bundle",
                        "version": "1.0.0",
                    }
                ],
                "stack_refs": [],
                "profiles": {
                    "default": {
                        "include": ["fixture-bundle"],
                        "exclude": [],
                        "overrides": {},
                    }
                },
                "bindings": [],
                "output_bindings": [],
                "assurance_contract": "contract://test",
            }
        )
        self._write(system_path, system)
        instance_path = self.root / "instance.json"
        instance = with_content_hash(
            {
                **self._common("ellmos.system-instance.v1", "fixture-instance"),
                "instance_id": "fixture-instance@TEST-HOST",
                "system_ref": {
                    "path": system_path.name,
                    "version": "1.0.0",
                },
                "host_id": "TEST-HOST",
                "desired_profile": "default",
                "component_states": {},
                "desired_sources": [],
                "evidence_refs": [],
                "output_bindings": [],
            }
        )
        self._write(instance_path, instance)
        return bundle_path, catalog_path, system_path, instance_path

    def _common(self, schema: str, manifest_id: str) -> dict[str, object]:
        return {
            "schema": schema,
            "id": manifest_id,
            "version": "1.0.0",
            "status": "active",
            "lifecycle": "active",
            "authority": {"owner": "unit-test"},
            "provenance": {"source": "unit-test"},
        }

    def _write(self, path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _file_hash(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
