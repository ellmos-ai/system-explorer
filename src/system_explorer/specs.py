from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import Store
from .util import file_effective_date, sha256_file


VALID_COVERAGE = {
    "full",
    "partial",
    "negative",
    "contradicted",
    "uncovered",
    "unproven",
    "declared",
    "observed",
    "fulfilled",
}


def import_spec(path: Path, store: Store) -> dict[str, int]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "system-explorer.desired.v1":
        raise ValueError("Unsupported desired-state schema")
    digest = sha256_file(path)
    effective_at = value.get("effective_at") or file_effective_date(path)
    evidence_id = store.add_evidence(
        uri=path.resolve().as_uri(),
        source_kind="desired-spec",
        sha256=digest,
        effective_at=effective_at,
        modified_at=str(path.stat().st_mtime),
        confidence=float(value.get("confidence", 1.0)),
        sensitivity=value.get("sensitivity", "user-local"),
        metadata={"schema": value["schema"], "system": value.get("system")},
    )
    stats = {
        "functions": 0,
        "carriers": 0,
        "coverage": 0,
        "observations": 0,
        "structure": 0,
    }
    for item in value.get("functions", []):
        store.add_node(
            "function",
            item["name"],
            node_id=f"function:{item['id']}",
            scope=value.get("system"),
            metadata={
                "desired": True,
                "description": item.get("description", ""),
                "priority": item.get("priority", "normal"),
            },
        )
        stats["functions"] += 1
    for item in value.get("carriers", []):
        store.add_node(
            "carrier",
            item["name"],
            node_id=f"carrier:{item['id']}",
            scope=value.get("system"),
            metadata={
                "carrier_kind": item["kind"],
                "desired": True,
                **item.get("metadata", {}),
            },
        )
        stats["carriers"] += 1
    for item in value.get("coverage", []):
        _add_coverage(item, "desired", evidence_id, effective_at, store)
        stats["coverage"] += 1
    for item in value.get("observations", []):
        _add_coverage(item, "actual", evidence_id, effective_at, store)
        stats["observations"] += 1
    for item in value.get("structure", []):
        source_id = _qualified_id(item["source"])
        target_id = _qualified_id(item["target"])
        _ensure_structure_node(source_id, value.get("system"), store)
        _ensure_structure_node(target_id, value.get("system"), store)
        store.add_edge(
            source_id,
            item["relation"],
            target_id,
            mode="desired",
            status=item.get("status", "required"),
            confidence=float(item.get("confidence", 1.0)),
            evidence_id=evidence_id,
            effective_at=effective_at,
        )
        stats["structure"] += 1
    store.commit()
    return stats


def desired_template() -> dict[str, Any]:
    return {
        "schema": "system-explorer.desired.v1",
        "system": "example-system",
        "effective_at": "2026-01-01T00:00:00+00:00",
        "confidence": 1.0,
        "functions": [
            {
                "id": "knowledge.search",
                "name": "Search existing knowledge before acting",
                "description": "Agents can retrieve relevant prior evidence.",
                "priority": "high",
            }
        ],
        "carriers": [
            {"id": "knowledge-provider", "name": "Knowledge provider", "kind": "module"}
        ],
        "coverage": [
            {
                "function": "knowledge.search",
                "carrier": "knowledge-provider",
                "status": "full",
                "confidence": 1.0,
            }
        ],
        "observations": [],
        "structure": [],
    }


def _qualified_id(value: str) -> str:
    if ":" in value:
        return value
    return f"carrier:{value}"


def _add_coverage(
    item: dict[str, Any],
    mode: str,
    evidence_id: str,
    effective_at: str | None,
    store: Store,
) -> None:
    status = item.get("status", "full" if mode == "desired" else "observed")
    if status not in VALID_COVERAGE:
        raise ValueError(f"Unsupported coverage status: {status}")
    function_id = f"function:{item['function']}"
    carrier_id = f"carrier:{item['carrier']}"
    if not any(node["id"] == function_id for node in store.nodes("function")):
        store.add_node("function", item["function"], node_id=function_id)
    if not any(node["id"] == carrier_id for node in store.nodes("carrier")):
        store.add_node(
            "carrier",
            item["carrier"],
            node_id=carrier_id,
            metadata={"carrier_kind": item.get("carrier_kind", "unknown")},
        )
    store.add_edge(
        carrier_id,
        "carries",
        function_id,
        mode=mode,
        status=status,
        confidence=float(item.get("confidence", 1.0)),
        evidence_id=evidence_id,
        effective_at=item.get("effective_at") or effective_at,
        metadata={
            "requirement": item.get("requirement"),
            "overlap_group": item.get("overlap_group"),
            "notes": item.get("notes"),
            "method": item.get("method", "manual-spec"),
        },
    )


def _ensure_structure_node(node_id: str, scope: str | None, store: Store) -> None:
    if any(node["id"] == node_id for node in store.nodes()):
        return
    prefix, _, name = node_id.partition(":")
    node_type = prefix if prefix in {"function", "system", "entrypoint", "actor"} else "carrier"
    store.add_node(
        node_type,
        name or node_id,
        node_id=node_id,
        scope=scope,
        metadata={"desired": True, "placeholder": True},
    )
