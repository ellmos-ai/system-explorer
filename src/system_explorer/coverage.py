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
    for function_id, function in sorted(functions.items(), key=lambda item: item[1]["name"]):
        carriers = by_function.get(function_id, [])
        desired = [edge for edge in carriers if edge["mode"] == "desired"]
        actual = [edge for edge in carriers if edge["mode"] == "actual"]
        verdict = _coverage_verdict(actual, desired=bool(desired))
        active_carriers = {
            edge["source_id"]
            for edge in actual
            if edge["status"] not in {"negative", "contradicted", "uncovered"}
        }
        overlap = len(active_carriers) > 1
        if overlap and verdict in {"full", "partial"}:
            totals["overlap"] += 1
        desired_by_scope = _desired_scope_rows(desired, actual, nodes)
        desired_overlap = any(item["overlap"] for item in desired_by_scope)
        if desired_overlap:
            totals["desired_overlap"] += 1
        desired_requirements = sorted(
            {
                requirement
                for item in desired_by_scope
                for requirement in item["requirements"]
            },
            key=_requirement_sort_key,
        )
        effective_requirement = (
            desired_requirements[0] if desired_requirements else "unspecified"
        )
        gap_class = _gap_class(effective_requirement, verdict) if desired else "none"
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
                "desired_scopes": [item["scope"] for item in desired_by_scope],
                "desired_by_scope": desired_by_scope,
                "effective_requirement": effective_requirement,
                "gap_class": gap_class,
                "desired": desired,
                "actual": actual,
                "carriers": list(unique_carriers.values()),
            }
        )
    desired_rows = [row for row in rows if row["desired"]]
    actual_rows = [row for row in rows if row["actual"]]
    scope_rows = [
        item
        for row in desired_rows
        for item in row["desired_by_scope"]
    ]
    desired_totals: dict[str, dict[str, int]] = {
        requirement: defaultdict(int) for requirement in REQUIREMENT_ORDER
    }
    scope_totals: dict[str, dict[str, Any]] = {}
    for item in scope_rows:
        requirement_totals = desired_totals[item["effective_requirement"]]
        requirement_totals["functions"] += 1
        requirement_totals[item["verdict"]] += 1
        if item["gap_class"] != "none":
            requirement_totals["gaps"] += 1
        scope = scope_totals.setdefault(
            item["scope"],
            {
                "functions": 0,
                "provider_edges": 0,
                "actual_provider_edges": 0,
                "duplicate_provider_functions": 0,
                "hard_gaps": 0,
                "advisory_gaps": 0,
                "optional_gaps": 0,
                "unclassified_gaps": 0,
            },
        )
        scope["functions"] += 1
        scope["provider_edges"] += item["provider_edges"]
        scope["actual_provider_edges"] += item["actual_provider_edges"]
        if item["overlap"]:
            scope["duplicate_provider_functions"] += 1
        gap_counter = {
            "hard": "hard_gaps",
            "advisory": "advisory_gaps",
            "optional": "optional_gaps",
            "unclassified": "unclassified_gaps",
        }.get(item["gap_class"])
        if gap_counter:
            scope[gap_counter] += 1
    desired_summary = {
        "functions": len(desired_rows),
        "scope_functions": len(scope_rows),
        "provider_edges": sum(len(row["desired"]) for row in desired_rows),
        "duplicate_provider_functions": sum(
            1 for row in desired_rows if row["desired_overlap"]
        ),
        "hard_gaps": sum(1 for item in scope_rows if item["gap_class"] == "hard"),
        "advisory_gaps": sum(
            1 for item in scope_rows if item["gap_class"] == "advisory"
        ),
        "optional_gaps": sum(
            1 for item in scope_rows if item["gap_class"] == "optional"
        ),
        "unclassified_gaps": sum(
            1 for item in scope_rows if item["gap_class"] == "unclassified"
        ),
        "requirements": {
            requirement: dict(desired_totals[requirement])
            for requirement in REQUIREMENT_ORDER
        },
        "scopes": dict(sorted(scope_totals.items())),
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
        "actual_overlap_functions": totals.get("overlap", 0),
        "desired_overlap_functions": totals.get("desired_overlap", 0),
        "verdicts": {
            verdict: totals[verdict]
            for verdict in ("full", "partial", "negative", "uncovered", "unproven")
            if verdict in totals
        },
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


def _desired_scope_rows(
    desired: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in desired:
        scope = edge.get("metadata", {}).get("resolution_scope", "unscoped")
        grouped[str(scope)].append(edge)
    rows = []
    actual_has_origin = any(
        nodes.get(edge["source_id"], {}).get("metadata", {}).get("origin_system")
        for edge in actual
    )
    for scope, edges in sorted(grouped.items()):
        match_values = {
            str(value)
            for edge in edges
            for value in (
                edge.get("metadata", {}).get("resolution_host_id"),
                edge.get("metadata", {}).get("resolution_system_id"),
                edge.get("metadata", {}).get("resolution_scope"),
            )
            if value
        }
        scoped_actual = [
            edge
            for edge in actual
            if nodes.get(edge["source_id"], {})
            .get("metadata", {})
            .get("origin_system")
            in match_values
        ]
        if len(grouped) == 1 and not actual_has_origin:
            scoped_actual = actual
        verdict = _coverage_verdict(scoped_actual, desired=True)
        requirements = sorted(
            {
                requirement
                for edge in edges
                for requirement in _edge_requirements(edge)
            },
            key=_requirement_sort_key,
        )
        effective_requirement = requirements[0] if requirements else "unspecified"
        providers = sorted({edge["source_id"] for edge in edges})
        desired_statuses = sorted(
            {
                status
                for edge in edges
                for status in _edge_desired_statuses(edge)
            }
        )
        rows.append(
            {
                "scope": scope,
                "verdict": verdict,
                "provider_edges": len(edges),
                "actual_provider_edges": len(scoped_actual),
                "providers": providers,
                "overlap": len(providers) > 1,
                "requirements": requirements,
                "effective_requirement": effective_requirement,
                "desired_statuses": desired_statuses,
                "gap_class": _gap_class(effective_requirement, verdict),
            }
        )
    return rows


def _edge_desired_statuses(edge: dict[str, Any]) -> set[str]:
    metadata = edge.get("metadata", {})
    values = metadata.get("desired_statuses")
    if isinstance(values, list):
        statuses = {value for value in values if isinstance(value, str)}
        if statuses:
            return statuses
    status = metadata.get("desired_status")
    return {status} if isinstance(status, str) else set()


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


def _coverage_verdict(
    actual: list[dict[str, Any]],
    *,
    desired: bool,
) -> str:
    statuses = {edge["status"] for edge in actual}
    if "negative" in statuses or "contradicted" in statuses:
        return "negative"
    if any(status in {"full", "fulfilled"} for status in statuses):
        return "full"
    if statuses & POSITIVE:
        return "partial"
    return "uncovered" if desired else "unproven"
