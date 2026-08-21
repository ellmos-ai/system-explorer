from __future__ import annotations

import importlib.metadata
import json
import unittest
from pathlib import Path

import system_explorer


PROJECT_VERSION = "0.4.0"


class VersioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_project_version_and_development_status_are_consistent(self) -> None:
        pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        manifest = json.loads(
            (self.root / "ellmos-module.v2.json").read_text(encoding="utf-8")
        )
        claude = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        state = (self.root / "STATE.md").read_text(encoding="utf-8")
        changelog = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn('version = "0.4.0"', pyproject)
        self.assertEqual(manifest["version"], PROJECT_VERSION)
        self.assertEqual(manifest["status"], "development")
        self.assertRegex(claude, r"(?m)^version:\s*0\.4\.0\s*$")
        self.assertRegex(state, r"(?m)^version:\s*0\.4\.0\s*$")
        self.assertIn("Development-Stand `0.4.0`", changelog)
        self.assertEqual(system_explorer.__version__, PROJECT_VERSION)

    def test_metadata_checks_editable_install_or_documents_external_fallback(self) -> None:
        distribution = importlib.metadata.distribution("system-explorer")
        location = Path(distribution.locate_file(""))
        source_root = (self.root / "src").resolve()
        versioning = (self.root / "VERSIONING.md").read_text(encoding="utf-8")
        try:
            local_metadata = location.resolve().is_relative_to(source_root)
        except AttributeError:  # pragma: no cover - Python 3.9 fallback
            local_metadata = str(location.resolve()).startswith(str(source_root))
        if local_metadata and distribution.version == PROJECT_VERSION:
            self.assertEqual(distribution.version, PROJECT_VERSION)
        else:
            self.assertIn("nicht aus diesem Clone", versioning)
            self.assertIn("Fallback", versioning)

    def test_readme_and_badges_parity(self) -> None:
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        for readme in (readme_en, readme_de):
            self.assertIn("Pytest-173%20passed", readme)
            self.assertIn("Ecosystem-ellmos--ai", readme)
            self.assertIn("Umbrella-open--bricks", readme)
            self.assertIn("policy-registry", readme)
            self.assertIn("sqlite-transit-sync", readme)
            self.assertIn("coma", readme)
            self.assertIn("automation-master", readme)
            self.assertIn("DevCenter", readme)
            self.assertIn("CodeBox", readme)

    def test_llms_txt_and_manifest_parity(self) -> None:
        llms_txt = (self.root / "llms.txt").read_text(encoding="utf-8")
        manifest = json.loads(
            (self.root / "ellmos-module.v2.json").read_text(encoding="utf-8")
        )
        self.assertIn("Last-checked: 2026-08-21", llms_txt)
        self.assertEqual(manifest["id"], "system-explorer")
        self.assertEqual(manifest["version"], PROJECT_VERSION)
        adapter_ids = {a["id"] for a in manifest.get("adapters", [])}
        self.assertIn("codex-jsonl", adapter_ids)
        self.assertIn("claude-code-jsonl", adapter_ids)
        self.assertIn("gemini-sqlite", adapter_ids)
        self.assertIn("provider-native-redacted-events", adapter_ids)


if __name__ == "__main__":
    unittest.main()
