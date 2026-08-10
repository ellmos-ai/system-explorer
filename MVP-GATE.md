# MVP-Gate-Readback

Stand: 2026-08-10. Dieser Bericht bezieht sich auf den lokalen
Source-of-Truth-Commit `ea22747f442d87d2825f530ed29eebb05d7868f8` in
`C:\_Local_DEV\repos\system-explorer`.

## Entscheidung

**BLOCKED — kein Release, keine Live-Acceptance und kein Mirror-Write.**

Die lokalen Funktions- und UI-Gates sind bestanden. Der kontrollierte
OneDrive-Mirror ist jedoch nicht auf diesem Commit und darf wegen der
divergierenden Git-Historie sowie des aktiven Cloud-Locks nicht ersatzweise
überschrieben werden.

## PASS

| Gate | Reproduzierbarer Check | Readback |
|---|---|---|
| Unit/Integration | `$env:PYTHONIOENCODING='utf-8'; python -m pytest -q` | 150 passed, 26 subtests |
| Unittest-Kompatibilität | `python -m unittest discover -s tests -q` | 150 tests, OK |
| Lint/Build | `python -m ruff check src tests`; `python -m compileall -q src` | clean / exit 0 |
| CLI/Manifest | `python -m system_explorer.cli --help`; `python -m system_explorer.cli manifest validate ellmos-module.v2.json` | exit 0; manifest valid |
| Dokumente | `python _tools/doc-lint` | CLAUDE.md, START.md und STATE.md OK |
| Atomic Search-Route | positiver Batch, ungültiger später Receipt mit Tabellen-Snapshot, Wiederholung | Tests grün; kein Teilpersistenz- oder Duplikatbefund |
| Loopback UI | `serve --config examples/explorer.json --host 127.0.0.1 --port 18765` | `/` 200 und enthält `SYSTEM EXPLORER`; `/api/map?view=coverage&system=all` 200, 0 Nodes/0 Edges |
| Manifest/Assets | `/manifest.json`, alle vier im Manifest referenzierten PNGs | Manifest 200, Name `system-explorer`, 4 Icons; alle Assets 200 (`14930`, `71575`, `10062`, `47496` Bytes) |

Der UI-Smoke lief als Loopback-Prozess und wurde anschließend beendet. Die
leere Karte ist der erwartete Readback der frischen, ignorierten
`.state/evidence.db` aus `examples/explorer.json`; daraus wird keine
Produktionsabdeckung abgeleitet.

## NOT RUN

- Provider-spezifische Live-Hook-Authentisierung, externe Consent-/Privacy-
  Entscheidungen und ein echter Live-Capture-Dienst wurden nicht ausgeführt.
  Der neue Adapter ist deaktiviert-by-default; ohne explizite Freigaben bleibt
  der MVP unverändert.
- Eine externe Store-/Release-Acceptance wurde nicht behauptet. Es wurden
  keine Credentials gelesen und kein Live-Provider angesprochen.

## BLOCKED

### Local clone versus controlled mirror

- Lokaler Branch: `main`, `HEAD=ea22747f442d87d2825f530ed29eebb05d7868f8`,
  Status `ahead 3, behind 6` gegenüber `origin/main=6915688`.
- Mirror-Pointer:
  `C:\Users\lukas\OneDrive\.TOPICS\.AI\.MODULES\.CONTROL\system-explorer\REPO.pointer.json`
  meldet Source-of-Truth `C:\_Local_DEV\repos\system-explorer`, aber den alten
  Commit `fbc779cc0f8128c0f072103b17bd8b47e9414ecd` und
  `mirrored_at=2026-08-01T12:09:08.135Z`.
- Der OneDrive-Mirror meldet aktives `cldflt.sys` mit hohem Rename-/Cloud-Lock-
  Risiko. Es erfolgte deshalb kein Kopieren, Überschreiben, Pull, Merge,
  Force-Push oder OneDrive-Worktree-Pull.

| Datei | lokaler SHA-256 | Mirror SHA-256 / Status |
|---|---|---|
| `pyproject.toml` | `0edf25845433c46dc99b66adeb5ccfa3a2663b459ce093c3a8858b1d3768f8fe` | identisch |
| `ellmos-module.v2.json` | `142abda91875969592355c64acc6cf6b511cde6a502d045f19ea3b942e9d9a25` | `2ee57ab3b1f4f0e9bd237df786b1002a8088112465099bd48461b4e9224092ec` — abweichend |
| `src/system_explorer/cli.py` | `21e1cbf4f53646f4c724412c30d407026ba36d9f8feaa92541fc644ffa40f908` | `5df117a27d10146b55e3b550be068fa7fdea9117a85a0fe224a526c342dd11d3` — abweichend |
| `src/system_explorer/provider_hooks.py` | `93dde15e500c2e8533911419c628a2aaa5b6912d238a074c9b046b4af106b593` | fehlt im Mirror |

Der Mirror ist damit ein kontrolliert erkennbarer, älterer Dokumentations-
Stand, kein zertifizierter Release-Kandidat. Eine spätere Synchronisation
erfordert einen neuen Readback und eine ausdrückliche Freigabe für den
kontrollierten Slice.
