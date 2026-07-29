# Architekturentscheidungen

Neueste Entscheidungen stehen oben. Ersetzte Entscheidungen bleiben mit
Verweis erhalten.

## 2026-07-29: Steuertextdateien bilden einen eigenen Graph

### Kontext

`AGENTS.md`, `CLAUDE.md`, Policies, Decisions und READMEs steuern ein
Agentensystem über Bootreihenfolgen, Pointer und Verzeichnisgrenzen. Eine
flache Dateiliste bildet diese Wirkung nicht ab.

### Entscheidung

Explorer typisiert Steuer-, Policy-, Decision- und Dokumentationsknoten.
`contains`, `enters_at`, `points_to` und `references` modellieren Baum,
Einstieg und Abhängigkeit. Frei definierte Dateien und Eintrittsordner können
per Konfiguration, CLI oder lokaler UI registriert werden. Fehlende Pointer
bleiben als Referenzknoten sichtbar.

### Grenze

Der Scanner bewertet Beziehungen und Provenienz, führt aber keine Anweisung
aus den gefundenen Dokumenten aus.

## 2026-07-29: Sollfunktion und Funktionsträger sind getrennte Ebenen

### Kontext

Die Existenz eines Skills oder Moduls beweist nicht, dass die beabsichtigte
Systemfunktion getragen wird. Ein Träger kann vollständig, teilweise, gar
nicht oder sogar entgegengesetzt wirken.

### Entscheidung

Funktionen und Träger sind getrennte Knoten. `carries`-Beziehungen besitzen
Soll-/Ist-Modus, Status, Konfidenz, Zeit und Evidenz. Deckungsurteile sind
`full`, `partial`, `uncovered`, `negative` und `unproven`; Mehrfachdeckung ist
eine zusätzliche Eigenschaft.

### Grenze

Mehrfachdeckung ist zunächst neutral. Ob sie erwünscht ist, entscheidet eine
externe Kardinalitäts- oder Policy-Regel.

## 2026-07-29: Evidenz wird referenziert, nicht kopiert

### Kontext

Provider-Transcripts und Systemdokumente enthalten sensible Inhalte. Eine
zweite Inhaltsdatenbank würde Datenschutz-, Aktualitäts- und
Source-of-Truth-Probleme erzeugen.

### Entscheidung

SQLite speichert URI, Locator, Hash, Zeitbezug, Konfidenz, Sensitivität und
normalisierte Ereignismerkmale. Prompt-, Antwort-, Argument- und
Ergebnisrohtexte bleiben an der Quelle. Neuere wirksame Evidenz gewinnt
innerhalb derselben Beziehung.

### Grenze

Ein Hash ist Integritätsbeleg, keine Anonymisierung.

## 2026-07-29: Explorer bleibt read-only gegenüber dem Zielsystem

### Kontext

Ein grafischer Prompt könnte leicht zu einer zweiten, unkontrollierten
Ausführungs- oder Control-Plane werden.

### Entscheidung

Prompts erzeugen ausschließlich `ChangeProposal`-Entwürfe mit
Schema-, Ontologie-, Kardinalitäts-, Policy-, Lock-, Freigabe-, Dry-Run- und
Readback-Gates. `apply.authorized` ist im MVP immer `false`.

### Grenze

Eine spätere Ausführung muss außerhalb von Explorer durch vorhandene,
autorisierte Adapter erfolgen.
