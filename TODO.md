# Pre-Release TODO: system-explorer

**Audit Date:** 2026-10-02<br>
**Auditor:** Antigravity / Gemini via `[AI_MODULES_CARE]`<br>
**Target Repo:** `ellmos-ai/system-explorer`<br>

---

## Scope notes (read first)

Evidence-backed system maps of desired functions, carriers, actual use, and architecture drift.
Separates desired functions from function carriers across skills, repos, MCP servers, stacks, and CLI tools.
Guarantees zero-egress, local loopback binding (`127.0.0.1:8765`), fail-closed cryptographic authority receipts, and immutable SQLite evidence storage (`INV-LOCAL-01` through `INV-SLA-10`).

---

## BLOCKER

> Items that **must** be resolved before public release. Any remaining blocker prevents the Final Gate Check from passing.

- [x] **Secrets:** Automated regex- and AST-scan confirms 0 plaintext credentials, tokens, or API keys in tracked files
- [x] **Private Data (PII):** 0 PII patterns, private contact leaks, or employer references
- [x] **Hardcoded Paths:** Neutralized all personal developer paths; portable `<OneDrive>` and relative paths
- [x] **Database Files:** No `.db`, `.sqlite`, or temporary database files tracked in Git
- [x] **.env Files:** No `.env` or secret configuration files tracked
- [x] **BACH Internals:** Zero BACH-specific documents or coupling in tracked files
- [x] **.gitignore:** Contains all mandatory patterns (`__pycache__`, `*.pyc`, `.env`, `*.db`, `.venv/`, `.idea/`, `.vscode/`, `data/`) and multi-host lock/sync protections
- [x] **LICENSE:** Permissive MIT License present and verified
- [x] **README.md:** Complete English `README.md` with 18-point dual navigation and German `README_de.md` parity
- [x] **TODO.md:** Standardized `TODO.md` with `## STATUS` table present

---

## HIGH PRIORITY

> Quality and architectural invariants for release readiness.

- [x] **TASK-SE-01 — Cardinality Evaluation:** Kardinalitäten aus gepinnten externen Composition-Regeln scopeweise bewerten; fehlende oder widersprüchliche Regeln blockieren.
- [x] **TASK-SE-02 — Read-Only GUI Host Embedding:** UI als optionales GET-only-Panel in vorhandenen GUI-Host (`unified-gui-readonly` Plugin) einbetten.
- [x] **TASK-SE-03 — Swarm Probe Receipts Import:** Externe Schwarmresultate als standardisierte, referenzielle Probe-Receipts importieren, ohne Coverage-/Authority-Eskalation.
- [x] **TASK-SE-04 — Stack Schema Anchoring:** Autoritatives externes `ellmos.stack.v2`-Schema über eine gepinnte Referenz anbinden; fehlende oder driftende Quelle blockiert die Resolution.
- [ ] **TASK-SE-05 — Signed Incremental Evidence Receipts:** Signierte Evidenzreceipts und inkrementelle Scans über Merkle-Bäume weiter optimieren.

---

## MEDIUM PRIORITY

> Enhancements and optional adapter bridges.

- [ ] **TASK-SE-06 — Live Hooks Adapter Auth:** Provider-native Live-Hooks ausschließlich als optionale Adapter anbinden (redigierter Vertrag vorhanden; konkrete Provider-Auth bleibt extern).
- [ ] **TASK-SE-07 — Gemini/AGY Decoder:** Protobuf-spezifischen Gemini/agy-Decoder für strukturierte Session-Transkripte ergänzen.
- [ ] **TASK-SE-08 — UC6 Render Adapter:** Optionalen echten UC6-Renderadapter erst anbinden, wenn `ai-media-editor` einen stabilen maschinenlesbaren Rendervertrag mit Rechte-/Strategie-/Readback-Receipt veröffentlicht.
- [x] **TASK-SE-09 — PEP 561 Support:** `system_explorer/py.typed` integriert und in `pyproject.toml` verankert.
- [x] **TASK-SE-10 — Level 1 SBOM Parity:** `THIRD_PARTY_LICENSES.md` und `THIRD_PARTY_LICENSES.txt` mit 10 Invarianten synchronisiert.

---

## LOW PRIORITY

> Future optimizations and ecosystem extensions.

- [ ] Extended web dashboard filtering by tags and module scopes
- [ ] Automated Mermaid diagram export CLI command
- [ ] CI matrix expansion for Python 3.14 pre-releases

---

## STATUS

| Category | Status | Notes |
|----------|--------|-------|
| Secrets | :green_circle: | 0 secrets tracked; test sentinels use explicit raw_sentinel identifiers |
| Private Data (PII) | :green_circle: | 0 personal PII or private developer data found in tracked files |
| Hardcoded Paths | :green_circle: | All personal paths replaced with portable `<OneDrive>` and relative paths |
| Database Files | :green_circle: | 0 `.db` or SQLite files tracked; SQLite evidence generated in temp |
| .env Files | :green_circle: | 0 `.env` files tracked; `.gitignore` guards all environment files |
| BACH Internals | :green_circle: | 0 BACH-internal documents or dependencies; sovereign module |
| .gitignore | :green_circle: | All required patterns (`__pycache__`, `*.pyc`, `.env`, `*.db`, `data/`, etc.) present |
| Language & Parity | :green_circle: | English `README.md`, bilingual `README_de.md`, 18-point dual navigation |
| LICENSE & SBOM | :green_circle: | MIT License, Level 1 SBOM (`THIRD_PARTY_LICENSES.md` & `.txt`), PEP 639 metadata |
| Overall | **PASS (10/10 Gates)** | `final_gate_check.py` 10 PASS, 0 FAIL, 0 WARN; 231 Pytest-Tests grün |

**Audit Date:** 2026-10-02 (Audited by Antigravity / Gemini via `[AI_MODULES_CARE]`)<br>
**Gate Check Exit Code:** 0 (10 PASS, 0 FAIL, 0 WARN — READY FOR RELEASE)<br>
**Test Suite Status:** 205 passed, 26 subtests passed (100% grün auf Windows)
