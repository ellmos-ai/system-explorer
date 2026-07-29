# Evidenzmodell

## Registrieren statt kopieren

Ein Evidenzeintrag speichert URI, Quellart, Hash, optionalen Locator,
Beobachtungs-, Änderungs- und Wirksamkeitszeitpunkt, Konfidenz,
Sensitivitätsklasse und kleine strukturierte Metadaten. Rohe Prompt-,
Antwort-, Toolargument- oder Toolergebnisinhalte werden nicht gespeichert.

## Belegstufen

- Manifest `provides`: deklarierte Fähigkeit, Konfidenz kleiner als 1.
- Skill-Tags: abgeleitete Fähigkeit, niedrige Konfidenz.
- Promptreferenz: Interesse oder Pfadkontakt, keine Nutzung.
- Tool-Call: beobachtete Invocation, noch kein Erfolg.
- Tool-Result: Rückgabe; Fehlerstatus bleibt erhalten.
- Readback/Test/Artefakt: kann eine erfüllte Funktion stützen.
- Negativer Beleg: bleibt sichtbar und kann Minusdeckung begründen.

## Zeitliche Auflösung

Für dieselbe Quelle–Relation–Ziel–Modus-Kombination gewinnt die Evidenz mit
neuerem Wirksamkeitsdatum, danach neuerem Änderungsdatum, höherer Konfidenz und
schließlich neuerem Erfassungszeitpunkt. Verschiedene Beziehungen werden nicht
gegenseitig überschrieben.

## Datenschutz

Hashes dienen Integrität und Deduplizierung, nicht Anonymität. Transcriptquellen
sind standardmäßig `sensitive`. Systemprompts, Konten, E-Mail-Adressen,
Credential-Konfigurationen, Berechtigungsdateien und rohe MCP-Konfigurationen
werden nicht gezielt importiert.

## Steuerdokumente

Bei Textdokumenten werden nicht nur Dateien, sondern auch Rollen,
Verzeichniszugehörigkeit und Pointer registriert. Ein Pointerbeleg enthält
Zieldarstellung, Quellzeile, Syntax und den Status `resolved`; der Text der
Quellzeile selbst wird nicht in die Evidenzdatenbank kopiert. Nutzerdefinierte
Steuerdateien und Eintrittsordner erhalten `registered_interactively` bzw.
`entry_directory`.
