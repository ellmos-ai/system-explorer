---
name: "system-explorer-state"
type: state-snapshot
version: 0.4.0
updated: "2026-08-29"
updated_by: "codex"
current_phase: "MVP release"
last_verified: "2026-08-29"
description: |
  Current-state snapshot for fast session-start orientation in system-explorer.
---

# STATE

- Phase: MVP-Implementierung
- Architektur: evidenzgestützte Soll-/Ist-/Deckungskarten
- Mutationen am Zielsystem: absichtlich nicht implementiert
- Datenspeicherung: lokale SQLite-Referenzen, keine rohen Transcripttexte
- Randressourcen: installierte Software mit Funktionen, LLM-Steuerwegen,
  Readiness-Symbolen und getrenntem Tokenersparnisstatus
- Software-Endpoint-Registry: deterministische, schema-validierte und
  inhaltsgehashte Read-only-Projektion des Ressourcengraphen; eigenständig per
  `software-endpoints --refresh` nutzbar und als OCEAN-Provider vorgesehen
- Verifikation 2026-08-29: 181 Pytest-Tests plus 26 Subtests, Ruff, Compileall,
  CLI-Hilfe und Modulmanifestvalidierung grün
- V4-Komposition: additive Bundle-/System-/Instanz-/Test-/Fleet- und
  Komponentenregistry-Verträge, deterministische Read-only-Auflösung sowie
  fail-closed `declared_only`-Activation-Gates
- Externe Autoritätsgrenzen: scopeweise Cardinality-Regeln, referenzielle
  Probe-Receipts und gepinnte `ellmos.stack.v2`-Schema-Verifikation
- Fleet-Auflösung: `fleet-resolve` löst gepinnte Fleet-Manifeste zu ihren
  Mitgliedssystemen auf, erhält Hostbindungen, führt begründete
  Desired-Abweichungen und trennt blockierende Pflichtlücken von tolerierten
- Medien-Connector: UC6-Handoff aus analysierten Karten; echter Render bleibt
  expliziter `ai-media-editor`-Schritt
- Repo-Schaltpläne: Dry-Run, atomarer Apply, optionaler Commit/Push und
  Upstream-Readback für einzelne Repos oder pfadbasierte Bundles
- TASKPLAN-Readback (2026-08-10): lokaler Funktions-HEAD `ea22747` mit 150
  Pytest-Tests/26 Subtests und 150 Unittest-Fällen, Ruff, Compileall,
  CLI-Hilfe, Manifest-Validierung und `doc-lint` erfolgreich; Loopback-UI,
  Manifest und vier statische Assets mit HTTP 200 gelesen. Vollständige
  Trennung von PASS/NOT RUN/BLOCKED: [`MVP-GATE.md`](MVP-GATE.md).
  `origin/main` (`6915688`) liegt sechs Commits voraus; der direkte Push
  wurde `non-fast-forward` abgelehnt. Kein Pull, Merge oder Force-Push.
- MVP-Freigabe: BLOCKED wegen kontrolliertem Mirror-Readback; kein Release.
- TASKPLAN-Bundle 1719/1722/1724: neutral implementiert und synthetisch
  verifiziert; externe Autoritäten bleiben referenziell und fail-closed.
