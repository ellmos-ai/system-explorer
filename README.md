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
- Registry-, Datenbank- und Cloudkarten mit Tabellen, Ist-/Soll-Datenakteuren,
  Transferwegen und reinen Credential-Referenzen
- lokales SQLite-Evidenzregister mit URI, Locator, Hash und Zeitbezug statt
  kopierter Quelldaten
- Sollspezifikation für Funktionen, Träger, Deckung und Struktur
- Transcript-Adapter für Codex, Claude Code, Claude Desktop, Gemini/agy, Kimi
  und generisches JSONL
- Actual-, Desired-, Diff- und Coverage-Karten als JSON, ASCII, Mermaid und HTML
- föderierte Kartenimporte/-exporte mit identischen Ansichten je Gerät,
  Systemgrenzen sowie Gesamtebenenanalyse
- Privat-/Teiloffen-Servercheck, Schutzdeckung, Kosten-/Lokalvergleich und
  Zweckprüfung einzelner Module oder Repositories
- LLM-Spuren- und LLM-Handlungskarten für Sessions, CLI-, API-, Tool- und
  Systemverbindungswege
- Funktionspfadkarten von Entrypoints und Akteuren über Träger zu Funktionen,
  Outputs und systemübergreifenden Übergaben
- kristallisierte Randressourcen für installierte Software, Fremdmodule,
  Repositories, Skripte und Skills mit LLM-Steuerweg, Flexibilität und
  belegpflichtigem Tokenersparnispotenzial
- optionale ApiProber-Evidenzaufnahme für autorisierte passive REST-Prüfungen
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
system-explorer map --config data-cloud.json --view data --format html --output data-map.html
system-explorer documents --config explorer.json --role policy
system-explorer register X:\system\SPECIAL-ENTRY.md --role control --entry --config explorer.json
system-explorer map --config explorer.json --view coverage --format html --output map.html
system-explorer map-export --config explorer.json --view all --output system-map-WORKSTATION.json
system-explorer map-import system-map-LAPTOP.json --config explorer.json
system-explorer map --config explorer.json --view llm-traces --system LAPTOP
system-explorer map --config explorer.json --view federation
system-explorer server-check --config deployment.json
system-explorer provider-refresh --config deployment.json
system-explorer purpose-check --target carrier:system-explorer --config deployment.json
system-explorer resources --config software-resources.json
system-explorer map --config software-resources.json --view resources
system-explorer serve --config explorer.json
```

Die Oberfläche bindet standardmäßig nur an `127.0.0.1:8765`.

Eigene Steuerdateien werden über `control_documents` (Glob, Rolle,
Entry-Flag), Eintrittsordner über `entry_directories` konfiguriert. Die
Control- und Tree-Ansichten zeigen aufgelöste und fehlende Pointer samt
Quellzeile. Auch über CLI und lokale UI lassen sich zusätzliche Dokumente
interaktiv registrieren und wiederfinden.

Die Data-Ansicht erkennt JSON-Registries und SQLite-Schemata automatisch.
Weitere Registries, Datenbanken, Tabellenzwecke, Writer/Reader,
Cloudverbindungen, direkte oder indirekte Mirrors und Credential-Referenzen
werden neutral über die Konfiguration beschrieben; siehe
[`examples/data-cloud.json`](examples/data-cloud.json). Credential-Werte
werden nie gelesen oder gespeichert.

Die Systemidentität steht unter `system`; `map_imports`, `connections` und
`handoffs` bilden Fremdkarten, SSH/Tailscale-Verbindungen sowie asynchrone
`.SYNC`-Übergaben ab. Jede fachliche Ansicht kann in CLI und UI auf ein
Herkunftssystem eingeschränkt oder über alle vorliegenden Karten kombiniert
werden. Siehe
[`docs/FEDERATED-MAPS.md`](docs/FEDERATED-MAPS.md) und
[`examples/deployment-federation.json`](examples/deployment-federation.json).

Server- und Repozwecke werden als Kriterien statt als bloße Labels geprüft.
Die Regeln für Privatserver, teiloffene Dienste, ApiProber und Kostenvergleich
stehen in
[`docs/DEPLOYMENT-PURPOSE-MODEL.md`](docs/DEPLOYMENT-PURPOSE-MODEL.md);
eine datierte Anbieterbaseline steht in
[`docs/CLOUD-SERVER-BASELINE_2026-07-29.md`](docs/CLOUD-SERVER-BASELINE_2026-07-29.md).

Installierte Software wird nicht automatisch mit LLM-Nutzbarkeit
gleichgesetzt. `software_resources` und eine begrenzte
`software_discovery.commands`-Allowlist registrieren Ressource, Funktion und
Steuerweg. `◆`, `◇`, `△`, `○` und `?` kennzeichnen native, direkte,
indirekte, rein referenzielle und unbelegte LLM-Bereitschaft. Die Regeln und
Wahrheitsgrenzen stehen in
[`docs/CRYSTALLIZED-RESOURCES.md`](docs/CRYSTALLIZED-RESOURCES.md); eine
neutrale Konfiguration in
[`examples/software-resources.json`](examples/software-resources.json).

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
