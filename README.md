# system-explorer

[![Pytest](https://img.shields.io/badge/Pytest-127%20passed-brightgreen.svg)](tests)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ecosystem: ellmos-ai](https://img.shields.io/badge/Ecosystem-ellmos--ai-blue.svg)](https://github.com/ellmos-ai)
[![Umbrella: open-bricks](https://img.shields.io/badge/Umbrella-open--bricks-purple.svg)](https://github.com/open-bricks)

[English](README.md) | [Deutsch](README_de.md)

> [!NOTE]
> For LLM-optimized index and quick reference, see [`llms.txt`](file:///C:/_Local_DEV/repos/system-explorer/llms.txt).

`system-explorer` creates evidence-based maps of a modular agent and software
system. The tool separates two layers:

1. **Desired functions** – what the overall system is intended to provide.
2. **Function carriers** – skills, repositories/modules, MCP interfaces,
   stacks, actors, commands, or other components that actually or
   prospectively provide these functions.

This mapping reveals full, partial, absent, overlapping, and negative
coverage. A function without an evidenced carrier is not merely "unknown";
it is a visible system gap.

## Features

- bounded scanner for manifests, skills, entry points, and document links
- typed control maps for `AGENTS.md`, `CLAUDE.md`, `README.md`, policies,
  decisions, freely configured control files, and entry directories
- registry, database, and cloud maps with tables, actual/desired data actors,
  transfer paths, and credential references only
- local SQLite evidence registry containing URI, locator, hash, and temporal
  context instead of copied source data
- desired specification for functions, carriers, coverage, and structure
- transcript adapters for Codex, Claude Code, Claude Desktop, Gemini/agy, Kimi,
  and generic JSONL
- actual, desired, diff, and coverage maps as JSON, ASCII, Mermaid, and HTML
- federated map imports/exports with identical views per device, system
  boundaries, and whole-system analysis
- private/partially open server checks, protection coverage, cost/locality
  comparisons, and purpose checks for individual modules or repositories
- LLM trace and LLM action maps for sessions and CLI, API, tool, and system
  connection paths
- function-path maps from entry points and actors through carriers to
  functions, outputs, and cross-system handoffs
- crystallized peripheral resources for installed software, external modules,
  repositories, scripts, and skills, including LLM control paths,
  flexibility, and evidence-required token-saving potential
- additive V4 composition contracts for bundles, catalogs, systems, desired
  instances, resolution tests, and fleets
- deterministic pinned read-only resolution with profiles, suppressions, root
  containment, and canonical content hashes
- typed read-only bridge from `system-explorer.resolution.v1` into desired and
  coverage evidence with requirement severity and provider overlap
- explicit hashed function-equivalence contracts between differing desired
  and actual function IDs, without name or outcome heuristics
- optional ApiProber evidence intake for authorized passive REST checks
- `ai-media-editor` connector for explainer-video-ready storyboards, narration
  scripts, and Mermaid diagrams derived from analyzed system maps
- safe idempotent repository/bundle diagram maintenance with dry run,
  lock/dirty gates, atomic readback, and optional commit and push
- local graphical interface with evidence-related details
- read-only, prompt-assisted change proposals with mandatory gates
- path-probing plans for external, budgeted swarm tests

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
system-explorer init --config explorer.json
system-explorer ingest --config explorer.json --time-budget-seconds 300
system-explorer coverage --config explorer.json
system-explorer assess --config explorer.json
system-explorer map --config explorer.json --view control --format mermaid
system-explorer map --config data-cloud.json --view data --format html --output data-map.html
system-explorer documents --config explorer.json --role policy
system-explorer register X:\system\SPECIAL-ENTRY.md --role control --entry --config explorer.json
system-explorer map --config explorer.json --view coverage --format html --output map.html
system-explorer map-export --config explorer.json --view all --output system-map-WORKSTATION.json
system-explorer map-import system-map-LAPTOP.json --config explorer.json
system-explorer map --config explorer.json --view llm-traces --system LAPTOP
system-explorer map --config explorer.json --view federation
system-explorer server-check --config deployment.json
system-explorer provider-refresh --config deployment.json
system-explorer purpose-check --target carrier:system-explorer --config deployment.json
system-explorer resources --config software-resources.json
system-explorer map --config software-resources.json --view resources
system-explorer explain-video --config explorer.json --output explainer-package --media-editor ..\ai-media-editor --probe
system-explorer diagrams --repo C:\_Local_DEV\repos\my-module
system-explorer diagrams --bundle .\bundles\media.bundle.v1.json --apply --commit --push
system-explorer manifest-validate C:\_Local_DEV\repos\ellmos-development-system
system-explorer component-registry-check component.registry.bindings.v1.json --bundle-root bundles
system-explorer system-resolve instance.v1.json --catalog bundles.catalog.v1.json --registry-bindings component.registry.bindings.v1.json
system-explorer coverage --config explorer.json --resolution resolved-system.json
system-explorer coverage --config explorer.json --equivalence function-equivalence.json
system-explorer import-resolution resolved-system.json --config explorer.json
system-explorer import-function-equivalence function-equivalence.json --config explorer.json
system-explorer test-resolve system-test.v1.json --catalog bundles.catalog.v1.json
system-explorer serve --config explorer.json
```

By default, the interface binds only to `127.0.0.1:8765`.

### Bounded scans and progress

`scan` and the scan phase of `ingest` have a default CLI time budget of 300
seconds. Each root is processed as a separate transactional checkpoint. If an
error occurs before the commit, the open root transaction is rolled back;
already completed roots remain consistently stored. If an error occurs
exactly at a commit boundary that is no longer open, telemetry reports
`root_commit_state_uncertain` instead of falsely claiming a rollback. In JSONL
mode, progress and CLI errors are written exclusively as JSONL to `stderr`,
while the final result is written exclusively to `stdout`.

```powershell
python -m system_explorer.cli scan `
  --config C:\path\to\system-explorer.json `
  --time-budget-seconds 900 `
  --progress jsonl `
  --progress-interval-seconds 5
```

`--progress off` disables telemetry. `--time-budget-seconds 0` explicitly
disables the deadline; this is not recommended for unattended runs. `Ctrl+C`
exits with code 130 and rolls back an open transaction. A resume cursor does
not yet exist: the next run scans the roots again and uses idempotent upserts.
Hard process termination can still create SQLite recovery artifacts and is
not a controlled shutdown.

In an additional Git worktree, a global editable install may still point to a
different clone. For a verifiably correct test run, either use an isolated
virtual environment in the worktree or explicitly place its source first:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest discover -s tests -v
python -m ruff check src tests
```

Custom control files are configured through `control_documents` (glob, role,
entry flag), and entry directories through `entry_directories`. The control
and tree views show resolved and missing pointers together with their source
line. Additional documents can also be registered and rediscovered
interactively through the CLI and local UI.

The data view automatically recognizes JSON registries and SQLite schemas.
Additional registries, databases, table purposes, writers/readers, cloud
connections, direct or indirect mirrors, and credential references are
described neutrally through configuration; see
[`examples/data-cloud.json`](examples/data-cloud.json). Credential values are
never read or stored.

System identity is defined under `system`; `map_imports`, `connections`, and
`handoffs` represent external maps, SSH/Tailscale connections, and
asynchronous `.SYNC` handoffs. Every domain view can be restricted to an
origin system in the CLI and UI, or combined across all available maps. See
[`docs/FEDERATED-MAPS.md`](docs/FEDERATED-MAPS.md) and
[`examples/deployment-federation.json`](examples/deployment-federation.json).

Server and repository purposes are evaluated as criteria rather than mere
labels. Rules for private servers, partially open services, ApiProber, and
cost comparisons are documented in
[`docs/DEPLOYMENT-PURPOSE-MODEL.md`](docs/DEPLOYMENT-PURPOSE-MODEL.md); a dated
provider baseline is available in
[`docs/CLOUD-SERVER-BASELINE_2026-07-29.md`](docs/CLOUD-SERVER-BASELINE_2026-07-29.md).

Installed software is not automatically equated with LLM usability.
`software_resources` and a bounded `software_discovery.commands` allowlist
register the resource, function, and control path. `◆`, `◇`, `△`, `○`, and `?`
denote native, direct, indirect, reference-only, and unevidenced LLM readiness.
The rules and truth boundaries are documented in
[`docs/CRYSTALLIZED-RESOURCES.md`](docs/CRYSTALLIZED-RESOURCES.md); a neutral
configuration is available in
[`examples/software-resources.json`](examples/software-resources.json).

The V4 contracts, hash rules, output/log bindings, and CLI boundaries are
documented in
[`docs/V4-COMPOSITION-CONTRACTS.md`](docs/V4-COMPOSITION-CONTRACTS.md).
`manifest-validate` checks either a single file or an entire repository tree.
`component-registry-check` validates typed bundle references against exactly
hashed native sources and calculates occurrence-based `declared_only` gates.
`system-resolve --registry-bindings` consumes this exact canonical logic; a
second resolver in the manifest repository is unnecessary. Host context and
observation time belong only in explicitly generated receipts, not in the
host-neutral binding manifest. Resolver output is written atomically only
with an explicit `--output`; runtime actions and target-system mutations
remain excluded.

### Actual-self search routing

`import-actual-self` accepts a hashed and Ed25519-signed
`ellmos.actual-self-component-receipt.v1` from a native runtime query. Stable
reference, registry hash, source/record ID, host scope, expiry, and exact
function IDs must match an already source-verified resolution. The producer –
for example `access_surface:controlcenter` – remains the evidence source and
is not reinterpreted as a function provider. `declared`, `inferred`, external
hosts, expired receipts, and name similarity provide no availability.
Permitted signer, host, adapter, receipt schema, and maximum TTL come from the
local content-hashed `system-explorer.receipt-trust-store.v1`; the query cannot
supply its own trust key. In addition, `receipt_trust_store_sha256` in the
local Explorer configuration must pin the SHA-256 of the trust-store file
separately; the content hash stored inside the store is not a root of trust.
Each signer record additionally pins the SHA-256 of the referenced public-key
file. This key pin is rechecked during every verification so that a replaced
PEM cannot be authorized by an unchanged trust store.

```powershell
system-explorer search-route search-query.json `
  --config explorer.json `
  --resolution resolved-system.json `
  --actual-self controlcenter-native-readback.json `
  --authority-receipt scoped-decision-receipt.json `
  --output search-receipt.json
```

`search-route` does not accept free-text search. Exact candidates, semantic
ranking, and ControlCenter lexical search may supply only typed stable
references. System Explorer then filters them against registry identity,
actual-self evidence, and scope-specific coverage. Scores are compared only
within their explicitly named `score_domain`. Ambiguity remains fail-closed.

The generated `ellmos.search-routing-receipt.v1` is read-only by default and
does not execute a tool. An explicitly requested executable selection also
requires matching, separately signed
`ellmos.search-authority-receipt.v1` references. The query contains only their
stable references; embedded or self-asserted authority fields are invalid. A
`delegated-avatar-decision` is valid only within its component, capability,
query, host, and system scopes, and requires a delegation reference, evidence
references, minimum confidence, freshness, and freedom from conflicts. The
signer policy must explicitly permit the delegation reference. The receipt
issuer and `scope.host_ids` must match the host of the currently resolved
system instance; a multi-host signer does not permit foreign-host replay. A
raw TOM_lm prediction alone is not an authority. Stored actual/authority
receipts are cryptographically verified again for every search; a manipulated
SQLite metadata record is insufficient.

The `ai-media-editor` connector materializes a UC6 handoff with a storyboard,
German narration, and Mermaid visuals from selected maps. It does not silently
render media itself or copy raw evidence. The separate repository diagram
adapter writes only a marked generated documentation file into explicitly
named Git roots; dry run is the default. Its contract and security gates are
documented in
[`docs/CONNECTOR-ADAPTERS.md`](docs/CONNECTOR-ADAPTERS.md).

## Security and truth boundaries

- Sources remain in place; only references and checksums are stored.
- Prompt and transcript content is not stored.
- A manifest declaration does not prove actual use.
- A tool call proves successful function execution only together with a
  result, readback, or test.
- The module produces proposals but does not modify target systems.
- Newer evidence wins only within the same relationship; older positive
  evidence cannot obscure negative evidence.

Details are available in [ARCHITECTURE.md](ARCHITECTURE.md), data rules in
[`docs/EVIDENCE-MODEL.md`](docs/EVIDENCE-MODEL.md), and adapter boundaries in
[`docs/PROVIDER-ADAPTERS.md`](docs/PROVIDER-ADAPTERS.md).

## Resolution as desired evidence

A stored `system-explorer.resolution.v1` output can be imported directly as
desired evidence:

`ellmos.system.v1` may compose pinned `subsystem_refs`. The resolver validates
their role and profile, rejects path/identity cycles, and keeps every child as
an independently hashed nested resolution; child bundles and functions are
never flattened into the parent. Identical system/instance output bindings
are deduplicated, while conflicting policies for the same target fail closed.
Until scoped subsystem projection exists, the resolution importer rejects a
non-empty subsystem tree explicitly instead of silently dropping it.

```powershell
system-explorer coverage `
  --config explorer.json `
  --resolution resolved-system.json
```

Alternatively, `desired_resolution_sources` in the Explorer configuration
accepts one or more resolution paths; `coverage` and `ingest` import them
relative to the configuration directory. Scope and `component.ref` determine
a collision-safe hashed carrier ID; both readable values remain in metadata.
Only known active `desired_status` values and their `provides` create desired
function edges; `unavailable` remains visible as carrier status but provides
no function. `consumes` remains descriptive carrier metadata. `required`,
`recommended`, `optional`, and `desired_status` remain attached to the edges.
A newer resolution for the same instance replaces its older active desired
projection. Older generations are recorded as `stale-ignored` during later
imports and cannot roll back active state; equal generations with different
content hashes are rejected as conflicts. Parsing, source hash, and file
metadata come from the same opened byte snapshot. State validation and
projection replacement run together within a SQLite `BEGIN IMMEDIATE`
boundary so concurrent imports of the same scope are decided serially.

Coverage output separates `discovery_summary` from `desired_summary` and
reports multiple resolution scopes individually: only `required` counts as a
hard gap, while recommended and optional gaps remain separately visible.
Multiple desired providers within the same scope appear as `desired_overlap`;
the same providers on different hosts are not merged into an artificial
overlap. `assess` and `propose` preserve this scope boundary, so a satisfied
host cannot conceal another host's gap. Actual coverage additionally requires
a typed match of `component_ref` or `stable_ref`. A different observed
provider on the same host is reported as `wrong-provider` and
`carrier-mismatch`, not as satisfying the desired function. A fallback that
the resolution explicitly declares as a second provider remains eligible for
coverage. For host-bound instances, only the explicit host ID counts; neither
the instance scope nor a shared logical system ID may satisfy multiple hosts
at once.

The scanner propagates real component identity without name heuristics: valid
`ellmos.module.v2` manifests provide exactly `module:<id>`, and skills provide
only an explicitly declared `component_ref`. Duplicate source claims are a
fail-closed conflict; untagged carriers and mere name, case, path, tag,
package, or command similarity remain ineligible for coverage. Software
resources are bound only when their canonical configuration declaration is
also present as hashed evidence.

The import writes exclusively to the local Explorer evidence registry.
Resolutions with non-empty `runtime_actions` or `target_mutations` are
rejected; neither source nor target system is changed.

## Explicit function equivalence

Differing desired and actual function IDs are never equated based on names,
capitalization, paths, tags, or a similarly described outcome. A positive
mapping instead requires a `system-explorer.function-equivalence.v1` contract
with:

- a typed `component_ref`;
- exact schema, version, and content-hash pins for desired and actual
  contracts;
- a typed decision or policy authority;
- decision/policy evidence already present in the evidence store, with an
  identical URI and SHA-256 and carrying the same concrete `authority_ref`;
- a verified actual carrier on exactly the same host;
- positive native actual evidence with a permitted readback/probe source type
  and SHA-256. `declared` and `inferred` are insufficient.

Template contracts are host-neutral; actual host deviations require an
explicit `host-override` with host ID and rationale. Multiple applicable
authorities for the same target constitute a conflict and materialize no
coverage. Contract or scanner hash drift withdraws coverage until a renewed
mapping exists. The synthetic edge inherits the native actual status and
cannot upgrade it; `observed` therefore remains partial coverage.

The V4 inventory found 68 unique desired function IDs and 886 actual function
IDs with no exact intersection. This release therefore deliberately provides
only the registry, importer, and synthetic tests, but no real equivalence
mapping. Real pairs are added only after an explicit capability contract and
decision/policy provenance exist.

## Bundles and partners

`system-explorer` remains usable on its own. In a V4 composition, it is the
required discovery, mapping, and coverage checker for the
`ellmos-core-discovery-bundle`. Direct partners are `ellmos-core` as the
orchestration caller and the recommended component resolver and semantic
routing partner.

The module can also provide read-only support at two boundaries:

- `ellmos-governance-assurance-bundle`: optional mapping of decision
  documents, policies, and references. Decisions and policies remain with
  their domain authorities.
- `ellmos-sync-federation-bundle`: recommended cloud-safe map projection.
  Federation and transfer remain with their designated carriers.

MCP servers such as ControlCenter are access surfaces, not function owners of
this module. Authoritative membership, versions, profiles, and private
composition recipes are defined exclusively in the respective bundle
manifest; this public overview is only a safe discovery aid.
