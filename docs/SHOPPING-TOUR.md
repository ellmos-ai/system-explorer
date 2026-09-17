# Komponenten-Shopping-Tour

Vor der Implementierung wurden vorhandene Systemkomponenten nach
Wiederverwendbarkeit geprüft.

## Wiederverwenden

- `ellmos.module.v2`: provides/requires/optional/conflicts, Surfaces,
  Entrypoints und Source-of-Truth
- `ellmos.stack.v2` und Composition Rules: Sollzusammensetzung und spätere
  Kardinalitätsprüfung
- bestehende Feature-/Implementation-Mappingidee: semantische Funktion von
  konkreter Implementierung trennen
- ControlCenter: späterer Zugriffspunkt und Context-Packs
- Policy Registry: spätere Policy-Auflösung
- BYUM/Prompt Listener/Hooker: referenzierbare Nutzungsereignisse
- swarm-ai und Trampelpfadanalyse: externe empirische Probeausführung
- Unified GUI: möglicher späterer Host

## Nicht duplizieren

- keine zweite Orchestrierung oder Schedulerlogik
- keine zweite Policy- oder Memory-Wahrheit
- keine Kopie fremder Datenbanken
- keine neue Systeminstanz-Wahrheit; ein geplantes Schema wird nicht als aktiv
  vorausgesetzt

## Neu erforderlich

- neutrales Evidenzregister
- explizite Funktion-zu-Träger-Deckungsbeziehung einschließlich Minusdeckung
- zeitbezogene Soll-/Ist-Auflösung
- providerübergreifende, inhaltsarme Transcript-Normalisierung
- Kartenprojektionen und read-only Proposal-UI

## Verifizierte Unified-GUI-Anbindung

Der vorhandene Host `ellmos-unified-gui` stellt mit `mount(host_app, prefix)`
und Version `0.4.0` einen stabilen Einbettungsvertrag bereit. `system-explorer`
liefert dafür optional `mount_unified_gui_panel(...)`. Die Bridge prüft den
Host-Vertrag und die Mindestversion vor dem Mounten; ein fehlender oder
inkompatibler Host deaktiviert die Einbettung ohne Route-Mutation.

Das eingebettete Panel ist eine eigene GET-only-Sub-App. Es verwendet dieselbe
lokale Evidence-Quelle, enthält keine Proposal-/Register-Routen und startet
keinen zweiten Control-Plane- oder Schreibpfad. Die bestehende Standalone-UI
bleibt unverändert.
