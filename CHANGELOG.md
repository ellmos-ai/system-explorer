# Changelog

## Unreleased

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
