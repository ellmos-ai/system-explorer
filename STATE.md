---
name: "system-explorer-state"
type: state-snapshot
version: 0.2.0
updated: "2026-07-29"
updated_by: "codex"
current_phase: "MVP release"
last_verified: "2026-07-29"
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
- V4-Komposition: additive Bundle-/System-/Instanz-/Test-/Fleet-Verträge und
  deterministische Read-only-Auflösung auf Feature-Branch
- Medien-Connector: UC6-Handoff aus analysierten Karten; echter Render bleibt
  expliziter `ai-media-editor`-Schritt
- Repo-Schaltpläne: Dry-Run, atomarer Apply, optionaler Commit/Push und
  Upstream-Readback für einzelne Repos oder pfadbasierte Bundles
- Nächster Freigabepunkt: Test-, UI- und Mirror-Readback
