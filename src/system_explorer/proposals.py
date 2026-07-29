from __future__ import annotations

import re
from typing import Any

from .assessment import assess
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


def propose(prompt: str, store: Store) -> dict[str, Any]:
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
    gaps = [
        row["function"]["id"]
        for row in coverage["functions"]
        if row["verdict"] in {"uncovered", "negative", "partial"}
    ]
    return {
        "schema": "system-explorer.change-proposal.v1",
        "created_at": utc_now(),
        "prompt_sha256": sha256_text(prompt),
        "prompt_retained": False,
        "status": "draft-read-only",
        "actions": actions,
        "mentioned_nodes": mentioned,
        "relevant_function_gaps": gaps[:25],
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
        "apply": {"authorized": False, "reason": "Proposal UI never mutates the target system."},
    }


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
