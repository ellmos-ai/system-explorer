from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from system_explorer.assessment import assess
from system_explorer.cli import main
from system_explorer.contracts import canonical_content_hash
from system_explorer.coverage import coverage_report
from system_explorer.proposals import propose
from system_explorer.resolution_bridge import import_resolution
from system_explorer.store import Store
from system_explorer.util import stable_id


FIXTURE = Path(__file__).parent / "fixtures" / "resolution.v1.json"


def carrier_id(scope: str, ref: str) -> str:
    return stable_id("carrier", scope, ref)


class ResolutionBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "state" / "evidence.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _config(self, *, resolution_sources: list[str] | None = None) -> Path:
        path = self.root / "explorer.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                    "desired_resolution_sources": resolution_sources or [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def _write_resolution(self, path: Path, value: dict[str, object]) -> None:
        value["content_hash"] = canonical_content_hash(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_resolution_import_preserves_typed_desired_evidence(self) -> None:
        source_before = FIXTURE.read_bytes()
        fixture_value = json.loads(source_before)

        with Store(self.db) as store:
            stats = import_resolution(FIXTURE, store)
            nodes = {node["id"]: node for node in store.nodes()}
            edges = store.resolved_edges("desired")
            evidence = store.evidence()
            report = coverage_report(store)
            findings = assess(store)["findings"]
            proposal = propose("Review desired coverage gaps", store)

        self.assertEqual(FIXTURE.read_bytes(), source_before)
        self.assertEqual(stats["source_schema"], "system-explorer.resolution.v1")
        self.assertEqual(stats["content_hash"], fixture_value["content_hash"])
        self.assertEqual(stats["carriers"], 5)
        self.assertEqual(stats["functions"], 4)
        self.assertEqual(stats["desired_edges"], 5)
        self.assertEqual(stats["empty_provides"], 1)
        self.assertEqual(stats["inactive_provides"], 1)
        self.assertEqual(stats["duplicate_provider_functions"], 1)
        self.assertEqual(stats["runtime_actions"], [])
        self.assertEqual(stats["target_mutations"], [])

        scope = "fixture-development-system@TEST-HOST"
        self.assertIn(carrier_id(scope, "module:required-provider"), nodes)
        self.assertIn(carrier_id(scope, "skill:recommended-provider"), nodes)
        self.assertIn(carrier_id(scope, "software:optional-provider"), nodes)
        self.assertIn(carrier_id(scope, "skill:empty-provider"), nodes)
        self.assertIn(carrier_id(scope, "software:unavailable-provider"), nodes)
        self.assertNotIn("function:function.consumed-only", nodes)
        self.assertNotIn("function:function.unavailable", nodes)
        self.assertEqual(
            nodes[carrier_id(scope, "module:required-provider")]["metadata"][
                "consumes"
            ],
            ["function.consumed-only"],
        )

        edge_by_pair = {
            (edge["source_id"], edge["target_id"]): edge for edge in edges
        }
        self.assertEqual(
            edge_by_pair[
                (
                    carrier_id(scope, "module:required-provider"),
                    "function:function.required",
                )
            ]["metadata"]["requirement"],
            "required",
        )
        self.assertEqual(
            edge_by_pair[
                (
                    carrier_id(scope, "skill:recommended-provider"),
                    "function:function.recommended",
                )
            ]["metadata"]["requirement"],
            "recommended",
        )
        self.assertEqual(
            edge_by_pair[
                (
                    carrier_id(scope, "software:optional-provider"),
                    "function:function.optional",
                )
            ]["metadata"]["requirement"],
            "optional",
        )
        self.assertEqual(
            {edge["metadata"]["desired_status"] for edge in edges},
            {"available", "configured"},
        )
        self.assertEqual(
            edge_by_pair[
                (
                    carrier_id(scope, "module:required-provider"),
                    "function:function.required",
                )
            ]["metadata"]["desired_status"],
            "configured",
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["source_kind"], "system-resolution")
        self.assertEqual(
            evidence[0]["metadata"]["source_schema"],
            "system-explorer.resolution.v1",
        )
        self.assertEqual(
            evidence[0]["metadata"]["resolution_content_hash"],
            fixture_value["content_hash"],
        )
        self.assertEqual(
            evidence[0]["metadata"]["system_content_hash"],
            fixture_value["system"]["content_hash"],
        )
        self.assertEqual(
            evidence[0]["metadata"]["instance_content_hash"],
            fixture_value["instance"]["content_hash"],
        )

        rows = {
            row["function"]["name"]: row for row in report["functions"]
        }
        self.assertEqual(report["discovery_summary"]["functions"], 4)
        self.assertEqual(report["discovery_summary"]["carrier_nodes"], 5)
        self.assertEqual(report["desired_summary"]["functions"], 4)
        self.assertEqual(report["desired_summary"]["hard_gaps"], 2)
        self.assertEqual(report["desired_summary"]["advisory_gaps"], 1)
        self.assertEqual(report["desired_summary"]["optional_gaps"], 1)
        self.assertEqual(
            report["desired_summary"]["duplicate_provider_functions"],
            1,
        )
        self.assertEqual(rows["function.optional"]["gap_class"], "optional")
        self.assertFalse(rows["function.optional"]["gap_class"] == "hard")
        self.assertEqual(rows["function.recommended"]["gap_class"], "advisory")
        self.assertEqual(rows["function.required"]["gap_class"], "hard")
        self.assertTrue(rows["function.shared"]["desired_overlap"])
        self.assertEqual(
            rows["function.shared"]["desired_requirements"],
            ["required", "optional"],
        )
        finding_by_function = {
            finding["function"]: finding
            for finding in findings
            if "function" in finding
            and finding["kind"]
            in {
                "function-gap",
                "recommended-function-gap",
                "optional-function-gap",
            }
        }
        self.assertEqual(
            finding_by_function["function:function.optional"]["kind"],
            "optional-function-gap",
        )
        self.assertEqual(
            finding_by_function["function:function.optional"]["severity"],
            "review",
        )
        self.assertIn(
            "function:function.required",
            proposal["relevant_function_gaps"],
        )
        self.assertNotIn(
            "function:function.optional",
            proposal["relevant_function_gaps"],
        )

    def test_resolution_instances_remain_isolated_in_coverage(self) -> None:
        first = json.loads(FIXTURE.read_text(encoding="utf-8"))
        second = json.loads(FIXTURE.read_text(encoding="utf-8"))
        first["instance"]["instance_id"] = "fixture-development-system@HOST-A"
        first["instance"]["host_id"] = "HOST-A"
        second["instance"]["instance_id"] = "fixture-development-system@HOST-B"
        second["instance"]["host_id"] = "HOST-B"
        second["bundles"][0]["components"][0]["requirement"] = "optional"
        first_path = self.root / "host-a.json"
        second_path = self.root / "host-b.json"
        self._write_resolution(first_path, first)
        self._write_resolution(second_path, second)

        with Store(self.db) as store:
            import_resolution(first_path, store)
            import_resolution(second_path, store)
            edges = store.resolved_edges("desired")
            nodes = {node["id"]: node for node in store.nodes("carrier")}
            functions = store.nodes("function")
            report = coverage_report(store)

        self.assertEqual(len(edges), 10)
        self.assertIn(
            carrier_id(
                "fixture-development-system@HOST-A",
                "module:required-provider",
            ),
            nodes,
        )
        self.assertIn(
            carrier_id(
                "fixture-development-system@HOST-B",
                "module:required-provider",
            ),
            nodes,
        )
        self.assertTrue(all(function["scope"] is None for function in functions))
        required = next(
            row
            for row in report["functions"]
            if row["function"]["name"] == "function.required"
        )
        by_scope = {
            item["scope"]: item for item in required["desired_by_scope"]
        }
        self.assertEqual(
            by_scope["fixture-development-system@HOST-A"]["gap_class"],
            "hard",
        )
        self.assertEqual(
            by_scope["fixture-development-system@HOST-B"]["gap_class"],
            "optional",
        )
        self.assertFalse(
            by_scope["fixture-development-system@HOST-A"]["overlap"]
        )
        self.assertFalse(
            by_scope["fixture-development-system@HOST-B"]["overlap"]
        )
        self.assertEqual(
            report["desired_summary"]["scopes"][
                "fixture-development-system@HOST-A"
            ]["hard_gaps"],
            2,
        )
        self.assertEqual(
            report["desired_summary"]["scopes"][
                "fixture-development-system@HOST-B"
            ]["optional_gaps"],
            3,
        )

    def test_logical_system_origin_cannot_satisfy_two_host_scopes(self) -> None:
        first = json.loads(FIXTURE.read_text(encoding="utf-8"))
        second = json.loads(FIXTURE.read_text(encoding="utf-8"))
        first["instance"]["instance_id"] = "fixture-development-system@HOST-A"
        first["instance"]["host_id"] = "HOST-A"
        second["instance"]["instance_id"] = "fixture-development-system@HOST-B"
        second["instance"]["host_id"] = "HOST-B"
        first_path = self.root / "logical-origin-host-a.json"
        second_path = self.root / "logical-origin-host-b.json"
        self._write_resolution(first_path, first)
        self._write_resolution(second_path, second)

        with Store(self.db) as store:
            import_resolution(first_path, store)
            import_resolution(second_path, store)
            actual = store.add_node(
                "carrier",
                "Logical system carrier without host binding",
                node_id="carrier:logical-system-only",
                metadata={
                    "origin_system": "fixture-development-system",
                    "component_ref": "module:required-provider",
                },
            )
            store.add_edge(
                actual,
                "carries",
                "function:function.required",
                mode="actual",
                status="full",
            )
            store.commit()
            report = coverage_report(store)

        required = next(
            row
            for row in report["functions"]
            if row["function"]["name"] == "function.required"
        )
        self.assertEqual(
            {
                item["scope"]: item["verdict"]
                for item in required["desired_by_scope"]
            },
            {
                "fixture-development-system@HOST-A": "uncovered",
                "fixture-development-system@HOST-B": "uncovered",
            },
        )
        self.assertTrue(
            all(
                item["actual_provider_edges"] == 0
                for item in required["desired_by_scope"]
            )
        )

    def test_untagged_actual_cannot_satisfy_host_bound_resolution(self) -> None:
        with Store(self.db) as store:
            import_resolution(FIXTURE, store)
            actual = store.add_node(
                "carrier",
                "Untagged provider",
                node_id="carrier:untagged",
                metadata={"component_ref": "module:required-provider"},
            )
            store.add_edge(
                actual,
                "carries",
                "function:function.required",
                mode="actual",
                status="full",
            )
            store.commit()
            report = coverage_report(store)

        required = next(
            row
            for row in report["functions"]
            if row["function"]["name"] == "function.required"
        )
        scope = required["desired_by_scope"][0]
        self.assertEqual(scope["verdict"], "uncovered")
        self.assertEqual(scope["observed_provider_edges"], 0)
        self.assertEqual(scope["actual_provider_edges"], 0)

    def test_instance_scope_alias_cannot_replace_resolution_host_id(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        instance_scope = fixture["instance"]["instance_id"]
        with Store(self.db) as store:
            import_resolution(FIXTURE, store)
            actual = store.add_node(
                "carrier",
                "Scope alias provider",
                node_id="carrier:scope-alias",
                metadata={
                    "origin_system": instance_scope,
                    "component_ref": "module:required-provider",
                },
            )
            store.add_edge(
                actual,
                "carries",
                "function:function.required",
                mode="actual",
                status="full",
            )
            store.commit()
            report = coverage_report(store)

        required = next(
            row
            for row in report["functions"]
            if row["function"]["name"] == "function.required"
        )
        scope = required["desired_by_scope"][0]
        self.assertEqual(scope["verdict"], "uncovered")
        self.assertEqual(scope["observed_provider_edges"], 0)

    def test_new_resolution_revision_supersedes_removed_desired_edges(self) -> None:
        path = self.root / "current-resolution.json"
        first = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self._write_resolution(path, first)

        with Store(self.db) as store:
            import_resolution(path, store)
            second = json.loads(json.dumps(first))
            optional = next(
                component
                for component in second["bundles"][0]["components"]
                if component["role"] == "optional-client"
            )
            optional["provides"] = ["function.shared"]
            second["functions"].remove("function.optional")
            self._write_resolution(path, second)
            stats = import_resolution(path, store)
            edges = store.resolved_edges("desired")
            report = coverage_report(store)

        self.assertEqual(stats["superseded"]["edges"], 5)
        self.assertEqual(len(edges), 4)
        self.assertFalse(
            any(
                edge["target_id"] == "function:function.optional"
                for edge in edges
            )
        )
        self.assertEqual(report["desired_summary"]["functions"], 3)
        self.assertEqual(report["desired_summary"]["optional_gaps"], 0)
        optional_row = next(
            row
            for row in report["functions"]
            if row["function"]["name"] == "function.optional"
        )
        self.assertEqual(optional_row["verdict"], "unproven")
        self.assertEqual(optional_row["gap_class"], "none")

    def test_stale_resolution_cannot_replace_newer_projection(self) -> None:
        stale = json.loads(FIXTURE.read_text(encoding="utf-8"))
        current = json.loads(json.dumps(stale))
        optional = next(
            component
            for component in current["bundles"][0]["components"]
            if component["role"] == "optional-client"
        )
        optional["provides"] = ["function.shared"]
        current["functions"].remove("function.optional")
        stale_path = self.root / "stale-resolution.json"
        current_path = self.root / "current-resolution.json"
        self._write_resolution(stale_path, stale)
        self._write_resolution(current_path, current)
        base_ns = 1_800_000_000_000_000_000
        os.utime(stale_path, ns=(base_ns, base_ns))
        os.utime(
            current_path,
            ns=(base_ns + 2_000_000_000, base_ns + 2_000_000_000),
        )

        with Store(self.db) as store:
            current_stats = import_resolution(current_path, store)
            stale_stats = import_resolution(stale_path, store)
            unchanged_stats = import_resolution(current_path, store)
            report = coverage_report(store)
            evidence = store.evidence()

        self.assertEqual(current_stats["status"], "imported")
        self.assertEqual(stale_stats["status"], "stale-ignored")
        self.assertEqual(stale_stats["superseded"], {"edges": 0, "carriers": 0})
        self.assertEqual(unchanged_stats["status"], "unchanged")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(
            evidence[0]["metadata"]["resolution_content_hash"],
            current["content_hash"],
        )
        self.assertFalse(
            any(
                row["function"]["name"] == "function.optional"
                for row in report["functions"]
            )
        )
        self.assertEqual(report["desired_summary"]["functions"], 3)

    def test_equal_generation_concurrent_imports_are_serialized(self) -> None:
        first = json.loads(FIXTURE.read_text(encoding="utf-8"))
        second = json.loads(json.dumps(first))
        second["desired_profile"] = "conflicting-generation"
        first_path = self.root / "concurrent-a.json"
        second_path = self.root / "concurrent-b.json"
        self._write_resolution(first_path, first)
        self._write_resolution(second_path, second)
        generation_ns = 1_800_000_100_000_000_000
        os.utime(first_path, ns=(generation_ns, generation_ns))
        os.utime(second_path, ns=(generation_ns, generation_ns))
        with Store(self.db):
            pass

        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, str]] = []

        def import_in_thread(source: Path) -> None:
            with Store(self.db) as store:
                barrier.wait()
                try:
                    stats = import_resolution(source, store)
                    outcomes.append(("result", stats["status"]))
                except ValueError as error:
                    outcomes.append(("error", str(error)))

        threads = [
            threading.Thread(target=import_in_thread, args=(first_path,)),
            threading.Thread(target=import_in_thread, args=(second_path,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(
            [outcome for outcome in outcomes if outcome == ("result", "imported")],
            [("result", "imported")],
        )
        conflicts = [
            message
            for kind, message in outcomes
            if kind == "error" and "generation conflicts" in message
        ]
        self.assertEqual(len(conflicts), 1)
        with Store(self.db) as store:
            evidence = store.evidence()
            state = store.resolution_projection_state(
                "resolution:fixture-development-system@TEST-HOST"
            )
            edges = store.resolved_edges("desired")
        self.assertEqual(len(evidence), 1)
        self.assertIsNotNone(state)
        self.assertEqual(
            {edge["metadata"]["resolution_content_hash"] for edge in edges},
            {state["content_hash"]},
        )

    def test_projection_state_rejects_existing_equal_generation_conflict(
        self,
    ) -> None:
        projection = "resolution:fixture-development-system@TEST-HOST"
        generation = [1_800_000_000_000_000_000] * 2
        with Store(self.db) as store:
            for index, content_hash in enumerate(("a" * 64, "b" * 64)):
                store.add_evidence(
                    uri=f"file:///conflict-{index}.json",
                    source_kind="system-resolution",
                    sha256=str(index) * 64,
                    metadata={
                        "resolution_projection": projection,
                        "resolution_generation": generation,
                        "resolution_content_hash": content_hash,
                    },
                )
            store.commit()
            with self.assertRaisesRegex(
                ValueError,
                "conflicting hashes at its latest generation",
            ):
                store.resolution_projection_state(projection)

    def test_assessment_and_proposal_keep_host_gaps_isolated(self) -> None:
        first = json.loads(FIXTURE.read_text(encoding="utf-8"))
        second = json.loads(FIXTURE.read_text(encoding="utf-8"))
        first["instance"]["instance_id"] = "fixture-development-system@HOST-A"
        first["instance"]["host_id"] = "HOST-A"
        second["instance"]["instance_id"] = "fixture-development-system@HOST-B"
        second["instance"]["host_id"] = "HOST-B"
        first_path = self.root / "assessment-host-a.json"
        second_path = self.root / "assessment-host-b.json"
        self._write_resolution(first_path, first)
        self._write_resolution(second_path, second)

        with Store(self.db) as store:
            import_resolution(first_path, store)
            import_resolution(second_path, store)
            actual = store.add_node(
                "carrier",
                "Observed provider on A",
                node_id="carrier:observed-host-a",
                metadata={
                    "origin_system": "HOST-A",
                    "component_ref": "module:required-provider",
                },
            )
            store.add_edge(
                actual,
                "carries",
                "function:function.required",
                mode="actual",
                status="full",
            )
            store.commit()
            report = coverage_report(store)
            assessment = assess(store)
            proposal = propose("Review required coverage", store)

        required = next(
            row
            for row in report["functions"]
            if row["function"]["name"] == "function.required"
        )
        self.assertEqual(required["verdict"], "full")
        by_scope = {
            item["scope"]: item for item in required["desired_by_scope"]
        }
        self.assertEqual(
            by_scope["fixture-development-system@HOST-A"]["verdict"],
            "full",
        )
        self.assertEqual(
            by_scope["fixture-development-system@HOST-B"]["verdict"],
            "uncovered",
        )
        function_gaps = [
            finding
            for finding in assessment["findings"]
            if finding["kind"] == "function-gap"
            and finding["function"] == "function:function.required"
        ]
        self.assertEqual(
            [finding["scope"] for finding in function_gaps],
            ["fixture-development-system@HOST-B"],
        )
        scoped_proposal_gaps = [
            gap
            for gap in proposal["relevant_scoped_function_gaps"]
            if gap["function"] == "function:function.required"
        ]
        self.assertEqual(
            [gap["scope"] for gap in scoped_proposal_gaps],
            ["fixture-development-system@HOST-B"],
        )
        self.assertIn(
            "function:function.required",
            proposal["relevant_function_gaps"],
        )

    def test_provider_identity_is_fail_closed_and_allows_declared_fallbacks(
        self,
    ) -> None:
        with Store(self.db) as store:
            import_resolution(FIXTURE, store)
            actual_required = store.add_node(
                "carrier",
                "Observed required provider",
                node_id="carrier:observed-required",
                metadata={
                    "origin_system": "TEST-HOST",
                    "component_ref": "module:required-provider",
                },
            )
            actual_wrong = store.add_node(
                "carrier",
                "Observed wrong provider",
                node_id="carrier:observed-wrong",
                metadata={
                    "origin_system": "TEST-HOST",
                    "component_ref": "module:not-recommended-provider",
                },
            )
            actual_fallback = store.add_node(
                "carrier",
                "Observed declared fallback",
                node_id="carrier:observed-fallback",
                metadata={
                    "origin_system": "TEST-HOST",
                    "stable_ref": "software:optional-provider",
                },
            )
            store.add_edge(
                actual_required,
                "carries",
                "function:function.required",
                mode="actual",
                status="full",
            )
            store.add_edge(
                actual_wrong,
                "carries",
                "function:function.recommended",
                mode="actual",
                status="full",
            )
            store.add_edge(
                actual_fallback,
                "carries",
                "function:function.shared",
                mode="actual",
                status="full",
            )
            store.commit()
            report = coverage_report(store)
            assessment = assess(store)
            proposal = propose("Review provider identity", store)

        rows = {
            row["function"]["name"]: row for row in report["functions"]
        }
        required = rows["function.required"]["desired_by_scope"][0]
        recommended = rows["function.recommended"]["desired_by_scope"][0]
        fallback = rows["function.shared"]["desired_by_scope"][0]
        self.assertEqual(required["verdict"], "full")
        self.assertFalse(required["carrier_mismatch"])
        self.assertEqual(recommended["verdict"], "wrong-provider")
        self.assertTrue(recommended["carrier_mismatch"])
        self.assertEqual(recommended["actual_provider_edges"], 0)
        self.assertEqual(recommended["observed_provider_edges"], 1)
        self.assertEqual(
            recommended["unexpected_actual_providers"],
            ["carrier:observed-wrong"],
        )
        self.assertEqual(recommended["gap_class"], "advisory")
        self.assertEqual(fallback["verdict"], "full")
        self.assertTrue(fallback["overlap"])
        self.assertFalse(fallback["carrier_mismatch"])
        mismatch = next(
            finding
            for finding in assessment["findings"]
            if finding["kind"] == "carrier-mismatch"
        )
        self.assertEqual(
            mismatch["function"],
            "function:function.recommended",
        )
        self.assertEqual(mismatch["severity"], "medium")
        proposal_gap = next(
            gap
            for gap in proposal["relevant_scoped_function_gaps"]
            if gap["function"] == "function:function.recommended"
        )
        self.assertEqual(proposal_gap["verdict"], "wrong-provider")

    def test_carrier_ids_do_not_collide_when_scope_and_ref_contain_colons(
        self,
    ) -> None:
        first = json.loads(FIXTURE.read_text(encoding="utf-8"))
        second = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for value, scope, host, ref in (
            (first, "alpha:beta", "HOST-A", "gamma"),
            (second, "alpha", "HOST-B", "beta:gamma"),
        ):
            value["instance"]["instance_id"] = scope
            value["instance"]["host_id"] = host
            value["bundles"][0]["components"] = [
                value["bundles"][0]["components"][0]
            ]
            value["bundles"][0]["components"][0]["ref"] = ref
            value["functions"] = ["function.required", "function.shared"]
        first_path = self.root / "collision-a.json"
        second_path = self.root / "collision-b.json"
        self._write_resolution(first_path, first)
        self._write_resolution(second_path, second)

        with Store(self.db) as store:
            import_resolution(first_path, store)
            import_resolution(second_path, store)
            nodes = {
                node["id"]: node for node in store.nodes("carrier")
            }

        first_id = carrier_id("alpha:beta", "gamma")
        second_id = carrier_id("alpha", "beta:gamma")
        self.assertNotEqual(first_id, second_id)
        self.assertIn(first_id, nodes)
        self.assertIn(second_id, nodes)
        self.assertEqual(nodes[first_id]["metadata"]["component_ref"], "gamma")
        self.assertEqual(
            nodes[second_id]["metadata"]["component_ref"],
            "beta:gamma",
        )

    def test_cli_and_config_import_resolution_before_coverage(self) -> None:
        config = self._config(resolution_sources=[str(FIXTURE)])
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                [
                    "coverage",
                    "--config",
                    str(config),
                    "--resolution",
                    str(FIXTURE),
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        value = json.loads(stdout.getvalue())
        self.assertEqual(len(value["resolution_imports"]), 1)
        self.assertEqual(value["desired_summary"]["functions"], 4)
        self.assertEqual(value["discovery_summary"]["desired_provider_edges"], 5)
        self.assertEqual(value["desired_summary"]["optional_gaps"], 1)
        self.assertEqual(value["desired_summary"]["hard_gaps"], 2)

    def test_import_rejects_hash_or_runtime_mutation_contracts(self) -> None:
        original = json.loads(FIXTURE.read_text(encoding="utf-8"))
        candidates = []

        wrong_hash = dict(original)
        wrong_hash["content_hash"] = "0" * 64
        candidates.append(wrong_hash)

        for field in ("runtime_actions", "target_mutations"):
            candidate = json.loads(json.dumps(original))
            candidate[field] = [{"action": "forbidden"}]
            candidate["content_hash"] = canonical_content_hash(candidate)
            candidates.append(candidate)

        mismatch = json.loads(json.dumps(original))
        mismatch["functions"].append("function.not-provided")
        mismatch["content_hash"] = canonical_content_hash(mismatch)
        candidates.append(mismatch)

        unknown_status = json.loads(json.dumps(original))
        unknown_status["bundles"][0]["components"][0][
            "desired_status"
        ] = "configrued"
        unknown_status["content_hash"] = canonical_content_hash(unknown_status)
        candidates.append(unknown_status)

        malformed_instance = json.loads(json.dumps(original))
        malformed_instance["instance"] = ["not", "an", "object"]
        malformed_instance["content_hash"] = canonical_content_hash(
            malformed_instance
        )
        candidates.append(malformed_instance)

        incomplete_instance = json.loads(json.dumps(original))
        del incomplete_instance["instance"]["host_id"]
        incomplete_instance["content_hash"] = canonical_content_hash(
            incomplete_instance
        )
        candidates.append(incomplete_instance)

        for index, candidate in enumerate(candidates):
            with self.subTest(index=index):
                path = self.root / f"invalid-{index}.json"
                path.write_text(json.dumps(candidate), encoding="utf-8")
                db = self.root / f"invalid-{index}.db"
                with Store(db) as store:
                    with self.assertRaises(ValueError):
                        import_resolution(path, store)
                    self.assertEqual(store.nodes(), [])
                    self.assertEqual(store.evidence(), [])

    def test_import_provenance_is_bound_to_one_source_snapshot(self) -> None:
        path = self.root / "replace-during-import.json"
        original = json.loads(FIXTURE.read_text(encoding="utf-8"))
        replacement = json.loads(json.dumps(original))
        replacement["desired_profile"] = "replacement"
        self._write_resolution(path, original)
        original_bytes = path.read_bytes()
        original_stat = path.stat()
        replacement["content_hash"] = canonical_content_hash(replacement)
        replacement_bytes = json.dumps(replacement).encode("utf-8")

        def snapshot_then_replace(source_path: Path):
            source_path.write_bytes(replacement_bytes)
            return original_bytes, original_stat

        with patch(
            "system_explorer.resolution_bridge._read_resolution_snapshot",
            side_effect=snapshot_then_replace,
        ):
            with Store(self.db) as store:
                stats = import_resolution(path, store)
                evidence = store.evidence()

        self.assertEqual(stats["content_hash"], original["content_hash"])
        self.assertEqual(
            stats["source_sha256"],
            hashlib.sha256(original_bytes).hexdigest(),
        )
        self.assertEqual(
            evidence[0]["metadata"]["resolution_content_hash"],
            original["content_hash"],
        )
        self.assertEqual(
            evidence[0]["sha256"],
            hashlib.sha256(original_bytes).hexdigest(),
        )
        self.assertNotEqual(path.read_bytes(), original_bytes)


if __name__ == "__main__":
    unittest.main()
