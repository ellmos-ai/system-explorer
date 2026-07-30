from __future__ import annotations

from collections import defaultdict
from typing import Any

from .store import Store


POSITIVE = {"full", "partial", "declared", "inferred", "observed", "fulfilled"}
REQUIREMENT_ORDER = ("required", "recommended", "optional", "unspecified")
GAP_VERDICTS = {"uncovered", "unproven", "partial", "negative"}


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
    desired_totals: dict[str, dict[str, int]] = {
        requirement: defaultdict(int) for requirement in REQUIREMENT_ORDER
    }
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
        desired_carriers = {edge["source_id"] for edge in desired}
        desired_overlap = len(desired_carriers) > 1
        if desired_overlap:
            totals["desired_overlap"] += 1
        desired_requirements = sorted(
            {
                requirement
                for edge in desired
                for requirement in _edge_requirements(edge)
            },
            key=_requirement_sort_key,
        )
        effective_requirement = (
            desired_requirements[0] if desired_requirements else "unspecified"
        )
        gap_class = _gap_class(effective_requirement, verdict) if desired else "none"
        if desired:
            requirement_totals = desired_totals[effective_requirement]
            requirement_totals["functions"] += 1
            requirement_totals[verdict] += 1
            if gap_class != "none":
                requirement_totals["gaps"] += 1
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
                "desired_overlap": desired_overlap,
                "desired_requirements": desired_requirements,
                "effective_requirement": effective_requirement,
                "gap_class": gap_class,
                "desired": desired,
                "actual": actual,
                "carriers": list(unique_carriers.values()),
            }
        )
    desired_rows = [row for row in rows if row["desired"]]
    actual_rows = [row for row in rows if row["actual"]]
    desired_summary = {
        "functions": len(desired_rows),
        "provider_edges": sum(len(row["desired"]) for row in desired_rows),
        "duplicate_provider_functions": sum(
            1 for row in desired_rows if row["desired_overlap"]
        ),
        "hard_gaps": sum(1 for row in desired_rows if row["gap_class"] == "hard"),
        "advisory_gaps": sum(
            1 for row in desired_rows if row["gap_class"] == "advisory"
        ),
        "optional_gaps": sum(
            1 for row in desired_rows if row["gap_class"] == "optional"
        ),
        "unclassified_gaps": sum(
            1 for row in desired_rows if row["gap_class"] == "unclassified"
        ),
        "requirements": {
            requirement: dict(desired_totals[requirement])
            for requirement in REQUIREMENT_ORDER
        },
    }
    discovery_summary = {
        "functions": len(rows),
        "carrier_nodes": sum(
            1 for node in nodes.values() if node["node_type"] == "carrier"
        ),
        "desired_functions": len(desired_rows),
        "actual_functions": len(actual_rows),
        "desired_provider_edges": desired_summary["provider_edges"],
        "actual_provider_edges": sum(len(row["actual"]) for row in actual_rows),
        "verdicts": dict(totals),
    }
    return {
        "summary": dict(totals),
        "discovery_summary": discovery_summary,
        "desired_summary": desired_summary,
        "functions": rows,
    }


def _edge_requirements(edge: dict[str, Any]) -> set[str]:
    metadata = edge.get("metadata", {})
    values = metadata.get("requirements")
    if isinstance(values, list):
        requirements = {
            value for value in values if value in REQUIREMENT_ORDER[:-1]
        }
        if requirements:
            return requirements
    requirement = metadata.get("requirement")
    return {requirement} if requirement in REQUIREMENT_ORDER[:-1] else set()


def _requirement_sort_key(requirement: str) -> int:
    return REQUIREMENT_ORDER.index(requirement)


def _gap_class(requirement: str, verdict: str) -> str:
    if verdict not in GAP_VERDICTS:
        return "none"
    return {
        "required": "hard",
        "recommended": "advisory",
        "optional": "optional",
        "unspecified": "unclassified",
    }[requirement]
