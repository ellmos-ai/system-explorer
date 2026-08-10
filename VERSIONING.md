# Versionsstand

Der kanonische Projektstand ist **0.4.0**. `pyproject.toml` ist die primäre
Packaging-Quelle; `src/system_explorer.__version__`, `ellmos-module.v2.json`,
`CLAUDE.md` und `STATE.md` müssen exakt denselben Wert führen.

Der Status bleibt **development**. Der Manifestwert in
`ellmos-module.v2.json` ist dafür maßgeblich; diese Änderung autorisiert weder
Release, Tag, Upload noch Push.

Die lokale Regression prüft zusätzlich `importlib.metadata`. Wenn die
ausgeführte Umgebung eine externe, nicht aus diesem Clone stammende Distribution
auflöst, wird sie nicht als Projektmetadatenquelle verwendet. Dieser begründete
Fallback wird als Umgebungshinweis geprüft, statt eine fremde Installation oder
historische `egg-info`-Datei umzuschreiben.

Versionsfelder wie `START.md`-Dokumentschema, Receipt-/Fixture-Versionen und die
Default-Version eines exportierten `ellmos.module.v2`-Payloads sind getrennte
Verträge und werden nicht pauschal auf die Projektversion angehoben.
