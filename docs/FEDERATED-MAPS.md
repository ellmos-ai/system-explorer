# Föderierte Multi-System-Karten

## Grundsatz

Jede Maschine kartiert zunächst sich selbst und exportiert eine portable Karte:

```text
system-map-WORKSTATION.json
system-map-LAPTOP.json
system-map-HETZNER.json
```

Der Vertrag `system-explorer.map.v1` enthält Systemidentität, Erzeugungszeit,
Ansicht, Knoten, Kanten, referenzielle Evidenzmetadaten und Datenschutzflags.
`--view all` ist das vollständige, später in alle Fachansichten projizierbare
Paket; Einzelansichten können bewusst als kleinere Exporte gewählt werden.
Rohbelege und Credential-Werte gehören nicht in den Export.

```powershell
system-explorer map-export --config workstation.json --view all `
  --output system-map-WORKSTATION.json
system-explorer map-import system-map-LAPTOP.json --config workstation.json
```

Importierte IDs werden mit der Herkunftsidentität gekapselt. Gleichnamige
Knoten verschiedener Maschinen kollidieren daher nicht. Jeder importierte
Knoten trägt `origin_system`, `original_node_id` und `map_level`.

## Gleiche Ansichten auf jeder Ebene

Alle fachlichen Projektionen sind mit einem Herkunftssystem filterbar:

- Dateisystem und Steuerung: `control`, `tree`;
- Funktionspfade und Deckung: `function-paths`, `actual`, `desired`, `diff`,
  `coverage`;
- Einzelknotenzweck: `purpose`;
- Server, Schutz und Kosten: `deployment`;
- Registry, Datenbank und Cloud: `data`;
- hinterlassene LLM-Spuren: `llm-traces`;
- für LLMs nutzbare CLI-, API-, Tool- und Verbindungswege: `llm-actions`.

Ohne Filter entsteht die Gesamtebenenanalyse über alle vorliegenden Karten.
Mit `--system LAPTOP` wird dieselbe Ansicht nur für den Laptop erzeugt:

```powershell
system-explorer map --config workstation.json --view coverage --system LAPTOP
system-explorer map --config workstation.json --view llm-traces --system HETZNER
system-explorer map --config workstation.json --view control
```

Die zusätzliche Ansicht `federation` zeigt Systeminstanzen, Ebenen,
Systemgrenzen und Verbindungs-/Übergabeknoten. Sie verdichtet importierte
Karten auf Knoten-/Kantenzahl und Erzeugungszeit, damit eine große Fremdkarte
die Systemübersicht nicht überlädt; deren Detailknoten erscheinen in den
jeweiligen Fachansichten.

## Systemgrenzen

Direkte Verbindungen werden explizit als `system_connection` modelliert, etwa
`ssh`, `tailscale` oder `ssh+tailscale`. Ihre Existenz autorisiert keine
Aktion. Status und Evidenz müssen getrennt belegt werden.

Asynchrone Aufträge werden als `handoff` modelliert. Ein Auftrag über `.SYNC`
und `system-gap-master` trägt die Bedingung, dass der Funktionsträger auf dem
Zielsystem installiert und der Übergabeweg dort bekannt sein muss. Explorer
visualisiert und exportiert diese Übergabe; es führt sie nicht selbst aus.

## Kombinationsansichten

Die UI kombiniert Systemebenenfilter und Fachansicht orthogonal. Dadurch sind
unter anderem sinnvoll:

- Gesamtabdeckung aller Systeme;
- identische Kontrollpfade pro Gerät;
- LLM-Spuren auf einem Server gegenüber einem Laptop;
- öffentliche Serveroberflächen zusammen mit LLM-Handlungsmöglichkeiten;
- Daten-/Cloudwege über direkte und indirekte Systemverbindungen.
