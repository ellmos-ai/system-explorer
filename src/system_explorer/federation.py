from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import Store
from .util import expand_path, sha256_file, stable_id, utc_now


MAP_SCHEMA = "system-explorer.map.v1"


def export_system_map(
    store: Store,
    *,
    system: dict[str, Any],
    view: str = "all",
) -> dict[str, Any]:
    from .maps import graph_view

    system_id = str(system["id"])
    if view == "all":
        graph = _filter_origin(store.graph(), system_id)
    else:
        graph = graph_view(store, view, system_id=system_id)
    nodes = []
    for node in graph["nodes"]:
        copied = dict(node)
        copied["metadata"] = {
            **copied.get("metadata", {}),
            "origin_system": system_id,
            "map_level": system.get("level", "own-system"),
        }
        nodes.append(copied)
    evidence_ids = {
        edge.get("evidence_id")
        for edge in graph["edges"]
        if edge.get("evidence_id")
    }
    evidence = [
        item for item in store.evidence() if item["id"] in evidence_ids
    ]
    return {
        "schema": MAP_SCHEMA,
        "generated_at": utc_now(),
        "system": {
            "id": system_id,
            "name": system.get("name", system_id),
            "kind": system.get("kind", "workstation"),
            "level": system.get("level", "own-system"),
        },
        "view": view,
        "nodes": nodes,
        "edges": graph["edges"],
        "evidence_references": evidence,
        "privacy": {
            "raw_evidence_included": False,
            "credential_values_included": False,
        },
    }


def import_system_map(path: Path, store: Store) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != MAP_SCHEMA:
        raise ValueError(f"Unsupported map schema: {value.get('schema')}")
    privacy = value.get("privacy", {})
    if privacy.get("raw_evidence_included") is not False:
        raise ValueError("Map must declare raw_evidence_included=false")
    if privacy.get("credential_values_included") is not False:
        raise ValueError("Map must declare credential_values_included=false")
    system = value.get("system", {})
    if not isinstance(system, dict) or not system.get("id"):
        raise ValueError("Map system.id is required")
    system_key = str(system["id"])
    instance_id = f"system-instance:{system_key}"
    evidence_id = store.add_evidence(
        uri=path.resolve().as_uri(),
        source_kind="system-map-export",
        sha256=sha256_file(path),
        effective_at=value.get("generated_at"),
        sensitivity="user-local",
        metadata={"schema": MAP_SCHEMA, "source_system": system_key},
    )
    imported_evidence: dict[str, str] = {}
    for item in value.get("evidence_references", []):
        if not isinstance(item, dict) or not item.get("id") or not item.get("uri"):
            continue
        imported_evidence[str(item["id"])] = store.add_evidence(
            uri=str(item["uri"]),
            source_kind=f"imported:{item.get('source_kind', 'reference')}",
            sha256=item.get("sha256"),
            locator=item.get("locator"),
            effective_at=item.get("effective_at"),
            modified_at=item.get("modified_at"),
            confidence=float(item.get("confidence", 1.0)),
            sensitivity=item.get("sensitivity", "user-local"),
            metadata={
                **item.get("metadata", {}),
                "imported_from_map": str(path.resolve()),
                "original_evidence_id": item["id"],
            },
        )
    store.add_node(
        "system_instance",
        system.get("name", system_key),
        node_id=instance_id,
        metadata={
            **system,
            "imported": True,
            "source_map": str(path.resolve()),
            "map_symbol": _system_symbol(system.get("kind")),
        },
    )
    id_map: dict[str, str] = {}
    for node in value.get("nodes", []):
        if not isinstance(node, dict) or not node.get("id"):
            continue
        imported_id = f"federated:{system_key}:{stable_id(str(node['id']))}"
        id_map[str(node["id"])] = imported_id
        store.add_node(
            node.get("node_type", "unknown"),
            node.get("name", str(node["id"])),
            node_id=imported_id,
            scope=node.get("scope"),
            metadata={
                **node.get("metadata", {}),
                "origin_system": system_key,
                "original_node_id": node["id"],
                "imported": True,
                "map_level": system.get("level", "remote-system"),
            },
        )
        store.add_edge(
            instance_id,
            "maps",
            imported_id,
            status="imported",
            evidence_id=evidence_id,
        )
    imported_edges = 0
    for edge in value.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = id_map.get(str(edge.get("source_id")))
        target = id_map.get(str(edge.get("target_id")))
        if not source or not target:
            continue
        store.add_edge(
            source,
            edge.get("relation", "relates_to"),
            target,
            mode=edge.get("mode", "actual"),
            status=edge.get("status", "observed"),
            confidence=float(edge.get("confidence", 1.0)),
            evidence_id=imported_evidence.get(
                str(edge.get("evidence_id")), evidence_id
            ),
            metadata={**edge.get("metadata", {}), "imported": True},
        )
        imported_edges += 1
    store.add_node(
        "system_instance",
        system.get("name", system_key),
        node_id=instance_id,
        metadata={
            "map_node_count": len(id_map),
            "map_edge_count": imported_edges,
            "map_generated_at": value.get("generated_at"),
            "map_view": value.get("view"),
        },
    )
    store.commit()
    return {
        "system": system_key,
        "nodes": len(id_map),
        "edges": imported_edges,
        "evidence": evidence_id,
        "evidence_references": len(imported_evidence),
    }


def register_federation(config: dict[str, Any], store: Store) -> dict[str, int]:
    system = config.get("system", {})
    if not isinstance(system, dict) or not system.get("id"):
        return {
            "systems": 0,
            "connections": 0,
            "handoffs": 0,
            "map_imports": 0,
            "map_import_errors": 0,
        }
    own_id = f"system-instance:{system['id']}"
    store.add_node(
        "system_instance",
        system.get("name", system["id"]),
        node_id=own_id,
        metadata={
            **system,
            "imported": False,
            "map_symbol": _system_symbol(system.get("kind")),
        },
    )
    tag_current_system(config, store)
    stats = {
        "systems": 1,
        "connections": 0,
        "handoffs": 0,
        "map_imports": 0,
        "map_import_errors": 0,
    }
    base = Path(config.get("_base", "."))
    for item in config.get("map_imports", []):
        path_value = item.get("path") if isinstance(item, dict) else item
        if not path_value:
            continue
        path = expand_path(str(path_value), base)
        if not path.exists():
            stats["map_import_errors"] += 1
            continue
        try:
            import_system_map(path, store)
            stats["map_imports"] += 1
        except (OSError, ValueError, json.JSONDecodeError):
            stats["map_import_errors"] += 1
    for item in config.get("connections", []):
        source_id = _system_id(item.get("source", system["id"]), store)
        target_id = _system_id(item["target"], store)
        transport = item.get("transport", "unknown")
        connection_id = f"connection:{stable_id(source_id, target_id, transport)}"
        store.add_node(
            "system_connection",
            item.get("name", transport),
            node_id=connection_id,
            metadata={
                **item,
                "crosses_system_boundary": True,
                "direct": transport in {"ssh", "tailscale", "ssh+tailscale"},
            },
        )
        store.add_edge(source_id, "connects_via", connection_id, status=item.get("status", "declared"))
        store.add_edge(connection_id, "reaches", target_id, status=item.get("status", "declared"))
        stats["connections"] += 1
    for item in config.get("handoffs", []):
        source_id = _system_id(item.get("source", system["id"]), store)
        target_id = _system_id(item["target"], store)
        handoff_id = f"handoff:{stable_id(source_id, target_id, str(item.get('purpose', '')))}"
        store.add_node(
            "handoff",
            item.get("name", item.get("purpose", "cross-system task")),
            node_id=handoff_id,
            metadata={
                **item,
                "crosses_system_boundary": True,
                "requires_installed_carrier": item.get("via") == "system-gap-master",
            },
        )
        store.add_edge(source_id, "hands_off", handoff_id, status="declared")
        store.add_edge(handoff_id, "assigned_to", target_id, status="desired", mode="desired")
        stats["handoffs"] += 1
    tag_current_system(config, store)
    store.commit()
    return stats


def tag_current_system(config: dict[str, Any], store: Store) -> int:
    system = config.get("system", {})
    if not isinstance(system, dict) or not system.get("id"):
        return 0
    system_id = str(system["id"])
    count = 0
    for node in store.nodes():
        metadata = node.get("metadata", {})
        if metadata.get("origin_system") or metadata.get("imported"):
            continue
        if node["node_type"] == "system_instance" and node["id"] != f"system-instance:{system_id}":
            continue
        store.add_node(
            node["node_type"],
            node["name"],
            node_id=node["id"],
            scope=node.get("scope"),
            metadata={
                "origin_system": system_id,
                "map_level": system.get("level", "own-system"),
            },
        )
        count += 1
    store.commit()
    return count


def federation_graph(store: Store) -> dict[str, Any]:
    types = {"system_instance", "system_connection", "handoff"}
    relations = {"connects_via", "reaches", "hands_off", "assigned_to"}
    all_nodes = {node["id"]: node for node in store.nodes()}
    edges = [
        edge
        for edge in store.resolved_edges()
        if edge["relation"] in relations
    ]
    selected_ids = {
        node_id
        for node_id, node in all_nodes.items()
        if node["node_type"] in types
    }
    selected_ids |= {
        value for edge in edges for value in (edge["source_id"], edge["target_id"])
    }
    levels: dict[str, dict[str, Any]] = {}
    for node_id in selected_ids:
        node = all_nodes.get(node_id)
        if not node:
            continue
        origin = node.get("metadata", {}).get("origin_system")
        if node["node_type"] == "system_instance":
            origin = node["id"].split(":", 1)[1]
        if origin:
            levels.setdefault(
                str(origin),
                {
                    "id": str(origin),
                    "label": str(origin),
                    "kind": node.get("metadata", {}).get("kind"),
                },
            )
    return {
        "nodes": [all_nodes[item] for item in selected_ids if item in all_nodes],
        "edges": [
            edge
            for edge in edges
            if edge["source_id"] in selected_ids and edge["target_id"] in selected_ids
        ],
        "view": "federation",
        "levels": list(levels.values()),
    }


def _system_id(value: Any, store: Store) -> str:
    key = str(value)
    node_id = key if key.startswith("system-instance:") else f"system-instance:{key}"
    if node_id not in {node["id"] for node in store.nodes("system_instance")}:
        store.add_node(
            "system_instance",
            key,
            node_id=node_id,
            metadata={"id": key, "imported": False, "declared_only": True},
        )
    return node_id


def _system_symbol(kind: Any) -> str:
    return "☁" if kind in {"server", "cloud-server"} else "▣" if kind == "workstation" else "▱"


def _filter_origin(graph: dict[str, Any], system_id: str) -> dict[str, Any]:
    selected = {
        node["id"]
        for node in graph.get("nodes", [])
        if node.get("metadata", {}).get("origin_system") == system_id
        or node.get("id") == f"system-instance:{system_id}"
    }
    return {
        **graph,
        "nodes": [
            node for node in graph.get("nodes", []) if node["id"] in selected
        ],
        "edges": [
            edge
            for edge in graph.get("edges", [])
            if edge["source_id"] in selected and edge["target_id"] in selected
        ],
    }
