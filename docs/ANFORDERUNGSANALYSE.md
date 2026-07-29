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
- JSON-Registries und `*registry*`-Dateien erkennen
- Datenbanken mit Tabellen, Füll-/Abrufzweck, Einstiegen sowie Ist-/Soll-
  Writern und -Readern kartieren
- lokale, direkt cloudverbundene und indirekt gespiegelte Pfade,
  Mappingpunkte, Anbieter, Transferwege und Credential-Referenzen zeigen
- Provider-Sessions ohne Inhaltskopie auswerten
- LLM-lesbare JSON-/ASCII-/Mermaid-Karten und grafische UI
- promptgestützte Pläne ohne direkte Mutation
- empirische Trampelpfade und günstige Schwärme vorbereiten
- Privatserverzweck gegen extern belegte öffentliche Nichterreichbarkeit
  prüfen; teiloffene Server gegen Schutzkontrollen prüfen
- Kosten-/Nutzenvergleich Cloudserver gegen lokale Zweckerfüllung mit
  datierten Anbieterquellen
- Zweckdeckung einzelner Module, Repositories und Server über Kriterien
- ApiProber als optionalen passiven, autorisierten Evidenzadapter einbinden
- portable Karten pro System exportieren, fremde Karten kollisionsfrei
  importieren und als Gesamtebene analysieren
- identische Steuerungs-, Funktions-, Deckungs-, Daten-, Deployment-,
  LLM-Spuren- und LLM-Handlungsansichten auf jeder Systemebene
- Systemgrenzen und direkte SSH-/Tailscale-Verbindungen sowie asynchrone
  `.SYNC`-/`system-gap-master`-Übergaben modellieren

- Eintrittspunkte, Interfaces, Outputs, Konsumenten, Handoffs,
  Alternativpfade und Kapselungsdeklarationen aus Manifesten kartieren
- installierte Fremdsoftware, Module, Repositories, Skripte und Skills als
  kristallisierte Randressourcen mit Funktionen und LLM-Steuerwegen erfassen
- LLM-Bereitschaft sichtbar typisieren und von bloßer Installation trennen
- Standardisierungs-, Flexibilitäts- und Tokenersparnispotenzial getrennt
  führen; Tokenersparnis erst nach empirischem Beleg als beobachtet bewerten

## Nichtziel im MVP

- universelle Ausführungs- oder Reparaturengine
- Ersatz bestehender Control-, Policy-, Memory- oder GUI-Systeme
- automatische Systemänderungen
- Behauptung tatsächlicher Nutzung allein aus statischen Manifesten
