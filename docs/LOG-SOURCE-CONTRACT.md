---
name: "system-explorer-log-source-contract"
type: contract
version: 0.1.0
updated: "2026-10-27"
last_verified: "2026-10-27"
description: "Transportneutraler, datensparsamer Logquellenvertrag für bestätigte Owner."
---

# Logquellenvertrag v1

`system_explorer.log_source` stellt die Library-Funktionen `resolve_source()` und
`read_excerpt()` bereit. Der Code besitzt keine BACH-Logs, keinen Server und
keinen persistenten Speicher. Ein Zeiger im Ticket-Master-Register berechtigt
für sich allein zu keinem Lesezugriff. Ein BACH-Owneradapter muss erst an der
tatsächlichen, künftig bestätigten Owner-Schnittstelle implementiert werden.

## Aufruf und Autorität

1. Ein Consumer holt aus dem aktuellen pointer-only `log-registry.v1` die
   `source_ref`, `system_ref`, `owner_ref`, `target_ref` sowie Access-,
   Redaktions-, Provenienz- und Retentionreferenzen. Die aktuelle Identität
   (`actor_ref`) und ein minimaler Zweck (`purpose_ref`) kommen aus seiner
   authentifizierten Session. Bereits vorhandene MessageID und ReceiptID
   werden nur zur Korrelation übernommen; diese Library vergibt keine IDs.
2. `resolve_source(request, owner)` validiert die kleine Anfrage und ruft nur
   `owner.resolve_source` auf. Der Owner bestätigt die **aktuelle** Quelle,
   Identität, Zielbindung, ACL und Policys und liefert ausschließlich
   Autorisierungs-/Frischemetadaten. Kein Logtext wird dabei angefordert.
3. `read_excerpt(request, owner)` validiert erneut und ruft frisch
   `owner.resolve_source` auf. Bei `denied`, `missing`, `stale` und
   `unreachable` wird `read_redacted_excerpt` nicht aufgerufen. Nur für eine
   aktuelle bestätigte Bindung erhält der Owner Limit und Feld-Whitelist.
   Der Owner muss **vor seinem Textzugriff** ACL und Ziel erneut prüfen und
   **vor Rückgabe** redigieren. Die Library nimmt ausschließlich die vier
   strukturierten Felder `time_utc`, `level`, `event_code`, `count` an; freie
   Texte, Rohtranskripte, Audio, E-Mail-Adressen, Tokens und absolute
   Hostpfade haben keinen Ergebnisslot. `event_code` muss zusätzlich in der
   aktuellen, höchstens 64 Einträge großen Owner-Allowlist stehen. Unbekannte
   Felder oder Codes führen zu `denied` ohne Einträge.
4. Ein Consumer darf den Auszug ausschließlich transient und unter derselben
   aktuellen Berechtigung für eine interaktive Besprechung nutzen. Weder
   Ticket-Master-Receipts noch Transport-, Audit- oder Chatlogs dürfen ihn
   persistieren. `resolve_source` und `read_excerpt` erzeugen keinen Ack,
   keine Queue, keinen Retry und keine `delivered`-Behauptung.

`OwnerLogProvider` ist ein öffentliches Python-`Protocol`. Der konkrete
BACH-Adapter muss `resolve_source(request, window)` und
`read_redacted_excerpt(request, window, limit, fields)` implementieren. Er
darf den zweiten Aufruf nicht allein aufgrund der ersten Entscheidung oder
eines gespeicherten Message-Snapshots freigeben. Der hier getestete
`SyntheticOwner` ist ausschließlich eine Fixture und keine BACH-API.

## Zeit- und Ergebnisvertrag

Die Requestschema-Kennung ist `ellmos.system-log-source.request.v1`, die
Resultkennung `ellmos.system-log-source.result.v1`. Das Fenster `24h` meint
rollierende 24 Stunden bis zum UTC-Prüfzeitpunkt. `monthly` verlangt
`YYYY-MM`: der Beginn ist 00:00:00 UTC am Ersten, das Ende 00:00:00 UTC des
Folgemonats; für den laufenden Monat endet es am Prüfzeitpunkt. `other`
verlangt explizite RFC-3339-UTC-Grenzen `[from_utc,to_utc)` und ist auf 31
Tage begrenzt. Die Library akzeptiert nur UTC mit `Z` und niemals eine
implizite lokale Zeitzone. Maximal 32 strukturierte Einträge sind zulässig;
der Owner kann enger begrenzen. Der Zeitstempel ist ein Pflichtfeld.

`available` enthält mindestens einen sicheren Eintrag. `empty` bedeutet,
dass der Owner erreichbar, autorisierend und frisch ist, aber keine Einträge
im Fenster hat. `missing` bedeutet, dass die bestätigte Quellreferenz fehlt;
`stale` bezeichnet veraltete Provenienz oder verletzte Retention;
`denied` verweigert Bindung, ACL, Feldfreigabe oder unsichere Rückgabe;
`unreachable` bezeichnet einen nicht erreichbaren oder fehlerhaften Owner.
Diese Zustände werden nicht ineinander umgedeutet. Fehlertexte des Owners
erscheinen nicht im Ergebnis.

## Abnahmegrenze

Die synthetischen Tests belegen die Reihenfolge von Autorisierung und
Excerpt-Aufruf, Referenzbindung, UTC-Fenster, Limit, Frische, Retention und
Feld-Whitelist. Sie können die tatsächliche BACH-ACL, Redaktion vor dem
Owner-internen Textzugriff, ein reales Register, Geräteauthentifizierung oder
eine Chat-/GUI-/Serveranzeige nicht beweisen. Ein eigener BACH-Owneradapter
braucht dafür die aktuelle kanonische Owner-API, registrierte Quellen und
eine getrennte Runtime-Abnahme. Kein Hostname und kein Planname gilt als
Zielautorität.

P-009: Die Nutzeridee wird mit RFC-3339-UTC, halb offenen Zeitintervallen,
versionierten Contracts und Least-Privilege-Feldfreigabe umgesetzt. Diese
Standards ersetzen weder die Owner-ACL noch das vorhandene Ticket-Master-
Message-/Receipt- oder system-gap-master-Transportprotokoll.
