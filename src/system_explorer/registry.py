from __future__ import annotations

from pathlib import Path
from typing import Any

from .scanner import _scan_document_pointers, document_node_type
from .store import Store
from .util import file_effective_date, sha256_file, stable_id


DOCUMENT_NODE_TYPES = {
    "control_document",
    "policy_document",
    "decision_document",
    "memory_document",
    "runtime_document",
    "documentation",
}
DOCUMENT_ROLES = {
    "control",
    "policy",
    "decision",
    "documentation",
    "memory",
    "runtime-log",
    "architecture",
    "cloud-readiness",
    "entry",
}


def register_path(
    path: Path,
    role: str,
    store: Store,
    *,
    config: dict[str, Any],
    name: str | None = None,
    entry: bool = False,
) -> dict[str, Any]:
    if role not in DOCUMENT_ROLES:
        raise ValueError(f"unsupported document role: {role}")
    path = path.resolve()
    if not path.exists():
        raise ValueError(f"path does not exist: {path}")
    if path.is_dir():
        node_id = store.add_node(
            "directory",
            name or path.name,
            node_id=stable_id("directory", str(path)),
            scope=str(path.parent),
            metadata={
                "path": str(path),
                "entry_directory": entry or role == "entry",
                "document_role": role,
                "registered_interactively": True,
            },
        )
        if entry or role == "entry":
            entry_id = store.add_node(
                "entrypoint",
                name or path.name,
                node_id=stable_id("entry-directory", str(path)),
                scope=str(path.parent),
                metadata={"path": str(path), "entry_kind": "directory"},
            )
            store.add_edge(
                entry_id, "points_to", node_id, status="user-registered"
            )
    else:
        evidence_id = store.add_evidence(
            uri=path.as_uri(),
            source_kind=f"document:{role}:interactive",
            sha256=sha256_file(path),
            effective_at=file_effective_date(path),
            modified_at=str(path.stat().st_mtime),
            sensitivity=config.get("privacy", {}).get(
                "sensitivity", "user-local"
            ),
            metadata={"registered_interactively": True, "document_role": role},
        )
        node_id = store.add_node(
            document_node_type(role),
            name or path.name,
            node_id=stable_id("path", str(path)),
            scope=str(path.parent),
            metadata={
                "path": str(path),
                "uri": path.as_uri(),
                "document_role": role,
                "important_system_document": True,
                "registered_interactively": True,
            },
        )
        if entry or role == "control":
            entry_id = store.add_node(
                "entrypoint",
                name or path.name,
                node_id=stable_id("entry-file", str(path)),
                scope=str(path.parent),
                metadata={"path": str(path), "entry_kind": "user-defined"},
            )
            store.add_edge(
                entry_id,
                "points_to",
                node_id,
                status="user-registered",
                evidence_id=evidence_id,
            )
        if path.suffix.casefold() in {".md", ".txt"} and path.stat().st_size <= 2_000_000:
            stats = {"nodes": 0, "edges": 0}
            _scan_document_pointers(
                path,
                node_id,
                role,
                evidence_id,
                config,
                store,
                stats,
            )
    store.commit()
    return {
        "id": node_id,
        "path": str(path),
        "role": role,
        "entry": entry or role in {"control", "entry"},
    }


def find_documents(
    store: Store, *, role: str | None = None, name: str | None = None
) -> list[dict[str, Any]]:
    needle = (name or "").casefold()
    result = []
    for node in store.nodes():
        if node["node_type"] not in DOCUMENT_NODE_TYPES:
            continue
        node_role = node.get("metadata", {}).get("document_role")
        if role and node_role != role:
            continue
        if needle and needle not in node["name"].casefold() and needle not in str(
            node.get("metadata", {}).get("path", "")
        ).casefold():
            continue
        result.append(node)
    return result
