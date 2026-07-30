---
name: "system-explorer-start"
type: session-bootstrap
version: 0.1.0
updated: "2026-07-29"
last_verified: "2026-07-29"
description: |
  Imperative bootstrap sequence for new sessions in system-explorer.
---

# START

## Orientierung

1. `README.md` – Produktgrenze und Schnellstart
2. `ARCHITECTURE.md` – Funktions-/Trägermodell
3. `docs/EVIDENCE-MODEL.md` – Wahrheits- und Datenschutzregeln
4. `examples/explorer.json` und `examples/desired-system.json`

## Entwicklung

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
system-explorer doctor --config examples/explorer.json
```

In einem zusätzlichen Git-Worktree muss das Editable-Install in einer
isolierten virtuellen Umgebung erfolgen. Alternativ ist für Prüfungen
`$env:PYTHONPATH = (Resolve-Path .\src).Path` explizit zu setzen, damit nicht
versehentlich ein anderer lokaler Clone importiert wird.

Der lokale Arbeitsstand ist Git-Source-of-Truth. Eine OneDrive-Kopie ist nur
ein kontrollierter Mirror ohne `.git`.
