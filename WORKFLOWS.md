# WORKFLOWS.md — Router zu Multi-Step-Playbooks

> **Zweck:** Navigation. „Welcher Workflow für welches Problem?"
> **Content:** Siehe `workflows/*.md` — hier steht **kein** Prozedur-Detail.
> **Abgrenzung zu PATTERNS.md:** Patterns = einzelne Code-Snippets.
> Workflows = Multi-Step-Prozeduren mit Side-Effects.
> **Auto-generiert:** Die Tabelle im AUTOGEN-Block unten wird von
> `_tools/workflows-sync` gepflegt. Handgeschriebene Inhalte oberhalb und
> unterhalb der Marker bleiben unangetastet.

---

## Verfügbare Workflows (auto-generated)

<!-- @auto-generated:workflow-index -->
<!-- last-updated: 2026-07-29 22:05 -->
<!-- tool: _tools/workflows-sync -->
<!-- count: 1 workflows in 1 categories -->

## General (1)

| Workflow | Purpose | Frequency | Duration |
|---|---|---|---|
| **Repository-Schaltpläne aktualisieren** [`update-repo-diagrams.md`](./workflows/update-repo-diagrams.md) | Verwaltete Systemkarten in einem einzelnen Git-Repository oder in den | ad-hoc oder bei Architekturänderungen | abhängig von Anzahl und Größe der Repositories |

<!-- @end:workflow-index -->

## Beispiel (handschriftlich, zur Orientierung)

Falls du lieber ohne Auto-Generator arbeitest, kann die Tabelle so aussehen:

| Du willst... | Öffne |
|---|---|
| [Vom Beispiel auf einen echten Workflow starten] | [`workflows/_example-workflow.md`](./workflows/_example-workflow.md) |
| [Einen Release-Prozess dokumentieren] | `workflows/release.md` (falls angelegt) |
| [Ein Security-Playbook dokumentieren] | `workflows/security-audit.md` (falls angelegt) |
| [Einen Hotfix-Ablauf dokumentieren] | `workflows/hotfix.md` (falls angelegt) |
| [Ein Admin-Playbook für Force-Push pflegen] | `workflows/force-push.md` (falls angelegt) |

(Diesen Beispiel-Block kannst du löschen wenn `workflows-sync` eingerichtet ist.)

## Wann welcher Workflow?

- **Nach Dependabot-Alert** → vorhandenes Security-Playbook nutzen oder neu anlegen
- **Nach Feature-Branch-Merge** → Release-Workflow nutzen oder anlegen
- **Bei Crash in Production** → Hotfix-Workflow nutzen oder anlegen
- **Bei Neuem Team-Mitglied** → Orientierungs- oder Onboarding-Workflow anlegen
- **Bei History-Bereinigung** → eigenes Admin-Force-Push-Playbook des Projekts

## Wann einen neuen Workflow anlegen

Ein neuer Workflow ist gerechtfertigt wenn:
- Mindestens **5 Schritte** mit **Side-Effects** (nicht nur „docs lesen")
- Das Prozedere mindestens **alle 3 Monate** wiederkehrt
- Es **Fallstricke** gibt, die ein LLM-Agent spontan nicht rekonstruieren kann
- Ein **klares Exit-Criterion** existiert (wann ist der Workflow fertig?)

Wenn einer dieser Punkte fehlt: **kein eigener Workflow**, sondern Abschnitt
in einem existierenden oder Pattern in `PATTERNS.md`.

## Konventionen

Siehe [`workflows/README.md`](./workflows/README.md) für:
- Datei-Struktur eines einzelnen Workflows
- Namens-Konvention (kein `WORKFLOW-A.md` — sprechende Namen!)
- Pflicht-Abschnitte (Purpose, Steps, Exit-Criteria, Fallstricke)
