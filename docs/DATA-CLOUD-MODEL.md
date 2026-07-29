# Daten- und Cloudmodell

## Registry-Erkennung

Automatisch erkannt werden Dateien mit `registry`, `catalog` oder `inventory`
im Namen sowie JSON-Roots/Collections wie `registry`, `entries`, `records`,
`items`, `modules`, `providers` oder `components`. Nutzer können die Globs mit
`registry_documents` ersetzen und zusätzliche Registryzwecke unter
`registries` deklarieren.

## Datenbanken

SQLite-Dateien werden im Read-only-Modus geöffnet. Gespeichert werden nur
Tabellenname sowie Spaltenname/-typ. `databases` ergänzt:

- Gesamt-, Füll- und Abrufzweck
- Tabellenzwecke
- Ist-/Soll-Writer und -Reader
- Zugriffseinstiege
- Cloudanbieter, Transferweg und Cloud-Readiness
- Credential-Referenz

## Cloud

`cloud.providers` definiert neutrale Anbieter. `cloud.paths` markiert lokale,
direkte oder indirekt gespiegelte Pfade. Bekannte Syncordner wie OneDrive,
Dropbox, Google Drive oder iCloud werden mit niedrigerer Konfidenz automatisch
als indirekte Mirrors erkannt; explizite Konfiguration gewinnt.
`cloud.links` kann darüber hinaus einen beliebigen bestehenden Knoten per
`node_id` oder einen Pfad als Mappingpunkt mit Anbieter, Modus, Transfer und
Credential-Referenz verbinden.

## Credentials

`credentials` enthält nur logische IDs, Anbieter, Speicherart und optional
einen Ortshinweis. Secrets, Tokens, Passwörter und Connection Strings werden
nicht gelesen. Eine `uses_credential`-Kante beantwortet „welche Referenz wird
benötigt?“, nicht „welchen Wert hat sie?“.
