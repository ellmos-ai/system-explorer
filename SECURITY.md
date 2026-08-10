# Security

Bitte Sicherheitsprobleme nicht als öffentliche Issue mit Nutzerdaten melden.
Das Modul liest lokale System- und Transcriptquellen. Standardmäßig verbleiben
Inhalte am Ursprungsort; die Datenbank enthält nur Referenzen, Hashes,
Locatoren und normalisierte Ereignismerkmale.

Die Weboberfläche ist für eine lokale Bindung an `127.0.0.1` vorgesehen.
Eine externe Bindung benötigt vorgeschaltete Authentisierung und ist nicht Teil
des MVP.

## Signierte Authority-Receipts

Ausführbare Search-Authority bleibt fail-closed: Jede `evidence`- und
`conflicts`-Referenz muss vor dem Import eindeutig im lokalen Evidence Store
vorhanden sein, dieselbe lowercase SHA-256 tragen und eine autorisierende
Quelle `document:decision` oder `document:policy` besitzen. Externe oder
read-only Belege, fehlende oder gelöschte Einträge, Hashabweichungen und
Mehrdeutigkeiten blockieren Import und Resolver ohne Teilpersistenz. Der
Resolver führt diese Prüfung bei jeder erneuten Verwendung erneut durch.

Receipt- und Resolution-Validatoren teilen dieselben Regeln für Stable Refs,
SHA-256 und Zeitstempel. Doppelte Resolution-Komponenten mit abweichendem Typ,
Registry-Binding oder `provides` werden vor jeder Store-Mutation abgewiesen.
