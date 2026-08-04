from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from system_explorer.contracts import canonical_content_hash
from system_explorer.coverage import coverage_report
from system_explorer.federation import tag_current_system
from system_explorer.manifests import new_module_manifest
from system_explorer.resolution_bridge import import_resolution
from system_explorer.resources import register_software_resources
from system_explorer.scanner import scan
from system_explorer.store import Store


FIXTURE = Path(__file__).parent / "fixtures" / "resolution.v1.json"


class ScannerIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scan_root = self.root / "scan"
        self.scan_root.mkdir()
        self.db = self.root / "state" / "evidence.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _config(self) -> dict[str, object]:
        return {
            "_base": str(self.root),
            "roots": [
                {
                    "id": "fixture",
                    "path": str(self.scan_root),
                    "max_depth": 5,
                    "include": ["*.md", "*.json"],
                    "exclude_dirs": [".git"],
                }
            ],
            "privacy": {"sensitivity": "test"},
            "system": {"id": "TEST-HOST", "level": "own-system"},
        }

    def _write_module(
        self, directory: str, module_id: str, provides: list[str]
    ) -> Path:
        path = self.scan_root / directory / "ellmos-module.v2.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        value = new_module_manifest(
            module_id=module_id,
            display_name=module_id,
            category="runtime",
            kind="service",
            repository=None,
        )
        value["provides"] = provides
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def _resolution(
        self, provider_ref: str, function_name: str = "function.required"
    ) -> Path:
        value = json.loads(FIXTURE.read_text(encoding="utf-8"))
        component = value["bundles"][0]["components"][0]
        component["ref"] = provider_ref
        component["provides"] = [function_name]
        if function_name != "function.required":
            value["functions"] = [
                function_name if item == "function.required" else item
                for item in value["functions"]
            ]
        value["content_hash"] = canonical_content_hash(value)
        path = self.root / "resolution.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_valid_module_manifest_gets_exact_host_bound_component_ref(self) -> None:
        self._write_module("module-a", "module-a", ["function.required"])

        with Store(self.db) as store:
            scan(self._config(), store)
            tag_current_system(self._config(), store)
            node = next(
                item
                for item in store.nodes("carrier")
                if item["id"] == "carrier:module-a"
            )
            claims = store.db.execute(
                "SELECT * FROM component_identity_claims"
            ).fetchall()

        self.assertEqual(node["metadata"]["component_ref"], "module:module-a")
        self.assertEqual(node["metadata"]["identity_status"], "verified")
        self.assertEqual(
            node["metadata"]["identity_source_kind"], "ellmos.module.v2"
        )
        self.assertEqual(node["metadata"]["origin_system"], "TEST-HOST")
        self.assertEqual(len(claims), 1)

    def test_invalid_module_and_name_only_skill_remain_unbound(self) -> None:
        invalid = self.scan_root / "invalid" / "ellmos-module.v2.json"
        invalid.parent.mkdir()
        invalid.write_text(
            json.dumps(
                {
                    "schema": "ellmos.module.v2",
                    "id": "invalid",
                    "provides": ["function.required"],
                }
            ),
            encoding="utf-8",
        )
        skill = self.scan_root / "skills" / "mapper" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: mapper\ntags: [mapping]\n---\n# Mapper\n",
            encoding="utf-8",
        )

        with Store(self.db) as store:
            scan(self._config(), store)
            carriers = {node["id"]: node for node in store.nodes("carrier")}

        self.assertNotIn(
            "component_ref", carriers["carrier:invalid"]["metadata"]
        )
        self.assertNotIn(
            "component_ref", carriers["carrier:skill:mapper"]["metadata"]
        )

    def test_module_id_with_profile_separator_is_not_promoted(self) -> None:
        self._write_module(
            "profile-like", "ellmos-core:library", ["function.required"]
        )

        with Store(self.db) as store:
            scan(self._config(), store)
            node = next(
                item
                for item in store.nodes("carrier")
                if item["id"] == "carrier:ellmos-core:library"
            )

        self.assertNotIn("component_ref", node["metadata"])

    def test_explicit_skill_ref_is_bound_without_name_derivation(self) -> None:
        skill = self.scan_root / "skills" / "local-name" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\n"
            "name: local-name\n"
            "component_ref: skill:infrastructure:canonical-name\n"
            "tags: [mapping]\n"
            "---\n# Mapper\n",
            encoding="utf-8",
        )

        with Store(self.db) as store:
            scan(self._config(), store)
            node = next(
                item
                for item in store.nodes("carrier")
                if item["id"] == "carrier:skill:local-name"
            )

        self.assertEqual(
            node["metadata"]["component_ref"],
            "skill:infrastructure:canonical-name",
        )
        self.assertEqual(node["metadata"]["identity_status"], "verified")

    def test_duplicate_sources_fail_closed_then_deleted_duplicate_recovers(self) -> None:
        self._write_module("first", "duplicate", ["function.required"])
        second = self._write_module(
            "second", "duplicate", ["function.required"]
        )

        with Store(self.db) as store:
            scan(self._config(), store)
            conflict = next(
                node
                for node in store.nodes("carrier")
                if node["id"] == "carrier:duplicate"
            )
            self.assertEqual(
                conflict["metadata"]["identity_status"], "conflict"
            )
            self.assertNotIn("component_ref", conflict["metadata"])
            self.assertEqual(
                store.db.execute(
                    "SELECT COUNT(*) FROM component_identity_claims"
                ).fetchone()[0],
                2,
            )

            second.unlink()
            scan(self._config(), store)
            recovered = next(
                node
                for node in store.nodes("carrier")
                if node["id"] == "carrier:duplicate"
            )
            claim_count = store.db.execute(
                "SELECT COUNT(*) FROM component_identity_claims"
            ).fetchone()[0]

        self.assertEqual(recovered["metadata"]["identity_status"], "verified")
        self.assertEqual(
            recovered["metadata"]["component_ref"], "module:duplicate"
        )
        self.assertEqual(claim_count, 1)

    def test_missing_scan_root_invalidates_previous_identity_claim(self) -> None:
        self._write_module("module-a", "module-a", ["function.required"])
        config = self._config()

        with Store(self.db) as store:
            scan(config, store)
            moved = self.root / "scan-offline"
            self.scan_root.rename(moved)
            stats = scan(config, store)
            node = next(
                item
                for item in store.nodes("carrier")
                if item["id"] == "carrier:module-a"
            )
            claim_count = store.db.execute(
                "SELECT COUNT(*) FROM component_identity_claims"
            ).fetchone()[0]

        self.assertEqual(stats["errors"], 1)
        self.assertEqual(node["metadata"]["identity_status"], "unbound")
        self.assertNotIn("component_ref", node["metadata"])
        self.assertEqual(claim_count, 0)

    def test_unhashed_software_config_ref_cannot_cover_resolution(self) -> None:
        resolution = self._resolution("software:configured-only")
        installed = self.root / "configured.exe"
        installed.write_bytes(b"fixture")

        with Store(self.db) as store:
            software = store.add_node(
                "software_resource",
                "Legacy configured resource",
                node_id="software:configured-only",
                metadata={
                    "component_ref": "software:configured-only",
                    "identity_status": "verified",
                    "identity_evidence_id": "legacy-spoof",
                    "identity_source_sha256": "legacy-spoof",
                },
            )
            store.add_node(
                "function",
                "function.required",
                node_id="function:function.required",
            )
            store.add_edge(
                software,
                "carries",
                "function:function.required",
                mode="actual",
                status="full",
            )
            store.commit()

        with Store(self.db) as store:
            migrated = next(
                node
                for node in store.nodes("software_resource")
                if node["id"] == "software:configured-only"
            )
            self.assertNotIn("component_ref", migrated["metadata"])
            self.assertNotIn("identity_status", migrated["metadata"])
            config = {
                "_base": str(self.root),
                "software_resources": [
                    {
                        "id": "configured-only",
                        "path": str(installed),
                        "component_ref": "software:configured-only",
                        "identity_status": "verified",
                        "identity_evidence_id": "spoofed-evidence",
                        "identity_source_sha256": "spoofed-hash",
                        "functions": ["function.required"],
                    }
                ],
            }
            register_software_resources(config, store)
            tag_current_system(self._config(), store)
            import_resolution(resolution, store)
            software = next(
                node
                for node in store.nodes("software_resource")
                if node["id"] == "software:configured-only"
            )
            report = coverage_report(store)

        required = next(
            row
            for row in report["functions"]
            if row["function"]["name"] == "function.required"
        )
        self.assertEqual(
            required["desired_by_scope"][0]["verdict"], "wrong-provider"
        )
        self.assertEqual(
            required["desired_by_scope"][0]["actual_provider_edges"], 0
        )
        self.assertNotIn("component_ref", software["metadata"])
        self.assertNotIn("identity_status", software["metadata"])
        self.assertEqual(
            software["metadata"]["declared_component_ref"],
            "software:configured-only",
        )

    def test_exact_provider_and_function_are_required_for_coverage(self) -> None:
        self._write_module("module-a", "module-a", ["function.required"])
        exact_resolution = self._resolution("module:module-a")

        with Store(self.db) as store:
            scan(self._config(), store)
            tag_current_system(self._config(), store)
            import_resolution(exact_resolution, store)
            exact = coverage_report(store)

        required = next(
            row
            for row in exact["functions"]
            if row["function"]["name"] == "function.required"
        )
        self.assertEqual(required["desired_by_scope"][0]["verdict"], "partial")

        mismatch_db = self.root / "state" / "mismatch.db"
        case_resolution = self._resolution("module:MODULE-A")
        with Store(mismatch_db) as store:
            scan(self._config(), store)
            tag_current_system(self._config(), store)
            import_resolution(case_resolution, store)
            mismatch = coverage_report(store)

        required = next(
            row
            for row in mismatch["functions"]
            if row["function"]["name"] == "function.required"
        )
        self.assertEqual(
            required["desired_by_scope"][0]["verdict"], "wrong-provider"
        )

        function_db = self.root / "state" / "function-mismatch.db"
        function_resolution = self._resolution(
            "module:module-a", "function.other"
        )
        with Store(function_db) as store:
            scan(self._config(), store)
            tag_current_system(self._config(), store)
            import_resolution(function_resolution, store)
            function_mismatch = coverage_report(store)

        other = next(
            row
            for row in function_mismatch["functions"]
            if row["function"]["name"] == "function.other"
        )
        self.assertEqual(other["desired_by_scope"][0]["verdict"], "uncovered")

    def test_subsystem_composition_scans_outside_git_with_verified_pin(self) -> None:
        child = self._system_manifest("child-system")
        child_path = (
            self.scan_root / "systems" / "products" / "child" / "system.v1.json"
        )
        child_path.parent.mkdir(parents=True)
        child_path.write_text(json.dumps(child), encoding="utf-8")
        parent = self._system_manifest(
            "parent-system",
            subsystem_refs=[
                {
                    "path": "systems/products/child/system.v1.json",
                    "content_hash": child["content_hash"],
                    "profile": "default",
                    "role": "child-service",
                }
            ],
        )
        parent_path = (
            self.scan_root / "systems" / "products" / "parent" / "system.v1.json"
        )
        parent_path.parent.mkdir(parents=True)
        parent_path.write_text(json.dumps(parent), encoding="utf-8")

        with Store(self.db) as store:
            scan(self._config(), store)
            edges = store.db.execute(
                "SELECT status, metadata_json FROM edges WHERE relation = 'composes'"
            ).fetchall()

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["status"], "declared")
        self.assertTrue(json.loads(edges[0]["metadata_json"])["pin_verified"])

    def test_subsystem_scanner_does_not_trust_unpinned_or_invalid_targets(self) -> None:
        child = self._system_manifest("child-system")
        child_path = self.scan_root / "child.json"
        child_path.write_text(json.dumps(child), encoding="utf-8")
        unpinned = self._system_manifest(
            "unpinned-parent",
            subsystem_refs=[
                {
                    "path": "child.json",
                    "profile": "default",
                    "role": "child-service",
                }
            ],
        )
        (self.scan_root / "unpinned.json").write_text(
            json.dumps(unpinned), encoding="utf-8"
        )
        wrong_pin = self._system_manifest(
            "wrong-pin-parent",
            subsystem_refs=[
                {
                    "path": "child.json",
                    "content_hash": "0" * 64,
                    "profile": "default",
                    "role": "child-service",
                }
            ],
        )
        (self.scan_root / "wrong-pin.json").write_text(
            json.dumps(wrong_pin), encoding="utf-8"
        )
        child["content_hash"] = "f" * 64
        child_path.write_text(json.dumps(child), encoding="utf-8")

        with Store(self.db) as store:
            scan(self._config(), store)
            edges = store.db.execute(
                "SELECT status FROM edges WHERE relation = 'composes'"
            ).fetchall()

        self.assertEqual(edges, [])

    def test_subsystem_scanner_marks_wrong_pin_unproven(self) -> None:
        child = self._system_manifest("child-system")
        (self.scan_root / "child.json").write_text(
            json.dumps(child), encoding="utf-8"
        )
        parent = self._system_manifest(
            "parent-system",
            subsystem_refs=[
                {
                    "path": "child.json",
                    "content_hash": "0" * 64,
                    "profile": "default",
                    "role": "child-service",
                }
            ],
        )
        (self.scan_root / "parent.json").write_text(
            json.dumps(parent), encoding="utf-8"
        )

        with Store(self.db) as store:
            scan(self._config(), store)
            edges = store.db.execute(
                "SELECT status, metadata_json FROM edges WHERE relation = 'composes'"
            ).fetchall()

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["status"], "unproven")
        self.assertFalse(json.loads(edges[0]["metadata_json"])["pin_verified"])

    def _system_manifest(
        self, system_id: str, **overrides: object
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": "ellmos.system.v1",
            "id": system_id,
            "version": "1.0.0",
            "status": "active",
            "lifecycle": "active",
            "authority": {"owner": "test"},
            "provenance": {"source": "unit-test"},
            "purpose": ["Test subsystem scan"],
            "bundle_refs": [],
            "stack_refs": [],
            "profiles": {
                "default": {"include": [], "exclude": [], "overrides": {}}
            },
            "bindings": [],
            "output_bindings": [],
            "assurance_contract": "assurance://test",
        }
        value.update(overrides)
        value["content_hash"] = canonical_content_hash(value)
        return value
