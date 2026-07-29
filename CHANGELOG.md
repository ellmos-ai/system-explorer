# Changelog

## [Unreleased]

### Hinzugefügt

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
