# V4-Kompositionsverträge

## Zweck und Grenze

Die additiven Verträge beschreiben Bundles, Systeme, gewünschte
Systeminstanzen, Resolutionstests und Flotten. System Explorer validiert und
löst diese Dokumente deterministisch und read-only auf. Er startet keine
Runtime, liest keine Secrets und verändert kein Zielsystem.

Die sechs JSON-Schemas liegen unter `schemas/`:

- `ellmos.bundle.v1`
- `ellmos.bundles.catalog.v1`
- `ellmos.system.v1`
- `ellmos.system-instance.v1`
- `ellmos.system-test.v1`
- `ellmos.fleet.v1`

Alle Verträge besitzen `schema`, `id`, `version`, operativen `status`,
separaten `lifecycle`, `authority`, `provenance` und `content_hash`.
Operative Statuswerte beschreiben Verfügbarkeit von `registered` bis
`healthy`, `suppressed` oder `unavailable`; der Lebenszyklus bleibt davon
getrennt (`draft`, `active`, `deprecated`).

## Kanonischer Hash

`content_hash` ist SHA-256 über kanonisches UTF-8-JSON:

1. nur das `content_hash`-Feld des Wurzelobjekts entfernen,
2. Objektschlüssel sortieren,
3. kompakte Separatoren `,` und `:` verwenden,
4. Unicode nicht als ASCII-Escapes serialisieren.

Whitespace und ursprüngliche Schlüsselreihenfolge beeinflussen den Hash
nicht. Referenzen auf Bundles, Systeme und Stacks müssen über `version`,
`commit` oder `content_hash` gepinnt sein. Komponenten benötigen mindestens
einen Version- oder Commit-Pin.

## Pfad- und Auflösungsregeln

Alle Eingaben eines Resolverlaufs müssen zu demselben Git-Root gehören. Ohne
Git-Root wird ihr engster gemeinsamer Elternordner verwendet. Relative
Manifest- und Katalogpfade werden gegen diesen Resolution-Root aufgelöst;
absolute Pfade und Ausbrüche aus dem Root werden abgewiesen.

Kataloge indexieren Bundle-ID, relativen Pfad, Manifestdatei, Sichtbarkeit und
operativen Status. IDs und Pins müssen mit dem geladenen Manifest
übereinstimmen. Profile wenden `include`, `exclude` und begrenzte
`overrides` deterministisch an. Unbekannte Profileinträge, doppelte IDs,
Fallback-/Abhängigkeitszyklen sowie nicht auflösbare erforderliche
Komponenten sind Fehler.

`ellmos.stack.v2` bleibt kompatibel, wird aber nur tolerant über sein
`bundle_refs`-Feld konsumiert. Das autoritative Stack-Schema liegt außerhalb
dieses Repositories und wird hier nicht kopiert. Ein vollständiger
Stack-v2-Vertrag bleibt ein Follow-up.

## Output- und Log-Bindings

`ellmos.system.v1` und `ellmos.system-instance.v1` typisieren gewünschte
Ausgaben über `output_bindings`. Ein Binding enthält:

- `kind`: `one_off_report`, `decision_request`, `decision_synthesis`,
  `automation_summary`, `runtime_log` oder `audit_receipt`
- `owner_ref`, `storage_uri`, `visibility`, `raw_content_allowed`
- optional `retention`, `backup_uri`, `desktop_shortcut` und
  `materialization`; letzteres ist eng auf
  `resolution-only-unmaterialized` begrenzt

Sicherheitsregeln:

- rohe Runtime-Logs verwenden ausschließlich normalisierte
  `host-local://`-URIs; OneDrive und Desktop sind keine Rohlogziele, auch
  nicht percent-kodiert, als Query, Backup oder Shortcut,
- Entscheidungen verwenden `control-center://_DECISIONS`,
- redigierte Automationssynthesen gehören dem
  `ellmos-automation-control-bundle` und verwenden
  `user://.USR/logs/automation`; `raw_content_allowed` ist dabei zwingend
  `false`,
- Audit-, Mutation- und Policy-Receipts gehören dem
  `ellmos-governance-assurance-bundle`,
- das Memory-/Human-Context-Bundle besitzt keine Logs,
- ein einmaliger Bericht mit `desktop://` benötigt ein
  `user://.USR/`-Backup.

System Explorer indexiert später ausschließlich Metadaten, URI, Typ, Owner,
Aufbewahrung und Health. Native Rohlogs bleiben beim produzierenden Modul
oder der Runtime. Unbekannte Output-Binding-Felder und Secret-Wert-Aliase
werden abgewiesen; ausschließlich explizite Referenzfelder mit dem Suffix
`_ref`, etwa `client_secret_ref`, bleiben zulässig. Suffixe wie `_uri`,
`_path`, `_id`, `_provider` oder `_status` machen ein Secret-Feld nicht
harmlos.
Die rekursive Prüfung gilt auch für generische `bindings`. Cloud-safe
Manifeste enthalten ausschließlich logische Secret-Referenzen, niemals
Credential-Werte oder absolute lokale Secret-/Credential-Pfade.

Die Auflösung solcher Referenzen auf hostlokale Credential-Pfade ist ein
separater, hier nicht implementierter Runtime-Vertrag. Ebenso bleiben
authentifizierter Peer-Pull über SSH/Tailscale und Datenbank-Synchronisierung
über `sqlite-transit-sync` mit Snapshot und Receipt spätere Verträge.
Live-WAL-Dateien werden nicht kopiert; `.SYNC` erhält keine Credential-Werte.

## CLI

Einzeldatei oder gesamter Repo-Baum:

```powershell
system-explorer manifest-validate .\manifest.json
system-explorer manifest-validate C:\_Local_DEV\repos\ellmos-development-system
```

Die Baumprüfung läuft rekursiv und pfadsortiert. Sie validiert die sechs
V4-Verträge sowie kompatible `ellmos.module.v2`- und `ellmos.stack.v2`-
Manifeste. Andere `ellmos.*`-Schemas werden als `skipped` ausgewiesen, nicht
stillschweigend als validiert behauptet.

System- und Testauflösung:

```powershell
system-explorer system-resolve systems\instances\WORKSTATION-LG.json `
  --catalog manifests\bundles.catalog.v1.json

system-explorer test-resolve tests\profiles\no-federation.json `
  --catalog manifests\bundles.catalog.v1.json
```

Ohne `--output` erscheint die Auflösung nur auf stdout. Mit `--output` wird
kompaktes, schlüsselsortiertes JSON atomar auf genau diesen Pfad geschrieben.
Die Resolution enthält ausdrücklich leere `runtime_actions` und
`target_mutations`; Testauflösungen setzen `writeback_to_base` zwingend auf
`false`.

`component_states` einer gewünschten Instanz sind eng typisiert. Der Resolver
gibt jeden deklarierten State unverändert als `component_state` am zugehörigen
aufgelösten Komponentenobjekt aus, zusätzlich zu `desired_status`. Damit
bleiben gewünschte Trusted-Peer-Felder (`desired_profile`, `publisher_slot`,
`publishes`, `peer_transfer`, `network_path`, `peer_verification`,
`destination_policy`) und Database-Transit-Felder (`activation`,
`database_allowlist`, `live_database_in_sync`) prüfbar, ohne eine
Runtime-Aktion abzuleiten. Der Peer-Transport ist dabei ausschließlich
SFTP über SSH; Tailscale kann nur den Netzwerkpfad tragen.
`ready-disabled` verlangt zwingend eine leere `database_allowlist` und
`live_database_in_sync: false`.

## Fremdfixture-Readback vom 2026-07-29

Die zu Beginn von W1 vorhandenen einfachen Manifeste im lokalen
`ellmos-development-system`-Clone erfüllen den strikten Vertrag noch nicht.
Die beobachteten Migrationspunkte sind insbesondere gemeinsame
Metadaten/Hashes, typisierte gepinnte Komponenten, der Schema-Name
`ellmos.bundles.catalog.v1`, gepinnte System-/Instanzreferenzen sowie
`base_system_ref`, `base_hash` und begründete `suppressions` in Tests. Der
Resolver lockert diese Grenzen nicht; die erzeugende Manifest-Änderung muss
vor gemeinsamer Auflösung angepasst werden.
