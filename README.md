# system-explorer

`system-explorer` erstellt evidenzgestützte Karten eines modularen Agenten- und
Softwaresystems. Das Werkzeug trennt dabei zwei Ebenen:

1. **Sollfunktionen** – was das Gesamtsystem leisten soll.
2. **Funktionsträger** – Skills, Repositories/Module, MCP-Schnittstellen,
   Stacks, Akteure, Befehle oder andere Komponenten, die diese Funktionen
   tatsächlich oder geplant tragen.

Aus dieser Zuordnung erkennt es Voll-, Unter-, Nicht-, Mehrfach- und
Minusdeckung. Eine Funktion ohne belegten Träger ist nicht einfach
„unbekannt“, sondern eine sichtbare Systemlücke.

## Eigenschaften

- begrenzter Scanner für Manifeste, Skills, Einstiegspunkte und Dokumentlinks
- typisierte Steuerkarten für `AGENTS.md`, `CLAUDE.md`, `README.md`, Policies,
  Decisions, frei konfigurierte Steuerdateien und Eintrittsverzeichnisse
- lokales SQLite-Evidenzregister mit URI, Locator, Hash und Zeitbezug statt
  kopierter Quelldaten
- Sollspezifikation für Funktionen, Träger, Deckung und Struktur
- Transcript-Adapter für Codex, Claude Code, Claude Desktop, Gemini/agy, Kimi
  und generisches JSONL
- Actual-, Desired-, Diff- und Coverage-Karten als JSON, ASCII, Mermaid und HTML
- lokale grafische Oberfläche mit belegbezogenen Details
- schreibgeschützte, promptgestützte Änderungsentwürfe mit Pflichtgates
- Trampelpfad-Probepläne für externe, budgetierte Schwarmtests

## Schnellstart

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
system-explorer init --config explorer.json
system-explorer ingest --config explorer.json
system-explorer coverage --config explorer.json
system-explorer assess --config explorer.json
system-explorer map --config explorer.json --view control --format mermaid
system-explorer documents --config explorer.json --role policy
system-explorer register X:\system\SPECIAL-ENTRY.md --role control --entry --config explorer.json
system-explorer map --config explorer.json --view coverage --format html --output map.html
system-explorer serve --config explorer.json
```

Die Oberfläche bindet standardmäßig nur an `127.0.0.1:8765`.

Eigene Steuerdateien werden über `control_documents` (Glob, Rolle,
Entry-Flag), Eintrittsordner über `entry_directories` konfiguriert. Die
Control- und Tree-Ansichten zeigen aufgelöste und fehlende Pointer samt
Quellzeile. Auch über CLI und lokale UI lassen sich zusätzliche Dokumente
interaktiv registrieren und wiederfinden.

## Sicherheits- und Wahrheitsgrenzen

- Quellen bleiben an ihrem Ort; gespeichert werden Referenzen und Prüfsummen.
- Prompt- und Transcript-Inhalte werden nicht gespeichert.
- Eine Manifestdeklaration beweist keine tatsächliche Nutzung.
- Ein Toolaufruf beweist erst zusammen mit Ergebnis, Readback oder Test einen
  erfolgreichen Funktionsvollzug.
- Das Modul erzeugt Vorschläge, führt aber keine Zielsystemänderungen aus.
- Neuere Evidenz gewinnt nur innerhalb derselben Beziehung; negative Evidenz
  wird nicht durch ältere positive Evidenz verdeckt.

Details stehen in [ARCHITECTURE.md](ARCHITECTURE.md), die Datenregeln in
[`docs/EVIDENCE-MODEL.md`](docs/EVIDENCE-MODEL.md) und die Adaptergrenzen in
[`docs/PROVIDER-ADAPTERS.md`](docs/PROVIDER-ADAPTERS.md).
