from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from system_explorer.assessment import assess
from system_explorer.coverage import coverage_report
from system_explorer.manifests import load_manifest, validate_manifest
from system_explorer.maps import graph_view, render_ascii, render_html, render_mermaid
from system_explorer.proposals import propose
from system_explorer.registry import find_documents, register_path
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
            proposal = propose("Verbessere Knowledge search", store)
        self.assertIn("SYSTEM MAP", render_ascii(graph))
        self.assertIn("flowchart LR", render_mermaid(graph))
        self.assertIn("<!doctype html>", render_html(graph))
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

    def test_project_manifest_validates(self) -> None:
        path = Path(__file__).resolve().parents[1] / "ellmos-module.v2.json"
        self.assertEqual(validate_manifest(load_manifest(path)), [])


if __name__ == "__main__":
    unittest.main()
