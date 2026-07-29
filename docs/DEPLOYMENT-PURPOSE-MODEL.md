# Deployment- und Zweckmodell

## Zweck vor Bestand

Ein Knoten ist nicht allein deshalb zweckerfüllend, weil er existiert oder
gestartet ist. Ein expliziter Zweck verweist auf prüfbare Sollfunktionen. Das
Urteil eines Repos, Moduls oder Servers ergibt sich aus der Deckung dieser
Kriterien:

- `full`: alle Kriterien sind positiv und vollständig belegt;
- `partial`: mindestens ein Kriterium ist nur teilweise erfüllt;
- `uncovered`: mindestens ein erforderliches Kriterium hat keinen Ist-Träger;
- `negative`: beobachtetes Verhalten widerspricht mindestens einem Kriterium;
- `unproven`: Zweck oder belastbare Beobachtung fehlen.

`system-explorer purpose-check --target <id>` zeigt das Urteil je Kriterium.

## Privatserver

Der Zweck `private-server` verlangt, dass alle nicht gewünschten öffentlichen
Oberflächen von einem externen Messpunkt als blockiert belegt sind.

- Eine von außen erreichbare, nicht gewünschte Oberfläche ergibt `negative`.
- Eine deklarierte Default-Deny-Firewall ohne vollständigen externen Readback
  ergibt höchstens `partial`.
- Ohne externen Messpunkt bleibt die Nichterreichbarkeit `unproven`.
- Nur vollständig extern als blockiert beobachtete Oberflächen ergeben
  `full`.

Damit wird die Abwesenheit eines lokalen Fehlers nicht mit bewiesener
Nichterreichbarkeit aus dem Internet verwechselt.

## Teiloffener Dienst

Ein absichtlich öffentlicher Dienst wird mindestens gegen TLS,
Authentifizierung, Default-Deny/Allowlist, Rate-Limit, Logging und sichere
Credential-Ablage geprüft. Fehlende oder nicht belegte Kontrollen ergeben
Unterdeckung; fehlendes TLS oder fehlende Authentifizierung einer öffentlichen
Oberfläche ergibt Minusdeckung.

Die Liste ist ein neutraler technischer Mindestcheck, keine vollständige
Compliance- oder Penetrationsprüfung.

## ApiProber

ApiProber ist ein optionaler Funktionsträger für autorisierte, passive
REST-Oberflächenkartierung. Explorer:

1. erzeugt einen rate-limitierten, nur für freigegebene Ziele gedachten Plan;
2. startet standardmäßig keinen Netzscan;
3. importiert JSON-Exporte als referenzierte Evidenz;
4. speichert keine Response-Bodies oder Credential-Werte.

Beispiel:

```powershell
system-explorer server-check --config deployment.json
system-explorer import-apiprober exports\service.json --server service --config deployment.json
system-explorer map --config deployment.json --view deployment --format html --output deployment-map.html
```

## Kosten-/Nutzenvergleich

`monthly_cost` wird gegen eine lokale Alternative aus laufenden Kosten,
Hardware-Amortisierung, Energie und administrativer Zeit gerechnet. Das
Ergebnis ist eine transparente Rechenhilfe. Verfügbarkeit, Latenz,
Ortsunabhängigkeit, Wartungsaufwand, Datenschutz und Angriffsfläche bleiben
separate Entscheidungskriterien.

Preise müssen Quelle, Währung und Wirksamkeits-/Abrufdatum tragen. Fehlende
oder veraltete Preisbelege werden nicht als aktuelle Marktpreise ausgegeben.
Nur ein explizit verifizierter Preisbeleg (`verified: true`) erzeugt die
Richtung `local`, `cloud` oder `equal`; andernfalls bleibt sie `unproven`.

Providerdokumente können ausdrücklich neu abgerufen werden:

```powershell
system-explorer provider-refresh --config deployment.json
```

Der Refresh akzeptiert nur öffentliche HTTP(S)-Ziele, blockiert private,
Loopback- und Spezialadressen, begrenzt Timeout und Größe und speichert nur
Status, Ziel-URL, Hash, Zeit und Content-Type. Inhalte werden nicht kopiert.
