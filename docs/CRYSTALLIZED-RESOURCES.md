# Kristallisierte Randressourcen

## Begriff

Installierte Fremdprogramme, Module, Repositories, Skripte und Skills können
bereits entworfene kognitive Strukturen und wiederholbare Workflows
verkörpern. `system-explorer` führt sie deshalb als Randressourcen des
Gesamtsystems. Die Kristallisierung erleichtert Standardisierung und kann
wiederholtes LLM-Reasoning ersetzen; sie ist dafür typischerweise weniger
flexibel als ein leicht änderbarer Skill.

`software_resource` bleibt ein eigener Knotentyp. Zugeordnete
`function`-Knoten beschreiben seine Funktion im Gesamtsystem,
`interface`-Knoten den tatsächlichen oder deklarierten Steuerweg.

## LLM-Bereitschaft

| Symbol | Stufe | Nachgewiesener oder deklarierter Weg |
|---|---|---|
| `◆` | `native` | MCP, Tool-API, strukturierte API oder OpenAPI |
| `◇` | `direct` | CLI, Bibliothek, SDK, IPC oder Dateiprotokoll |
| `△` | `indirect` | Browser-, GUI-, Computer-Use- oder RPA-Steuerung |
| `○` | `reference` | Dokumentation oder manuelle Nutzung |
| `?` | `unproven` | kein LLM-Steuerweg registriert |

„Installiert“ bedeutet nicht „LLM-nutzbar“. Erst ein Interface verbindet
einen Akteur über `controls_via` mit der Ressource. Eine native strukturierte
Schnittstelle wird höher eingestuft als indirekte GUI-Steuerung, ohne damit
automatisch Qualität, Sicherheit oder Zweckdeckung zu behaupten.

## Tokenersparnis und Flexibilität

`token_saving` ist eine eigene, belegpflichtige Aussage. Ein stabiler
Endpunkt kann wiederholte Planung oder Textproduktion ersetzen, doch eine
Deklaration bleibt `declared` oder `unproven`, bis Laufzeitspuren,
Trampelpfadtests oder vergleichbare Messungen die Ersparnis belegen. Explorer
berechnet keine erfundenen Tokenwerte.

`crystallized_intelligence` und `flexibility` sind getrennte Achsen. Als
Defaults gelten hohe Flexibilität für Skills, mittlere für Skripte und eher
niedrige für fertige Fremdsoftware; die Konfiguration darf diese Bewertung
überschreiben.

LLM-erzeugte Skripte können fehlende CLI-/API-Wege überbrücken. `generated_by`
registriert den Erzeuger, ist jedoch weder Review- noch
Ausführungsgenehmigung und beweist keine Funktionsdeckung.

## Erkennung und Sicherheitsgrenze

Es gibt keinen unbeschränkten Inventarscan aller installierten Programme.
Ressourcen werden entweder explizit unter `software_resources` beschrieben
oder über die enge Allowlist `software_discovery.commands` aufgelöst.
Gespeichert werden Pfad, Hash und Metadaten, nicht der Dateiinhalt. So bleibt
die Kartierung nachvollziehbar und vermeidet eine breite Sammlung lokaler
Software- und Nutzungsdaten.
