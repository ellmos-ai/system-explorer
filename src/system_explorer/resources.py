from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .store import Store
from .util import expand_path, sha256_file, stable_id


READINESS = {
    "native": {"symbol": "◆", "rank": 4},
    "direct": {"symbol": "◇", "rank": 3},
    "indirect": {"symbol": "△", "rank": 2},
    "reference": {"symbol": "○", "rank": 1},
    "unproven": {"symbol": "?", "rank": 0},
}
NATIVE_METHODS = {"mcp", "tool-api", "structured-api", "openapi"}
DIRECT_METHODS = {"cli", "library", "sdk", "ipc", "file-protocol"}
INDIRECT_METHODS = {"browser", "gui", "computer-use", "rpa"}
REFERENCE_METHODS = {"documentation", "manual"}


def register_software_resources(
    config: dict[str, Any], store: Store
) -> dict[str, int]:
    stats = {
        "software_resources": 0,
        "software_interfaces": 0,
        "software_functions": 0,
        "installed_observed": 0,
        "installed_missing": 0,
    }
    base = Path(config.get("_base", "."))
    for item in config.get("software_resources", []):
        _register_resource(item, base, store, stats)
    for item in config.get("software_discovery", {}).get("commands", []):
        value = item if isinstance(item, dict) else {"id": str(item), "command": str(item)}
        value = {
            "kind": "external-program",
            "origin": "third-party",
            "interfaces": [{"method": "cli", "entrypoint": value.get("command", value["id"])}],
            **value,
        }
        _register_resource(value, base, store, stats)
    store.commit()
    return stats


def resource_report(store: Store) -> dict[str, Any]:
    resources = store.nodes("software_resource")
    summary: dict[str, int] = {}
    rows = []
    edges = store.resolved_edges()
    nodes = {node["id"]: node for node in store.nodes()}
    for resource in resources:
        readiness = resource.get("metadata", {}).get("llm_readiness", "unproven")
        summary[readiness] = summary.get(readiness, 0) + 1
        interfaces = [
            nodes[edge["target_id"]]
            for edge in edges
            if edge["source_id"] == resource["id"]
            and edge["relation"] == "exposes_interface"
            and edge["target_id"] in nodes
        ]
        functions = [
            nodes[edge["target_id"]]
            for edge in edges
            if edge["source_id"] == resource["id"]
            and edge["relation"] == "carries"
            and edge["target_id"] in nodes
        ]
        rows.append(
            {
                "resource": resource,
                "interfaces": interfaces,
                "functions": functions,
                "token_saving": resource["metadata"].get(
                    "token_saving", {"status": "unproven"}
                ),
            }
        )
    return {"resources": rows, "summary": summary, "symbols": READINESS}


def resource_graph(store: Store) -> dict[str, Any]:
    all_nodes = {node["id"]: node for node in store.nodes()}
    selected = {
        node_id
        for node_id, node in all_nodes.items()
        if node["node_type"] in {"software_resource", "interface", "function", "actor"}
        or (
            node["node_type"] == "carrier"
            and node.get("metadata", {}).get("carrier_kind")
            in {"skill", "module", "repository", "mcp", "stack", "script"}
        )
    }
    relations = {
        "carries",
        "exposes_interface",
        "controls_via",
        "generated_by",
        "alternative_to",
    }
    edges = [
        edge
        for edge in store.resolved_edges()
        if edge["relation"] in relations
        and edge["source_id"] in selected
        and edge["target_id"] in selected
    ]
    connected = {
        node_id
        for edge in edges
        for node_id in (edge["source_id"], edge["target_id"])
    }
    return {
        "nodes": [
            all_nodes[node_id]
            for node_id in selected
            if node_id in connected
            or all_nodes[node_id]["node_type"] == "software_resource"
        ],
        "edges": edges,
        "view": "resources",
        "report": resource_report(store),
    }


def _register_resource(
    item: dict[str, Any],
    base: Path,
    store: Store,
    stats: dict[str, int],
) -> str:
    key = str(item["id"])
    interfaces = [
        interface
        if isinstance(interface, dict)
        else {"method": str(interface)}
        for interface in item.get("interfaces", [])
    ]
    readiness = _readiness(interfaces)
    installed, resolved_path, evidence_id = _installation_evidence(item, base, store)
    kind = item.get("kind", "external-program")
    flexibility = item.get(
        "flexibility",
        "high" if kind == "skill" else "medium" if kind == "script" else "low",
    )
    token_saving = item.get("token_saving", {})
    if isinstance(token_saving, bool):
        token_saving = {
            "status": "declared" if token_saving else "not-declared",
            "level": "unproven",
        }
    token_saving = {
        "status": token_saving.get("status", "unproven"),
        "level": token_saving.get("level", "unproven"),
        "basis": token_saving.get(
            "basis", "stable endpoint may replace repeated reasoning"
        ),
    }
    resource_id = f"software:{key}"
    store.add_node(
        "software_resource",
        item.get("name", key),
        node_id=resource_id,
        scope=resolved_path or item.get("scope"),
        metadata={
            **{
                field: value
                for field, value in item.items()
                if field not in {"interfaces", "functions"}
            },
            "resource_layer": "peripheral",
            "resource_kind": kind,
            "origin": item.get("origin", "unknown"),
            "installed": installed,
            "resolved_path": resolved_path,
            "crystallized_intelligence": item.get("crystallization", "high"),
            "flexibility": flexibility,
            "llm_readiness": readiness,
            "llm_ready_symbol": READINESS[readiness]["symbol"],
            "token_saving": token_saving,
        },
    )
    stats["software_resources"] += 1
    stats["installed_observed" if installed else "installed_missing"] += 1
    for index, interface in enumerate(interfaces, start=1):
        method = str(interface.get("method", "unproven")).lower()
        interface_id = f"software-interface:{stable_id(key, method, str(index))}"
        store.add_node(
            "interface",
            interface.get("name", method),
            node_id=interface_id,
            scope=resource_id,
            metadata={
                **interface,
                "control_method": method,
                "structured": method in NATIVE_METHODS,
                "credential_value_retained": False,
            },
        )
        store.add_edge(
            resource_id,
            "exposes_interface",
            interface_id,
            status="observed" if installed else "declared",
            evidence_id=evidence_id,
        )
        for actor in interface.get("actors", []):
            actor_value = (
                actor if isinstance(actor, dict) else {"id": str(actor)}
            )
            actor_key = str(actor_value["id"])
            actor_id = f"actor:{actor_key}"
            store.add_node(
                "actor",
                actor_value.get("name", actor_key),
                node_id=actor_id,
                metadata={
                    "provider": actor_value.get("provider"),
                    "resource_controller": True,
                },
            )
            store.add_edge(
                actor_id,
                "controls_via",
                interface_id,
                status="declared",
                evidence_id=evidence_id,
            )
        stats["software_interfaces"] += 1
    for function in item.get("functions", []):
        value = function if isinstance(function, dict) else {"id": str(function)}
        function_key = str(value["id"])
        function_id = f"function:{function_key}"
        store.add_node(
            "function",
            value.get("name", function_key),
            node_id=function_id,
            metadata={"resource_function": True},
        )
        store.add_edge(
            resource_id,
            "carries",
            function_id,
            mode="actual",
            status=(
                value.get("status", "observed")
                if installed
                else value.get("missing_status", "unproven")
            ),
            evidence_id=evidence_id,
        )
        stats["software_functions"] += 1
    generated_by = item.get("generated_by")
    if generated_by:
        actor_id = f"actor:{generated_by}"
        store.add_node(
            "actor",
            str(generated_by),
            node_id=actor_id,
            metadata={"provider": item.get("generated_by_provider")},
        )
        store.add_edge(
            resource_id,
            "generated_by",
            actor_id,
            status="declared",
            evidence_id=evidence_id,
        )
    return resource_id


def _installation_evidence(
    item: dict[str, Any], base: Path, store: Store
) -> tuple[bool, str | None, str | None]:
    command = item.get("command")
    path_value = item.get("path")
    resolved: Path | None = None
    source_kind = "software-declaration"
    if command:
        found = shutil.which(str(command))
        resolved = Path(found).resolve() if found else None
        source_kind = "command-resolution"
    elif path_value:
        candidate = expand_path(str(path_value), base)
        resolved = candidate.resolve() if candidate.exists() else None
        source_kind = "path-resolution"
    installed = resolved is not None
    if not installed:
        return False, None, None
    digest = None
    hash_status = "not-a-file"
    try:
        if resolved.is_file():
            digest = sha256_file(resolved)
            hash_status = "observed"
    except OSError:
        hash_status = "unavailable"
    evidence_id = store.add_evidence(
        uri=resolved.as_uri(),
        source_kind=source_kind,
        sha256=digest,
        sensitivity="user-local",
        metadata={
            "software_id": item["id"],
            "installed_observed": True,
            "content_retained": False,
            "hash_status": hash_status,
        },
    )
    return True, str(resolved), evidence_id


def _readiness(interfaces: list[dict[str, Any]]) -> str:
    methods = {str(item.get("method", "")).lower() for item in interfaces}
    if methods & NATIVE_METHODS:
        return "native"
    if methods & DIRECT_METHODS:
        return "direct"
    if methods & INDIRECT_METHODS:
        return "indirect"
    if methods & REFERENCE_METHODS:
        return "reference"
    return "unproven"
