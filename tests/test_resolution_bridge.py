from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from system_explorer.assessment import assess
from system_explorer.cli import main
from system_explorer.contracts import canonical_content_hash
from system_explorer.coverage import coverage_report
from system_explorer.proposals import propose
from system_explorer.resolution_bridge import import_resolution
from system_explorer.store import Store


FIXTURE = Path(__file__).parent / "fixtures" / "resolution.v1.json"


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
        self.assertIn(f"carrier:{scope}:module:required-provider", nodes)
        self.assertIn(f"carrier:{scope}:skill:recommended-provider", nodes)
        self.assertIn(f"carrier:{scope}:software:optional-provider", nodes)
        self.assertIn(f"carrier:{scope}:skill:empty-provider", nodes)
        self.assertIn(f"carrier:{scope}:software:unavailable-provider", nodes)
        self.assertNotIn("function:function.consumed-only", nodes)
        self.assertNotIn("function:function.unavailable", nodes)
        self.assertEqual(
            nodes[f"carrier:{scope}:module:required-provider"]["metadata"]["consumes"],
            ["function.consumed-only"],
        )

        edge_by_pair = {
            (edge["source_id"], edge["target_id"]): edge for edge in edges
        }
        self.assertEqual(
            edge_by_pair[
                (
                    f"carrier:{scope}:module:required-provider",
                    "function:function.required",
                )
            ]["metadata"]["requirement"],
            "required",
        )
        self.assertEqual(
            edge_by_pair[
                (
                    f"carrier:{scope}:skill:recommended-provider",
                    "function:function.recommended",
                )
            ]["metadata"]["requirement"],
            "recommended",
        )
        self.assertEqual(
            edge_by_pair[
                (
                    f"carrier:{scope}:software:optional-provider",
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
                    f"carrier:{scope}:module:required-provider",
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
            report = coverage_report(store)

        self.assertEqual(len(edges), 10)
        self.assertIn(
            "carrier:fixture-development-system@HOST-A:module:required-provider",
            nodes,
        )
        self.assertIn(
            "carrier:fixture-development-system@HOST-B:module:required-provider",
            nodes,
        )
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


if __name__ == "__main__":
    unittest.main()
