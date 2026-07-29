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
