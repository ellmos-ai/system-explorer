from __future__ import annotations

from collections import defaultdict
from typing import Any

from .store import Store


POSITIVE = {"full", "partial", "declared", "inferred", "observed", "fulfilled"}


def coverage_report(store: Store) -> dict[str, Any]:
    nodes = {node["id"]: node for node in store.nodes()}
    functions = {
        node_id: node for node_id, node in nodes.items() if node["node_type"] == "function"
    }
    edges = [
        edge
        for edge in store.resolved_edges()
        if edge["relation"] == "carries" and edge["target_id"] in functions
    ]
    by_function: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        by_function[edge["target_id"]].append(edge)

    rows = []
    totals = defaultdict(int)
    for function_id, function in sorted(functions.items(), key=lambda item: item[1]["name"]):
        carriers = by_function.get(function_id, [])
        desired = [edge for edge in carriers if edge["mode"] == "desired"]
        actual = [edge for edge in carriers if edge["mode"] == "actual"]
        statuses = {edge["status"] for edge in actual}
        if "negative" in statuses or "contradicted" in statuses:
            verdict = "negative"
        elif any(status in {"full", "fulfilled"} for status in statuses):
            verdict = "full"
        elif statuses & POSITIVE:
            verdict = "partial"
        elif desired:
            verdict = "uncovered"
        else:
            verdict = "unproven"
        active_carriers = {
            edge["source_id"]
            for edge in actual
            if edge["status"] not in {"negative", "contradicted", "uncovered"}
        }
        overlap = len(active_carriers) > 1
        if overlap and verdict in {"full", "partial"}:
            totals["overlap"] += 1
        totals[verdict] += 1
        unique_carriers = {
            edge["source_id"]: nodes.get(edge["source_id"], {"id": edge["source_id"]})
            for edge in carriers
        }
        rows.append(
            {
                "function": function,
                "verdict": verdict,
                "overlap": overlap,
                "desired": desired,
                "actual": actual,
                "carriers": list(unique_carriers.values()),
            }
        )
    return {"summary": dict(totals), "functions": rows}
