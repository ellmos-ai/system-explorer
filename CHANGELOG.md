# Changelog

## Unreleased

- 2026-08-26: Repository Hygiene Verification Refresh (Pfad A).
  - `llms.txt` Last-checked und Verifikationsbaseline auf den heutigen Maintenance-Check synchronisiert.
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
  Development-Stand `0.4.0` synchronisiert; ein Release ist nicht autorisiert.
- Der externe `importlib.metadata`-Fallback wird in `VERSIONING.md` und einem
  Regressionstest ausdrücklich als umgebungsfremd behandelt.

### TASKPLAN-Readback 1716–1718 (2026-08-10)
- Commit `ea22747` bündelt Resolution-, Actual-Self- und Authority-Imports der
  `search-route` in einer äußeren All-or-Nothing-Transaktion; ungültige spätere
  Receipts lassen Store, Evidence, Identity und Edges unverändert.
- 150 Pytest-Tests/26 Subtests sowie 150 Unittest-Fälle, Ruff, Compileall,
  CLI-Hilfe, Manifest-Validierung und `doc-lint` sind lokal grün.
