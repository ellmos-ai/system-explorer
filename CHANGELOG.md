# Changelog

## Unreleased

- 2026-09-26: Pfad A: CI Lifecycle Workflows, Multi-Host Lock Defense, PEP 621 Pytest Hardening & Contract Test Expansion.
  - CI/CD Lifecycle Workflow Provisioning & Hardening: `.github/workflows/welcome.yml` neu bereitgestellt mit `actions/first-interaction@v3`, `timeout-minutes: 5`, Concurrency-Gruppe `welcome-${{ github.ref }}` (`cancel-in-progress: true`), least-privilege permissions `issues: write`, `pull-requests: write`; `.github/workflows/stale.yml` mit Concurrency-Gruppe `stale-${{ github.ref }}` (`cancel-in-progress: true`) gehärtet.
  - Multi-Host Cloud-Sync-, Lock- und Cache-Härtung in `.gitignore`: Multi-Host Sync-Muster (`*-ASUS*`, `*-LAPTOP*`, `*-Mac Studio*`, `*-MacBook*`, `*-IDEAPAD*`, `*_WORKSTATION*`, `*_WORKSTATION-LG*`, `*-WORKSTATION-LG.*`), kanonische Locks (`LOCK.user.*`, `LOCK.until.*`, `LOCK.condition.*`, `.automation-lock`, mit Ausnahme von `!package-lock.json`), Test- und Coverage-Caches (`.pytest_temp/`, `.pytest_tmp*/`, `.hypothesis/`, `.turbo/`, `.nyc_output/`, `.tox/`).
  - PEP 621 & Pytest Standardisierung in `pyproject.toml`: `minversion = "7.0"`, `addopts = "-ra -v --basetemp=.pytest_temp"` und `norecursedirs` um Test-/Tooling-Caches (`.git`, `.pytest_temp`, `.pytest_tmp*`, `.hypothesis`, `.turbo`, `.nyc_output`, `.tox`) standardisiert.
  - Level 1 SBOM Re-Audit in `THIRD_PARTY_LICENSES.md`: Re-Audit Stand 2026-09-26 mit Querverweis auf kanonische `NOTICE`, unprivileged `RunAsInvoker` Non-Elevation Zertifizierung, Bestätigung aller 10 Governance- und Laufzeitinvarianten `INV-LOCAL-01` bis `INV-SLA-10`, Zero-Copyleft & Zero-Egress Core Isolation.
  - Shields.io-Testbadges und Kontext-Parität: Badges in `README.md` und `README_de.md` mit `Verified-2026--09--26` und Teststand aktualisiert; `llms.txt` Stand 2026-09-26 aktualisiert; lokales Marketing- und Governance-Register `MARKETING-LOG.txt` um Pfad A Revisionsbericht Stand 2026-09-26 ergänzt.
  - Vertragstest-Erweiterung: `tests/test_metadata.py` um 4 neue Contract-Tests für welcome.yml Concurrency/Timeouts/Permissions, stale.yml Concurrency, erweiterte .gitignore Multi-Host/Lock-Guards, pyproject pytest norecursedirs und basetemp erweitert.

- 2026-09-21: Pfad B: Discoverability Sättigung (20/20 GitHub Topics), 17-Point Navigation & Comparative Matrix Parity, Level 1 SBOM & Statutory Disclaimer (§ 521 BGB).
  - GitHub Discoverability Sättigung: Live-Repository-Topics via GitHub API auf das Maximum von 20/20 Themen ausgebaut (`system-cartography`, `evidence-based`, `architecture-drift`, `sqlite-storage`, `local-first`, `mcp`, `ai-agents`, `antigravity`, `claude-code`, `codex`, `multi-agent`, `zero-egress`, `open-bricks`, `provenance`, `runtime-invariants`, `codebase-index`, `fail-closed`, `developer-tools`, `cli`).
  - Zweisprachige Schnellnavigation auf 17-Punkte-Standard mit 100%iger wechselseitiger HTML-Anker-Parität (`<a id="..."></a>`) erweitert, inklusive neuer Navigationspunkte für `#comparative-matrix--alternatives` und `#vergleichsmatrix--alternativen`.
  - 10-Dimensionen 5-Wege-Vergleichsmatrix (system-explorer vs. Statische Wikis, APM / Distributed Tracing, Graph-Datenbanken, Generische Linter) zweisprachig in `README.md` und `README_de.md` integriert.
  - Target Personas um strukturierte High-Intent-Suchbegriffe für autonome Agenten, SREs, Local-First-Entwickler und Governance-Auditoren erweitert.
  - Kanonische `NOTICE`-Attributionsdatei angelegt und in PEP 621 / PEP 639 `license-files = ["LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.md"]` sowie `[project.urls]` in `pyproject.toml` verankert.
  - `THIRD_PARTY_LICENSES.md` um Level 1 SBOM Integritätsstatus-Tabelle und 10-Zeilen Invarianten-Kreuzreferenzmatrix (`INV-LOCAL-01` bis `INV-SLA-10`) mit Prüfmethoden und Sicherheitsgrenzen erweitert (Audit 2026-09-21).
  - Gesetzlicher Haftungsausschluss gemäß § 521 BGB (Gefälligkeitsverhältnis) zweisprachig in `README.md`, `README_de.md` und `llms.txt` verankert.
  - Shields.io-Testbadge auf 221 bestandene Pytest-Tests aktualisiert.
  - Lokales Marketing-Audit in `MARKETING-LOG.txt` für den 2026-09-21 dokumentiert.
  - Metadaten- und Vertragstestsuite `tests/test_metadata.py` um Validierungen für 17-Punkte-Navigation, PEP 639 `NOTICE`, Level 1 SBOM und § 521 BGB Haftungsausschluss ausgebaut.

- 2026-09-16: Pfad A: Repository-Hygiene, CI Workflow Hardening, Stale Lifecycle, Multi-Host Sync Defense & Contract Parity.
  - CI-Workflow `.github/workflows/ci.yml` gehärtet: `timeout-minutes: 15` für Matrix-Runner integriert (Schutz vor unbegrenzten Runner-Hängern) sowie top-level `permissions: contents: read` nach dem Least-Privilege-Prinzip deklariert.
  - Automatisierten Stale-Lifecycle `.github/workflows/stale.yml` nach offiziellem `.GITHUBBOT`-Template mit `actions/stale@v9`, `timeout-minutes: 10`, 30 Tagen Inaktivitäts- und 7 Tagen Schließfrist sowie standardisierten Ausnahme-Labels (`pinned`, `security`, `proposal`, `feature`, `rfc`, `priority: high`) implementiert.
  - Multi-Host-Cloud-Sync- und Gitignore-Härtung: `.gitignore` um erweiterte Sync-Konfliktmuster (`* (Kopie)*`, `* (Copy)*`, `*conflicted copy*`) sowie Merge-Artefakte (`*.orig`, `*.rej`) erweitert.
  - Shields.io-Testbadge in `README.md` und `README_de.md` auf 190 bestandene Pytest-Tests aktualisiert.
  - Maschinenlesbaren Kontext `llms.txt` auf Stand `2026-09-16`, 190 Pytest-Tests und `.github/workflows/stale.yml` synchronisiert.
  - Lokales `MARKETING-LOG.txt` um Pfad-A-Hygiene-Audit-Eintrag für den 2026-09-16 ergänzt.
  - Automatisierte Metadaten- und Vertragstestsuite in `tests/test_metadata.py` um 4 Contract-Tests erweitert (`test_ci_stale_workflow_present`, `test_ci_workflow_hardening`, `test_gitignore_extended_multi_host_patterns` sowie aktualisierter `test_changelog_recent_pfad_a_entry`).

- 2026-09-12: Pfad B: Discoverability, 16-Point Navigation, Target Personas & Metadata Contract Refresh.
  - Kanonischen Development-Stand auf `0.4.2` synchronisiert über `pyproject.toml`, `src/system_explorer/__init__.py`, `ellmos-module.v2.json`, `CLAUDE.md`, `STATE.md`, `VERSIONING.md`, `llms.txt` und zweisprachige READMEs.
  - Zweisprachige README-Architektur (`README.md` & `README_de.md`) auf den 16-Punkte-Schnellnavigations-Standard mit 100%iger wechselseitiger Anker-Parität erweitert (`#target-personas--discoverability` / `#zielgruppen--auffindbarkeit`, `#third-party-licenses--transparency` / `#drittanbieter-lizenzen--transparenz`).
  - Dedizierte Abschnitte für Target Personas (Autonome KI-Agenten, Enterprise System-Architekten, Local-First Entwickler, Sicherheits-Auditoren) und Drittanbieter-Lizenzen in beiden Sprachfassungen integriert.
  - Shields.io-Badges um `Third-Party Audited` und `Marketing Log: Active` ergänzt sowie Version auf `0.4.2` aktualisiert.
  - `pyproject.toml` unter `[project.urls]` um standardisierte PEP 621 URLs für `"Third-Party Licenses"`, `"Marketing-Log"` und `"LLM-Ready"` erweitert.
  - `THIRD_PARTY_LICENSES.md` mit Audit-Datum 2026-09-12 und verbindlichen Governance- und Laufzeit-Invarianten-Zusicherungen (`INV-LOCAL-01` bis `INV-SLA-10`) re-verifiziert (100% permissiver Open-Source-Stack, Apache-2.0 / BSD-3-Clause / MIT / PSFL, kein restriktives Copyleft).
  - Lokales Marketing- und Visual-Architecture-Protokoll `MARKETING-LOG.txt` mit 4 Ziel-Personas, zweisprachiger High-Intent Keyword-Matrix (EN/DE), 5-Wege-Wettbewerbsmatrix über 10 Dimensionen, 10 Laufzeit-Invarianten und Geschwisterwerkzeuge-Zuordnung modernisiert.
  - `llms.txt` Last-checked-Zeitstempel auf 2026-09-12 und Verifikationsbaseline synchronisiert.
  - Automatisierte Metadaten- und Vertragstestsuite in `tests/test_metadata.py` und `tests/test_versioning.py` für Version 0.4.2, 16-Punkte-Navigationsanker und erweiterte PEP 621 URLs ausgebaut.

- 2026-09-10: Pfad A: Repository Hygiene, Pytest Standard Config, .gitignore Hardening & Contract Parity Refresh.
  - Kanonischen Development-Stand auf `0.4.1` synchronisiert über `pyproject.toml`, `src/system_explorer/__init__.py`, `ellmos-module.v2.json`, `CLAUDE.md`, `STATE.md`, `VERSIONING.md`, `llms.txt` und zweisprachige READMEs.
  - `pyproject.toml` unter `[tool.pytest.ini_options]` um standardisierte Runner-Flags `addopts = "-ra -v"` ergänzt.
  - `.gitignore` umfassend gehärtet gegen Multi-Host-Synchronisationskonflikte (`*-WORKSTATION.*`, `* (kopie)*`, `* (copy)*`), Lock-Dateien (`uv.lock`) und Coverage-Caches (`.coverage.*`).
  - CI-Workflow `.github/workflows/ci.yml` hinsichtlich Bytecode-Kompilierung (`compileall`) und Runner-Flags (`pytest -ra -v`) re-validiert.
  - Zweisprachige `SECURITY.md` hinsichtlich Supported-Versions-Matrix (`0.4.x`), 48h-Reaktions-SLA, 5-Werktage-Triage und offizieller Kontakte re-verifiziert.
  - `llms.txt` Last-checked-Zeitstempel auf 2026-09-10 und Verifikationsbaseline synchronisiert.
  - Automatisierte Vertragstestsuite in `tests/test_metadata.py` und `tests/test_versioning.py` um Tests für Pytest-Konfiguration, erweiterte Gitignore-Muster und aktuellen Pfad-A-Changelog-Eintrag ausgebaut.

- 2026-09-09: Pfad B: Discoverability, Visual Architecture, Runtime Invariants & CI Hardening.
  - Primäres zweisprachiges Systemarchitektur-Diagramm (`flowchart TD`) in `README.md` und `README_de.md` integriert: visualisiert Client/CLI-Schicht, Bounded Scanner & Harvester, SQLite-Evidenzschicht, Auflösungs-Engine und Fail-Closed-Governance-Gate.
  - Verbindliche 10-Punkte-Laufzeitinvarianten-Tabelle (`INV-LOCAL-01` bis `INV-SLA-10`) in beiden Dokumentationen etabliert.
  - Vollständiges Shields.io-Badge-Set um Version (0.4.0), Security SLA (48h/5d) und Code-Style Ruff ergänzt sowie 14-Punkte-Schnellnavigation mit exakten Ankerzielen synchronisiert.
  - `SECURITY.md` um Dachorganisations-Kontakt `security@open-bricks.org` erweitert und Reaktions-SLAs bekräftigt.
  - CI-Workflow `.github/workflows/ci.yml` um Bytecode-Kompilierungsprüfung (`compileall`) erweitert und Pytest-Aufruf gehärtet (`-ra -v`).
  - `.gitignore` gegen Multi-Host-Konfliktdateien, Multi-Agent-Locks (`LOCK`, `LOCK.*`, `*.lock`, `LOCK.permissions.json`) und temporäre Build-Caches gehärtet.
  - Lokales Marketing- und Visual-Architecture-Protokoll `MARKETING-LOG.txt` im Repository-Root etabliert.
  - `llms.txt` Last-checked-Zeitstempel auf 2026-09-09 synchronisiert.
  - Vertragstestsuite `tests/test_metadata.py` um Validierungen für Architektur-Flowchart, Invarianten-Tabelle, Marketing-Log und CI-Bytecode-Gate erweitert.

- 2026-09-08: AI Security & Dependency Audit: Third-Party-Lizenzinventar, PEP 639 & SLA-Härtung.
  - Drittanbieter-Lizenzinventar `THIRD_PARTY_LICENSES.md` mit detaillierter Aufstellung aller Runtime- (`cryptography>=41`, Apache-2.0 / BSD-3-Clause) und Entwicklungsabhängigkeiten (`pytest`, `ruff`, `build`, `jsonschema`) sowie vollständigen Lizenztexten angelegt.
  - `pyproject.toml` um standardisierte PEP 639 `license-files = ["LICENSE", "THIRD_PARTY_LICENSES.md"]` Deklaration erweitert.
  - `.gitignore` um Secret-, Credential- und Token-Muster (`.npmrc`, `*token*`, `*secret*`, `*.pem`, `*.pfx`, `*.p12`) und Multi-Host-Konfliktmuster (`*-WORKSTATION-LG*`, `*-ASUS-GEI*`) gehärtet.
  - Zweisprachige `SECURITY.md` um verbindliches Response-SLA (Empfangsbestätigung innerhalb von 48 Stunden, Triage & Ersteinschätzung innerhalb von 5 Werktagen) erweitert.
  - `llms.txt` Last-checked-Zeitstempel auf 2026-09-08 aktualisiert und Querverweis auf `THIRD_PARTY_LICENSES.md` ergänzt.
  - Metadaten- und Vertragstestsuite `tests/test_metadata.py` um Prüfungen für Lizenzinventar, PEP 639 `license-files`, erweiterte Gitignore-Muster und Sicherheits-SLA erweitert.

- 2026-08-26: Repository Hygiene Verification Refresh (Pfad A).
  - `llms.txt` Last-checked und Verifikationsbaseline auf den heutigen Maintenance-Check synchronisiert.
  - CI-Dev-Extras um `jsonschema>=4.0` ergänzt, damit `tests/test_search_routing.py` in frischen GitHub-Actions-Umgebungen sammelbar ist.
  - Scan-Time-Budget-Test normalisiert temporäre Root-Pfade und persistierte Scope-Vergleiche, damit macOS-/Windows-Runner die Rollback-Strecke deterministisch prüfen.
  - Lokale Testsuite erneut vollständig geprüft (179 Pytest Tests plus 26 Subtests), ergänzt durch Ruff, Compileall, `git diff --check` und engen Secret-Scan.
  - GitHub-Repositorybeschreibung auf den dokumentierten Projektzweck gesetzt.

- 2026-08-24: Repository Hygiene, CI Concurrency Hardening & Contract Parity Check (Pfad A).
  - GitHub Actions CI-Workflow (`.github/workflows/ci.yml`) um Concurrency-Steuerung mit automatischem Abbruch veralteter Läufe (`cancel-in-progress: true`) gehärtet.
  - Zweisprachige `SECURITY.md` um strukturierte Supported-Versions-Matrix (`0.4.x`) in beiden Sprachfassungen erweitert.
  - PEP 621 Metadaten in `pyproject.toml` um `Topic :: Security`, `Topic :: System :: Monitoring` und vollständige Ecosystem-URLs (`Parent Organization` und `Umbrella Ecosystem`) erweitert.
  - Repository-Hygiene & `.gitignore` um Synchronisationskonfliktmuster (`*.sync-conflict-*`, `*.conflict`) und Lockdateien (`LOCK*.txt`) ergänzt.
  - Automatisierte Metadaten- und Vertragstestsuite `tests/test_metadata.py` um Tests für CI-Concurrency, Supported-Versions-Matrix, Ecosystem-URLs und Gitignore-Hygiene erweitert (11/11 tests, Gesamtsuite: 179 Pytest Tests 100% grün).
  - Maschinenlesbarer Kontext (`llms.txt`) und README-Badges auf Version `0.4.0` und 179 verifizierte Tests synchronisiert.

- 2026-08-21: Discoverability, README-Design, Security & Metadata Parity Check (Pfad B).
  - GitHub Actions CI-Workflow (`.github/workflows/ci.yml`) für Multi-OS (`ubuntu-latest`, `windows-latest`, `macos-latest`) und Python 3.10-3.13 Matrix mit `ruff`-Linter und `pytest` implementiert.
  - Zweisprachige `SECURITY.md` mit Local-First-, Zero-Egress-, Fail-Closed Authority-Receipt- und Loopback-Bindungsgarantien sowie direkten Sicherheitskontaktadressen (`security@ellmos.ai` / `support@lukasgeiger.com`) integriert.
  - Zweisprachiges Mermaid-Sequenzdiagramm für den evidenzbasierten Funktions-Auflösungs- & Drift-Erkennungs-Lebenszyklus in `README.md` und `README_de.md` integriert.
  - Verbliebene Git-Merge-Konfliktmarker in `README.md` und `README_de.md` vollständig behoben und beide Abschnitte (External Composition Authorities & Blocked Resolution Quarantining) nahtlos vereint.
  - Schnellnavigation und Shields.io Badges (CI Status, Python 3.10-3.13, Pytest 173 passed, Zero-Egress, Local-First, MIT, open-bricks, LLM-Ready) in `README.md` und `README_de.md` synchronisiert.
  - Geschwisterwerkzeuge-Matrix auf 18 Partner-Repositories über 7 Ökosysteme erweitert.
  - PEP 621 Metadaten in `pyproject.toml` um Classifiers, Keywords, `[project.urls]` und `[tool.ruff]` erweitert.
  - Neue automatisierte Metadaten- und Vertragstestsuite `tests/test_metadata.py` mit 10/10 Tests implementiert (173 Pytest Tests 100% grün).

- 2026-08-16: Discoverability, README-Design, Badges & Metadata Parity Check (Pfad B).
  Merge-Reconciliation zwischen `main` und `origin/main` (V4-Composition-Integrität,
  transaktionales Receipt-Handling, Stack-Schema-Pins und Fleet-Resolution vereint).
  Banner und Pytest-Badge (163 passed) in `README.md` und `README_de.md` synchronisiert.
  Geschwisterwerkzeuge-Matrix (`policy-registry`, `sqlite-transit-sync`, `coma`,
  `automation-master`, `DevCenter`, `CodeBox`) in beiden Sprachfassungen verlinkt.
  Erweiterte automatisierte Paritätstests in `tests/test_versioning.py`.

- 2026-08-13: TASKPLAN-Bundle 1719/1722/1724 ergänzt scopeweise,
  hash-/versionsgepinnte externe Composition-Regeln mit fail-closed
  Cardinality-Report, referenzielle `system-explorer.probe-receipt.v1`-
  Imports ohne Rohresultat-/Coverage-Eskalation sowie die optionale
  `--stack-schema-pin`-Prüfung für externe `ellmos.stack.v2`-Autorität.
  Synthetische Tests decken exact/min/max, Overlap/Konflikt, Receipt-
  Idempotenz/Tamper und Schema-Drift ab. Keine Provider-, Schwarm-, Credential-
  oder Mirror-Aktion.

## [Unreleased]

### Versionsstand (2026-08-10)
- Packaging, Runtime, Manifest und Steuerdokumente sind auf den kanonischen
  Development-Stand `0.4.1` synchronisiert; ein Release ist nicht autorisiert.
- Der externe `importlib.metadata`-Fallback wird in `VERSIONING.md` und einem
  Regressionstest ausdrücklich als umgebungsfremd behandelt.

### TASKPLAN-Readback 1716–1718 (2026-08-10)
- Commit `ea22747` bündelt Resolution-, Actual-Self- und Authority-Imports der
  `search-route` in einer äußeren All-or-Nothing-Transaktion; ungültige spätere
  Receipts lassen Store, Evidence, Identity und Edges unverändert.
- 150 Pytest-Tests/26 Subtests sowie 150 Unittest-Fälle, Ruff, Compileall,
  CLI-Hilfe, Manifest-Validierung und `doc-lint` sind lokal grün.
