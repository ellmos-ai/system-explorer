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
        self.assertEqual(version, "0.4.2")

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
            "THIRD_PARTY_LICENSES.md",
            "THIRD_PARTY_LICENSES.txt",
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
        self.assertIn("security@open-bricks.org", security_text)
        self.assertIn("support@lukasgeiger.com", security_text)

        # Architectural guarantees
        self.assertIn("Zero-Egress", security_text)
        self.assertIn("Fail-Closed", security_text)
        self.assertIn("127.0.0.1", security_text)

        # Response SLA
        self.assertIn("### Response SLA", security_text)
        self.assertIn("### Reaktionszeiten (SLA)", security_text)
        self.assertIn("Within 48 hours", security_text)
        self.assertIn("Within 5 business days", security_text)
        self.assertIn("Innerhalb von 48 Stunden", security_text)
        self.assertIn("Innerhalb von 5 Werktagen", security_text)

        # Supported versions table
        self.assertIn("### Supported Versions", security_text)
        self.assertIn("### Unterstützte Versionen", security_text)
        self.assertIn("0.4.x", security_text)

    def test_third_party_licenses_inventory(self) -> None:
        """Verify third-party license inventory document structure and declarations."""
        licenses_path = self.root / "THIRD_PARTY_LICENSES.md"
        self.assertTrue(licenses_path.is_file(), "Missing THIRD_PARTY_LICENSES.md")
        licenses_text = licenses_path.read_text(encoding="utf-8")

        self.assertIn("cryptography", licenses_text)
        self.assertIn(">=41", licenses_text)
        self.assertIn("Apache-2.0 OR BSD-3-Clause", licenses_text)
        self.assertIn("pytest", licenses_text)
        self.assertIn("ruff", licenses_text)
        self.assertIn("build", licenses_text)
        self.assertIn("jsonschema", licenses_text)
        self.assertIn("Apache License 2.0", licenses_text)
        self.assertIn("BSD 3-Clause License", licenses_text)
        self.assertIn("MIT License", licenses_text)

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
        self.assertIn("compileall -q src tests", ci_content)
        self.assertIn("ruff check", ci_content)
        self.assertIn("pytest -ra -v", ci_content)

    def test_pyproject_pep621_metadata(self) -> None:
        """Verify PEP 621 metadata fields, URLs, classifiers, and ruff lint configuration."""
        pyproject_text = (self.root / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[project]", pyproject_text)
        self.assertIn('license-files = ["LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.md", "THIRD_PARTY_LICENSES.txt"]', pyproject_text)
        self.assertIn("[project.urls]", pyproject_text)
        self.assertIn("Homepage = ", pyproject_text)
        self.assertIn("Repository = ", pyproject_text)
        self.assertIn("Notice = ", pyproject_text)
        self.assertIn("Security = ", pyproject_text)
        self.assertIn('"Third-Party Licenses" = ', pyproject_text)
        self.assertIn('"Third-Party Licenses (Text)" = ', pyproject_text)
        self.assertIn('"Marketing-Log" = ', pyproject_text)
        self.assertIn('"LLM-Ready" = ', pyproject_text)
        self.assertIn('"Parent Organization" = "https://github.com/ellmos-ai"', pyproject_text)
        self.assertIn('"Umbrella Ecosystem" = "https://github.com/open-bricks"', pyproject_text)
        self.assertIn("Topic :: Security", pyproject_text)
        self.assertIn("Topic :: System :: Monitoring", pyproject_text)
        self.assertIn("architecture-drift", pyproject_text)
        self.assertIn("runtime-invariants", pyproject_text)
        self.assertIn("[tool.ruff]", pyproject_text)
        self.assertIn("cryptography>=41", pyproject_text)

    def test_gitignore_hygiene_patterns(self) -> None:
        """Verify .gitignore contains standard sync conflict, lock, and cache exclusions."""
        gitignore_text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.sync-conflict-*", gitignore_text)
        self.assertIn("*.conflict", gitignore_text)
        self.assertIn("*-conflict-*", gitignore_text)
        self.assertIn("*-WORKSTATION-LG*", gitignore_text)
        self.assertIn("*-ASUS-GEI*", gitignore_text)
        self.assertIn("*-WORKSTATION.*", gitignore_text)
        self.assertIn("* (kopie)*", gitignore_text)
        self.assertIn("* (copy)*", gitignore_text)
        self.assertIn("LOCK*.txt", gitignore_text)
        self.assertIn("LOCK.permissions.json", gitignore_text)
        self.assertIn("uv.lock", gitignore_text)
        self.assertIn(".coverage.*", gitignore_text)
        self.assertIn(".npmrc", gitignore_text)
        self.assertIn("*token*", gitignore_text)
        self.assertIn("*secret*", gitignore_text)
        self.assertIn("*.tmp", gitignore_text)
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
            self.assertIn("version-0.4.2", doc)
            self.assertIn("actions/workflows/ci.yml", doc)
            self.assertRegex(doc, r"Pytest-\d+%20(passed|bestanden)")
            self.assertIn("Zero--Egress", doc)
            self.assertIn("Local--First", doc)
            self.assertIn("security%20sla-48h%20response%20%7C%205d%20triage", doc)
            self.assertIn("third--party-100%25%20permissive", doc)
            self.assertIn("marketing%20log-active", doc)
            self.assertIn("code%20style-ruff", doc)
            self.assertIn("LLM--Ready-llms.txt", doc)

        # 18-point dual navigation items and semantic aliases
        for i in range(1, 19):
            anchor = f"#sec-{i:02d}"
            self.assertIn(anchor, readme_en, f"Missing nav anchor {anchor} in README.md")
            self.assertIn(anchor, readme_de, f"Missing nav anchor {anchor} in README_de.md")

        expected_nav_ids_en = [
            "features",
            "target-personas--discoverability",
            "comparative-matrix--alternatives",
            "system-architecture",
            "evidence-backed-resolution-lifecycle",
            "quick-start",
            "bounded-scans-and-progress",
            "external-composition-and-probe-authorities",
            "actual-self-search-routing",
            "security-and-truth-boundaries",
            "resolution-as-desired-evidence",
            "explicit-function-equivalence",
            "governance--runtime-invariants",
            "bundles--partners",
            "ecosystem--sibling-tools",
            "testing--quality-verification",
            "third-party-licenses--transparency",
            "statutory-disclaimer--response-sla",
        ]
        for nav_id in expected_nav_ids_en:
            self.assertIn(f'id="{nav_id}"', readme_en, f"Missing semantic anchor id='{nav_id}' in README.md")

        expected_nav_ids_de = [
            "funktionen",
            "zielgruppen--auffindbarkeit",
            "vergleichsmatrix--alternativen",
            "systemarchitektur",
            "evidenzbasierter-auflösungs-lebenszyklus",
            "schnellstart",
            "begrenzte-scans-und-fortschritt",
            "externe-composition--und-probe-autoritäten",
            "actual-self-search-routing",
            "sicherheit-und-wahrheitsschranken",
            "resolution-als-soll-evidenz",
            "explizite-funktions-äquivalenz",
            "governance--und-laufzeit-invarianten",
            "bundles--partner",
            "ökosystem--geschwisterwerkzeuge",
            "tests-verifikation--qualitaetssicherung",
            "drittanbieter-lizenzen--transparenz",
            "gesetzlicher-haftungsausschluss--reaktions-sla",
        ]
        for nav_id in expected_nav_ids_de:
            self.assertIn(f'id="{nav_id}"', readme_de, f"Missing semantic anchor id='{nav_id}' in README_de.md")

        self.assertIn("SECURITY.md", readme_en)
        self.assertIn("SECURITY.md", readme_de)

    def test_readme_mermaid_flowchart_architecture(self) -> None:
        """Verify Mermaid flowchart exists and models layered local architecture."""
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        self.assertIn("## System Architecture", readme_en)
        self.assertIn("## Systemarchitektur", readme_de)

        for doc in (readme_en, readme_de):
            self.assertIn("```mermaid", doc)
            self.assertIn("flowchart TD", doc)
            self.assertIn("127.0.0.1:8765", doc)
            self.assertIn("SQLite", doc)

        self.assertIn("Fail-Closed Invariant Gate", readme_en)
        self.assertIn("Fail-Closed Invarianten-Gate", readme_de)

    def test_governance_invariants_table_parity(self) -> None:
        """Verify 10 governance and runtime invariants are defined in both READMEs."""
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        self.assertIn("## Governance & Runtime Invariants", readme_en)
        self.assertIn("## Governance- & Laufzeit-Invarianten", readme_de)

        expected_inv_ids = [
            "INV-LOCAL-01",
            "INV-EVID-02",
            "INV-FAIL-03",
            "INV-RO-04",
            "INV-NON-05",
            "INV-SCOP-06",
            "INV-ED25519-07",
            "INV-TIME-08",
            "INV-CROSS-09",
            "INV-SLA-10",
        ]
        for inv_id in expected_inv_ids:
            self.assertIn(inv_id, readme_en, f"Missing {inv_id} in README.md")
            self.assertIn(inv_id, readme_de, f"Missing {inv_id} in README_de.md")

    def test_marketing_log_present(self) -> None:
        """Verify MARKETING-LOG.txt exists and documents Pfad B."""
        marketing_log = self.root / "MARKETING-LOG.txt"
        self.assertTrue(marketing_log.is_file(), "MARKETING-LOG.txt missing")
        content = marketing_log.read_text(encoding="utf-8")
        self.assertIn("Pfad B", content)
        self.assertIn("2026-09-09", content)
        self.assertIn("2026-09-12", content)
        self.assertIn("2026-09-28", content)
        self.assertIn("INV-LOCAL-01", content)
        self.assertIn("INV-SLA-10", content)
        self.assertIn("TARGET PERSONAS", content)
        self.assertIn("COMPETITIVE DIFFERENTIATION MATRIX", content)

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
            self.root / "THIRD_PARTY_LICENSES.md",
            self.root / "MARKETING-LOG.txt",
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
        self.assertIn("Last-checked: 2026-09-30", llms_text)
        self.assertIn("Attribution: NOTICE", llms_text)
        self.assertIn("SECURITY.md", llms_text)
        self.assertIn("THIRD_PARTY_LICENSES.md", llms_text)
        self.assertIn("THIRD_PARTY_LICENSES.txt", llms_text)
        self.assertIn("MARKETING-LOG.txt", llms_text)
        self.assertIn(".github/workflows/ci.yml", llms_text)
        self.assertIn(".github/workflows/stale.yml", llms_text)
        self.assertIn(".github/workflows/welcome.yml", llms_text)
        self.assertIn(".github/workflows/auto-assign.yml", llms_text)
        self.assertIn(".github/workflows/label-sync.yml", llms_text)
        self.assertIn(".github/labels.yml", llms_text)
        self.assertIn("ARCHITECTURE.md", llms_text)
        self.assertRegex(llms_text, r"\d+.*Pytest tests")

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

    def test_pytest_configuration_and_flags(self) -> None:
        """Verify pyproject.toml defines standardized pytest testpaths, addopts, and norecursedirs."""
        pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[tool.pytest.ini_options]", pyproject)
        self.assertIn('minversion = "7.0"', pyproject)
        self.assertIn('testpaths = ["tests"]', pyproject)
        self.assertIn('addopts = "-ra -v --basetemp=.pytest_temp"', pyproject)
        self.assertIn("norecursedirs = [", pyproject)

    def test_changelog_recent_pfad_a_entry(self) -> None:
        """Verify CHANGELOG.md contains a recent Pfad A hygiene entry."""
        changelog = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("2026-09-28", changelog)
        self.assertIn("Pfad A", changelog)

    def test_ci_workflow_hardening(self) -> None:
        """Verify CI workflow defines timeout-minutes and permissions: contents: read."""
        ci_path = self.root / ".github" / "workflows" / "ci.yml"
        self.assertTrue(ci_path.is_file(), "ci.yml missing")
        ci_text = ci_path.read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 15", ci_text)
        self.assertIn("permissions:", ci_text)
        self.assertIn("contents: read", ci_text)

    def test_ci_stale_workflow_present(self) -> None:
        """Verify stale issues and PRs lifecycle workflow is configured with proper gates."""
        stale_path = self.root / ".github" / "workflows" / "stale.yml"
        self.assertTrue(stale_path.is_file(), "stale.yml missing")
        stale_text = stale_path.read_text(encoding="utf-8")
        self.assertIn("actions/stale@v9", stale_text)
        self.assertIn("timeout-minutes: 10", stale_text)
        self.assertIn("issues: write", stale_text)
        self.assertIn("pull-requests: write", stale_text)
        self.assertIn("days-before-stale: 30", stale_text)
        self.assertIn("days-before-close: 7", stale_text)
        self.assertIn("exempt-issue-labels:", stale_text)
        self.assertIn("exempt-pr-labels:", stale_text)

    def test_gitignore_extended_multi_host_patterns(self) -> None:
        """Verify gitignore includes extended case variations and merge artifact exclusions."""
        gitignore_text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("* (Kopie)*", gitignore_text)
        self.assertIn("* (Copy)*", gitignore_text)
        self.assertIn("*conflicted copy*", gitignore_text)
        self.assertIn("*.orig", gitignore_text)
        self.assertIn("*.rej", gitignore_text)

    def test_changelog_recent_pfad_b_entry(self) -> None:
        """Verify CHANGELOG.md contains a recent Pfad B entry."""
        changelog = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("2026-09-30", changelog)
        self.assertIn("Pfad B", changelog)

    def test_target_personas_and_licenses_sections_exist(self) -> None:
        """Verify dedicated target personas and third-party license sections exist in both READMEs."""
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        self.assertIn("## Target Personas & Discoverability", readme_en)
        self.assertIn("## Zielgruppen & Auffindbarkeit", readme_de)
        self.assertIn("## Third-Party Licenses & Level 1 SBOM", readme_en)
        self.assertIn("## Drittanbieter-Lizenzen & Level 1 SBOM", readme_de)

    def test_notice_and_level1_sbom_compliance(self) -> None:
        """Verify NOTICE attribution file and Level 1 SBOM integrity status in licenses."""
        notice_file = self.root / "NOTICE"
        self.assertTrue(notice_file.exists(), "NOTICE file must exist in repo root")
        notice_text = notice_file.read_text(encoding="utf-8")
        self.assertIn("Lukas Geiger", notice_text)
        self.assertIn("ellmos-ai", notice_text)
        self.assertIn("open-bricks", notice_text)

        licenses_text = (self.root / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("Level 1 SBOM", licenses_text)
        self.assertIn("RunAsInvoker", licenses_text)
        self.assertIn("INV-LOCAL-01", licenses_text)
        self.assertIn("INV-SLA-10", licenses_text)

        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")
        self.assertIn("§ 521 BGB", readme_en)
        self.assertIn("§ 521 BGB", readme_de)
        self.assertIn('<a id="comparative-matrix--alternatives"></a>', readme_en)
        self.assertIn('<a id="vergleichsmatrix--alternativen"></a>', readme_de)

    def test_welcome_workflow_provisioned(self) -> None:
        """Verify welcome workflow is configured with first-interaction, timeout, and least privilege."""
        welcome_path = self.root / ".github" / "workflows" / "welcome.yml"
        self.assertTrue(welcome_path.is_file(), "welcome.yml missing")
        welcome_text = welcome_path.read_text(encoding="utf-8")
        self.assertIn("actions/first-interaction@v3", welcome_text)
        self.assertIn("timeout-minutes: 5", welcome_text)
        self.assertIn("concurrency:", welcome_text)
        self.assertIn("cancel-in-progress: true", welcome_text)
        self.assertIn("issues: write", welcome_text)
        self.assertIn("pull-requests: write", welcome_text)

    def test_stale_workflow_concurrency(self) -> None:
        """Verify stale issues and PRs lifecycle workflow defines concurrency controls."""
        stale_path = self.root / ".github" / "workflows" / "stale.yml"
        self.assertTrue(stale_path.is_file(), "stale.yml missing")
        stale_text = stale_path.read_text(encoding="utf-8")
        self.assertIn("concurrency:", stale_text)
        self.assertIn("group: stale-${{ github.ref }}", stale_text)
        self.assertIn("cancel-in-progress: true", stale_text)

    def test_gitignore_canonical_lock_guards(self) -> None:
        """Verify .gitignore contains canonical multi-agent locks and test cache guards."""
        gitignore_text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("LOCK.user.*", gitignore_text)
        self.assertIn("LOCK.until.*", gitignore_text)
        self.assertIn("LOCK.condition.*", gitignore_text)
        self.assertIn(".automation-lock", gitignore_text)
        self.assertIn("!package-lock.json", gitignore_text)
        self.assertIn(".pytest_temp/", gitignore_text)
        self.assertIn(".hypothesis/", gitignore_text)
        self.assertIn("*-ASUS*", gitignore_text)
        self.assertIn("*-MacBook*", gitignore_text)
        self.assertIn("*-WORKSTATION-LG*", gitignore_text)
        self.assertIn("*-WORKSTATION-LG.*", gitignore_text)

    def test_auto_assign_workflow_provisioned(self) -> None:
        """Verify auto-assign workflow is configured with github-script, timeout, and least privilege."""
        workflow_path = self.root / ".github" / "workflows" / "auto-assign.yml"
        self.assertTrue(workflow_path.is_file(), "auto-assign.yml missing")
        content = workflow_path.read_text(encoding="utf-8")
        self.assertIn("actions/github-script@v7", content)
        self.assertIn("timeout-minutes: 5", content)
        self.assertIn("concurrency:", content)
        self.assertIn("cancel-in-progress: true", content)
        self.assertIn("pull-requests: write", content)

    def test_label_sync_workflow_and_manifest(self) -> None:
        """Verify label-sync workflow and canonical labels.yml manifest exist and define 11 standard labels."""
        workflow_path = self.root / ".github" / "workflows" / "label-sync.yml"
        self.assertTrue(workflow_path.is_file(), "label-sync.yml missing")
        wf_content = workflow_path.read_text(encoding="utf-8")
        self.assertIn("EndBug/label-sync@v2", wf_content)
        self.assertIn("timeout-minutes: 5", wf_content)
        self.assertIn("concurrency:", wf_content)
        self.assertIn("cancel-in-progress: true", wf_content)
        self.assertIn("issues: write", wf_content)
        self.assertIn(".github/labels.yml", wf_content)

        labels_path = self.root / ".github" / "labels.yml"
        self.assertTrue(labels_path.is_file(), "labels.yml missing")
        labels_content = labels_path.read_text(encoding="utf-8")
        for label in [
            "bug",
            "enhancement",
            "good first issue",
            "help wanted",
            "documentation",
            "duplicate",
            "wontfix",
            "priority: high",
            "priority: low",
            "needs-triage",
            "stale",
        ]:
            self.assertIn(label, labels_content)

    def test_level1_sbom_text_companion(self) -> None:
        """Verify Level 1 SBOM text companion THIRD_PARTY_LICENSES.txt structure and invariants."""
        sbom_path = self.root / "THIRD_PARTY_LICENSES.txt"
        self.assertTrue(sbom_path.is_file(), "THIRD_PARTY_LICENSES.txt missing")
        self.assertGreater(sbom_path.stat().st_size, 0)
        content = sbom_path.read_text(encoding="utf-8")
        self.assertIn("LEVEL 1 SBOM", content)
        self.assertIn("INV-LOCAL-01", content)
        self.assertIn("INV-SLA-10", content)
        self.assertIn("RunAsInvoker", content)
        self.assertIn("Zero-Copyleft", content)
        self.assertIn("Apache-2.0", content)
        self.assertIn("BSD-3-Clause", content)
        self.assertIn("MIT License", content)
        self.assertIn("PSFL-2.0", content)

    def test_gitignore_multi_host_and_os_noise(self) -> None:
        """Verify .gitignore contains extended multi-host sync and OS noise patterns."""
        gitignore_text = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("Desktop.ini", gitignore_text)
        self.assertIn("ehthumbs.db", gitignore_text)
        self.assertIn("*-IDEAPAD-GEI*", gitignore_text)

    def test_ascii_four_view_topology_projection(self) -> None:
        """Verify ASCII four-view architectural topology projection exists in Section 04 of both READMEs."""
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        self.assertIn("### ASCII Four-View Architectural Topology", readme_en)
        self.assertIn("[VIEW 1: CLI RUNTIMES, USER INTERFACES & AUTOMATION ENTRY POINTS]", readme_en)
        self.assertIn("[VIEW 2: SYSTEM-EXPLORER SOVEREIGN CORE ENGINE & CARTOGRAPHY ORCHESTRATOR]", readme_en)
        self.assertIn("[VIEW 3: SQLITE EVIDENCE LEDGER, ED25519 SEARCH RECEIPTS & TRUST STORE]", readme_en)
        self.assertIn("[VIEW 4: AIR-GAP DEFENSE PERIMETER, ZERO-EGRESS & GOVERNANCE BOUNDARY]", readme_en)

        self.assertIn("### ASCII Vier-Ebenen-Architekturtopologie", readme_de)
        self.assertIn("[EBENE 1: CLI-LAUFZEITEN, BENUTZEROBERFLÄCHEN & AUTOMATIONS-EINSTIEGSPUNKTE]", readme_de)
        self.assertIn("[EBENE 2: SOVEREIGN CARTOGRAPHY ENGINE & DRIFT-DETEKTION]", readme_de)
        self.assertIn("[EBENE 3: SQLITE EVIDENZ-LEDGER, ED25519 SUCH-QUITTUNGEN & TRUST STORE]", readme_de)
        self.assertIn("[EBENE 4: AIR-GAP SCHUTZPERIMETER, ZERO-EGRESS & GOVERNANCE-GRENZE]", readme_de)

    def test_dedicated_sections_testing_and_statutory_disclaimer(self) -> None:
        """Verify Section 16 (Testing & QA) and Section 18 (Statutory Disclaimer & SLA) exist in both READMEs."""
        readme_en = (self.root / "README.md").read_text(encoding="utf-8")
        readme_de = (self.root / "README_de.md").read_text(encoding="utf-8")

        # Section 16
        self.assertIn("## Testing, Verification & Quality Assurance", readme_en)
        self.assertIn('<a id="sec-16"></a>', readme_en)
        self.assertIn("## Tests, Verifikation & Qualitätssicherung", readme_de)
        self.assertIn('<a id="sec-16"></a>', readme_de)

        # Section 18
        self.assertIn("## Statutory Disclaimer & Security Response SLA (§ 521 BGB)", readme_en)
        self.assertIn('<a id="sec-18"></a>', readme_en)
        self.assertIn("## Gesetzlicher Haftungsausschluss & Reaktions-SLA (§ 521 BGB)", readme_de)
        self.assertIn('<a id="sec-18"></a>', readme_de)

        # SLA text and German statutory disclaimer
        for doc in (readme_en, readme_de):
            self.assertIn("48", doc)
            self.assertIn("§ 521 BGB", doc)
            self.assertIn("Gefälligkeitsverhältnis", doc)

    def test_level1_sbom_audit_date_recency(self) -> None:
        """Verify Level 1 SBOM documents reflect current 2026-09-30 audit date."""
        licenses_md = (self.root / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        licenses_txt = (self.root / "THIRD_PARTY_LICENSES.txt").read_text(encoding="utf-8")

        self.assertIn("Audit Date:** 2026-09-30", licenses_md)
        self.assertIn("Stand 2026-09-30", licenses_md)
        self.assertIn("Audited: 2026-09-30", licenses_txt)


if __name__ == "__main__":
    unittest.main()
