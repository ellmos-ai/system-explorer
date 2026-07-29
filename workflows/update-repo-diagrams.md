# Workflow: Repository-Schaltpläne aktualisieren

> **Last verified:** 2026-07-29
> **Frequency:** ad-hoc oder bei Architekturänderungen
> **Duration:** abhängig von Anzahl und Größe der Repositories

## Purpose

Verwaltete Systemkarten in einem einzelnen Git-Repository oder in den
pfadbasiert referenzierten Repositories eines Bundles planen, aktualisieren,
committen und optional pushen.

## Preconditions

- Alle Zielpfade sind lokale Git-Klone.
- Keine fremden `LOCK*.txt` liegen in den Zielroots.
- Für `--commit` und `--push` sind die Repositories vor dem Lauf clean.
- Bundle-Komponenten, die aktualisiert werden sollen, verwenden auflösbare
  `ref.path`-Werte.

## Steps

1. **Dry-Run prüfen**

   ```powershell
   system-explorer diagrams --repo <repo>
   ```

2. **Ziele und Hashes im Receipt kontrollieren**

   Prüfen, dass nur `docs/system-map.md` im erwarteten Git-Root geplant ist.

3. **Atomar anwenden**

   ```powershell
   system-explorer diagrams --repo <repo> --apply
   ```

4. **Diff lesen**

   ```powershell
   git -C <repo> diff -- docs/system-map.md
   ```

5. **Optional committen und pushen**

   Den Lauf bei sauberer Baseline direkt wiederholen:

   ```powershell
   system-explorer diagrams --repo <repo> --apply --commit --push
   ```

6. **Readback prüfen**

   Das JSON-Receipt muss den Commit und bei `--push` `pushed: true` zeigen.

## Exit-Criteria

- [ ] Der generierte Marker ist vorhanden.
- [ ] Keine fremde Datei wurde überschrieben oder committed.
- [ ] Wiederholung ohne Architekturänderung ergibt `unchanged`.
- [ ] Bei Push stimmt der Upstream-Readback mit dem Commit überein.

## Fallstricke

- `--allow-dirty` darf nicht mit `--commit` kombiniert werden.
- Ein existierendes, menschlich gepflegtes `docs/system-map.md` wird
  absichtlich nicht übernommen; zuerst einen anderen Zielpfad wählen.
- Nicht auflösbare Bundle-Referenzen erscheinen als
  `skipped_component_refs` und sind kein erfolgreicher Komponenten-Update.

## Verwandte

- [`../docs/CONNECTOR-ADAPTERS.md`](../docs/CONNECTOR-ADAPTERS.md)
- [`../DECISIONS.md`](../DECISIONS.md)

## Historie

- **2026-07-29** — Erstellt mit dem Repo-/Bundle-Diagramm-Connector.
