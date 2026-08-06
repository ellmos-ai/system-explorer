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
  Pflichtlücken gegenüber tolerierten Abweichungen und Fleet-weiter
  Funktionsdeckung. `schemas/ellmos.fleet.v1.schema.json` und die
  Fleet-Behandlung in `contracts.py` sind vorhanden; der Resolver-Teil fehlt
  (kein `fleet-resolve` in `cli.py`, keine Fleet-Auflösung in `resolver.py`).
  Herkunft: PR #2 (`codex/fleet-resolution`, Juli 2026), geschlossen am
  2026-08-07 — Begründung in `DECISIONS.md`. Der Branch bleibt als Vorlage
  lesbar, sein Auflösungsmodell ist aber überholt: er entstand vor #13/#14.
