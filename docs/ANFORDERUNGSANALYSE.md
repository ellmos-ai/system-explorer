# Anforderungsanalyse

## Ziel

Ein neutrales Modul soll tatsächliche und gewünschte Systemarchitektur,
Funktionen, Nutzungspfade und Übergaben kartieren. Die zentrale Diagnose ist
nicht nur „welche Module existieren?“, sondern „welche gewünschte Funktion
wird durch welchen Träger mit welchem Beleg getragen?“.

## Muss

- Skills, Repos/Module, MCP-Module, Stacks und Einstiegspunkte als Träger
- Sollfunktionen und Sollstruktur frei definierbar
- Actual/Desired/Diff sowie Voll-, Unter-, Nicht-, Mehrfach- und Minusdeckung
- neuere wirksame Evidenz bei widersprüchlichen Aussagen bevorzugen
- relevante Manifeste, Systemdokumente und Policies finden
- `AGENTS.md`, `CLAUDE.md`, `README.md`, Decisions sowie nutzerdefinierte
  Steuerdateien und Eintrittsordner typisieren
- Verzeichnisbäume, Dokumentpointer und Steuerabhängigkeiten als Graph
- Dokumente automatisch sowie interaktiv registrieren und wiederfinden
- Provider-Sessions ohne Inhaltskopie auswerten
- LLM-lesbare JSON-/ASCII-/Mermaid-Karten und grafische UI
- promptgestützte Pläne ohne direkte Mutation
- empirische Trampelpfade und günstige Schwärme vorbereiten

## Nichtziel im MVP

- universelle Ausführungs- oder Reparaturengine
- Ersatz bestehender Control-, Policy-, Memory- oder GUI-Systeme
- automatische Systemänderungen
- Behauptung tatsächlicher Nutzung allein aus statischen Manifesten
