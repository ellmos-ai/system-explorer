# Security Policy / Sicherheitsrichtlinie

[English](#english) | [Deutsch](#deutsch)

---

## English

### Reporting Security Issues

Please **do not report security vulnerabilities through public GitHub issues**.

If you discover a security issue or vulnerability in `system-explorer`, please report it via GitHub Security Advisories or contact:

- **Security Team**: `security@ellmos.ai`
- **Maintainer**: `support@lukasgeiger.com` / `lukas@open-bricks.org`

Please include detailed steps to reproduce the vulnerability and any relevant logs or evidence payloads. We will acknowledge receipt within 48 hours and provide regular status updates.

### Local-First & Zero-Egress Boundary Guarantees

`system-explorer` is designed from the ground up to operate locally and securely:

1. **Zero-Egress & Data Boundary**: The module reads local system files, transcripts, manifests, and repositories. Raw source contents remain at their original locations; the local SQLite evidence store contains only references, SHA-256 hashes, locators, and normalized event features. No private user prompts or session contents are transmitted to external servers.
2. **Signed Authority Receipts & Fail-Closed Validation**: Executable search authority remains strictly fail-closed. Every `evidence` and `conflicts` reference must be uniquely present in the local evidence store, carry matching lowercase SHA-256 hashes, and reference an authoritative source (`document:decision` or `document:policy`). Ambiguities, missing records, or hash mismatches block imports and resolver execution without partial persistence.
3. **Local Loopback Binding Only**: The web interface is bound to `127.0.0.1` by default. It must not be exposed to external network interfaces without external authentication barriers.
4. **Non-Elevation (User-Mode Execution)**: `system-explorer` executes entirely in standard user space and does not require administrative or root privileges.
5. **Deterministic Immutability**: Receipt and resolution validators enforce strict rules for stable references, SHA-256 digests, and monotonic timestamps. Duplicate resolution components with conflicting types, registry bindings, or provided capabilities are rejected before any store mutation.

---

## Deutsch

### Sicherheitslücken melden

Bitte **melden Sie Sicherheitslücken nicht über öffentliche GitHub-Issues**.

Wenn Sie eine Schwachstelle in `system-explorer` entdecken, melden Sie diese bitte über GitHub Security Advisories oder kontaktieren Sie:

- **Sicherheitsteam**: `security@ellmos.ai`
- **Maintainer**: `support@lukasgeiger.com` / `lukas@open-bricks.org`

Bitte fügen Sie eine Beschreibung der Schritte zur Reproduktion sowie relevante Logs oder Belegstrukturen bei. Wir bestätigen den Eingang innerhalb von 48 Stunden.

### Local-First- & Zero-Egress-Garantien

`system-explorer` ist auf strikte lokale Datensicherheit und Fail-Closed-Integrität ausgelegt:

1. **Zero-Egress & Datengrenzen**: Das Modul liest lokale System- und Transcriptquellen. Standardmäßig verbleiben Inhalte am Ursprungsort; die lokale SQLite-Datenbank enthält nur Referenzen, SHA-256-Hashes, Locatoren und normalisierte Ereignismerkmale. Keine privaten Nutzerprompts oder Transkripte verlassen die lokale Maschine.
2. **Signierte Authority-Receipts & Fail-Closed-Validierung**: Ausführbare Search-Authority bleibt fail-closed: Jede `evidence`- und `conflicts`-Referenz muss vor dem Import eindeutig im lokalen Evidence Store vorhanden sein, dieselbe lowercase SHA-256 tragen und eine autorisierende Quelle `document:decision` oder `document:policy` besitzen. Externe oder read-only Belege, fehlende oder gelöschte Einträge, Hashabweichungen und Mehrdeutigkeiten blockieren Import und Resolver ohne Teilpersistenz.
3. **Lokale Loopback-Bindung**: Die Weboberfläche ist ausschließlich für eine lokale Bindung an `127.0.0.1` vorgesehen.
4. **Non-Elevation (Standard-Benutzerkontext)**: `system-explorer` erfordert keine administrativen Rechte (Root/Administrator).
5. **Deterministische Unveränderlichkeit**: Receipt- und Resolution-Validatoren teilen dieselben Regeln für Stable Refs, SHA-256 und Zeitstempel. Doppelte Resolution-Komponenten mit abweichendem Typ, Registry-Binding oder `provides` werden vor jeder Store-Mutation abgewiesen.
