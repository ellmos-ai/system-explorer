from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from system_explorer.cli import main
from system_explorer.media_connector import (
    build_explainer_package,
    discover_ai_media_editor,
)
from system_explorer.repo_diagrams import sync_repository_diagrams


class ConnectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _media_editor(self) -> Path:
        repo = self.root / "ai-media-editor"
        repo.mkdir()
        (repo / "ellmos-module.v2.json").write_text(
            json.dumps(
                {
                    "schema": "ellmos.module.v2",
                    "id": "ai-media-editor",
                    "version": "0.2.0",
                    "provides": [
                        "domain.media.editing",
                        "workflow.media.pipeline",
                    ],
                    "entrypoints": {
                        "cli": "python editor.py",
                        "workflow": "CLAUDE.md",
                    },
                }
            ),
            encoding="utf-8",
        )
        (repo / "editor.py").write_text(
            "import sys\n"
            "if sys.argv[1:] == ['modes']:\n"
            "    print('6 Erklärvideo aus Audio')\n",
            encoding="utf-8",
        )
        (repo / "CLAUDE.md").write_text("# Media workflow\n", encoding="utf-8")
        return repo

    def _graph(self) -> dict:
        return {
            "nodes": [
                {
                    "id": "entry:cli",
                    "node_type": "entrypoint",
                    "name": "system-explorer CLI",
                    "metadata": {},
                },
                {
                    "id": "carrier:maps",
                    "node_type": "carrier",
                    "name": "Karten-Engine",
                    "metadata": {"carrier_kind": "module"},
                },
                {
                    "id": "function:mapping",
                    "node_type": "function",
                    "name": "Systemkarten erstellen",
                    "metadata": {"coverage_verdict": "full"},
                },
                {
                    "id": "function:gaps",
                    "node_type": "function",
                    "name": "Systemlücken erkennen",
                    "metadata": {"coverage_verdict": "uncovered"},
                },
            ],
            "edges": [
                {
                    "source_id": "entry:cli",
                    "relation": "invokes",
                    "target_id": "carrier:maps",
                    "mode": "actual",
                    "status": "observed",
                },
                {
                    "source_id": "carrier:maps",
                    "relation": "carries",
                    "target_id": "function:mapping",
                    "mode": "actual",
                    "status": "full",
                },
            ],
            "summary": {"full": 1, "uncovered": 1},
        }

    def _git_repo(self, name: str) -> Path:
        repo = self.root / name
        repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "System Explorer Test"],
            cwd=repo,
            check=True,
        )
        (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        (repo / "ellmos-module.v2.json").write_text(
            json.dumps(
                {
                    "schema": "ellmos.module.v2",
                    "id": name,
                    "display_name": name,
                    "version": "1.0.0",
                    "provides": [f"{name}.feature"],
                    "entrypoints": {"cli": f"{name} --help"},
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)
        return repo

    def test_media_connector_discovers_contract_and_builds_handoff(self) -> None:
        media_repo = self._media_editor()
        info = discover_ai_media_editor(media_repo)
        output = self.root / "explainer"
        result = build_explainer_package(
            {"coverage": self._graph()},
            output,
            title="System Explorer erklärt",
            media_editor=info,
            probe=True,
        )

        self.assertEqual(result["status"], "handoff-ready")
        self.assertTrue(result["connector_probe"]["ok"])
        self.assertTrue((output / "storyboard.json").is_file())
        self.assertTrue((output / "narration.md").is_file())
        self.assertTrue((output / "maps" / "coverage.mmd").is_file())
        self.assertTrue((output / ".system-explorer-explainer.json").is_file())
        handoff = json.loads((output / "ai-media-editor-handoff.json").read_text(encoding="utf-8"))
        self.assertEqual(handoff["consumer"]["id"], "ai-media-editor")
        self.assertEqual(handoff["production"]["usecase"], 6)
        narration = (output / "narration.md").read_text(encoding="utf-8")
        self.assertIn("Wo steigt man ein?", narration)
        self.assertIn("Was kann das System?", narration)
        self.assertIn("Wie funktioniert es?", narration)
        self.assertIn("Die besten Features", narration)
        self.assertFalse(handoff["production"]["rendered"])

    def test_media_connector_refuses_unmanaged_output_directory(self) -> None:
        media_repo = self._media_editor()
        output = self.root / "human-output"
        output.mkdir()
        (output / "narration.md").write_text("# Human text\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not managed"):
            build_explainer_package(
                {"coverage": self._graph()},
                output,
                title="Fixture",
                media_editor=discover_ai_media_editor(media_repo),
            )

    def test_media_connector_rejects_wrong_module(self) -> None:
        media_repo = self._media_editor()
        manifest = media_repo / "ellmos-module.v2.json"
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["id"] = "other-module"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ai-media-editor"):
            discover_ai_media_editor(media_repo)

    def test_explain_video_cli_creates_package_from_existing_store(self) -> None:
        media_repo = self._media_editor()
        config = self.root / "explorer.json"
        config.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": "./evidence.db",
                    "roots": [],
                    "system": {"id": "fixture", "name": "Fixture System"},
                }
            ),
            encoding="utf-8",
        )
        output = self.root / "cli-explainer"
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = main(
                [
                    "explain-video",
                    "--config",
                    str(config),
                    "--output",
                    str(output),
                    "--media-editor",
                    str(media_repo),
                    "--no-ingest",
                ]
            )
        self.assertEqual(code, 0)
        receipt = json.loads(stdout.getvalue())
        self.assertEqual(receipt["status"], "handoff-ready")
        self.assertTrue((output / "ai-media-editor-handoff.json").is_file())

    def test_repository_diagram_dry_run_apply_and_idempotency(self) -> None:
        repo = self._git_repo("component-a")
        dry = sync_repository_diagrams(repositories=[repo], apply=False)
        target = repo / "docs" / "system-map.md"
        self.assertFalse(target.exists())
        self.assertEqual(dry["repositories"][0]["action"], "create")

        applied = sync_repository_diagrams(repositories=[repo], apply=True)
        self.assertTrue(target.is_file())
        self.assertEqual(applied["repositories"][0]["action"], "created")
        body = target.read_text(encoding="utf-8")
        self.assertIn("generated-by: system-explorer", body)
        self.assertIn("flowchart LR", body)
        self.assertIn("component-a.feature", body)

        unchanged = sync_repository_diagrams(
            repositories=[repo],
            apply=True,
            allow_dirty=True,
        )
        self.assertEqual(unchanged["repositories"][0]["action"], "unchanged")

    def test_repository_diagram_refuses_dirty_or_unmanaged_target(self) -> None:
        repo = self._git_repo("component-b")
        (repo / "README.md").write_text("# foreign change\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "dirty"):
            sync_repository_diagrams(repositories=[repo], apply=True)

        subprocess.run(["git", "restore", "README.md"], cwd=repo, check=True)
        target = repo / "docs" / "system-map.md"
        target.parent.mkdir()
        target.write_text("# Human architecture\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not managed"):
            sync_repository_diagrams(repositories=[repo], apply=True)

    def test_repository_diagram_can_commit_only_its_generated_file(self) -> None:
        repo = self._git_repo("component-commit")
        before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        result = sync_repository_diagrams(
            repositories=[repo],
            apply=True,
            commit=True,
        )
        receipt = result["repositories"][0]
        self.assertNotEqual(receipt["commit"], before)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(status, "")
        changed = subprocess.run(
            ["git", "show", "--format=", "--name-only", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        self.assertEqual(changed, ["docs/system-map.md"])

    def test_repository_diagram_push_requires_commit_and_apply(self) -> None:
        repo = self._git_repo("component-flags")
        with self.assertRaisesRegex(ValueError, "--commit requires --apply"):
            sync_repository_diagrams(repositories=[repo], commit=True)
        with self.assertRaisesRegex(ValueError, "--push requires --commit"):
            sync_repository_diagrams(repositories=[repo], apply=True, push=True)

    def test_repository_diagram_pushes_and_reads_back_upstream(self) -> None:
        repo = self._git_repo("component-push")
        remote = self.root / "component-push.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote)],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        result = sync_repository_diagrams(
            repositories=[repo],
            apply=True,
            commit=True,
            push=True,
        )
        receipt = result["repositories"][0]
        self.assertTrue(receipt["pushed"])
        remote_head = subprocess.run(
            ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(remote_head, receipt["commit"])

    def test_bundle_updates_bundle_repo_and_path_components(self) -> None:
        bundle_repo = self._git_repo("bundle-root")
        component = self._git_repo("bundle-component")
        manifest = bundle_repo / "bundle.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "ellmos.bundle.v1",
                    "id": "demo-bundle",
                    "version": "1.0.0",
                    "components": [
                        {
                            "type": "module",
                            "ref": {
                                "path": str(component / "ellmos-module.v2.json"),
                                "version": "1.0.0",
                            },
                            "role": "worker",
                            "requirement": "required",
                            "provides": ["bundle.work"],
                            "consumes": [],
                            "version": "1.0.0",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "bundle.json"], cwd=bundle_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add bundle"],
            cwd=bundle_repo,
            check=True,
            capture_output=True,
        )

        result = sync_repository_diagrams(bundle_paths=[manifest], apply=True)
        paths = {Path(item["repo"]).name for item in result["repositories"]}
        self.assertEqual(paths, {"bundle-root", "bundle-component"})
        bundle_map = (bundle_repo / "docs" / "system-map.md").read_text(encoding="utf-8")
        self.assertIn("demo-bundle", bundle_map)
        self.assertIn("bundle-component", bundle_map)
        self.assertTrue((component / "docs" / "system-map.md").is_file())


if __name__ == "__main__":
    unittest.main()
