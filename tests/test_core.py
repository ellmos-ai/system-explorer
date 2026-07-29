from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from system_explorer.assessment import assess
from system_explorer.config import database_path, load_config
from system_explorer.coverage import coverage_report
from system_explorer.deployment import (
    deployment_report,
    import_apiprober_export,
    purpose_report,
    refresh_provider_sources,
)
from system_explorer.federation import (
    export_system_map,
    import_system_map,
    register_federation,
)
from system_explorer.manifests import load_manifest, validate_manifest
from system_explorer.maps import graph_view, render_ascii, render_html, render_mermaid
from system_explorer.proposals import propose
from system_explorer.registry import find_documents, register_path
from system_explorer.resources import resource_report
from system_explorer.scanner import scan
from system_explorer.specs import import_spec
from system_explorer.store import Store
from system_explorer.transcripts import import_transcripts


class ExplorerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "state" / "evidence.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_manifest_and_skill_scan_separates_functions_and_carriers(self) -> None:
        system = self.root / "system"
        module = system / "module-a"
        skill = system / "skills" / "mapper"
        module.mkdir(parents=True)
        skill.mkdir(parents=True)
        (system / ".git").mkdir()
        (module / "ellmos-module.v2.json").write_text(
            json.dumps(
                {
                    "schema": "ellmos.module.v2",
                    "id": "module-a",
                    "display_name": "Module A",
                    "provides": ["system.map"],
                    "entrypoints": {"cli": "module-a"},
                    "surfaces": ["cli"],
                    "encapsulation": "process-boundary",
                    "outputs": [
                        {
                            "name": "system-map.json",
                            "purpose": "portable map",
                            "consumers": ["control-center"],
                        }
                    ],
                    "handoffs": [
                        {
                            "name": "mapping receipt",
                            "target": "system-gap-master",
                        }
                    ],
                    "alternative_paths": [{"target": "fallback-mapper"}],
                    "status": "active",
                }
            ),
            encoding="utf-8",
        )
        (skill / "SKILL.md").write_text(
            "---\nname: mapper\ntags: [mapping, evidence]\n---\n# Mapper\n",
            encoding="utf-8",
        )
        (system / "README.md").write_text("# System\n", encoding="utf-8")
        (system / "CLAUDE.md").write_text(
            "Read `README.md` and [policy](SECURITY-POLICY.md).\n",
            encoding="utf-8",
        )
        (system / "AGENTS.md").write_text(
            "Boot: `CLAUDE.md`\n", encoding="utf-8"
        )
        (system / "SECURITY-POLICY.md").write_text("# Policy\n", encoding="utf-8")
        config = {
            "_base": str(self.root),
            "roots": [
                {
                    "id": "fixture",
                    "path": str(system),
                    "max_depth": 5,
                    "include": ["*.md", "*.json"],
                    "exclude_dirs": [".git"],
                }
            ],
            "privacy": {"sensitivity": "test"},
            "control_documents": [
                {"pattern": "AGENTS.md", "role": "control", "entry": True},
                {"pattern": "CLAUDE.md", "role": "control", "entry": True},
                {"pattern": "README.md", "role": "documentation", "entry": False},
                {"pattern": "*POLICY*.md", "role": "policy", "entry": False},
            ],
            "entry_directories": [{"path": "skills"}],
        }
        with Store(self.db) as store:
            stats = scan(config, store)
            kinds = {(node["node_type"], node["metadata"].get("carrier_kind")) for node in store.nodes()}
            names = {node["name"] for node in store.nodes("function")}
            roles = {
                node["metadata"].get("document_role")
                for node in store.nodes()
            }
            control = graph_view(store, "control")
            tree = graph_view(store, "tree")
            paths = graph_view(store, "function-paths")
        self.assertEqual(stats["errors"], 0)
        self.assertIn(("carrier", "module"), kinds)
        self.assertIn(("carrier", "skill"), kinds)
        self.assertIn(("carrier", "repository"), kinds)
        self.assertIn("system.map", names)
        self.assertIn("skill.mapping", names)
        self.assertIn("policy", roles)
        self.assertIn("control", roles)
        self.assertGreaterEqual(stats["directories"], 4)
        self.assertTrue(
            any(edge["relation"] == "points_to" for edge in control["edges"])
        )
        self.assertTrue(
            any(
                node["node_type"] == "directory"
                and node["metadata"].get("entry_directory")
                for node in tree["nodes"]
            )
        )
        path_relations = {edge["relation"] for edge in paths["edges"]}
        self.assertIn("produces", path_relations)
        self.assertIn("delivers_to", path_relations)
        self.assertIn("exposes_interface", path_relations)
        self.assertIn("hands_off", path_relations)
        self.assertIn("alternative_to", path_relations)

    def test_interactive_document_registration_and_lookup(self) -> None:
        policy = self.root / "SPECIAL-RULES.md"
        decision = self.root / "DECISION-001.md"
        decision.write_text("# Decision\n", encoding="utf-8")
        policy.write_text("Depends on `DECISION-001.md`.\n", encoding="utf-8")
        config = {"privacy": {"sensitivity": "test"}, "control_documents": []}
        with Store(self.db) as store:
            registered = register_path(
                policy, "policy", store, config=config, entry=False
            )
            found = find_documents(store, role="policy", name="special")
            control = graph_view(store, "control")
        self.assertEqual(registered["role"], "policy")
        self.assertEqual(len(found), 1)
        self.assertTrue(
            any(
                edge["relation"] == "references"
                and edge["metadata"].get("resolved")
                for edge in control["edges"]
            )
        )

    def test_crystallized_resource_separates_installation_control_and_savings(
        self,
    ) -> None:
        script = self.root / "bridge-tool.py"
        script.write_text("print('bridge')\n", encoding="utf-8")
        config_path = self.root / "resources.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                    "system": {"id": "WORKSTATION", "name": "Workstation"},
                    "software_resources": [
                        {
                            "id": "bridge-tool",
                            "name": "Bridge tool",
                            "kind": "script",
                            "origin": "llm-generated",
                            "path": str(script),
                            "generated_by": "kimi",
                            "interfaces": [
                                {
                                    "method": "mcp",
                                    "entrypoint": "bridge-tool",
                                    "actors": [
                                        {
                                            "id": "codex",
                                            "name": "Codex",
                                            "provider": "openai",
                                        }
                                    ],
                                },
                                {
                                    "method": "cli",
                                    "entrypoint": "python bridge-tool.py",
                                },
                            ],
                            "functions": [
                                {
                                    "id": "bridge-missing-interface",
                                    "name": "Bridge a missing interface",
                                }
                            ],
                            "token_saving": {
                                "status": "declared",
                                "level": "medium",
                            },
                        }
                    ],
                    "software_discovery": {
                        "commands": [
                            {
                                "id": "definitely-missing-tool",
                                "command": "system-explorer-definitely-missing",
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        config = load_config(config_path)
        with Store(self.db) as store:
            stats = scan(config, store)
            report = resource_report(store)
            graph = graph_view(store, "resources", system_id="WORKSTATION")
        resource = report["resources"][0]["resource"]
        self.assertTrue(resource["metadata"]["installed"])
        self.assertEqual(resource["metadata"]["llm_readiness"], "native")
        self.assertEqual(resource["metadata"]["llm_ready_symbol"], "◆")
        self.assertEqual(resource["metadata"]["flexibility"], "medium")
        self.assertEqual(
            resource["metadata"]["token_saving"]["status"], "declared"
        )
        self.assertEqual(stats["software_resources"], 2)
        self.assertTrue(
            any(
                row["resource"]["metadata"]["installed"] is False
                for row in report["resources"]
            )
        )
        relations = {edge["relation"] for edge in graph["edges"]}
        self.assertIn("exposes_interface", relations)
        self.assertIn("controls_via", relations)
        self.assertIn("carries", relations)
        self.assertIn("generated_by", relations)
        self.assertEqual(graph["report"]["summary"]["native"], 1)

    def test_unhashable_resolved_program_does_not_abort_resource_scan(
        self,
    ) -> None:
        program = self.root / "program.exe"
        program.write_bytes(b"shim")
        config_path = self.root / "unhashable-resource.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                    "software_resources": [
                        {
                            "id": "unhashable",
                            "path": str(program),
                            "interfaces": ["cli"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        config = load_config(config_path)
        with Store(self.db) as store:
            with patch(
                "system_explorer.resources.sha256_file",
                side_effect=OSError(22, "Invalid argument"),
            ):
                stats = scan(config, store)
            evidence = store.evidence()
        self.assertEqual(stats["software_resources"], 1)
        resource_evidence = next(
            item for item in evidence if item["source_kind"] == "path-resolution"
        )
        self.assertEqual(
            resource_evidence["metadata"]["hash_status"], "unavailable"
        )

    def test_registry_database_dataflow_cloud_and_credentials_graph(self) -> None:
        data = self.root / "data"
        data.mkdir()
        registry = data / "service-registry.json"
        registry.write_text(
            json.dumps({"items": [{"id": "alpha"}, {"id": "beta"}]}),
            encoding="utf-8",
        )
        source_db = data / "inventory.sqlite"
        db = sqlite3.connect(source_db)
        db.execute("CREATE TABLE components (id TEXT, status TEXT)")
        db.commit()
        db.close()
        config_path = self.root / "explorer.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": "./state/map.db",
                    "roots": [
                        {
                            "id": "data-system",
                            "path": "./data",
                            "max_depth": 3,
                            "include": ["*.json", "*.sqlite"],
                            "exclude_dirs": [],
                        }
                    ],
                    "registry_documents": ["*registry*"],
                    "registries": [
                        {
                            "path": "./data/service-registry.json",
                            "purpose": "Locate services",
                            "writers_actual": ["registry-builder"],
                            "readers_desired": ["router"],
                            "entrypoints": {"read": "service-registry.json"},
                        }
                    ],
                    "databases": [
                        {
                            "path": "./data/inventory.sqlite",
                            "name": "Inventory",
                            "purpose": "Track components",
                            "fill_purpose": "Store discovered component state",
                            "retrieval_purpose": "Resolve available components",
                            "cloud_ready": True,
                            "cloud_provider": "cloud-a",
                            "transfer": "encrypted-snapshot",
                            "credential_ref": "cloud-a-token",
                            "writers_actual": ["inventory-writer"],
                            "writers_desired": ["inventory-writer-v2"],
                            "readers_actual": ["inventory-ui"],
                            "readers_desired": ["control-center"],
                            "entrypoints": {"sqlite": "inventory.sqlite"},
                            "tables": [
                                {
                                    "name": "components",
                                    "fill_purpose": "Component state",
                                    "retrieval_purpose": "Availability lookup",
                                }
                            ],
                        }
                    ],
                    "credentials": [
                        {
                            "id": "cloud-a-token",
                            "provider": "cloud-a",
                            "storage": "os-keyring",
                            "location_hint": "logical-reference-only",
                        }
                    ],
                    "cloud": {
                        "providers": [
                            {
                                "id": "cloud-a",
                                "name": "Cloud A",
                                "kind": "object-storage",
                            }
                        ],
                        "paths": [
                            {
                                "path": "./data",
                                "mode": "indirect-mirror",
                                "provider": "cloud-a",
                                "transfer": "encrypted-snapshot",
                                "credential_ref": "cloud-a-token",
                            }
                        ],
                    },
                    "privacy": {"sensitivity": "test"},
                }
            ),
            encoding="utf-8",
        )
        config = load_config(config_path)
        with Store(database_path(config)) as store:
            stats = scan(config, store)
            graph = graph_view(store, "data")
            node_types = {node["node_type"] for node in graph["nodes"]}
            edges = graph["edges"]
            credential = store.nodes("credential_reference")[0]
            directories = store.nodes("directory")
        self.assertEqual(stats["errors"], 0)
        self.assertIn("registry", node_types)
        self.assertIn("registry_collection", node_types)
        self.assertIn("database", node_types)
        self.assertIn("database_table", node_types)
        self.assertIn("cloud_provider", node_types)
        self.assertIn("credential_reference", node_types)
        self.assertTrue(
            any(edge["relation"] == "fills" and edge["mode"] == "desired" for edge in edges)
        )
        self.assertTrue(any(edge["relation"] == "reads" for edge in edges))
        self.assertTrue(any(edge["relation"] == "mirrors_to" for edge in edges))
        self.assertTrue(any(edge["relation"] == "uses_credential" for edge in edges))
        self.assertFalse(credential["metadata"]["value_retained"])
        self.assertTrue(
            any(node["metadata"].get("cloud_symbol") == "⇄☁" for node in directories)
        )

    def test_coverage_full_partial_uncovered_negative_and_overlap(self) -> None:
        spec = self.root / "desired.json"
        spec.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.desired.v1",
                    "system": "fixture",
                    "functions": [
                        {"id": "full", "name": "Full"},
                        {"id": "partial", "name": "Partial"},
                        {"id": "missing", "name": "Missing"},
                        {"id": "negative", "name": "Negative"},
                    ],
                    "carriers": [
                        {"id": "a", "name": "A", "kind": "skill"},
                        {"id": "b", "name": "B", "kind": "module"},
                    ],
                    "coverage": [
                        {"function": name, "carrier": "a", "status": "full"}
                        for name in ("full", "partial", "missing", "negative")
                    ],
                    "observations": [
                        {"function": "full", "carrier": "a", "status": "full"},
                        {"function": "full", "carrier": "b", "status": "fulfilled"},
                        {"function": "partial", "carrier": "a", "status": "partial"},
                        {"function": "negative", "carrier": "a", "status": "negative"},
                    ],
                    "structure": [],
                }
            ),
            encoding="utf-8",
        )
        with Store(self.db) as store:
            import_spec(spec, store)
            report = coverage_report(store)
            assessment = assess(store)
        rows = {row["function"]["name"]: row for row in report["functions"]}
        self.assertEqual(rows["Full"]["verdict"], "full")
        self.assertTrue(rows["Full"]["overlap"])
        self.assertEqual(rows["Partial"]["verdict"], "partial")
        self.assertEqual(rows["Missing"]["verdict"], "uncovered")
        self.assertEqual(rows["Negative"]["verdict"], "negative")
        finding_kinds = {item["kind"] for item in assessment["findings"]}
        self.assertIn("negative-coverage", finding_kinds)
        self.assertIn("undercoverage", finding_kinds)
        self.assertIn("function-gap", finding_kinds)
        self.assertIn("overlap", finding_kinds)

    def test_newer_effective_evidence_wins_same_relationship(self) -> None:
        with Store(self.db) as store:
            carrier = store.add_node("carrier", "Runner")
            function = store.add_node("function", "Safe execution")
            old = store.add_evidence(
                uri="file:///old", source_kind="test", effective_at="2026-01-01T00:00:00Z"
            )
            new = store.add_evidence(
                uri="file:///new", source_kind="test", effective_at="2026-02-01T00:00:00Z"
            )
            store.add_edge(
                carrier, "carries", function, mode="actual", status="full", evidence_id=old
            )
            store.add_edge(
                carrier, "carries", function, mode="actual", status="negative", evidence_id=new
            )
            store.commit()
            edges = store.resolved_edges("actual")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["status"], "negative")

    def test_codex_transcript_correlates_call_and_result_without_raw_content(self) -> None:
        transcript = self.root / "rollout.jsonl"
        secret = "DO-NOT-STORE-RAW-CONTENT"
        records = [
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": secret}],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "read_manifest",
                    "call_id": "call-1",
                    "arguments": "{\"path\":\"C:\\\\workspace\\\\manifest.json\"}",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": secret,
                },
            },
        ]
        transcript.write_text(
            "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
        )
        with Store(self.db) as store:
            stats = import_transcripts("codex", transcript, store)
            evidence = store.evidence()
            nodes = store.nodes()
        self.assertEqual(stats["tool_calls"], 1)
        self.assertEqual(stats["tool_results"], 1)
        serialized = json.dumps({"evidence": evidence, "nodes": nodes})
        self.assertNotIn(secret, serialized)
        self.assertIn("read_manifest", serialized)

    def test_maps_and_read_only_proposal(self) -> None:
        with Store(self.db) as store:
            function = store.add_node("function", "Knowledge search")
            carrier = store.add_node("carrier", "Search skill", metadata={"carrier_kind": "skill"})
            store.add_edge(carrier, "carries", function, mode="actual", status="partial")
            store.commit()
            graph = graph_view(store, "coverage")
            paths = graph_view(store, "function-paths")
            proposal = propose("Verbessere Knowledge search", store)
        self.assertIn("SYSTEM MAP", render_ascii(graph))
        self.assertIn("flowchart LR", render_mermaid(graph))
        self.assertIn("<!doctype html>", render_html(graph))
        self.assertTrue(any(edge["relation"] == "carries" for edge in paths["edges"]))
        self.assertFalse(proposal["prompt_retained"])
        self.assertFalse(proposal["apply"]["authorized"])
        self.assertNotIn("Verbessere Knowledge search", json.dumps(proposal))

    def test_gemini_sqlite_is_opened_read_only_and_prompt_is_hashed(self) -> None:
        source = self.root / "conversation.db"
        db = sqlite3.connect(source)
        db.execute("CREATE TABLE steps (step_type INTEGER, content TEXT)")
        db.execute("INSERT INTO steps VALUES (14, 'private prompt')")
        db.commit()
        db.close()
        with Store(self.db) as store:
            stats = import_transcripts("gemini", source, store)
            serialized = json.dumps(store.evidence())
        self.assertEqual(stats["records"], 1)
        self.assertNotIn("private prompt", serialized)

    def test_claude_and_kimi_native_event_shapes(self) -> None:
        claude = self.root / "claude.jsonl"
        claude.write_text(
            "\n".join(
                json.dumps(item)
                for item in [
                    {
                        "type": "assistant",
                        "sessionId": "claude-1",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Read",
                                    "id": "use-1",
                                    "input": {"path": "C:\\workspace\\AGENTS.md"},
                                }
                            ],
                        },
                    },
                    {
                        "type": "user",
                        "sessionId": "claude-1",
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "use-1",
                                    "content": "private result",
                                }
                            ],
                        },
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        kimi = self.root / "wire.jsonl"
        kimi.write_text(
            "\n".join(
                json.dumps(item)
                for item in [
                    {
                        "type": "turn.prompt",
                        "session_id": "kimi-1",
                        "origin": "user",
                        "prompt": "private kimi prompt",
                    },
                    {
                        "type": "context.append_loop_event",
                        "session_id": "kimi-1",
                        "event": {
                            "type": "tool_call",
                            "name": "read_file",
                            "call_id": "kimi-call",
                            "arguments": "{}",
                        },
                    },
                    {
                        "type": "context.append_loop_event",
                        "session_id": "kimi-1",
                        "event": {
                            "type": "tool_result",
                            "name": "read_file",
                            "call_id": "kimi-call",
                            "output": "private kimi result",
                        },
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        desktop = self.root / "audit.jsonl"
        desktop.write_text(
            "\n".join(
                json.dumps(item)
                for item in [
                    {
                        "event_type": "command_lifecycle",
                        "kind": "started",
                        "command": "inspect_tree",
                        "session_id": "desktop-1",
                    },
                    {
                        "event_type": "command_lifecycle",
                        "kind": "completed",
                        "command": "inspect_tree",
                        "session_id": "desktop-1",
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        with Store(self.db) as store:
            claude_stats = import_transcripts("claude-code", claude, store)
            kimi_stats = import_transcripts("kimi", kimi, store)
            desktop_stats = import_transcripts(
                "claude-desktop", desktop, store
            )
            serialized = json.dumps(store.evidence())
        self.assertEqual(claude_stats["tool_calls"], 1)
        self.assertEqual(claude_stats["tool_results"], 1)
        self.assertEqual(kimi_stats["tool_calls"], 1)
        self.assertEqual(kimi_stats["tool_results"], 1)
        self.assertEqual(desktop_stats["tool_calls"], 1)
        self.assertEqual(desktop_stats["tool_results"], 1)
        self.assertNotIn("private result", serialized)
        self.assertNotIn("private kimi prompt", serialized)
        self.assertNotIn("private kimi result", serialized)

    def test_private_server_public_surface_is_negative_and_cost_is_compared(self) -> None:
        config_path = self.root / "server-explorer.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                    "provider_sources": [
                        {
                            "provider": "example-cloud",
                            "document_type": "pricing",
                            "url": "https://example.invalid/pricing",
                            "accessed_at": "2026-07-29",
                        }
                    ],
                    "servers": [
                        {
                            "id": "private-node",
                            "name": "Private Node",
                            "purpose": "private-server",
                            "location": "cloud",
                            "provider": "example-cloud",
                            "surfaces": [
                                {
                                    "id": "ssh",
                                    "url": "ssh://example.invalid:22",
                                    "reachable": True,
                                    "desired_public": False,
                                    "vantage": "external",
                                    "probe_adapter": "api-prober",
                                }
                            ],
                            "controls": {"firewall_default_deny": True},
                            "monthly_cost": {
                                "amount": 12,
                                "currency": "EUR",
                                "source": "provider-price-page",
                                "effective_at": "2026-07-29",
                                "verified": True,
                            },
                            "local_alternative": {
                                "one_time_cost": 180,
                                "amortization_months": 36,
                                "monthly_cost": 2,
                            },
                        }
                    ],
                    "privacy": {"sensitivity": "test"},
                }
            ),
            encoding="utf-8",
        )
        config = load_config(config_path)
        with Store(self.db) as store:
            scan(config, store)
            report = deployment_report(store)
            graph = graph_view(store, "deployment", system_id="current-system")
        row = report["servers"][0]
        self.assertEqual(row["verdict"], "negative")
        self.assertEqual(row["cost_comparison"]["lower_cost"], "local")
        self.assertTrue(row["api_prober_plan"]["authorized_targets_only"])
        self.assertTrue(any(edge["relation"] == "probed_by" for edge in graph["edges"]))
        self.assertTrue(
            any(node["node_type"] == "provider_document" for node in graph["nodes"])
        )
        self.assertTrue(any(node["node_type"] == "cost_offer" for node in graph["nodes"]))

    def test_part_open_server_controls_and_module_purpose(self) -> None:
        config_path = self.root / "purpose-explorer.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                    "servers": [
                        {
                            "id": "service",
                            "purpose": "part-open-service",
                            "surfaces": [
                                {
                                    "id": "api",
                                    "url": "https://example.invalid/api",
                                    "desired_public": True,
                                }
                            ],
                            "controls": {
                                "tls": True,
                                "authentication": True,
                                "firewall_default_deny": True,
                                "rate_limit": False,
                                "logging": True,
                                "secret_storage": True,
                            },
                        }
                    ],
                    "purposes": [
                        {
                            "id": "maps-systems",
                            "target": "carrier:repo:explorer",
                            "target_name": "Explorer repo",
                            "criteria": [
                                {"function": "scan", "name": "Scan systems"},
                                {"function": "render", "name": "Render maps"},
                            ],
                        }
                    ],
                    "privacy": {"sensitivity": "test"},
                }
            ),
            encoding="utf-8",
        )
        config = load_config(config_path)
        with Store(self.db) as store:
            scan(config, store)
            store.add_edge(
                "carrier:repo:explorer",
                "carries",
                "function:scan",
                mode="actual",
                status="full",
            )
            store.add_edge(
                "carrier:repo:explorer",
                "carries",
                "function:render",
                mode="actual",
                status="partial",
            )
            store.commit()
            servers = deployment_report(store)
            purposes = purpose_report(store)
        self.assertEqual(servers["servers"][0]["verdict"], "partial")
        self.assertEqual(purposes["purposes"][0]["verdict"], "partial")

    def test_federated_maps_keep_origins_levels_and_cross_system_routes(self) -> None:
        workstation_config = {
            "system": {
                "id": "WORKSTATION",
                "name": "Workstation",
                "kind": "workstation",
                "level": "own-system",
            },
            "_base": str(self.root),
            "connections": [
                {
                    "source": "WORKSTATION",
                    "target": "HETZNER",
                    "transport": "ssh+tailscale",
                    "status": "observed",
                }
            ],
            "handoffs": [
                {
                    "source": "WORKSTATION",
                    "target": "LAPTOP",
                    "via": "system-gap-master",
                    "route": ".SYNC",
                    "purpose": "close remote gap",
                }
            ],
        }
        laptop_map_path = self.root / "system-map-LAPTOP.json"
        with Store(self.db) as store:
            node = store.add_node("actor", "Codex", node_id="actor:codex")
            session = store.add_node("session", "session-1")
            store.add_edge(node, "participates_in", session, status="observed")
            register_federation(workstation_config, store)
            exported = export_system_map(
                store,
                system=workstation_config["system"],
                view="llm-traces",
            )
        laptop_export = {
            **exported,
            "system": {
                "id": "LAPTOP",
                "name": "Laptop",
                "kind": "laptop",
                "level": "remote-system",
            },
        }
        laptop_map_path.write_text(json.dumps(laptop_export), encoding="utf-8")
        other_db = self.root / "federated.db"
        with Store(other_db) as store:
            imported = import_system_map(laptop_map_path, store)
            register_federation(workstation_config, store)
            all_graph = graph_view(store, "federation")
            laptop_traces = graph_view(store, "llm-traces", system_id="LAPTOP")
        self.assertEqual(imported["system"], "LAPTOP")
        self.assertTrue(any(level["id"] == "LAPTOP" for level in all_graph["levels"]))
        self.assertTrue(
            any(edge["relation"] == "connects_via" for edge in all_graph["edges"])
        )
        self.assertTrue(
            any(edge["relation"] == "hands_off" for edge in all_graph["edges"])
        )
        self.assertTrue(laptop_traces["nodes"])
        self.assertTrue(
            all(
                node["metadata"].get("origin_system") == "LAPTOP"
                for node in laptop_traces["nodes"]
            )
        )

    def test_apiprober_export_registers_referenced_endpoint_evidence(self) -> None:
        export = self.root / "apiprober-export.json"
        export.write_text(
            json.dumps(
                {
                    "endpoints": [
                        {"path": "/health", "method": "GET", "status_code": 200}
                    ]
                }
            ),
            encoding="utf-8",
        )
        with Store(self.db) as store:
            stats = import_apiprober_export(export, store, server_id="api")
            serialized = json.dumps(
                {"nodes": store.nodes(), "evidence": store.evidence()}
            )
        self.assertEqual(stats["endpoints"], 1)
        self.assertIn("/health", serialized)
        self.assertNotIn("response_body", serialized)

    def test_provider_refresh_rejects_non_http_source_before_fetch(self) -> None:
        with Store(self.db) as store:
            with self.assertRaises(ValueError):
                refresh_provider_sources(
                    {
                        "provider_sources": [
                            {
                                "provider": "local",
                                "url": "file:///etc/provider-pricing.txt",
                            }
                        ]
                    },
                    store,
                )

    def test_missing_configured_map_is_reported_as_scan_error(self) -> None:
        config_path = self.root / "missing-map.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                    "system": {"id": "HOST", "name": "Host"},
                    "map_imports": ["./does-not-exist.json"],
                }
            ),
            encoding="utf-8",
        )
        config = load_config(config_path)
        with Store(self.db) as store:
            stats = scan(config, store)
        self.assertEqual(stats["map_imports"], 0)
        self.assertEqual(stats["map_import_errors"], 1)
        self.assertEqual(stats["errors"], 1)

    def test_project_manifest_validates(self) -> None:
        path = Path(__file__).resolve().parents[1] / "ellmos-module.v2.json"
        self.assertEqual(validate_manifest(load_manifest(path)), [])

    def test_web_manifest_assets_and_portable_map_schema_exist(self) -> None:
        project = Path(__file__).resolve().parents[1]
        web = project / "src" / "system_explorer" / "web"
        manifest = json.loads((web / "manifest.json").read_text(encoding="utf-8"))
        for item in manifest["icons"]:
            self.assertTrue((web / item["src"]).is_file())
        schema = json.loads(
            (project / "schemas" / "system-explorer.map.v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"], "system-explorer.map.v1"
        )


if __name__ == "__main__":
    unittest.main()
