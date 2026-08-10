# Provider-Adapter

| Provider | Quelle | Normalisierung | Grenze |
|---|---|---|---|
| Codex | `rollout-*.jsonl`, Archive | Prompt-Hash, Function Call/Output, Session-/Pfadreferenz | kein Rohtext |
| Claude Code | Projekt-Session-JSONL | user/assistant, tool_use/tool_result, Session-/Entrypointmerkmale | keine angrenzenden Account-/MCP-Metadaten |
| Claude Desktop | `audit.jsonl` | user/assistant/system/result/command lifecycle | kein separater Live-Hook im MVP |
| Gemini/agy | Conversation-SQLite | Tabellenzeilen, Prompt `step_type=14`, Hashes für Binärfelder | unbekannte Protobuf-Typen werden nicht als Semantik erfunden |
| Kimi | Session-/Wire-JSONL | user prompts/steers, Loop-Toolereignisse, Nachrichten | Index dient nur zur Auffindung |
| Generic | JSONL | heuristische Rollen-, Tool- und Pfadfelder | niedrigere Konfidenz |

BYUM ist eine geeignete Quelle für menschliche Prompts, beweist aber allein
weder Funktionsvollzug noch Trägererfolg. Prompt Listener und Hooker können
Runtimeereignisse liefern; auch dort gilt Call ≠ Erfolg.

## Provider-native Live-Hooks (optional)

`system_explorer.provider_hooks.ProviderHookAdapter` ist ein deaktivierter
Standard für opt-in Provider-Hooks. Ohne alle drei Freigaben —
`enabled=true`, explizite `consent_granted=true` und externe
`authorized=true` — wird nur ein nicht persistierter `disabled`-Readback
erzeugt. Die bestehende Scan-/Import-Pipeline aktiviert den Adapter nicht.

Ein aktivierter Adapter akzeptiert ausschließlich diese inhaltsarmen Felder:

| Ereignis | Pflicht-/Statusfelder | Semantik |
|---|---|---|
| `call` | `timestamp`, `source_sha256`, optional `call_id` | `outcome=pending`, kein Erfolgsbeleg |
| `result` | `timestamp`, `source_sha256`, `readback_status` | Readback bleibt separat; `success`, `partial`, `failed` oder `unknown` |
| `error` | `timestamp`, `source_sha256`, optionaler `error_code` | `outcome=error`, Fehlerstatus ohne Fehlermeldung |

Jedes normalisierte Event trägt Provider-/Adapter-ID, UTC-Zeit, exakten
Source-Hash, Retention-Metadatum, `uncertain` und `redacted=true`. Prompt-,
Antwort-, Argument-, Credential-, Token- und sonstige Roh-/Secret-Felder
werden fail-closed abgewiesen und niemals geloggt oder im Evidence Store
gespeichert. Ein optional übergebener Store erhält nur
`provider-hook-event`-Metadaten; der Adapter commitet eine bereits laufende
äußere Transaktion nicht.
