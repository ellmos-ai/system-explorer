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


if __name__ == "__main__":
    unittest.main()
