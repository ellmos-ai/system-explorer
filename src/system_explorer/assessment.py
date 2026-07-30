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
    unused_entrypoints = [
        node["id"] for node in entrypoints if node["id"] not in entered
    ]
    findings = []
    for row in coverage["functions"]:
        scope_rows = row["desired_by_scope"]
        if scope_rows:
            for scope_row in scope_rows:
                findings.extend(
                    _scope_coverage_findings(
                        row,
                        verdict=scope_row["verdict"],
                        gap_class=scope_row["gap_class"],
                        requirement=scope_row["effective_requirement"],
                        scope=scope_row["scope"],
                        carrier_mismatch=scope_row["carrier_mismatch"],
                        unexpected_actual_providers=scope_row[
                            "unexpected_actual_providers"
                        ],
                    )
                )
                if scope_row["overlap"]:
                    findings.append(
                        {
                            "severity": "review",
                            "kind": "desired-provider-overlap",
                            "function": row["function"]["id"],
                            "scope": scope_row["scope"],
                            "recommendation": "Confirm whether multiple desired providers are intentional and routed.",
                        }
                    )
        else:
            findings.extend(
                _scope_coverage_findings(
                    row,
                    verdict=row["verdict"],
                    gap_class=row["gap_class"],
                    requirement=row["effective_requirement"],
                    scope=None,
                    carrier_mismatch=False,
                    unexpected_actual_providers=[],
                )
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
        "desired_summary": coverage["desired_summary"],
        "findings": findings,
        "recommended_direction": direction,
        "basis": {
            "nodes": len(nodes),
            "resolved_edges": len(edges),
            "evidence_records": len(store.evidence()),
            "inference": True,
        },
    }


def _scope_coverage_findings(
    row: dict[str, Any],
    *,
    verdict: str,
    gap_class: str,
    requirement: str,
    scope: str | None,
    carrier_mismatch: bool,
    unexpected_actual_providers: list[str],
) -> list[dict[str, Any]]:
    findings = []
    scope_field = {"scope": scope} if scope is not None else {}
    if carrier_mismatch:
        findings.append(
            {
                "severity": {
                    "required": "high",
                    "recommended": "medium",
                    "optional": "review",
                    "unspecified": "high",
                }[requirement],
                "kind": "carrier-mismatch",
                "function": row["function"]["id"],
                "requirement": requirement,
                **scope_field,
                "unexpected_actual_providers": unexpected_actual_providers,
                "recommendation": "Verify the desired component_ref on the observed carrier or approve an explicit fallback provider.",
            }
        )
    if verdict == "uncovered":
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
                "requirement": requirement,
                **scope_field,
                "recommendation": "Assign a carrier, then verify it with an observed execution receipt.",
            }
        )
    elif verdict == "negative":
        findings.append(
            {
                "severity": "critical",
                "kind": "negative-coverage",
                "function": row["function"]["id"],
                "requirement": requirement,
                **scope_field,
                "recommendation": "Stop treating the carrier as conforming; resolve intent or replace its path.",
            }
        )
    elif verdict == "partial":
        findings.append(
            {
                "severity": "review" if gap_class == "optional" else "medium",
                "kind": (
                    "optional-undercoverage"
                    if gap_class == "optional"
                    else "undercoverage"
                ),
                "function": row["function"]["id"],
                "requirement": requirement,
                **scope_field,
                "recommendation": "Identify the missing subfunction and test one narrow intervention.",
            }
        )
    return findings
