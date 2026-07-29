# Connector-Adapter

## Zweck

Connector-Adapter materialisieren ausdrücklich angeforderte Ableitungen aus
einer bereits analysierten Systemkarte. Sie sind von den
Provider-Beobachtungsadaptern getrennt:

- Provider-Adapter lesen referenzielle Evidenz ein.
- Connector-Adapter erzeugen begrenzte, überprüfbare Ausgabeartefakte.

Die Explorer-Kernanalyse verändert weiterhin keine Runtime, Konfiguration,
Policy oder fachliche Quelldatei.

## ai-media-editor

`system-explorer explain-video` erkennt `ai-media-editor` über dessen
`ellmos-module.v2.json`. Der Vertrag verlangt:

- Modul-ID `ai-media-editor`
- Fähigkeiten `domain.media.editing` und `workflow.media.pipeline`
- CLI- und Workflow-Entrypoint
- vorhandenes `editor.py`

Aus den ausgewählten Kartenansichten entstehen:

- `ai-media-editor-handoff.json`
- `storyboard.json`
- `narration.md`
- Mermaid-Schaltpläne unter `maps/`
- ein kurzes Produktions-README

Das Storyboard beantwortet systematisch:

1. Wo steigt man ein?
2. Was kann das System?
3. Wie funktioniert es?
4. Was sind die besten belegten Features?
5. Welche weiteren Features und Lücken gibt es?
6. Wie sind Schaltpläne und Karten aufgebaut?

Beispiel:

```powershell
system-explorer explain-video `
  --config examples/self-scan.json `
  --output C:\_Local_DEV\BUILDS\system-explorer-explainer `
  --media-editor C:\_Local_DEV\repos\ai-media-editor `
  --probe
```

Der optionale Probeaufruf prüft read-only, ob Usecase 6 über
`editor.py modes` sichtbar ist. Das erzeugte Paket ist
`handoff-ready`, nicht automatisch `rendered`. Reale TTS-, Hyperframes-,
FFmpeg-, Cloud- und Providerläufe bleiben beim `ai-media-editor`-Workflow und
unterliegen dessen Strategie-, Rechte-, Einwilligungs- und Datenschutzgates.
Ein nichtleerer Ausgabeordner ohne
`.system-explorer-explainer.json` beziehungsweise ein eindeutig vom Explorer
erzeugtes Legacy-Handoff wird nicht überschrieben.

## Repository- und Bundle-Schaltpläne

`system-explorer diagrams` erzeugt eine verwaltete
`docs/system-map.md` aus Git-Metadaten, `ellmos-module.v2.json` oder einem
`ellmos.bundle.v1`-Manifest.

```powershell
# Nur planen
system-explorer diagrams --repo C:\_Local_DEV\repos\my-module

# Datei atomar aktualisieren
system-explorer diagrams --repo C:\_Local_DEV\repos\my-module --apply

# Sauberes Repo: aktualisieren, nur die generierte Datei committen und pushen
system-explorer diagrams --repo C:\_Local_DEV\repos\my-module `
  --apply --commit --push

# Bundle-Root plus per Pfad referenzierte Komponenten aktualisieren
system-explorer diagrams --bundle .\bundles\media.bundle.v1.json --apply
```

Sicherheitsgrenzen:

- Dry-Run ist Standard; Schreiben verlangt `--apply`.
- Der Zielpfad ist relativ und muss innerhalb des jeweiligen Git-Roots liegen.
- Fremde bestehende Dokumente ohne Generator-Marker werden nicht überschrieben.
- `LOCK*.txt` blockiert die Aktualisierung.
- Dirty Repositories blockieren standardmäßig.
- `--allow-dirty` ist nur für einen bewusst geprüften Datei-Write erlaubt;
  gleichzeitiges `--commit` bleibt verboten.
- `--commit` verlangt einen sauberen Ausgangsstand und staged nur den
  generierten Zielpfad.
- `--push` verlangt `--commit`, nutzt normales `git push` und vergleicht den
  Upstream-Readback mit dem erzeugten Commit.

Damit bleibt die Schaltplanpflege eine explizite Dokumentmaterialisierung und
wird nicht zu einer allgemeinen Zielsystem-Mutationsengine.
