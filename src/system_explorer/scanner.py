from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from .infrastructure import (
    DATABASE_SUFFIXES,
    register_database_file,
    register_declared_infrastructure,
    register_registry_file,
)
from .deployment import register_deployment
from .federation import register_federation
from .manifests import load_manifest
from .resources import register_software_resources
from .store import Store
from .util import (
    expand_path,
    file_effective_date,
    sha256_file,
    stable_id,
)


ENTRY_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GPT.md",
    "GEMINI.md",
    "KIMI.md",
    "START.md",
    "SKILL.md",
    "llms.txt",
}
MANIFEST_NAMES = {
    "ellmos-module.v2.json",
    "ellmos.module.v2.json",
    "stack.v2.json",
    "server.json",
}
MANIFEST_SCHEMAS = {
    "ellmos.module.v2",
    "ellmos.stack.v2",
    "ellmos.system-instance.v1",
}
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
QUOTED_REF_RE = re.compile(
    r"""["'`]((?:[A-Za-z]:[\\/]|\.{1,2}[\\/])?[\w.-]+(?:[\\/][\w .-]+)*\.(?:md|txt|json|toml|ya?ml))(?:#[^"'`]*)?["'`]""",
    re.IGNORECASE,
)
BARE_REF_RE = re.compile(
    r"""(?<![\w])(?:\.\.?[\\/])?[\w.-]+(?:[\\/][\w.-]+)*\.(?:md|txt|json|toml|ya?ml)(?:#[\w.-]+)?""",
    re.IGNORECASE,
)
WINDOWS_DOC_RE = re.compile(
    r"""[A-Za-z]:\\[^\r\n"'`<>|?*]+?\.(?:md|txt|json|toml|ya?ml)(?:#[\w.-]+)?""",
    re.IGNORECASE,
)
QUOTED_DIRECTORY_RE = re.compile(
    r"""["'`]([A-Za-z]:\\[^"'`<>|?*]+|\.{1,2}[\\/][^"'`]+)["'`]"""
)


def scan(config: dict[str, Any], store: Store) -> dict[str, int]:
    stats = {
        "files": 0,
        "directories": 0,
        "evidence": 0,
        "nodes": 0,
        "edges": 0,
        "errors": 0,
        "registries": 0,
        "registry_collections": 0,
        "databases": 0,
        "database_tables": 0,
        "servers": 0,
        "server_surfaces": 0,
        "purposes": 0,
        "provider_documents": 0,
        "cost_offers": 0,
        "federated_systems": 0,
        "map_imports": 0,
        "map_import_errors": 0,
        "software_resources": 0,
        "software_interfaces": 0,
        "software_functions": 0,
    }
    base = Path(config["_base"])
    for root_config in config.get("roots", []):
        root = expand_path(root_config["path"], base)
        if not root.exists():
            stats["errors"] += 1
            continue
        root_id = store.add_node(
            "system",
            root_config.get("id", root.name),
            scope=str(root),
            metadata={"path": str(root), "carrier_kind": "system"},
        )
        directory_ids = _scan_directories(
            root, root_id, root_config, config, store, stats
        )
        if (root / ".git").exists():
            repository_id = store.add_node(
                "carrier",
                root.name,
                node_id=f"carrier:repository:{stable_id(str(root.resolve()))}",
                scope=str(root),
                metadata={"path": str(root), "carrier_kind": "repository"},
            )
            store.add_edge(root_id, "contains", repository_id, status="observed")
            stats["nodes"] += 1
            stats["edges"] += 1
        for path in _walk(root, root_config):
            try:
                _scan_file(
                    path,
                    root,
                    root_id,
                    directory_ids,
                    config,
                    store,
                    stats,
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                stats["errors"] += 1
    if config.get("_config_path"):
        infrastructure = register_declared_infrastructure(config, store)
        stats["registries"] += infrastructure["registries"]
        stats["databases"] += infrastructure["databases"]
        stats["database_tables"] += infrastructure["tables"]
        deployment = register_deployment(config, store)
        stats["servers"] += deployment["servers"]
        stats["server_surfaces"] += deployment["surfaces"]
        stats["purposes"] += deployment["purposes"]
        stats["provider_documents"] += deployment["provider_documents"]
        stats["cost_offers"] += deployment["cost_offers"]
        resources = register_software_resources(config, store)
        stats["software_resources"] += resources["software_resources"]
        stats["software_interfaces"] += resources["software_interfaces"]
        stats["software_functions"] += resources["software_functions"]
        federation = register_federation(config, store)
        stats["federated_systems"] += federation["systems"]
        stats["map_imports"] += federation["map_imports"]
        stats["map_import_errors"] += federation["map_import_errors"]
        stats["errors"] += federation["map_import_errors"]
    store.commit()
    return stats


def _walk(root: Path, root_config: dict[str, Any]) -> Iterable[Path]:
    max_depth = int(root_config.get("max_depth", 5))
    includes = root_config.get("include", ["*"])
    excludes = set(root_config.get("exclude_dirs", []))
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        dirs[:] = [
            name for name in dirs if name not in excludes and depth < max_depth
        ]
        for name in files:
            if any(fnmatch.fnmatch(name, pattern) for pattern in includes):
                yield current_path / name


def _scan_directories(
    root: Path,
    root_id: str,
    root_config: dict[str, Any],
    config: dict[str, Any],
    store: Store,
    stats: dict[str, int],
) -> dict[Path, str]:
    max_depth = int(root_config.get("max_depth", 5))
    excludes = set(root_config.get("exclude_dirs", []))
    entry_specs = config.get("entry_directories", []) + root_config.get(
        "entry_directories", []
    )
    ids: dict[Path, str] = {}
    resolved_root = root.resolve()
    for current, dirs, _ in os.walk(root):
        path = Path(current).resolve()
        depth = len(path.relative_to(resolved_root).parts)
        dirs[:] = [
            name for name in dirs if name not in excludes and depth < max_depth
        ]
        entry = _matches_directory_spec(path, resolved_root, entry_specs)
        node_id = stable_id("directory", str(path))
        ids[path] = store.add_node(
            "directory",
            path.name or str(path),
            node_id=node_id,
            scope=str(path.parent),
            metadata={
                "path": str(path),
                "relative_path": str(path.relative_to(resolved_root)),
                "entry_directory": entry,
            },
        )
        parent_id = ids.get(path.parent, root_id)
        store.add_edge(parent_id, "contains", node_id, status="observed")
        if entry:
            store.add_edge(root_id, "enters_at", node_id, status="configured")
            stats["edges"] += 1
        stats["directories"] += 1
        stats["nodes"] += 1
        stats["edges"] += 1
    return ids


def _scan_file(
    path: Path,
    root: Path,
    root_id: str,
    directory_ids: dict[Path, str],
    config: dict[str, Any],
    store: Store,
    stats: dict[str, int],
) -> None:
    role, configured_entry = document_role(path, config)
    digest = sha256_file(path)
    modified = path.stat().st_mtime
    effective = file_effective_date(path)
    uri = path.resolve().as_uri()
    evidence_id = store.add_evidence(
        uri=uri,
        source_kind=_source_kind(path, role),
        sha256=digest,
        effective_at=effective,
        modified_at=str(modified),
        sensitivity=config.get("privacy", {}).get("sensitivity", "user-local"),
        metadata={
            "relative_path": str(path.relative_to(root)),
            "document_role": role,
        },
    )
    stats["files"] += 1
    stats["evidence"] += 1

    artifact_id = store.add_node(
        document_node_type(role),
        path.name,
        node_id=stable_id("path", str(path.resolve())),
        scope=str(path.parent),
        metadata={
            "uri": uri,
            "path": str(path),
            "extension": path.suffix.lower(),
            "document_role": role,
            "important_system_document": role is not None,
        },
    )
    parent_id = directory_ids.get(path.parent.resolve(), root_id)
    store.add_edge(parent_id, "contains", artifact_id, evidence_id=evidence_id)
    stats["nodes"] += 1
    stats["edges"] += 1

    if path.name in MANIFEST_NAMES or _is_schema_manifest(path):
        _scan_manifest(path, root_id, evidence_id, store, stats)
    registry_stats = register_registry_file(
        path, artifact_id, evidence_id, config, store
    )
    stats["registries"] += registry_stats["registries"]
    stats["registry_collections"] += registry_stats["collections"]
    stats["nodes"] += registry_stats["collections"]
    stats["edges"] += registry_stats["edges"]
    if path.suffix.casefold() in DATABASE_SUFFIXES:
        database_stats = register_database_file(
            path, artifact_id, evidence_id, store
        )
        stats["databases"] += database_stats["databases"]
        stats["database_tables"] += database_stats["tables"]
        stats["nodes"] += database_stats["tables"]
        stats["edges"] += database_stats["edges"]
    if path.name == "SKILL.md":
        _scan_skill(path, root_id, evidence_id, store, stats)
    if path.name in ENTRY_NAMES or configured_entry:
        entry_id = store.add_node(
            "entrypoint",
            path.name,
            scope=str(path.parent),
            metadata={
                "path": str(path),
                "entry_kind": _entry_kind(path.name),
                "configured": configured_entry,
            },
        )
        store.add_edge(root_id, "enters_at", entry_id, evidence_id=evidence_id)
        store.add_edge(
            entry_id,
            "points_to",
            artifact_id,
            status="configured" if configured_entry else "conventional",
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 2
    if path.suffix.lower() in {".md", ".txt"} and path.stat().st_size <= 2_000_000:
        _scan_document_pointers(
            path, artifact_id, role, evidence_id, config, store, stats
        )


def _scan_manifest(
    path: Path, root_id: str, evidence_id: str, store: Store, stats: dict[str, int]
) -> None:
    value = load_manifest(path)
    schema = value.get("schema", "")
    carrier_kind = (
        "module"
        if "module" in schema
        else "stack"
        if "stack" in schema
        else "mcp"
    )
    carrier_id = store.add_node(
        "carrier",
        value.get("display_name")
        or value.get("name")
        or value.get("id")
        or path.parent.name,
        node_id=f"carrier:{value.get('id', stable_id('anon', path))}",
        scope=str(path.parent),
        metadata={
            "carrier_kind": carrier_kind,
            "manifest_schema": schema,
            "status": value.get("status"),
            "entrypoints": value.get("entrypoints", {}),
            "surfaces": value.get("surfaces", []),
            "encapsulation": value.get("encapsulation", "unproven"),
        },
    )
    store.add_edge(root_id, "contains", carrier_id, evidence_id=evidence_id)
    stats["nodes"] += 1
    stats["edges"] += 1
    for capability in value.get("provides", []):
        function_id = store.add_node(
            "function",
            capability,
            node_id=f"function:{capability}",
            metadata={"desired": False},
        )
        store.add_edge(
            carrier_id,
            "carries",
            function_id,
            mode="actual",
            status="declared",
            confidence=0.75,
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 1
    entrypoints = value.get("entrypoints", {})
    if not isinstance(entrypoints, dict):
        entrypoints = {}
    for name, target in entrypoints.items():
        entry_id = store.add_node(
            "entrypoint",
            name,
            scope=str(path.parent),
            metadata={"target": target, "carrier": carrier_id},
        )
        store.add_edge(carrier_id, "enters_at", entry_id, evidence_id=evidence_id)
        stats["nodes"] += 1
        stats["edges"] += 1
    for surface in value.get("surfaces", []):
        item = surface if isinstance(surface, dict) else {"name": str(surface)}
        name = str(item.get("name") or item.get("id") or "surface")
        interface_id = store.add_node(
            "interface",
            name,
            node_id=f"interface:{stable_id(carrier_id, name)}",
            scope=str(path.parent),
            metadata={**item, "interface_kind": "surface"},
        )
        store.add_edge(
            carrier_id,
            "exposes_interface",
            interface_id,
            status="declared",
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 1
    for index, output in enumerate(value.get("outputs", []), start=1):
        item = output if isinstance(output, dict) else {"name": str(output)}
        name = str(item.get("name") or item.get("id") or f"output-{index}")
        output_id = store.add_node(
            "output",
            name,
            node_id=f"output:{stable_id(carrier_id, name)}",
            scope=str(path.parent),
            metadata=dict(item),
        )
        store.add_edge(
            carrier_id,
            "produces",
            output_id,
            status="declared",
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 1
        for consumer in item.get("consumers", []):
            consumer_id = _declared_carrier(str(consumer), store)
            store.add_edge(
                output_id,
                "delivers_to",
                consumer_id,
                status="declared",
                evidence_id=evidence_id,
            )
            stats["nodes"] += 1
            stats["edges"] += 1
    for index, handoff in enumerate(value.get("handoffs", []), start=1):
        item = handoff if isinstance(handoff, dict) else {"target": str(handoff)}
        name = str(item.get("name") or item.get("purpose") or f"handoff-{index}")
        handoff_id = store.add_node(
            "handoff",
            name,
            node_id=f"module-handoff:{stable_id(carrier_id, name)}",
            scope=str(path.parent),
            metadata={**item, "handoff_kind": "module"},
        )
        store.add_edge(
            carrier_id,
            "hands_off",
            handoff_id,
            status="declared",
            evidence_id=evidence_id,
        )
        target = item.get("target")
        if target:
            target_id = _declared_carrier(str(target), store)
            store.add_edge(
                handoff_id,
                "assigned_to",
                target_id,
                status="declared",
                evidence_id=evidence_id,
            )
            stats["nodes"] += 1
            stats["edges"] += 1
        stats["nodes"] += 1
        stats["edges"] += 1
    for alternative in value.get("alternative_paths", []):
        item = (
            alternative
            if isinstance(alternative, dict)
            else {"target": str(alternative)}
        )
        target = item.get("target")
        if not target:
            continue
        target_id = _declared_carrier(str(target), store)
        store.add_edge(
            carrier_id,
            "alternative_to",
            target_id,
            status="declared",
            evidence_id=evidence_id,
            metadata=dict(item),
        )
        stats["nodes"] += 1
        stats["edges"] += 1


def _declared_carrier(name: str, store: Store) -> str:
    node_id = name if name.startswith("carrier:") else f"carrier:{name}"
    store.add_node(
        "carrier",
        name.removeprefix("carrier:"),
        node_id=node_id,
        metadata={"carrier_kind": "declared-reference"},
    )
    return node_id


def _scan_skill(
    path: Path, root_id: str, evidence_id: str, store: Store, stats: dict[str, int]
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = FRONTMATTER_RE.match(text)
    metadata = _simple_frontmatter(match.group(1) if match else "")
    name = metadata.get("name") or path.parent.name
    carrier_id = store.add_node(
        "carrier",
        name,
        node_id=f"carrier:skill:{name}",
        scope=str(path.parent),
        metadata={
            "carrier_kind": "skill",
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
        },
    )
    store.add_edge(root_id, "contains", carrier_id, evidence_id=evidence_id)
    stats["nodes"] += 1
    stats["edges"] += 1
    for tag in metadata.get("tags", []):
        function_name = f"skill.{str(tag).strip().lower().replace(' ', '-')}"
        function_id = store.add_node(
            "function", function_name, node_id=f"function:{function_name}"
        )
        store.add_edge(
            carrier_id,
            "carries",
            function_id,
            status="inferred",
            confidence=0.5,
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 1


def _scan_document_pointers(
    path: Path,
    source_id: str,
    source_role: str | None,
    evidence_id: str,
    config: dict[str, Any],
    store: Store,
    stats: dict[str, int],
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    targets = _extract_document_refs(text)
    seen: set[tuple[str, int | None]] = set()
    for raw_target, line, syntax in targets:
        target = raw_target.strip().strip("<>").split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "#")):
            continue
        key = (target.casefold(), line)
        if key in seen:
            continue
        seen.add(key)
        resolved = _resolve_reference(path.parent, target)
        exists = resolved is not None and resolved.exists()
        if exists and resolved:
            target_role, _ = document_role(resolved, config)
            target_id = store.add_node(
                document_node_type(target_role),
                resolved.name,
                node_id=stable_id("path", str(resolved.resolve())),
                scope=str(resolved.parent),
                metadata={
                    "path": str(resolved),
                    "uri": resolved.as_uri(),
                    "document_role": target_role,
                    "pointer_target": True,
                },
            )
        else:
            target_id = store.add_node(
                "artifact_reference",
                Path(target).name or target,
                node_id=stable_id("reference", str(path.parent), target),
                scope=str(path.parent),
                metadata={"target": target, "resolved": False},
            )
        store.add_edge(
            source_id,
            "points_to"
            if source_role in {"control", "entrypoint"}
            else "references",
            target_id,
            status="declared",
            confidence=0.85 if exists else 0.55,
            evidence_id=evidence_id,
            metadata={
                "target": target,
                "resolved": exists,
                "line": line,
                "syntax": syntax,
            },
        )
        stats["nodes"] += 1
        stats["edges"] += 1


def _simple_frontmatter(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            result[key.strip()] = [
                item.strip() for item in value[1:-1].split(",") if item.strip()
            ]
        else:
            result[key.strip()] = value.strip("\"'")
    return result


def _source_kind(path: Path, role: str | None) -> str:
    if path.name in MANIFEST_NAMES or _is_schema_manifest(path):
        return "manifest"
    if role:
        return f"document:{role}"
    if path.name in ENTRY_NAMES:
        return "entrypoint"
    if path.suffix.lower() in {".md", ".txt"}:
        return "documentation"
    return "file"


def _is_schema_manifest(path: Path) -> bool:
    if path.suffix.lower() != ".json" or path.stat().st_size > 2_000_000:
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and (
        value.get("schema") in MANIFEST_SCHEMAS
        or (
            isinstance(value.get("schema"), str)
            and value["schema"].startswith(("ellmos.module.", "ellmos.stack."))
        )
    )


def document_role(
    path: Path, config: dict[str, Any]
) -> tuple[str | None, bool]:
    for item in config.get("control_documents", []):
        pattern = item if isinstance(item, str) else item.get("pattern", "")
        if pattern and (
            fnmatch.fnmatch(path.name.casefold(), pattern.casefold())
            or fnmatch.fnmatch(str(path).casefold(), pattern.casefold())
        ):
            role = (
                "control" if isinstance(item, str) else item.get("role", "control")
            )
            entry = (
                True if isinstance(item, str) else bool(item.get("entry", False))
            )
            return role, entry
    value = "/".join(part.casefold() for part in path.parts)
    name = path.name.casefold()
    rules = (
        ("policy", ("policy", "policies", "rules")),
        ("decision", ("decision", "decisions", "adr-", "adr_")),
        ("memory", ("memory", "preferences", "preference")),
        ("runtime-log", ("log", "receipt", "runbook")),
        (
            "architecture",
            ("architecture", "ontology", "system-manifest", "manifest"),
        ),
        ("cloud-readiness", ("cloud", "deployment", "hosting", "readiness")),
        (
            "control",
            ("agents.md", "claude.md", "gpt.md", "gemini.md", "kimi.md"),
        ),
        ("documentation", ("readme.md", "docs", "documentation")),
    )
    for role, needles in rules:
        if any(needle in name or f"/{needle}/" in value for needle in needles):
            return role, role == "control"
    return None, False


def document_node_type(role: str | None) -> str:
    return {
        "control": "control_document",
        "entrypoint": "control_document",
        "policy": "policy_document",
        "decision": "decision_document",
        "memory": "memory_document",
        "runtime-log": "runtime_document",
    }.get(role or "", "documentation" if role else "artifact")


def _extract_document_refs(text: str) -> list[tuple[str, int | None, str]]:
    result: list[tuple[str, int | None, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in LINK_RE.finditer(line):
            result.append((match.group(1), line_number, "markdown-link"))
        for match in QUOTED_REF_RE.finditer(line):
            result.append((match.group(1), line_number, "quoted-path"))
        for match in BARE_REF_RE.finditer(line):
            result.append((match.group(0), line_number, "bare-path"))
        for match in WINDOWS_DOC_RE.finditer(line):
            result.append((match.group(0), line_number, "windows-path"))
        for match in QUOTED_DIRECTORY_RE.finditer(line):
            result.append((match.group(1), line_number, "quoted-directory"))
    return result


def _resolve_reference(parent: Path, value: str) -> Path | None:
    cleaned = os.path.expandvars(os.path.expanduser(value.strip()))
    try:
        path = Path(cleaned)
        return path.resolve() if path.is_absolute() else (parent / path).resolve()
    except (OSError, ValueError):
        return None


def _matches_directory_spec(
    path: Path, root: Path, specs: list[Any]
) -> bool:
    relative = str(path.relative_to(root))
    for item in specs:
        pattern = (
            item
            if isinstance(item, str)
            else item.get("path") or item.get("pattern", "")
        )
        if not pattern:
            continue
        if fnmatch.fnmatch(relative.casefold(), pattern.casefold()):
            return True
        expanded = Path(os.path.expandvars(os.path.expanduser(pattern)))
        if expanded.is_absolute() and path == expanded.resolve():
            return True
    return False


def _entry_kind(name: str) -> str:
    if name == "SKILL.md":
        return "skill"
    if name == "START.md":
        return "workflow"
    if name == "llms.txt":
        return "llm-index"
    return "provider-boot"
