# TODO

## Nach dem MVP

- provider-native Live-Hooks ausschließlich als optionale Adapter anbinden
- Kardinalitäten aus externen Composition-Regeln bewerten
- protobuf-spezifischen Gemini/agy-Decoder ergänzen
- UI als optionales Panel in vorhandenen GUI-Host einbetten
- externe Schwarmresultate als standardisierte Probe-Receipts importieren
- signierte Evidenzreceipts und inkrementelle Scans ergänzen
- autoritatives externes `ellmos.stack.v2`-Schema anbinden; bis dahin nur
  gepinnte Stackreferenzen prüfen und `bundle_refs` tolerant konsumieren
- optionalen echten UC6-Renderadapter erst anbinden, wenn
  `ai-media-editor` einen stabilen maschinenlesbaren Rendervertrag mit
  Rechte-/Strategie-/Readback-Receipt veröffentlicht
- `fleet-resolve` neu bauen: Fleet-Manifeste (`ellmos.fleet.v1`) zu aufgelösten
  Systemen auflösen, mit stabilen Fleet-IDs getrennt von relativen
  Manifestpfaden, erhaltenen `host`/`ref`-Hostbindungen, begründeten
  Desired-Abweichungen (`host_id`/`reason`), Ausweis blockierender
  Pflichtlücken vs. tolerierter Abweichungen und Fleet-weiter Funktionsdeckung.
  Das Schema `schemas/ellmos.fleet.v1.schema.json` und die Fleet-Behandlung in
  `contracts.py` sind vorhanden, der Resolver-Teil fehlt (kein `fleet-resolve`
  in `cli.py`, keine Fleet-Auflösung in `resolver.py`).
  Herkunft: PR #2 (`codex/fleet-resolution`, 2026-07). Der Branch wurde
  geschlossen, weil er auf einem Stand von vor #13/#14 sitzt und beim Merge
  rund 2.200 Zeilen späterer Arbeit gelöscht hätte (`media_connector.py`,
  `repo_diagrams.py`, `tests/test_connectors.py`, das
  ai-media-editor-Handoff-Schema). Der Code ist im Branch nachlesbar.
  Achtung beim Neubau: #13/#14 haben das Auflösungsmodell für verschachtelte
  Systeme geändert (fail-closed, nicht-flattenend, Root-only-Projektion) — die
  Fleet-Auflösung muss darauf aufsetzen, nicht auf dem alten Modell aus #2.
