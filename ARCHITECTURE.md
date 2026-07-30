# Architektur

## Rolle

`system-explorer` ist eine read-only Evidenz-, Kartierungs- und Deckungsschicht.
Es ist weder ein zweites Control Plane noch Scheduler, Policy-Registry,
Memory-System oder Ausführungsengine. Bestehende Systeme bleiben
Source-of-Truth; Explorer verweist auf sie.

## Kernmodell

```text
Sollfunktion ──wird_sollgetragen_von──> Funktionsträger
Sollfunktion <──wird_tatsächlich_getragen_von── Funktionsträger
      │                                      │
      └──────────── Deckungsurteil ──────────┘
                         │
                    Evidenzreferenz
```

Knotentypen sind unter anderem `function`, `carrier`, `system`, `actor`,
`entrypoint`, `session`, `directory`, `control_document`, `policy_document`,
`decision_document`, `documentation`, `artifact` und `artifact_reference`.
Funktionsträger spezialisieren sich über `carrier_kind`: `skill`, `module`,
`repository`, `mcp`, `stack`, `command` oder eine systemspezifische Art.

Beziehungen besitzen:

- `mode`: `desired` oder `actual`
- `status`: etwa `full`, `partial`, `negative`, `declared`, `observed`
- Konfidenz und Wirksamkeitszeit
- eine optionale Evidenzreferenz
- Zusatzdaten wie Anforderung, Call-ID oder Überlappungsgruppe

## Deckungslogik

| Urteil | Bedeutung |
|---|---|
| `full` | Die gewünschte Funktion ist vollständig und positiv belegt. |
| `partial` | Der Träger erfüllt nur einen Teil oder ist nur deklariert. |
| `uncovered` | Eine Sollfunktion hat keinen positiven Ist-Träger. |
| `negative` | Ein Träger wirkt nachweislich gegen die Sollfunktion. |
| `unproven` | Ist-Funktion ohne Sollbezug oder noch ohne ausreichenden Beleg. |
| `overlap` | Mehr als ein positiver Träger deckt dieselbe Funktion; neutral, bis Kardinalität oder Konfliktregeln es bewerten. |

## Schichten

1. **Discovery** – begrenztes Dateisystem-Scanning, Manifest-/Skill-Erkennung.
2. **Observation** – providerbezogene Transcript- und Ereignisadapter.
3. **Registry** – lokales SQLite mit referenzieller Evidenz.
4. **Reconciliation** – zeitliche Auflösung sowie Soll-/Ist-/Deckungsdiff.
5. **Projection** – JSON, ASCII, Mermaid, HTML und lokale UI.
6. **Proposal** – unverbindlicher ChangeProposal; nie unmittelbare Mutation.
7. **Empirical probes** – Probepläne für externe Schwarm- oder
   Trampelpfad-Runs.
8. **Data topology** – Registries, Datenbanken, Tabellen, Ist-/Soll-Datenflüsse,
   Cloudanbieter, Mirrors, Transfers und Credential-Referenzen.
9. **Deployment and purpose** – Serveroberflächen, Schutzdeckung,
   Kostenvergleich und kriterienbasierte Zweckurteile für einzelne Knoten.
10. **Federation** – portable, herkunftsgebundene Karten, Systemebenen,
    Systemgrenzen, Verbindungen und Übergaben.
11. **Crystallized resources** – installierte Software, Fremdmodule, Repos,
    Skripte und Skills mit Funktionen, LLM-Steuerwegen, Flexibilität und
    belegpflichtigem Tokenersparnispotenzial.
12. **Composition contracts** – gepinnte Bundles, Kataloge, logische Systeme,
    gewünschte Instanzen, Testoverlays und Flotten mit deterministischer
    Read-only-Auflösung.
13. **Media handoff connector** – abgeleitete Storyboards, Sprechertexte und
    Kartenpakete für `ai-media-editor` UC6; kein stiller Renderlauf.
14. **Generated repository diagrams** – explizite, markierte und atomare
    Dokumentmaterialisierung in benannten Git-Repositories.

## Scan-Laufzeit und Checkpoints

Die Library-API bleibt standardmäßig unbegrenzt und still. Die CLI setzt für
`scan` und `ingest` dagegen ein fail-closed Zeitbudget und schreibt
maschinenlesbare Fortschrittsereignisse auf `stderr`. Im JSONL-Modus werden
auch CLI-Fehler auf diesem Kanal als strukturierte Ereignisse ausgegeben.
Ergebnis-JSON bleibt dadurch auf `stdout` separat parsebar.

Jeder konfigurierte Root bildet einen eigenen SQLite-Checkpoint:

```text
root_started → directories/files → commit → root_completed
          │                         │
          └─ Fehler → rollback      └─ unklare Commit-Grenze
             → root_rolled_back        → root_commit_state_uncertain
```

Ein kontrollierter Abbruch rollt nur eine noch offene Transaktion zurück.
Bereits committete Roots bleiben erhalten. Die nachgelagerten
Infrastruktur-/Deployment-/Ressourcen-/Föderationsphasen sind ebenfalls
einzelne Checkpoints und werden vor und nach ihrer Ausführung gegen das
Budget geprüft. Eine bereits committete Phase wird bei einem späteren
Timeout nicht als zurückgerollt gemeldet. Es gibt bewusst keinen
Resume-Cursor: Ohne persistente, quellgebundene Cursor- und
Frischevalidierung wäre „Resume“ keine belegbare Fortsetzung. Wiederholte
Scans verwenden stattdessen die vorhandenen deterministischen IDs und
idempotenten Upserts.

## Steuerdokumentgraph

Textdateien bilden ein zusätzliches Steuerungssystem. Konventionelle und
konfigurierte Steuerdateien werden typisiert; `contains`, `enters_at`,
`points_to` und `references` modellieren Verzeichnisbaum, Einstieg,
Boot-/Steuerpointer und Dokumentabhängigkeiten. Pointer tragen Quellzeile,
Syntax, Auflösungsstatus und Evidenzreferenz. Fehlende Ziele bleiben als
`artifact_reference` sichtbar, statt still verworfen zu werden.

## Daten- und Cloudgraph

JSON-Dateien mit Registry-/Catalog-/Inventory-Namen oder typischen
Registry-Collections werden als `registry` mit
`registry_collection`-Unterknoten geführt. SQLite wird ausschließlich
read-only auf Tabellen- und Spaltennamen untersucht.

`data_actor --fills/reads--> database|registry` besitzt Soll-/Ist-Modus.
`entrypoint --accesses--> database`, `directory --mirrors_to--> cloud_provider`
und `database --connects_to/uses_credential--> ...` zeigen Zugriff,
Cloudübertragung und Credentialbedarf. Die Symbole `☁`, `⇄☁` und `⌂` bedeuten
direkt cloudverbunden, indirekt gespiegelt und lokal. Credential-Knoten
enthalten nur ID, Speicherart und optionalen Ortshinweis; niemals Werte.

## Wiederverwendungsgrenzen

Explorer konsumiert vorhandene Manifest- und Stack-Schemata, kann
ControlCenter-konforme Karten liefern und verweist auf Policy-, BYUM-,
Hooker-, Swarm- oder Gardener-Evidenz. Es kopiert deren Datenbanken und
Entscheidungslogik nicht. Die UI ist als eigenständige lokale Ansicht
implementiert und kann später in einen vorhandenen GUI-Host eingebettet
werden.

## Föderation und Ebenen

Der Exportvertrag `system-explorer.map.v1` kapselt eine Projektion mit
Systemidentität und Zeitstempel. Importierte Knoten erhalten gekapselte IDs
und `origin_system`; lokale und fremde Knoten werden nicht verschmolzen.
Fachansicht und Systemfilter sind orthogonal: dieselbe Control-, Coverage-,
Purpose-, Deployment-, Data- oder LLM-Projektion funktioniert pro System und
über alle vorliegenden Karten. `federation` visualisiert zusätzlich die
Grenzen sowie SSH-, Tailscale-, `.SYNC`- und Handoff-Wege.

## Deployment und Zweck

`server --exposes--> server_surface` und
`server --protected_by--> security_control` trennen Erreichbarkeit von
Schutzdeklarationen. Ein privater Zweck verlangt extern belegte Blockierung;
ein teiloffener Zweck verlangt positive Kontrolldeckung. Kostenbelege tragen
Quelle und Datum. `target --has_purpose--> purpose
--requires_function--> function` verbindet Einzelknotenzwecke mit der
allgemeinen Soll-/Ist-Deckungslogik.

## Ein-, Austritts- und Übergabepunkte

Manifeste können neben `entrypoints` und `surfaces` auch `outputs`,
`handoffs`, `alternative_paths` und `encapsulation` deklarieren. Explorer
projiziert daraus `interface`, `output` und `handoff` sowie die Kanten
`exposes_interface`, `produces`, `delivers_to`, `hands_off`, `assigned_to`
und `alternative_to`. Deklarationen bleiben als solche markiert; tatsächliche
Übergabe benötigt Laufzeitevidenz.

## Kristallisierte Randressourcen

`software_resource --exposes_interface--> interface` trennt die installierte
Ressource von ihrer LLM-Steuerbarkeit. `actor --controls_via--> interface`
zeigt, welcher LLM-Akteur den Weg nutzen kann; `software_resource
--carries--> function` ordnet die Systemfunktion zu. Die Readiness-Symbole
reichen von `◆ native` über `◇ direct`, `△ indirect` und `○ reference` bis
`? unproven`.

Software verkörpert standardisierte, kristallisierte Workflows und kann
Reasoning-Tokens sparen. Diese Ersparnis bleibt aber eine eigene,
belegpflichtige Aussage; Installation und Schnittstellendeklaration allein
beweisen weder tatsächliche Nutzung noch Tokenreduktion. Skills sind im
Default flexibler, fertige Programme stärker kristallisiert. `generated_by`
kennzeichnet von LLMs gebaute Brückenskripte, ohne sie freizugeben.

## Änderungsfluss

```text
Prompt → ChangeProposal → Schema-/Ontologieprüfung → Kardinalitätsprüfung
       → Policy-Auflösung → Lock-Prüfung → Freigabe → Adapter-Dry-Run
       → Ausführung außerhalb Explorer → Readback/Receipt
```

Im MVP endet der Fluss bei `ChangeProposal`.

Connector-Artefakte sind eine engere Ausnahme von dieser Grenze: Sie ändern
keine analysierte Runtime, Policy oder Konfiguration. `explain-video` schreibt
nur in den ausdrücklich gewählten Ausgabeordner. `diagrams` schreibt nur die
generierte Zieldatei innerhalb validierter Git-Roots und verlangt dafür
`--apply`; Commit und Push sind getrennte explizite Optionen mit Clean-,
Lock- und Readback-Gates. Details:
[`docs/CONNECTOR-ADAPTERS.md`](docs/CONNECTOR-ADAPTERS.md).

## V4-Kompositionsauflösung

Die additive Kompositionsschicht validiert kanonische Content-Hashes,
Version-/Commit-Pins, Root-Containment, Profilselektion, Statusgrenzen,
Fallback-/Abhängigkeitszyklen und Test-Suppressions. Sie materialisiert nur
eine deterministische Projektion; `runtime_actions`, `target_mutations` und
Test-Writeback bleiben leer beziehungsweise `false`.

Output-Bindings trennen einmalige Berichte, Entscheidungen,
Automationssynthesen, native Runtime-Logs und Governance-Receipts. Rohlogs
bleiben hostlokal beim Producer. Explorer darf ihre Metadaten und Health
indexieren, aber keine zentrale Rohlogkopie erzeugen. Details:
[`docs/V4-COMPOSITION-CONTRACTS.md`](docs/V4-COMPOSITION-CONTRACTS.md).
