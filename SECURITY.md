# Security

Bitte Sicherheitsprobleme nicht als öffentliche Issue mit Nutzerdaten melden.
Das Modul liest lokale System- und Transcriptquellen. Standardmäßig verbleiben
Inhalte am Ursprungsort; die Datenbank enthält nur Referenzen, Hashes,
Locatoren und normalisierte Ereignismerkmale.

Die Weboberfläche ist für eine lokale Bindung an `127.0.0.1` vorgesehen.
Eine externe Bindung benötigt vorgeschaltete Authentisierung und ist nicht Teil
des MVP.
