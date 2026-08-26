"""Metadata, CI matrix, documentation, security policy, and parity test suite for system-explorer."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import system_explorer


class SystemExplorerMetadataTests(unittest.TestCase):
    """Verifies project discovery metadata, contracts, and bilingual parity."""

    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_version_consistency(self) -> None:
        """Verify version across package, module manifest, pyproject.toml, and docs."""
        version = system_explorer.__version__
        self.assertEqual(version, "0.4.0")

        pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{version}"', pyproject)

        manifest = json.loads((self.root / "ellmos-module.v2.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], version)

    def test_required_documentation_files_exist(self) -> None:
        """Verify all essential documentation and legal files exist."""
        required_files = [
            "README.md",
            "README_de.md",
            "SECURITY.md",
            "LICENSE",
            "CHANGELOG.md",
            "llms.txt",
            "ARCHITECTURE.md",
            "pyproject.toml",
            "ellmos-module.v2.json",
        ]
        for rel_path in required_files:
            file_path = self.root / rel_path
            self.assertTrue(file_path.is_file(), f"Missing required file: {rel_path}")
            self.assertGreater(file_path.stat().st_size, 0, f"Empty file: {rel_path}")

    def test_bilingual_security_policy(self) -> None:
        """Verify bilingual English and German security guarantees and contacts."""
        security_text = (self.root / "SECURITY.md").read_text(encoding="utf-8")

        # Language anchors
        self.assertIn("## English", security_text)
        self.assertIn("## Deutsch", security_text)

        # Contact addresses
        self.assertIn("security@ellmos.ai", security_text)
        self.assertIn("support@lukasgeiger.com", security_text)

        # Architectural guarantees
        self.assertIn("Zero-Egress", security_text)
        self.assertIn("Fail-Closed", security_text)
        self.assertIn("127.0.0.1", security_text)

        # Supported versions table
        self.assertIn("### Supported Versions", security_text)
        self.assertIn("### Unterstützte Versionen", security_text)
        self.assertIn("0.4.x", security_text)

    def test_ci_workflow_structure(self) -> None:
        """Verify GitHub Actions CI workflow runs across platforms and Python versions."""
        ci_path = self.root / ".github" / "workflows" / "ci.yml"
        self.assertTrue(ci_path.is_file(), "CI workflow file .github/workflows/ci.yml missing")
        ci_content = ci_path.read_text(encoding="utf-8")

        # Concurrency control
        self.assertIn("concurrency:", ci_content)
        self.assertIn("cancel-in-progress: true", ci_content)

        # OS Matrix
        self.assertIn("ubuntu-latest", ci_content)
        self.assertIn("windows-latest", ci_content)
        self.assertIn("macos-latest", ci_content)

        # Python versions
        for py_ver in ["3.10", "3.11", "3.12", "3.13"]:
            self.assertIn(py_ver, ci_content)

        # Lint and test runners
        self.assertIn("ruff check", ci_content)
        self.assertIn("pytest", ci_content)

    def test_pyproject_pep621_metadata(self) -> None:
        """Verify PEP 621 metadata fields, URLs, classifiers, and ruff lint configuration."""
        pyproject_text = (self.root / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[project]", pyproject_text)
        self.assertIn("[project.urls]", pyproject_text)
        self.assertIn("Homepage = ", pyproject_text)
        self.assertIn("Repository = ", pyproject_text)
        self.assertIn("Security = ", pyproject_text)
        self.assertIn('"Parent Organization" = "https://github.com/ellmos-ai"', pyproject_text)
        self.assertIn('"Umbrella Ecosystem" = "https://github.com/open-bricks"', pyproject_text)
        self.assertIn("Topic :: Security", pyproject_text)
        self.assertIn("Topic :: System :: Monitoring", pyproject_text)
        self.assertIn("[tool.ruff]", pyproject_text)
        self.assertIn("cryptography>=41", pyproject_text)

    def test_gitignore_hygiene_patterns(self) -> None:
        """Verify .gitignore contains standard sync conflict, lock, and cache exclusions."""
        gitignore_text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.sync-conflict-*", gitignore_text)
        self.assertIn("*.conflict", gitignore_text)
        self.assertIn("LOCK*.txt", gitignore_text)
        self.assertIn(".pytest_cache/", gitignore_text)
        self.assertIn(".ruff_cache/", gitignore_text)

    def test_readme_navigation_and_badges_parity(self) -> None:
        """Verify navigation links and standard Shields.io badges in both READMEs."""
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        # Navigation headers
        self.assertIn("## Quick Navigation", readme_en)
        self.assertIn("## Schnellnavigation", readme_de)

        # Standard badges
        for doc in (readme_en, readme_de):
            self.assertIn("actions/workflows/ci.yml", doc)
            self.assertIn("Pytest-179%20passed", doc)
            self.assertIn("Zero--Egress", doc)
            self.assertIn("Local--First", doc)
            self.assertIn("LLM--Ready-llms.txt", doc)

    def test_readme_mermaid_sequence_diagrams(self) -> None:
        """Verify Mermaid sequence diagram exists and models the resolution lifecycle."""
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        for doc in (readme_en, readme_de):
            self.assertIn("```mermaid", doc)
            self.assertIn("sequenceDiagram", doc)
            self.assertIn("autonumber", doc)
            self.assertIn("System Explorer CLI", doc)
            self.assertIn("127.0.0.1", doc)

    def test_readme_no_conflict_markers(self) -> None:
        """Ensure no merge conflict markers exist in documentation or source files."""
        for check_path in [
            self.root / "README.md",
            self.root / "README_de.md",
            self.root / "SECURITY.md",
            self.root / "llms.txt",
            self.root / "CHANGELOG.md",
        ]:
            text = check_path.read_text(encoding="utf-8")
            self.assertNotIn("<<<<<<<", text, f"Conflict marker found in {check_path.name}")
            self.assertNotIn("=======", text, f"Conflict marker found in {check_path.name}")
            self.assertNotIn(">>>>>>>", text, f"Conflict marker found in {check_path.name}")

    def test_llms_txt_structure_and_links(self) -> None:
        """Verify llms.txt provides complete index, updated timestamp, and key documentation links."""
        llms_text = (self.root / "llms.txt").read_text(encoding="utf-8")

        self.assertIn("# system-explorer", llms_text)
        self.assertIn("Last-checked: 2026-08-26", llms_text)
        self.assertIn("SECURITY.md", llms_text)
        self.assertIn(".github/workflows/ci.yml", llms_text)
        self.assertIn("ARCHITECTURE.md", llms_text)
        self.assertIn("179 Pytest tests", llms_text)

    def test_ecosystem_table_parity(self) -> None:
        """Verify sibling ecosystem tools table contains essential partner repositories."""
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        expected_partners = [
            "policy-registry",
            "sqlite-transit-sync",
            "coma",
            "automation-master",
            "ellmos-delegation-authority",
            "ellmos-controlcenter-mcp",
            "ellmos-filecommander-mcp",
            "ellmos-codecommander-mcp",
            "n8n-manager-mcp",
            "lock-master",
            "ticket-master",
            "clutch",
            "DevCenter",
            "CodeBox",
            "open-bricks",
        ]
        for partner in expected_partners:
            self.assertIn(partner, readme_en, f"Missing partner {partner} in README.md")
            self.assertIn(partner, readme_de, f"Missing partner {partner} in README_de.md")


if __name__ == "__main__":
    unittest.main()
