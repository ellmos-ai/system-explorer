# Beitragsrichtlinie / Contributing Guide

## Deutsch

Vielen Dank für Ihr Interesse, zu `system-explorer` beizutragen!

### Wie Sie beitragen können

1. **Bug melden:** Erstellen Sie ein Issue mit dem Label `bug`
2. **Feature vorschlagen:** Erstellen Sie ein Issue mit dem Label `enhancement`
3. **Dokumentation verbessern:** Erstellen Sie ein Issue mit dem Label `documentation`
4. **Code beitragen:** Erstellen Sie einen Pull Request

### Pull Requests

1. Forken Sie das Repository
2. Erstellen Sie einen Feature-Branch: `git checkout -b feature/mein-feature`
3. Committen Sie Ihre Änderungen: `git commit -m "Beschreibung der Änderung"`
4. Pushen Sie den Branch: `git push origin feature/mein-feature`
5. Erstellen Sie einen Pull Request

### Developer Certificate of Origin (DCO)

Dieses Projekt verwendet den [Developer Certificate of Origin (DCO)](https://developercertificate.org/).
Bitte signieren Sie jeden Commit mit `--signoff`:

```bash
git commit --signoff -m "Beschreibung der Änderung"
```

Damit bestätigen Sie, dass Sie das Recht haben, den Code unter der Projektlizenz (MIT) einzureichen.

### Code-Richtlinien & Quality Gates

Vor jedem Commit und Pull Request müssen folgende Tore lokal fehlerfrei durchlaufen:

- **Linter (ruff):** `ruff check .` (0 Fehler)
- **Tests (pytest):** `pytest -ra -v` (100% grün)
- **Bytecode-Kompilierung:** `python -m compileall -q src tests` (0 Fehler)
- **Whitespace & Git Hygiene:** `git diff --check` (0 Whitespace-Fehler)
- **Release Gate Compliance:** `final_gate_check.py` (10 PASS, 0 FAIL, 0 WARN)
- **Encoding:** UTF-8 ohne BOM für alle Textdateien
- **Sicherheit & Egress:** Keine hardcodierten Pfade, Secrets oder API-Keys; striktes `RunAsInvoker` (keine Admin-/UAC-Rechte)
- **Invarianten:** Einhaltung aller 10 Governance- und Laufzeit-Invarianten `INV-LOCAL-01` bis `INV-SLA-10`

### Governance- & Laufzeit-Invarianten (INV-LOCAL-01 bis INV-SLA-10)

| Invariante | Name | Spezifikation & Sicherheitsgrenze |
|---|---|---|
| `INV-LOCAL-01` | **Local-First & Zero-Egress** | 100% Offline-Betrieb standardmäßig; Web-Dashboard bindet ausschließlich an `127.0.0.1:8765`; null Telemetrie oder Pingbacks. |
| `INV-EVID-02` | **Immutable Evidence & Checksums** | Discovered Files bleiben unverändert; SQLite-Speicher erfasst nur URIs, Locators und SHA-256 Hashes. |
| `INV-FAIL-03` | **Fail-Closed Resolution & Anti-Drift** | Fehlende Authority Receipts, Hash-Drift oder unbekannte Funktionen triggern sofortige Quarantäne. |
| `INV-RO-04` | **Read-Only Governance & Zero Mutation** | Vorschläge und Systemkarten operieren rein lesend und verändern niemals gescannte Codebasen. |
| `INV-NON-05` | **Non-Elevation & RunAsInvoker** | Strikt unprivilegierte Ausführung im regulären Benutzerkontext ohne Administrator- oder Root-Rechte. |
| `INV-SCOP-06` | **Strict Scope & Host Isolation** | Physische Maschinen (`WORKSTATION-LG` vs `ASUS-GEI`) bleiben strikt getrennt; kein automatisches Mergen gleicher Namen. |
| `INV-ED25519-07`| **Cryptographic Receipt Integrity** | Ed25519-signierte Actual-Self Receipts werden gegen gepinnte öffentliche Schlüssel validiert. |
| `INV-TIME-08` | **Bounded Scan Time & Rollback** | Transaktionale SQLite-Engine mit Time-Budgets; Abbrüche führen zu atomarem Rollback ohne Hot-Journal. |
| `INV-CROSS-09` | **Cross-Platform Parity & Sync Defense** | `.gitignore` blockiert Sync-Konflikte, Host-Nebenstände und Locks; Pfade plattformübergreifend normalisiert. |
| `INV-SLA-10` | **48h Response / 5d Triage SLA** | Verbindliche Sicherheitsreaktionszeiten mit 48h Erstprüfung und 5 Tagen Triage. |

### Plan D Source of Truth & Entwicklungs-Workflow

- **Kanonischer Arbeitsort (Source of Truth):** `C:\_Local_DEV\repos\system-explorer` (lokaler Klon) und GitHub `origin`.
- **OneDrive-Rolle:** Nur gitloser Spiegel/Projektion für Multi-Device-Verfügbarkeit. Geänderter Code wird nach OneDrive gespiegelt, nicht dort originär entwickelt, um Lock-Konflikte und Cloud-Sync-Abbrüche zu verhindern.

### Haftungsausschluss (§ 521 BGB Gefälligkeitsrecht)

Da dieses Softwareprojekt unentgeltlich als Open-Source-Software bereitgestellt wird, haftet der Anbieter gemäß § 521 BGB nur für Vorsatz und grobe Fahrlässigkeit. Es wird keine Gewähr für Mängelfreiheit oder ununterbrochenen Betrieb übernommen.

### Sicherheits-SLA & Kontakt

Verbindliche Sicherheits-SLA: 48 Stunden Reaktionszeit auf Meldungen, 5 Tage Triage-Frist. Sicherheitsrelevante Schwachstellen bitte vertraulich melden an:
- `security@ellmos.ai`
- `security@open-bricks.org`
- `support@lukasgeiger.com`
- `lukas@open-bricks.org`

### Version-Freeze-Disziplin (T-20260920-167562623)

- Die Version `0.4.2` ist in allen Manifesten (`pyproject.toml`, Quelltexten) eingefroren.
- Versionsanhebungen sind separaten, autorisierten Release-Vorgängen vorbehalten.
- Alle Neuerungen, Fehlerbehebungen und Hygiene-Updates werden unter `## [Unreleased]` in `CHANGELOG.md` dokumentiert.

### Erste Schritte

```bash
git clone https://github.com/ellmos-ai/system-explorer.git
cd system-explorer
pip install -e ".[dev]"
pytest -ra -v
python -m system_explorer.cli --help
```

---

## English

Thank you for your interest in contributing to `system-explorer`!

### How to Contribute

1. **Report bugs:** Create an issue with the `bug` label
2. **Suggest features:** Create an issue with the `enhancement` label
3. **Improve documentation:** Create an issue with the `documentation` label
4. **Contribute code:** Create a Pull Request

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "Description of change"`
4. Push the branch: `git push origin feature/my-feature`
5. Create a Pull Request

### Developer Certificate of Origin (DCO)

This project utilizes the [Developer Certificate of Origin (DCO)](https://developercertificate.org/).
Please sign off every commit using `--signoff`:

```bash
git commit --signoff -m "Description of change"
```

By signing off, you certify that you have the right to submit the code under the project's MIT License.

### Code Guidelines & Quality Gates

Before submitting commits or pull requests, verify all local quality gates pass cleanly:

- **Linter (ruff):** `ruff check .` (0 errors)
- **Tests (pytest):** `pytest -ra -v` (100% green)
- **Bytecode Compilation:** `python -m compileall -q src tests` (0 errors)
- **Whitespace & Git Hygiene:** `git diff --check` (0 whitespace errors)
- **Release Gate Compliance:** `final_gate_check.py` (10 PASS, 0 FAIL, 0 WARN)
- **Encoding:** UTF-8 without BOM for all text files
- **Security & Egress:** No hardcoded paths, secrets, or API keys; strict `RunAsInvoker` (no admin/elevation rights)
- **Invariants:** Full adherence to all 10 Governance and Runtime Invariants `INV-LOCAL-01` through `INV-SLA-10`

### Governance & Runtime Invariants (INV-LOCAL-01 to INV-SLA-10)

| Invariant ID | Name | Specification & Security Boundary |
|---|---|---|
| `INV-LOCAL-01` | **Local-First & Zero-Egress** | 100% offline by default; web dashboard binds exclusively to loopback `127.0.0.1:8765`; zero telemetry sockets. |
| `INV-EVID-02` | **Immutable Evidence & Checksums** | Discovered files remain in place; SQLite evidence records store only URIs, locators, and SHA-256 digests. |
| `INV-FAIL-03` | **Fail-Closed Resolution & Anti-Drift** | Missing authority receipts, content hash drift, or unknown functions fail closed without heuristic guessing. |
| `INV-RO-04` | **Read-Only Governance & Zero Mutation** | Maps and proposals generated without mutating scanned codebases or external systems. |
| `INV-NON-05` | **Non-Elevation & RunAsInvoker** | Executes entirely within unprivileged user space without administrative elevation. |
| `INV-SCOP-06` | **Strict Scope & Host Isolation** | Physical machines (`WORKSTATION-LG`, `ASUS-GEI`) strictly isolated; identical names are never cross-merged. |
| `INV-ED25519-07`| **Cryptographic Receipt Integrity** | Ed25519-signed actual-self receipts verified against pinned public keys. |
| `INV-TIME-08` | **Bounded Scan Time & Rollback** | Transactional SQLite engine with time budget; scan interruptions roll back atomically. |
| `INV-CROSS-09` | **Cross-Platform Parity & Sync Defense** | `.gitignore` excludes cloud sync conflict copies and respects canonical multi-agent locks. |
| `INV-SLA-10` | **48h Response / 5d Triage SLA** | Security vulnerability response with 48h initial check and 5-day triage commitment. |

### Plan D Source of Truth & Development Workflow

- **Canonical Working Location (Source of Truth):** `C:\_Local_DEV\repos\system-explorer` (local Git clone) and GitHub `origin`.
- **OneDrive Role:** Pure gitless mirror/projection for multi-device availability. Code is changed, tested, and committed locally to prevent sync locks.

### Statutory Disclaimer (§ 521 BGB German Gratuitous Rules)

As this software project is provided free of charge as open-source software, liability of the provider is limited to intent and gross negligence pursuant to § 521 BGB. No warranty is assumed for freedom from defects or uninterrupted operation.

### Security Response SLA & Contact

Enterprise coordinated vulnerability disclosure: 48-hour initial response, 5-day triage window. Please report security issues confidentially to:
- `security@ellmos.ai`
- `security@open-bricks.org`
- `support@lukasgeiger.com`
- `lukas@open-bricks.org`

### Version-Freeze Discipline (T-20260920-167562623)

- Version `0.4.2` is frozen across all manifests (`pyproject.toml`, source code).
- Version bumps belong strictly to authorized release pipelines.
- All new features, bugfixes, and hygiene updates are documented under `## [Unreleased]` in `CHANGELOG.md`.

### Getting Started

```bash
git clone https://github.com/ellmos-ai/system-explorer.git
cd system-explorer
pip install -e ".[dev]"
pytest -ra -v
python -m system_explorer.cli --help
```
