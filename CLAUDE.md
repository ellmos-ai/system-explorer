---
name: "system-explorer"
type: project-docs
profile: "FULL"
version: 0.4.0
created: "2026-07-29"
updated: "2026-08-05"
reason_last_change: "Read-only Vollsystem-Resolution mit sichtbar blockierten Activation-Gates ergänzt"
last_verified: "2026-08-05"
author: "Lukas Geiger"
anthropic_compatible: true
description: |
  Project-specific instructions for AI coding agents in system-explorer.
  Primary audience: Claude Code. Other agents redirect here via AGENTS.md.
---

# CLAUDE.md — Instructions für AI Coding Agents

> **Für LLM-Agenten (Claude Code, Codex, Cursor, Cline, Aider, Windsurf, Copilot).**
> Diese Datei wird von Claude Code **automatisch** in den Kontext geladen.
> Andere Agents lesen zuerst `AGENTS.md` → Redirect hierher.
>
> **YAML-Header oben** ist maschinenlesbar und wird von `_tools/doc-lint` validiert.
> Bei Änderungen an der Doku: `updated` und `last_verified` nachziehen.

---

> **Selbstkorrektur:** Wenn du veraltete Passagen oder Verweise entdeckst, oder sogar missgeleitet wirst, korrigiere diese Datei autonom. Wenn du etwas Neues gebaut oder erstellt hast, prüfe: Hättest du es durch das Lesen der Dateien, die du gelesen hast, bereits gefunden und/oder richtig verstanden? Wenn nicht, setze dort an und behebe es, sodass du es gefunden und verstanden hättest.

> **Dateigröße:** Wenn diese Datei zu lang wird, verwende das Cut-and-Clue-Verfahren → `CUT-AND-CLUE.md` (Pointer-Verfahren mit Vorläufer/Nachfolger-Dateien).

## Projekt

**system-explorer** — evidenzgestützte Soll-/Ist-/Deckungs- und
Steuerdokumentkarten für modulare Agenten- und Softwaresysteme.

**Pfad:** `C:\_Local_DEV\repos\system-explorer`
**Repository:** `github.com/ellmos-ai/system-explorer` (öffentlich)
**Sprache/Stack:** Python 3.10+, SQLite, Vanilla HTML/CSS/JavaScript

## Rolle & Stil

Arbeite als Senior Python-/Systemarchitektur-Entwickler mit Fokus auf
Evidenztreue, Datenschutz, neutrale Pfade und klar getrennte Wahrheitsgrenzen.

**Kommunikation:**
- Sprache: Deutsch (Code/Identifier bleiben englisch)
- Stil: knapp, direkt, ohne Preamble
- Bei Unsicherheit: fragen statt raten

## Einstieg (Quick Commands)

```bash
# Scanner, konfigurierte Sollquellen und Transcripts einlesen
system-explorer ingest --config examples/self-scan.json

# Lokale Kartenoberfläche
system-explorer serve --config examples/self-scan.json

# Tests
python -m unittest discover -s tests -v
ruff check src tests
```

**Für vollständige Session-Bootstrap-Sequenz siehe [`START.md`](./START.md).**
**Für aktuellen Stand siehe [`STATE.md`](./STATE.md).**

## Hard Rules (non-negotiable)

- **NIEMALS** Credentials committen (`.env`, `*.key`, `credentials.json`, tokens)
- **NIEMALS** `git push --force` auf `main`/`master` (wenn unvermeidbar, nur über ein projektspezifisch geprüftes Admin-Playbook)
- **NIEMALS** destructive Operationen ohne explizite User-Bestätigung (`rm -rf`, `DROP TABLE`, `git reset --hard`)
- **IMMER** bei Python auf Windows: `PYTHONIOENCODING=utf-8` vor dem Call
- **IMMER** vor Push: `git status` prüfen

## Soft Guidelines

- Bevorzuge `Edit` vor `Write` für existierende Dateien
- Keine prophylaktischen Features — nur was gerade gebraucht wird
- Keine Kommentare für selbsterklärenden Code
- Bei gleichartigen Dateien: vor Anlegen prüfen ob ein bestehendes erweitert werden kann

## Selbstreflexion vor komplexen Aktionen

Bevor du destructive Git-Operationen ausführst oder Architektur-relevante
Änderungen machst, frage dich:
1. Habe ich den aktuellen State verstanden (`git status`, `git log`)?
2. Gibt es eine weniger destruktive Alternative?
3. Ist `--force-with-lease` statt `--force` möglich?
4. Wird diese Änderung in `DECISIONS.md` dokumentierbar?

## Projekt-Struktur

Details siehe [`ARCHITECTURE.md`](./ARCHITECTURE.md). Kurz:

```
system-explorer/
├── src/system_explorer/  # Scanner, Store, Adapter, Karten, CLI und UI
├── tests/                # isolierte Unit-/Integrations-Fixtures
├── examples/             # neutrale Konfigurationen und Sollspezifikation
├── docs/                 # Evidenz-, Adapter- und Anforderungsdokumentation
├── workflows/      # Multi-Step-Playbooks
├── _tools/         # Admin-Utilities
└── .github/        # GitHub-native Config
```

## Wichtige Dateien

| Datei | Zweck |
|---|---|
| [`START.md`](./START.md) | Session-Bootstrap — lies als Erstes beim Session-Start |
| [`STATE.md`](./STATE.md) | Wo-stehen-wir-Snapshot — aktueller Stand |
| [`TODO.md`](./TODO.md) | Aktive Tasks |
| [`DONE.md`](./DONE.md) | Erledigte Tasks (archiviert via `_tools/todo-archive`) |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Struktur & Modul-Graph (auto-generiert) |
| [`DECISIONS.md`](./DECISIONS.md) | Warum-Entscheidungen (ADRs) |
| [`PATTERNS.md`](./PATTERNS.md) | Do/Don't mit Code-Beispielen |
| [`WORKFLOWS.md`](./WORKFLOWS.md) | Router zu Multi-Step-Playbooks |
| [`TOOLS.md`](./TOOLS.md) | Router zu Admin-Utilities |
| [`GLOSSARY.md`](./GLOSSARY.md) | Projekt-Jargon |
| [`CHANGELOG.md`](./CHANGELOG.md) | Chronik |
| [`docs/CONNECTOR-ADAPTERS.md`](./docs/CONNECTOR-ADAPTERS.md) | ai-media-editor- und Repo-/Bundle-Schaltplanvertrag |

## Domain-Kontext

Das Modul trennt gewünschte Systemfunktionen von ihren Funktionsträgern
(Skills, Repos/Module, MCP, Stacks, Commands und Akteure). Statische
Deklaration ist kein Nutzungsbeleg. Transcriptinhalte bleiben an ihrer Quelle;
Explorer registriert nur URI, Hash, Locator und normalisierte Merkmale.
Steuertextdateien bilden einen eigenen Graph aus Verzeichnis-, Einstiegs-,
Pointer- und Referenzbeziehungen.

Installierte Fremdprogramme, Module, Repositories und Skripte werden als
kristallisierte Randressourcen modelliert. Installation, LLM-Steuerbarkeit,
Funktionsdeckung, Flexibilität und empirisch belegte Tokenersparnis sind
getrennte Aussagen; siehe `docs/CRYSTALLIZED-RESOURCES.md`.

## Umgebungs-Hinweise

- Standard-Datenbank: `~/.system-explorer/evidence.db`
- UI nur auf Loopback binden, solange keine externe Authentisierung existiert.
- Git-Source-of-Truth ist dieser lokale Clone; OneDrive ist nur Mirror.
- Keine rohen Prompts, Antworten, Toolargumente oder Toolergebnisse speichern.
- Explorer erzeugt keine allgemeine Zielsystemmutation; Proposals bleiben
  read-only. Explizite Connector-Materialisierung ist enger begrenzt:
  `explain-video` schreibt nur ein Handoff-Paket, `diagrams` nur markierte
  generierte Dokumente in validierte Git-Roots. Details und Gates stehen in
  `docs/CONNECTOR-ADAPTERS.md`.

---

## Externe Schwarmtests

`probe-plan` erzeugt reproduzierbare Trampelpfadaufträge. Die Modulausführung
startet selbst keine Modelle; swarm-ai oder ein anderer budgetierter Runner
führt diese Tests extern aus und liefert später referenzierbare Receipts.

---

## Meta

- **YAML-Frontmatter oben** wird validiert via `_tools/doc-lint`
- **Staleness-Check**: Wenn `last_verified` älter als 30 Tage → `doc-lint` warnt
- **Bei Version-Bumps** von Projekt-Code: `version` im Frontmatter nachziehen und in `CHANGELOG.md` eintragen

---

<!-- REMEMBER: ENDUSERTEXTE BEKOMMEN ECHTE UMLAUTE Ü Ö Ä -->
