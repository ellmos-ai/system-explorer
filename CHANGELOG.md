# Changelog

## [Unreleased]

### Maintainer-Verifikation & Technische Hygiene (2026-08-04)
- 127 Pytest-Tests (100% grün), `ruff check` (clean) & `llms.txt` (Last-checked: 2026-08-04) verifiziert.
- Shields.io Badges (Pytest, Python 3.10+, MIT, ellmos-ai, open-bricks) und GFM-Callouts in `README.md` & `README_de.md` ergänzt.

### Hinzugefügt

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
