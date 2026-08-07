# Erledigt

## 2026-08-07

- [x] `fleet-resolve` auf dem aktuellen Auflösungsmodell neu gebaut statt aus
      PR #2 gemergt: Fleet-Manifeste zu Mitgliedssystemen, stabile Fleet-IDs
      getrennt von relativen Manifestpfaden, erhaltene und gegen die Instanz
      geprüfte Hostbindungen, begründete Desired-Abweichungen über
      `host_overrides`, blockierende Pflichtlücken getrennt von tolerierten
      Abweichungen, fleet-weite Funktionsdeckung mit Einzelanbieter-Markierung
- [x] Fleet-Deckung an die verschachtelte Komposition angeschlossen:
      Mitgliedsfunktionen schließen Subsysteme ein, die Root-only-Projektion
      bleibt als `root_functions` daneben sichtbar
- [x] Quarantänisierte Bundles zählen als blockierende Lücke statt als gedeckt;
      gemessen wird gegen die deklarierten `provides`, nicht gegen die nach der
      Quarantäne verbliebenen
- [x] `component_states` mit `status: "suppressed"` repariert — bewusstes
      Weglassen einer Komponente pro Instanz oder Host war zuvor unmöglich

## 2026-07-29

- [x] Architektur und vorhandene Wiederverwendungskomponenten inventarisiert
- [x] Funktionen und Funktionsträger als getrennte Ebenen modelliert
- [x] positive, partielle, fehlende, negative und mehrfache Deckung umgesetzt
- [x] Evidenzregister ohne Rohtextspeicherung implementiert
- [x] Manifest-, Skill-, Repo-, Stack-, MCP- und Einstiegserkennung ergänzt
- [x] Provider-Transcript-Adapter implementiert
- [x] AGENTS-/CLAUDE-/README-/Policy-/Decision- und Verzeichnisgraph ergänzt
- [x] Registry-, Datenbank-, Datenfluss-, Cloud- und Credentialgraph ergänzt
- [x] interaktive Dokumentregistrierung und Suche ergänzt
- [x] fachliche Kartenansichten und vier Renderformate umgesetzt
- [x] lokale UI und read-only Proposal-Fluss implementiert
- [x] Trampelpfad-Probeplan und Systemassessment ergänzt
- [x] Privat-/Teiloffen-Server-, Schutz- und Kostenprüfung ergänzt
- [x] Einzelknoten-Zweckprüfung und ApiProber-Evidenzadapter ergänzt
- [x] portable Multi-System-Karten und herkunftsgebundene Importe ergänzt
- [x] gleiche Ansichten pro Systemebene und als Gesamtebenenanalyse ergänzt
- [x] SSH-/Tailscale-Verbindungen und `.SYNC`-/`system-gap-master`-Handoffs
  ergänzt
- [x] LLM-Spuren- und LLM-Handlungsflächenansichten ergänzt
- [x] kristallisierte Software-Randressourcen mit Funktionen,
  LLM-Steuerwegen, Readiness-Symbolen und Tokenersparnisstatus ergänzt
- [x] `ai-media-editor`-Connector mit UC6-Erklärvideo-Handoff ergänzt
- [x] sichere Repo-/Bundle-Schaltplanpflege einschließlich optionalem
  Commit-/Push-Readback ergänzt
- [x] Unit-, Schema-, CLI-, API- und Browserprüfung durchgeführt
