# Changelog

## Unreleased

- 2026-08-16: Discoverability, README-Design, Badges & Metadata Parity Check (Pfad B).
  Merge-Reconciliation zwischen `main` und `origin/main` (V4-Composition-Integrität,
  transaktionales Receipt-Handling, Stack-Schema-Pins und Fleet-Resolution vereint).
  Banner und Pytest-Badge (163 passed) in `README.md` und `README_de.md` synchronisiert.
  Geschwisterwerkzeuge-Matrix (`policy-registry`, `sqlite-transit-sync`, `coma`,
  `automation-master`, `DevCenter`, `CodeBox`) in beiden Sprachfassungen verlinkt.
  Erweiterte automatisierte Paritätstests in `tests/test_versioning.py`.

- 2026-08-13: TASKPLAN-Bundle 1719/1722/1724 ergänzt scopeweise,
  hash-/versionsgepinnte externe Composition-Regeln mit fail-closed
  Cardinality-Report, referenzielle `system-explorer.probe-receipt.v1`-
  Imports ohne Rohresultat-/Coverage-Eskalation sowie die optionale
  `--stack-schema-pin`-Prüfung für externe `ellmos.stack.v2`-Autorität.
  Synthetische Tests decken exact/min/max, Overlap/Konflikt, Receipt-
  Idempotenz/Tamper und Schema-Drift ab. Keine Provider-, Schwarm-, Credential-
  oder Mirror-Aktion.

## [Unreleased]

### Versionsstand (2026-08-10)
- Packaging, Runtime, Manifest und Steuerdokumente sind auf den kanonischen
  Development-Stand `0.4.0` synchronisiert; ein Release ist nicht autorisiert.
- Der externe `importlib.metadata`-Fallback wird in `VERSIONING.md` und einem
  Regressionstest ausdrücklich als umgebungsfremd behandelt.

### TASKPLAN-Readback 1716–1718 (2026-08-10)
- Commit `ea22747` bündelt Resolution-, Actual-Self- und Authority-Imports der
  `search-route` in einer äußeren All-or-Nothing-Transaktion; ungültige spätere
  Receipts lassen Store, Evidence, Identity und Edges unverändert.
- 150 Pytest-Tests/26 Subtests sowie 150 Unittest-Fälle, Ruff, Compileall,
  CLI-Hilfe, Manifest-Validierung und `doc-lint` sind lokal grün.
- Loopback-UI, Manifest und vier statische PNG-Assets antworteten im Smoke mit
  HTTP 200. Der reproduzierbare Gate-Bericht steht in [`MVP-GATE.md`](MVP-GATE.md).
- Der kontrollierte OneDrive-Mirror ist wegen veraltetem Pointer, Hash-Deltas,
  fehlender neuer Dateien, divergierendem Upstream und aktivem Cloud-Lock
  BLOCKED; es gab keinen Pull, Merge, Force-Push oder Mirror-Write. Daher kein
  Release- oder Live-Acceptance-Claim.

### Maintainer-Verifikation & Technische Hygiene (2026-08-10)
- 144 Pytest-Tests und 20 Subtests, `ruff check`, `compileall`, CLI-Hilfe und
  `doc-lint` lokal erfolgreich verifiziert.
- Pytest-Badges in `README.md` und `README_de.md` sowie der Prüfzeitpunkt in
  `llms.txt` auf diesen Readback aktualisiert. Der direkte Push wurde wegen
  des divergierten, vorausliegenden `origin/main` als `non-fast-forward`
  abgelehnt; kein Pull, Merge, Force-Push oder Release.

### Maintainer-Verifikation & Technische Hygiene (2026-08-04)
- 127 Pytest-Tests (100% grün), `ruff check` (clean) & `llms.txt` (Last-checked: 2026-08-04) verifiziert.
- Shields.io Badges (Pytest, Python 3.10+, MIT, ellmos-ai, open-bricks) und GFM-Callouts in `README.md` & `README_de.md` ergänzt.

### Hinzugefügt

- `fleet-resolve`: löst ein gepinntes Fleet-Manifest (`ellmos.fleet.v1`) zu
  seinen Mitgliedssystemen auf. Stabile Fleet-IDs bleiben von relativen
  Manifestpfaden getrennt, `host`/`ref`-Hostbindungen werden erhalten und
  gegen die tatsächliche Instanz geprüft, begründete Desired-Abweichungen
  laufen über `host_overrides` (`host_id`, `reason`, `component_states`,
  `desired_profile`, `tolerated_gaps`). Ausgewiesen werden blockierende
  Pflichtlücken getrennt von tolerierten Abweichungen, fleet-weite
  Funktionsdeckung inklusive Einzelanbieter-Markierung sowie aufgelöste
  Rollen, Handoffs und Abhängigkeiten. Keine Runtime-Aktionen, keine
  Zielmutationen, kein Writeback.
- Fleet-Deckung baut auf dem heutigen Auflösungsmodell auf statt auf dem
  Stand vor der verschachtelten Komposition: Mitgliedsfunktionen schließen
  Subsystemfunktionen ein (`functions`), die Root-only-Projektion bleibt
  daneben als `root_functions` sichtbar, und ein durch das
  Component-Registry-Gate quarantänisiertes Bundle zählt als blockierende
  Lücke statt als gedeckt.
- opt-in `system-resolve --emit-blocked-resolution` für source-verifizierte,
  rein lesende Vollsystem-Evidenz; Bundles mit required `declared_only`-Lücken
  bleiben blockiert und werden vollständig operativ quarantänisiert
- explizite `--root-only-resolution`-Projektion für Root-Evidenzimporte bei
  vorhandenen Subsystemen; ausgelassene Children werden gezählt und niemals
  still als importiert oder verifiziert behandelt
- gepinnte, rekursive und nicht-flattenende `subsystem_refs` für
  `ellmos.system.v1`, einschließlich Pfad-/Identitätszyklen,
  Registry-Gates und `composes`-Graphkanten
- konfliktprüfende Deduplizierung identischer Output-Bindings über System und
  Instanz; widersprüchliche Policies am gleichen Ziel brechen fail-closed ab
- Resolution-Bridge lehnt verschachtelte Systeme bis zur namespaced
  Importprojektion ausdrücklich ab, statt sie still zu verlieren
- kanonischer `ellmos.component-registry-bindings.v1`-Vertrag mit
  typisierten, SHA-256-gepinnten Quellen und exakten Record-IDs
- separat gehashte Skill-Crosswalk-Quellen sowie fail-closed Prüfung von
  Source-ID, Quellenart, Record-ID und Crosswalk-Identität
- vorkommenslokales `declared_only`-Activation-Gate für Bundles; required
  blockiert, recommended degradiert und optional bleibt als Lücke sichtbar
- gemeinsamer `component-registry-check`- und
  `system-resolve --registry-bindings`-Pfad ohne zweiten Resolver
- hostneutrale Registry-Bindings mit Host-/Zeitbezug ausschließlich in
  expliziten nativen Receipts
- fail-closed `system-explorer.function-equivalence.v1`-Vertrag mit
  typisierten Komponenten, Hostscope, Schema-/Versions-/Hash-Pins sowie
  konkret gebundener Decision-/Policy-Evidenz
- native, gehashte Probe-/Readback-Pflicht für positive Actual-Abbildungen;
  `declared`, `inferred`, Namensheuristiken und konkurrierende Autoritäten
  erzeugen keine Coverage
- CLI-/Konfigurationsimport, stale-/konfliktsichere Projektionen,
  Reconciliation und synthetische adversariale Tests ohne reale Mapping-Paare
- read-only Resolution-v1-Importer für stabile Desired-Carrier- und
  Funktionskanten samt Requirement-, Status-, Hash- und Bundleprovenienz
- instanzisolierte, ersetzbare Resolution-Snapshots ohne stale Desired-Kanten
  oder Leistungszusage durch `unavailable`
- scopebewusste Assessment- und Proposal-Gaps ohne Maskierung durch einen
  anderen erfüllten Host
- fail-closed Providerabgleich über `component_ref`/`stable_ref` mit
  `wrong-provider`-/Carrier-Mismatch-Ausweisung und erlaubten deklarierten
  Fallbackprovidern
- kollisionssicher gehashte Resolution-Carrier-IDs und strikte Validierung
  von Instanzform sowie `desired_status`
- monotone Resolution-Generationen mit stale No-op, Konfliktprüfung und
  bytegebundener Parse-/Hash-/mtime-Provenienz
- atomar serialisierte Projection-Updates gegen gleichzeitige
  Gleichgenerationsimporte und widersprüchliche Maximalzustände
- strikt instanzbezogenes Host-Matching ohne Nivellierung über eine gemeinsame
  logische System-ID
- getrennte Discovery-/Desired-Coverage-Summaries mit harten, beratenden und
  optionalen Gaps sowie Desired-Provider-Overlap
- CLI- und Konfigurationsweg für Coverage gegen gespeicherte
  `system-explorer.resolution.v1`-Outputs
- JSONL-Fortschrittstelemetrie für `scan`/`ingest` auf `stderr`
- konfigurierbares CLI-Zeitbudget mit fail-closed Standard von 300 Sekunden
- atomare Root- und Nachlaufphasen-Checkpoints mit explizitem Rollback
  offener Transaktionen bei Deadline und `Ctrl+C`
- strukturierte Commit-Grenzmeldungen ohne falsche Rollback-Behauptung
- Commit-Versuchsmarker vor dem SQLite-Aufruf für die schmale
  Persistiert-aber-noch-nicht-bestätigt-Grenze
- SQLite-Integritätsprüfung im Store und Abbruchtests ohne Hot Journal
- `ai-media-editor`-Connector mit Vertragsprüfung, optionalem UC6-Probeaufruf
  und Erklärvideo-Handoff aus mehreren analysierten Kartenansichten
- deutsches Storyboard für Einstieg, Fähigkeiten, Funktionsweise,
  Feature-Highlights, weitere Features/Lücken und Schaltplanatlas
- Repo-/Bundle-Schaltpläne mit Dry-Run, Root-/Lock-/Dirty-Prüfung,
  Generator-Marker, atomarem Readback und optionalem Commit/Push
- JSON-Schema für `system-explorer.ai-media-editor-handoff.v1`
- JSON-Schemas für `ellmos.bundle.v1`, `ellmos.bundles.catalog.v1`,
  `ellmos.system.v1`, `ellmos.system-instance.v1`,
  `ellmos.system-test.v1` und `ellmos.fleet.v1`
- deterministische Manifest- und Repo-Baumvalidierung mit kanonischem
  Content-Hash, Secret-Grenze, Pins und Root-Containment
- Read-only-System-/Testauflösung mit Profilen, Statuswerten,
  Fallback-/Abhängigkeitszyklen, Suppressions und atomarem explizitem Output
- typisierte Output-/Log-Bindings mit hostlokaler Rohloggrenze,
  Entscheidungs-, Automations-, Governance- und Berichts-Ownership
- gehärtete Pinprüfung gegen den neu berechneten kanonischen Hash,
  einschließlich tolerierter Legacy-Stacks, sowie normalisierte Prüfung
  sämtlicher Rohlogziele und Secret-Aliase
- exakte Output-Binding-Allowlist mit eng typisiertem
  `resolution-only-unmaterialized`-Zustand sowie erzwungen redigierten
  Automationssynthesen
- rekursive Secret-Grenze für generische Bindings einschließlich absoluter
  lokaler Secret-Pfade; logische `secret_ref`-Werte bleiben zulässig
- begrenzte Percent-Decodierung bis zum Fixpunkt für URI-Zielprüfungen;
  ungültige oder nicht stabil dekodierbare URIs werden fail-closed abgewiesen

### Behoben

- `component_states` mit `status: "suppressed"` brach die Auflösung ab. Der
  Status entfernt seine eigene Komponente aus dem aufgelösten Satz; geprüft
  wurde anschließend gegen die Überlebenden, sodass genau der Eintrag, der
  unterdrückt hat, als „unresolved" gemeldet wurde. Bewusstes Weglassen einer
  Komponente pro Instanz oder Host war dadurch unmöglich. Geprüft wird jetzt
  gegen alle Komponenten, die das Profil angeboten hat. Aufgefallen beim Bau
  von `fleet-resolve`, betrifft aber `system-resolve` genauso.

### Geplant

- optionale Live-Hook- und GUI-Host-Adapter
- Import standardisierter Schwarm-Probe-Receipts
- vollständige Integration des autoritativen externen `ellmos.stack.v2`-
  Schemas; W1 konsumiert kompatibel nur `bundle_refs`

## [0.1.0] — 2026-07-29

### Hinzugefügt

- begrenzter Manifest-, Skill-, Verzeichnis- und Dokumentscanner
- Sollfunktions-/Funktionsträgermodell mit Voll-, Unter-, Nicht-, Mehrfach-
  und Minusdeckung
- referenzielles SQLite-Evidenzregister mit zeitlicher Auflösung
- Transcript-Adapter für Codex, Claude Code/Desktop, Gemini/agy, Kimi und
  generisches JSONL
- Control-/Policy-/Decision-/README-Graph mit aufgelösten und fehlenden
  Pointern sowie konfigurierbaren Eintrittsordnern
- JSON-Registry-, SQLite-Tabellen-, Datenfluss- und Cloudtopologie mit
  Cloudsymbolen, Transferwegen und sicheren Credential-Referenzen
- interaktive Dokumentregistrierung und -suche
- Actual-, Desired-, Diff-, Coverage-, Control- und Tree-Karten als JSON,
  ASCII, Mermaid und HTML
- lokale Weboberfläche und read-only ChangeProposal-Entwürfe
- Trampelpfad-Probepläne für externe budgetierte Schwärme
- Privat-/Teiloffen-Serverprüfung mit Schutzdeckung, datierten
  Providerdokumenten und Cloud-/Lokal-Kostenvergleich
- kriterienbasierte Zweckprüfung einzelner Module, Repositories und Server
- passive ApiProber-Planung und referenzieller JSON-Evidenzimport
- portable `system-explorer.map.v1`-Exporte und kollisionsfreie Kartenimporte
- föderierte Ebenen, SSH-/Tailscale-Verbindungen sowie
  `.SYNC`-/`system-gap-master`-Übergaben
- pro System und systemübergreifend nutzbare Deployment-, Purpose-,
  LLM-Spuren-, LLM-Handlungs- und Föderationskarten
- kristallisierte Randressourcenebene für installierte Software,
  Fremdmodule, Repositories, Skripte und Skills
- LLM-Readiness-Symbole, Akteur-zu-Interface-Steuerwege sowie getrennte
  Flexibilitäts- und Tokenersparnisangaben
