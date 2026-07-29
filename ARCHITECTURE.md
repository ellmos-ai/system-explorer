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

## Steuerdokumentgraph

Textdateien bilden ein zusätzliches Steuerungssystem. Konventionelle und
konfigurierte Steuerdateien werden typisiert; `contains`, `enters_at`,
`points_to` und `references` modellieren Verzeichnisbaum, Einstieg,
Boot-/Steuerpointer und Dokumentabhängigkeiten. Pointer tragen Quellzeile,
Syntax, Auflösungsstatus und Evidenzreferenz. Fehlende Ziele bleiben als
`artifact_reference` sichtbar, statt still verworfen zu werden.

## Wiederverwendungsgrenzen

Explorer konsumiert vorhandene Manifest- und Stack-Schemata, kann
ControlCenter-konforme Karten liefern und verweist auf Policy-, BYUM-,
Hooker-, Swarm- oder Gardener-Evidenz. Es kopiert deren Datenbanken und
Entscheidungslogik nicht. Die UI ist als eigenständige lokale Ansicht
implementiert und kann später in einen vorhandenen GUI-Host eingebettet
werden.

## Änderungsfluss

```text
Prompt → ChangeProposal → Schema-/Ontologieprüfung → Kardinalitätsprüfung
       → Policy-Auflösung → Lock-Prüfung → Freigabe → Adapter-Dry-Run
       → Ausführung außerhalb Explorer → Readback/Receipt
```

Im MVP endet der Fluss bei `ChangeProposal`.
