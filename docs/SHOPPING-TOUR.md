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
