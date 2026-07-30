from __future__ import annotations

from typing import Any

from .coverage import coverage_report
from .store import Store
from .util import utc_now


def assess(store: Store) -> dict[str, Any]:
    coverage = coverage_report(store)
    nodes = store.nodes()
    edges = store.resolved_edges()
    entrypoints = [node for node in nodes if node["node_type"] == "entrypoint"]
    entered = {
        edge["target_id"]
        for edge in edges
        if edge["relation"] in {"enters_at", "invoked", "used"}
    }
    unused_entrypoints = [node["id"] for node in entrypoints if node["id"] not in entered]
    findings = []
    for row in coverage["functions"]:
        verdict = row["verdict"]
        if verdict == "uncovered":
            gap_class = row["gap_class"]
            severity, kind = {
                "hard": ("high", "function-gap"),
                "advisory": ("medium", "recommended-function-gap"),
                "optional": ("review", "optional-function-gap"),
                "unclassified": ("high", "function-gap"),
                "none": ("review", "unclassified-function-gap"),
            }[gap_class]
            if (
                gap_class in {"hard", "unclassified"}
                and row["function"]["metadata"].get("priority") == "critical"
            ):
                severity = "critical"
            findings.append(
                {
                    "severity": severity,
                    "kind": kind,
                    "function": row["function"]["id"],
                    "requirement": row["effective_requirement"],
                    "recommendation": "Assign a carrier, then verify it with an observed execution receipt.",
                }
            )
        elif verdict == "negative":
            findings.append(
                {
                    "severity": "critical",
                    "kind": "negative-coverage",
                    "function": row["function"]["id"],
                    "recommendation": "Stop treating the carrier as conforming; resolve intent or replace its path.",
                }
            )
        elif verdict == "partial":
            gap_class = row["gap_class"]
            findings.append(
                {
                    "severity": "review" if gap_class == "optional" else "medium",
                    "kind": (
                        "optional-undercoverage"
                        if gap_class == "optional"
                        else "undercoverage"
                    ),
                    "function": row["function"]["id"],
                    "requirement": row["effective_requirement"],
                    "recommendation": "Identify the missing subfunction and test one narrow intervention.",
                }
            )
        if row["overlap"]:
            findings.append(
                {
                    "severity": "review",
                    "kind": "overlap",
                    "function": row["function"]["id"],
                    "recommendation": "Check cardinality, ownership, routing, and whether overlap is intentional.",
                }
            )
        if row["desired_overlap"]:
            findings.append(
                {
                    "severity": "review",
                    "kind": "desired-provider-overlap",
                    "function": row["function"]["id"],
                    "recommendation": "Confirm whether multiple desired providers are intentional and routed.",
                }
            )
    if unused_entrypoints:
        findings.append(
            {
                "severity": "review",
                "kind": "unobserved-entrypoints",
                "nodes": unused_entrypoints,
                "recommendation": "Run a bounded Trampelpfad probe before deprecating or promoting an entrypoint.",
            }
        )
    direction = [
        "stabilize-negative-coverage",
        "close-critical-function-gaps",
        "empirically-test-partial-coverage",
        "resolve-unintentional-overlap",
        "simplify-entrypoints-after-observation",
    ]
    return {
        "schema": "system-explorer.assessment.v1",
        "created_at": utc_now(),
        "summary": coverage["summary"],
        "findings": findings,
        "recommended_direction": direction,
        "basis": {
            "nodes": len(nodes),
            "resolved_edges": len(edges),
            "evidence_records": len(store.evidence()),
            "inference": True,
        },
    }
