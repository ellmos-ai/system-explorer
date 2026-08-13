from __future__ import annotations

import re
from typing import Any

from .assessment import assess
from .composition_rules import evaluate_cardinality
from .coverage import coverage_report
from .store import Store
from .util import sha256_text, utc_now


ACTION_WORDS = {
    "add": {"add", "create", "introduce", "anlegen", "ergänzen", "hinzufügen"},
    "move": {"move", "relocate", "verschieben", "umziehen"},
    "link": {"link", "connect", "reference", "verbinden", "verknüpfen"},
    "deprecate": {"remove", "retire", "deprecate", "entfernen", "ablösen"},
    "strengthen": {"improve", "strengthen", "complete", "verbessern", "stärken", "vervollständigen"},
}


def propose(
    prompt: str,
    store: Store,
    *,
    composition_rules: dict[str, Any] | None = None,
    desired_identities: list[dict[str, Any]] | None = None,
    actual_identities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    lowered = prompt.casefold()
    actions = [
        action for action, words in ACTION_WORDS.items() if any(word in lowered for word in words)
    ]
    if not actions:
        actions = ["review"]
    mentioned = []
    for node in store.nodes():
        tokens = [token for token in re.split(r"[^a-zA-Z0-9_-]+", node["name"].casefold()) if len(token) > 3]
        if tokens and any(token in lowered for token in tokens):
            mentioned.append({"id": node["id"], "name": node["name"], "type": node["node_type"]})
    coverage = coverage_report(store)
    assessment = assess(store)
    cardinality = evaluate_cardinality(
        composition_rules,
        desired=desired_identities or (),
        actual=actual_identities or (),
    )
    scoped_gaps = _scoped_coverage_gaps(coverage)
    gaps = list(
        dict.fromkeys(item["function"] for item in scoped_gaps)
    )
    return {
        "schema": "system-explorer.change-proposal.v1",
        "created_at": utc_now(),
        "prompt_sha256": sha256_text(prompt),
        "prompt_retained": False,
        "status": "draft-read-only",
        "actions": actions,
        "mentioned_nodes": mentioned,
        "relevant_function_gaps": gaps[:25],
        "relevant_scoped_function_gaps": scoped_gaps[:25],
        "recommended_direction": assessment["recommended_direction"],
        "required_gates": [
            "schema-validation",
            "ontology-validation",
            "composition-cardinality-check",
            "policy-resolution",
            "lock-check",
            "human-approval",
            "adapter-dry-run",
            "readback-and-receipt",
        ],
        "composition_cardinality": cardinality,
        "apply": {"authorized": False, "reason": "Proposal UI never mutates the target system."},
    }


def _scoped_coverage_gaps(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = []
    for row in coverage["functions"]:
        scope_rows = row["desired_by_scope"] or [
            {
                "scope": None,
                "verdict": row["verdict"],
                "gap_class": row["gap_class"],
                "effective_requirement": row["effective_requirement"],
            }
        ]
        for scope_row in scope_rows:
            if scope_row["verdict"] not in {
                "uncovered",
                "negative",
                "partial",
                "wrong-provider",
            }:
                continue
            if scope_row["gap_class"] == "optional":
                continue
            gaps.append(
                {
                    "function": row["function"]["id"],
                    "scope": scope_row["scope"],
                    "verdict": scope_row["verdict"],
                    "gap_class": scope_row["gap_class"],
                    "requirement": scope_row["effective_requirement"],
                }
            )
    return gaps


def probe_plan(system_path: str, task: str, repetitions: int = 3, max_steps: int = 20) -> dict[str, Any]:
    prompt = (
        f"You explore a system at {system_path}. TASK: {task}. "
        f"You only know this path. Explore for at most {max_steps} steps. "
        "Report VISITED_DIRECTORIES, READ_FILES, TASK_COMPLETED, MOST_HELPFUL_FILE, "
        "ENTRYPOINT_USED, CARRIERS_USED, and OUTPUT_HANDOFF."
    )
    return {
        "schema": "system-explorer.probe-plan.v1",
        "method": "trampelpfadanalyse",
        "repetitions": repetitions,
        "max_steps": max_steps,
        "prompt": prompt,
        "recommended_runner": "swarm-ai or another budgeted external orchestrator",
        "module_executes_models": False,
        "metrics": [
            "success_rate",
            "wrong_path_rate",
            "steps_to_target",
            "blind_spots",
            "entrypoint_frequency",
            "carrier_frequency",
        ],
    }
