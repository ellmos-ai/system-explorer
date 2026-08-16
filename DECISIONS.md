# Architekturentscheidungen

Neueste Entscheidungen stehen oben. Ersetzte Entscheidungen bleiben mit
Verweis erhalten.

## 2026-08-10: Projektversion 0.4.0 bleibt Development

`pyproject.toml` ist die kanonische Packaging-Quelle. Runtime, Modulmanifest,
Steuerdokumente und Changelog führen exakt `0.4.0`; der Manifeststatus bleibt
`development`. Eine fremde oder veraltete `importlib.metadata`-/`egg-info`-
Auflösung darf diesen Stand nicht überschreiben und wird als begründeter
Test-Fallback dokumentiert. Diese Entscheidung autorisiert kein Release, Tag,
Upload oder Push.

## 2026-08-10: Authority benötigt lokale, erlaubte Evidenz

Signatur und Trust Store beweisen nur die Herkunft eines Authority-Receipts.
Vor Import und bei jeder Resolver-Nutzung werden alle `evidence`- und
`conflicts`-Referenzen eindeutig gegen den lokalen Evidence Store, die exakte
SHA-256 und die erlaubten Quellen `document:decision`/`document:policy`
geprüft. Externe/read-only oder mehrdeutige Belege erzeugen keine Authority.

## 2026-08-10: Ein gemeinsamer Validator schützt Receipt- und Resolution-Grenzen

Stable Refs, SHA-256, Zeitstempel und exakte Objektfelder verwenden einen
gemeinsamen fail-closed Kern. Resolution-Komponenten mit demselben Ref dürfen
Typ, Registry-Binding oder `provides` nicht widersprüchlich wiederholen; die
Prüfung läuft vor jeder Store-Transaktion.

## 2026-08-07: Fleet-Auflösung wird neu gebaut statt aus PR #2 gemergt

### Kontext

PR #2 (`codex/fleet-resolution`, Juli 2026) hat ein `fleet-resolve` gebaut:
Fleet-Manifeste zu aufgelösten Systemen, mit stabilen Fleet-IDs getrennt von
relativen Manifestpfaden, erhaltenen `host`/`ref`-Hostbindungen, begründeten
Desired-Abweichungen und Ausweis blockierender Pflichtlücken. Diese Fähigkeit
fehlt bis heute: `schemas/ellmos.fleet.v1.schema.json` und die
Fleet-Behandlung in `contracts.py` sind da, aber es gibt weder ein
`fleet-resolve` in `cli.py` noch eine Fleet-Auflösung in `resolver.py`.

Der Branch ist seither stehengeblieben, während `main` 37 Commits
weitergelaufen ist — darunter #13 (verschachtelte Systeme nicht-flattenend und
zyklensicher auflösen) und #14 (fail-closed Vollsystem-Evidenz mit
Root-only-Projektion).

### Entscheidung

PR #2 wird geschlossen, nicht gemergt, und die Fähigkeit als Neubau in
`TODO.md` geführt. Ein Merge hätte 29 Dateien und rund 15.700 Zeilen späterer
Arbeit gelöscht — unter anderem `actual_self.py`, `component_registry.py`,
`function_equivalence.py`, `media_connector.py`, `receipt_trust.py`,
`repo_diagrams.py`, `resolution_bridge.py`, `search_authority.py`,
`search_routing.py`, acht Schemata, sieben Testmodule und `README_de.md`.

Ein Rebase wäre ebenfalls der falsche Weg: #13/#14 haben das Auflösungsmodell
selbst geändert. Die Fleet-Auflösung muss auf dem heutigen fail-closed-Modell
aufsetzen, nicht auf dem Modell, gegen das #2 geschrieben wurde. Der Branch
bleibt als Vorlage lesbar.

### Grenze

Die Entscheidung sagt nichts darüber, ob Fleet-Auflösung gebraucht wird —
sie wird gebraucht. Sie sagt nur, dass der vorhandene Branch nicht der Weg
dorthin ist.

### Vollzug (2026-08-07)

Der Neubau ist erfolgt und hat die Entscheidung im Nachhinein bestätigt: die
alte Gap-Berechnung hätte auf dem heutigen Modell falsch gerechnet. Sie las
`component.provides`, um Pflichtfunktionen zu bestimmen — die Quarantäne aus
dem `declared_only`-Gate leert genau dieses Feld. Ein vollständig blockiertes
Mitglied hätte damit als gedeckt gegolten, weil es nichts mehr verspricht.
Gemessen wird jetzt gegen die deklarierten Werte aus
`activation_quarantine.declared_provides`.

Zweite Abweichung derselben Art: Mitgliedsfunktionen schließen jetzt
Subsystemfunktionen ein. `resolution["functions"]` ist seit der
Root-only-Projektion bewusst wurzelbeschränkt; für eine Flotte ist die Frage
aber, was ein Mitglied insgesamt trägt. Beide Sichten stehen nebeneinander
(`functions`, `root_functions`), statt eine gegen die andere auszutauschen.

## 2026-07-30: Resolutionen werden als typisierte Desired-Evidenz projiziert

### Kontext

Die V4-Auflösung kennt die vollständige Bundle-/Komponentenzusammensetzung,
während ältere manuelle Desired-Spezifikationen nur einen kleinen
Funktionsausschnitt enthalten können. Die Auflösung selbst war bislang nicht
mit der Coverage-Engine verdrahtet.

### Entscheidung

Eine read-only Brücke importiert `system-explorer.resolution.v1` in den
lokalen Evidence Store. Kollisionssicher gehashte Carrier-IDs entstehen aus
Resolution-Scope und `component.ref`; ausschließlich bekannte aktive
`desired_status`-Werte und deren `provides` erzeugen
Desired-Kanten. Eine neuere Resolution ersetzt die aktive Projektion
desselben Scopes, ohne andere Instanzen zu verdrängen. Die Generation wird
monoton aus effektiver Zeit und mtime des einmalig geöffneten Quellsnapshots
geordnet; stale Importe sind No-ops, gleiche Generationen mit anderem Hash
Konflikte. Prüfung und Austausch erfolgen gemeinsam in einer
`BEGIN IMMEDIATE`-Transaktion; bereits vorhandene Mehrfachhashes derselben
Maximalgeneration werden fail-closed erkannt. Requirement,
`desired_status`, Bundle-Provenienz, Quellschema und Content-Hash bleiben
erhalten. Coverage weist Required-, Recommended- und Optional-Gaps
scopeweise getrennt aus und zeigt gewünschte Mehrfachprovider als Overlap.
Assessment und Proposal dürfen dafür kein global nivelliertes
Funktionsurteil verwenden. Beobachtete Deckung muss außerdem über
`component_ref` oder `stable_ref` einem gewünschten Provider zugeordnet sein;
ein bloß hostgleicher Fremdprovider wird als Carrier-Mismatch ausgewiesen.
Hostgebundene Instanzen dürfen dabei nicht über ihre gemeinsame logische
System-ID nivelliert werden.

### Grenze

Die Brücke entdeckt oder aktiviert keine Runtime. `consumes` ist keine
Leistungsbehauptung. Nichtleere `runtime_actions` oder `target_mutations`
werden abgewiesen. Ein erfolgreicher Import belegt nur den Sollvertrag, nicht
die tatsächliche Deckung einer Workstation oder eines anderen Hosts.

## 2026-07-30: Scans checkpointen pro Root und behaupten kein Resume

### Kontext

Ein großer Scan konnte mehrere Minuten ohne Ausgabe in einer einzigen
SQLite-Schreibtransaktion laufen. Ein externer Stop war dadurch schwer von
einem Hänger zu unterscheiden und konnte ein Recovery-Journal hinterlassen.

### Entscheidung

Die CLI veröffentlicht JSONL-Fortschritt auf `stderr`, setzt ein
konfigurierbares Standardzeitbudget und verarbeitet jeden Root als eigenen
Commit-Checkpoint. Deadline und kontrollierter Interrupt rollen nur eine noch
offene Root-Transaktion explizit zurück und erzeugen dafür kein
Erfolgsereignis. Ist die Commit-Grenze nicht mehr offen, wird der Zustand als
unklar ausgewiesen, statt einen Rollback zu behaupten. Abgeschlossene Roots
bleiben konsistent erhalten. Nachgelagerte Scanphasen besitzen dieselbe
Checkpoint- und Ereignissemantik.

### Grenze

Die Deadline ist kooperativ zwischen Dateisystemoperationen; sie kann einen
einzelnen blockierenden Betriebssystemaufruf nicht präemptiv abbrechen. Ein
hartes Prozess-Kill bleibt außerhalb des kontrollierten Vertrags. Resume wird
erst eingeführt, wenn persistente Cursor, Quellfrische und
Checkpoint-Provenienz gemeinsam validiert werden können.

## 2026-07-29: Connectoren materialisieren nur eng begrenzte Ableitungen

### Kontext

Analysierte Systemkarten sollen als Erklärvideo weiterverarbeitet und als
aktuelle Schaltpläne in einzelnen Repositories oder Bundle-Komponenten
sichtbar werden. Eine allgemeine Mutationsengine würde dagegen die
read-only-Wahrheitsgrenze des Explorers aufheben.

### Entscheidung

Der `ai-media-editor`-Connector erzeugt ein versioniertes UC6-Handoff mit
Storyboard, Sprechertext und Mermaid-Karten. Der Repo-Connector erzeugt nur
eine markierte Dokumentdatei innerhalb ausdrücklich benannter Git-Roots.
Dry-Run ist Standard; Schreiben, Commit und Push benötigen getrennte Flags.
Locks, Dirty-Baseline, Root-Containment, Fremddokumente und Push-Readback
werden fail-closed geprüft.

### Grenze

Das Handoff ist noch kein gerendertes MP4. Der Explorer verändert keine
Runtime, fachliche Konfiguration, Policy oder fremde handgepflegte
Architekturdokumentation. Reale Medienproduktion bleibt beim
`ai-media-editor`; Repo-Commits enthalten ausschließlich die generierte
Schaltplandatei.

## 2026-07-29: Software ist kristallisierte Randressource

### Kontext

Installierte Programme, Fremdmodule und Repositories verkörpern bereits
entwickelte kognitive Strukturen und standardisierte Workflows. LLMs können
dadurch Reasoning wiederverwenden, sofern ein steuerbarer Zugang existiert.

### Entscheidung

Explorer trennt `software_resource`, `interface`, `actor` und `function`.
Symbole markieren die LLM-Bereitschaft des besten registrierten Steuerwegs.
Kristallisierungsgrad, Flexibilität und Tokenersparnis werden als getrennte
Eigenschaften geführt. Breite Inventarscans unterbleiben; Erkennung erfolgt
explizit oder über eine begrenzte Befehls-Allowlist.

### Grenze

Installation beweist keine LLM-Nutzbarkeit. Deklariertes
Tokenersparnispotenzial wird erst mit Trampelpfad- oder Laufzeitevidenz zu
einem beobachteten Nutzen.

## 2026-07-29: Fachansicht und Systemebene sind orthogonal

### Kontext

Workstation, Laptop und Server sollen sich selbst kartieren und ihre Karten
gegenseitig importieren können. Eine reine Übersichtszeichnung würde die
fachlichen Analysefähigkeiten auf Fremdsystemen verlieren.

### Entscheidung

`system-explorer.map.v1` exportiert eine herkunftsgebundene, portable Karte
mit referenziellen Evidenzmetadaten. Importierte IDs werden pro System
gekapselt. Control-, Tree-, Coverage-, Purpose-, Deployment-, Data-,
LLM-Spuren- und LLM-Handlungsansichten sind auf `origin_system` filterbar und
ohne Filter als Gesamtebenenanalyse nutzbar. `federation` zeigt zusätzlich
Systemgrenzen, direkte Verbindungen und asynchrone Übergaben.

### Grenze

Eine kartierte SSH-, Tailscale- oder `.SYNC`-Verbindung ist keine
Ausführungsfreigabe. Explorer visualisiert Aufträge, führt sie aber nicht aus.

## 2026-07-29: Privatheit und Zweck benötigen positive Gegenprobe

### Kontext

Ein Server mit dem Label „privat“ verfehlt seinen Zweck, sobald eine nicht
gewünschte öffentliche Oberfläche erreichbar ist. Eine Firewalldeklaration
beweist aber noch keine externe Nichterreichbarkeit.

### Entscheidung

Privatserver erhalten nur bei vollständiger externer Blockierungsevidenz das
Urteil `full`; öffentliche Erreichbarkeit ergibt `negative`. Teiloffene
Dienste werden gegen TLS, Authentifizierung, Default-Deny/Allowlist,
Rate-Limit, Logging und sichere Secret-Ablage geprüft. Anbieterpreise und
Dokumente werden als datierte, refresh-pflichtige Referenzen modelliert.
ApiProber bleibt optional, passiv, rate-limitiert und autorisierungspflichtig.

### Grenze

Die Prüfung ersetzt weder Penetrationstest noch Compliance-Audit. Ein
Kostenurteil ersetzt keine Zweck-, Risiko- oder Verfügbarkeitsentscheidung.

## 2026-07-29: Daten- und Cloudtopologie speichert keine Nutzdaten

### Kontext

Registry-, Datenbank- und Cloudbeziehungen müssen sichtbar sein, ohne
Datenbankzeilen, Secrets oder Connection Strings in eine zweite Wahrheit zu
kopieren.

### Entscheidung

JSON-Registries werden über Struktur und Collection-Größen, SQLite über
Tabellen- und Spaltennamen kartiert. Writer/Reader besitzen Soll-/Ist-Modus.
Cloud-, Mirror- und Transferbeziehungen sind Kanten. Credentials erscheinen
nur als logische Referenzknoten mit `value_retained=false`.

### Grenze

Für nicht-SQLite-Datenbanken werden Schema und Zwecke im MVP deklarativ
konfiguriert; es wird keine produktive Verbindung geöffnet.

## 2026-07-29: Steuertextdateien bilden einen eigenen Graph

### Kontext

`AGENTS.md`, `CLAUDE.md`, Policies, Decisions und READMEs steuern ein
Agentensystem über Bootreihenfolgen, Pointer und Verzeichnisgrenzen. Eine
flache Dateiliste bildet diese Wirkung nicht ab.

### Entscheidung

Explorer typisiert Steuer-, Policy-, Decision- und Dokumentationsknoten.
`contains`, `enters_at`, `points_to` und `references` modellieren Baum,
Einstieg und Abhängigkeit. Frei definierte Dateien und Eintrittsordner können
per Konfiguration, CLI oder lokaler UI registriert werden. Fehlende Pointer
bleiben als Referenzknoten sichtbar.

### Grenze

Der Scanner bewertet Beziehungen und Provenienz, führt aber keine Anweisung
aus den gefundenen Dokumenten aus.

## 2026-07-29: Sollfunktion und Funktionsträger sind getrennte Ebenen

### Kontext

Die Existenz eines Skills oder Moduls beweist nicht, dass die beabsichtigte
Systemfunktion getragen wird. Ein Träger kann vollständig, teilweise, gar
nicht oder sogar entgegengesetzt wirken.

### Entscheidung

Funktionen und Träger sind getrennte Knoten. `carries`-Beziehungen besitzen
Soll-/Ist-Modus, Status, Konfidenz, Zeit und Evidenz. Deckungsurteile sind
`full`, `partial`, `uncovered`, `negative` und `unproven`; Mehrfachdeckung ist
eine zusätzliche Eigenschaft.

### Grenze

Mehrfachdeckung ist zunächst neutral. Ob sie erwünscht ist, entscheidet eine
externe Kardinalitäts- oder Policy-Regel.

## 2026-07-29: Evidenz wird referenziert, nicht kopiert

### Kontext

Provider-Transcripts und Systemdokumente enthalten sensible Inhalte. Eine
zweite Inhaltsdatenbank würde Datenschutz-, Aktualitäts- und
Source-of-Truth-Probleme erzeugen.

### Entscheidung

SQLite speichert URI, Locator, Hash, Zeitbezug, Konfidenz, Sensitivität und
normalisierte Ereignismerkmale. Prompt-, Antwort-, Argument- und
Ergebnisrohtexte bleiben an der Quelle. Neuere wirksame Evidenz gewinnt
innerhalb derselben Beziehung.

### Grenze

Ein Hash ist Integritätsbeleg, keine Anonymisierung.

## 2026-07-29: Explorer bleibt read-only gegenüber dem Zielsystem

### Kontext

Ein grafischer Prompt könnte leicht zu einer zweiten, unkontrollierten
Ausführungs- oder Control-Plane werden.

### Entscheidung

Prompts erzeugen ausschließlich `ChangeProposal`-Entwürfe mit
Schema-, Ontologie-, Kardinalitäts-, Policy-, Lock-, Freigabe-, Dry-Run- und
Readback-Gates. `apply.authorized` ist im MVP immer `false`.

### Grenze

Eine spätere Ausführung muss außerhalb von Explorer durch vorhandene,
autorisierte Adapter erfolgen.
