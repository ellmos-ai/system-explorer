---
name: system-explorer
version: 0.4.2
type: product-skill
status: development
description: >
  Evidence-backed local-first system cartography, function/carrier coverage,
  V4 composition resolution, software endpoint registry projection, and
  Ed25519-verified search routing without target system mutation.
---

# system-explorer — Product Skill (Human & LLM Usage)

> **Software Version:** `0.4.2` | **License:** MIT | **Index:** [`llms.txt`](llms.txt)
> **Truth Boundary:** Source systems stay authoritative; only URIs, locators,
> normalized metadata, and SHA-256 digests are stored locally. Raw prompt text
> and credentials are never stored.

## 1. When to Use & Boundaries

Use `system-explorer` when a human operator or LLM agent needs to:

- Map **desired system functions** against **evidenced function carriers**
  (modules, skills, MCP surfaces, registries, databases, CLI commands).
- Detect **architecture drift**, **carrier mismatches**, or **missing coverage**
  deterministically without heuristic name guessing.
- Validate V4 composition contracts (`manifest-validate`,
  `component-registry-check`, `system-resolve`, `fleet-resolve`, `test-resolve`).
- Project a deterministic, redacted **software endpoint registry**
  (`software-endpoints`).
- Verify Ed25519-signed `actual-self` and `search-authority` receipts via
  `search-route`.

**What `system-explorer` NEVER does:**

- Never modifies scanned target codebases or external registries during
  `scan`, `ingest`, `coverage`, `assess`, `system-resolve`, or `propose`
  (proposals are read-only; § 521 BGB).
- Never transmits data off-host (`100%` offline / Zero-Egress; web dashboard
  binds exclusively to `127.0.0.1:8765`).
- Never grants executable tool authority on `declared`, `inferred`, expired,
  or hash-drifted evidence (strictly fail-closed).

## 2. Prerequisites & Installation

- **Runtime:** Python `>=3.10`, `cryptography>=41` (optional UI extras:
  `fastapi>=0.100`, `httpx>=0.24`).
- **Privileges:** Unprivileged user mode (`RunAsInvoker`, no admin/root needed).

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
system-explorer --help
```

If running directly from a source checkout or worktree without an editable
install, prepend `src` to `PYTHONPATH`:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m system_explorer.cli --help
```

## 3. Core Workflows (Human & Machine)

| Task | Command | Output / Effect |
|---|---|---|
| Check config & DB permissions | `system-explorer doctor --config examples/explorer.json` | JSON health summary on `stdout` |
| Bounded evidence scan | `system-explorer ingest --config examples/self-scan.json --time-budget-seconds 300 --progress jsonl` | Progress JSONL on `stderr`, summary JSON on `stdout` |
| Coverage & gap report | `system-explorer coverage --config examples/self-scan.json` | JSON separating `discovery_summary` and `desired_summary` |
| Software endpoint projection | `system-explorer software-endpoints --config examples/software-resources.json --refresh` | Content-hashed `system-explorer.software-endpoint-registry.v1` JSON |
| Visual system map export | `system-explorer map --config examples/self-scan.json --view coverage --format mermaid` | JSON, ASCII, Mermaid, or standalone HTML |
| Validate module manifests | `system-explorer manifest-validate .` | Exit `0` when valid, non-zero on schema/hash conflict |
| Resolve V4 system instance | `system-explorer system-resolve instance.v1.json --catalog bundles.catalog.v1.json` | Deterministic read-only resolution (`--output` writes atomically) |
| Cryptographic search routing | `system-explorer search-route query.json --config explorer.json --resolution resolved.json --actual-self actual.json --authority-receipt auth.json` | Readback-verified `ellmos.search-routing-receipt.v1` or `BLOCKED` |
| Local web dashboard (Human UI) | `system-explorer serve --config examples/self-scan.json` | Loopback-only UI at `http://127.0.0.1:8765` |

## 4. Verification, Exit Codes & Readback

- **Exit `0`:** Command succeeded and all fail-closed checks passed.
- **Non-zero exit:** Schema mismatch, missing authority receipt, hash drift,
  lock/dirty gate block, or unreadable path (no partial target mutation).
- **Exit `130`:** Interrupted via `Ctrl+C`; active SQLite root transaction is
  rolled back cleanly.
- **Automated suite verification:**

```powershell
pytest -ra -v
ruff check src tests
python -m compileall -q src tests
```

## 5. Deep-Dive Documentation

- Machine index: [`llms.txt`](llms.txt) (compatibility pointer: [`llm.txt`](llm.txt))
- Architecture & domain layers: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Evidence & privacy boundaries: [`docs/EVIDENCE-MODEL.md`](docs/EVIDENCE-MODEL.md)
- V4 composition contracts: [`docs/V4-COMPOSITION-CONTRACTS.md`](docs/V4-COMPOSITION-CONTRACTS.md)
- Crystallized software resources: [`docs/CRYSTALLIZED-RESOURCES.md`](docs/CRYSTALLIZED-RESOURCES.md)
- Connector boundaries (`ai-media-editor`, `diagrams`): [`docs/CONNECTOR-ADAPTERS.md`](docs/CONNECTOR-ADAPTERS.md)
- Security & response SLA: [`SECURITY.md`](SECURITY.md)
