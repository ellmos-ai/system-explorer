from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import canonical_content_hash, with_content_hash
from .coverage import coverage_report
from .store import Store


QUERY_SCHEMA = "ellmos.search-routing-query.v1"
RECEIPT_SCHEMA = "ellmos.search-routing-receipt.v1"
QUERY_MODES = {"skill-search", "tool-search", "tool-overview"}
RANKING_METHODS = {"semantic-ranker", "controlcenter-lexical-candidate"}
TOOL_TYPES = {"module", "software_app", "interface", "access_surface"}
VERIFIED_ACTUAL_STATUSES = {"observed", "full", "fulfilled"}
ROOT_FIELDS = {
    "schema",
    "query_id",
    "query_mode",
    "scope",
    "required_capabilities",
    "exact_refs",
    "ranked_candidates",
    "authority_gates",
    "execution_requested",
    "observed_at",
    "content_hash",
}


def resolve_search_route(
    query: dict[str, Any],
    resolution: dict[str, Any],
    store: Store,
) -> dict[str, Any]:
    """Resolve stable component references against native actual-self evidence."""

    _validate_query(query, resolution)
    components = _components(resolution)
    coverage = coverage_report(store)
    required = list(query["required_capabilities"])
    expected_types = {"skill"} if query["query_mode"] == "skill-search" else TOOL_TYPES
    observed_at = _timestamp(query["observed_at"], "observed_at")

    evaluated = {
        ref: _evaluate_candidate(
            ref,
            component,
            expected_types=expected_types,
            required_capabilities=required,
            scope=query["scope"],
            observed_at=observed_at,
            store=store,
            coverage=coverage,
        )
        for ref, component in components.items()
    }
    matching_refs = sorted(
        ref
        for ref, candidate in evaluated.items()
        if candidate["type_eligible"] and candidate["capability_eligible"]
    )
    eligible_refs = [
        ref for ref in matching_refs if evaluated[ref]["availability_verified"]
    ]

    selected_ref: str | None = None
    candidate_method = "registry-capability"
    score_domain: str | None = None
    semantic_ranker_used = False
    ambiguous = False

    if query["query_mode"] != "tool-overview":
        exact_eligible = [
            ref
            for ref in query["exact_refs"]
            if ref in evaluated and evaluated[ref]["availability_verified"]
        ]
        if len(exact_eligible) == 1:
            selected_ref = exact_eligible[0]
            candidate_method = "exact-reference"
        elif len(exact_eligible) > 1:
            ambiguous = True
            candidate_method = "exact-reference"
        elif len(eligible_refs) == 1:
            selected_ref = eligible_refs[0]
        elif len(eligible_refs) > 1:
            for ranking in query["ranked_candidates"]:
                ranked = _rank_eligible(ranking, eligible_refs)
                if not ranked:
                    continue
                candidate_method = ranking["method"]
                score_domain = ranking["score_domain"]
                semantic_ranker_used = ranking["method"] == "semantic-ranker"
                if len(ranked) == 1:
                    selected_ref = ranked[0]
                else:
                    ambiguous = True
                break
            else:
                ambiguous = True

    selected = evaluated.get(selected_ref) if selected_ref else None
    gate_results = _evaluate_authority_gates(
        query["authority_gates"],
        query=query,
        selected_ref=selected_ref,
        observed_at=observed_at,
    )
    authority_passed = bool(gate_results) and all(
        gate["status"] == "passed" for gate in gate_results
    )
    executable = bool(
        query["execution_requested"]
        and selected
        and selected["availability_verified"]
        and authority_passed
    )

    if query["query_mode"] == "tool-overview":
        result_status = "overview"
    elif selected_ref:
        result_status = "resolved"
    elif ambiguous:
        result_status = "ambiguous"
    elif matching_refs:
        result_status = "declared-not-observed"
    else:
        result_status = "not-found"

    verification_ids = (
        list(selected["verification_receipts"]) if selected else []
    )
    source_hashes = {
        "query": query["content_hash"],
        "resolution": resolution["content_hash"],
        "component_registry": resolution["component_registry"]["content_hash"],
        "actual_evidence": (
            list(selected["evidence_sha256"]) if selected else []
        ),
    }
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "query_id": query["query_id"],
        "query_mode": query["query_mode"],
        "scope": query["scope"],
        "source_hashes": source_hashes,
        "candidate_ids": matching_refs,
        "candidate_method": candidate_method,
        "score_domain": score_domain,
        "eligibility_filters": [
            "stable-component-ref",
            "source-verified-native-registry-binding",
            "exact-component-type",
            "exact-capability-id",
            "actual-self-origin-host",
            "hashed-native-runtime-readback",
            "fresh-receipt",
            "exact-provider-coverage",
        ],
        "semantic_ranker_used": semantic_ranker_used,
        "selected_ref": selected_ref,
        "selection_authority": (
            "system-explorer.actual-self-evidence-resolver.v1"
            if selected_ref
            else "none"
        ),
        "authority_gates": gate_results,
        "identity_verified": bool(selected and selected["identity_verified"]),
        "availability_verified": bool(
            selected and selected["availability_verified"]
        ),
        "verification_receipt": verification_ids,
        "executable": executable,
        "observed_at": query["observed_at"],
        "result_status": result_status,
        "candidates": [evaluated[ref] for ref in matching_refs],
    }
    return with_content_hash(receipt)


def _evaluate_candidate(
    ref: str,
    component: dict[str, Any],
    *,
    expected_types: set[str],
    required_capabilities: list[str],
    scope: str,
    observed_at: datetime,
    store: Store,
    coverage: dict[str, Any],
) -> dict[str, Any]:
    component_type = component["type"]
    provides = sorted(component.get("provides", []))
    capabilities = required_capabilities or provides
    registry_resolution = component.get("registry_resolution", {})
    identity_verified = (
        registry_resolution.get("class") == "native-binding"
        and bool(registry_resolution.get("source"))
        and bool(registry_resolution.get("record_id"))
    )
    type_eligible = component_type in expected_types
    capability_eligible = bool(capabilities) and set(capabilities) <= set(provides)
    desired_active = component.get("desired_status") not in {
        "suppressed",
        "unavailable",
    }
    observation = _actual_self_observation(
        store,
        component_ref=ref,
        capabilities=capabilities,
        scope=scope,
        observed_at=observed_at,
    )
    coverage_verdicts = {
        capability: _scope_coverage_verdict(coverage, capability, scope, ref)
        for capability in capabilities
    }
    exact_provider_covered = bool(capabilities) and all(
        verdict in {"full", "partial"}
        for verdict in coverage_verdicts.values()
    )
    availability_verified = bool(
        identity_verified
        and type_eligible
        and capability_eligible
        and desired_active
        and observation["availability_verified"]
        and exact_provider_covered
    )
    rejection_reasons = []
    if not identity_verified:
        rejection_reasons.append("registry-identity-unverified")
    if not type_eligible:
        rejection_reasons.append("component-type-mismatch")
    if not capability_eligible:
        rejection_reasons.append("capability-mismatch")
    if not desired_active:
        rejection_reasons.append("desired-status-inactive")
    rejection_reasons.extend(observation["rejection_reasons"])
    if not exact_provider_covered:
        rejection_reasons.append("exact-provider-coverage-unverified")

    return {
        "ref": ref,
        "component_type": component_type,
        "provides": provides,
        "identity_verified": identity_verified,
        "type_eligible": type_eligible,
        "capability_eligible": capability_eligible,
        "desired_active": desired_active,
        "coverage_verdicts": coverage_verdicts,
        "availability_verified": availability_verified,
        "verification_receipts": observation["verification_receipts"],
        "evidence_sha256": observation["evidence_sha256"],
        "rejection_reasons": sorted(set(rejection_reasons)),
    }


def _actual_self_observation(
    store: Store,
    *,
    component_ref: str,
    capabilities: list[str],
    scope: str,
    observed_at: datetime,
) -> dict[str, Any]:
    nodes = {node["id"]: node for node in store.nodes()}
    function_names = {
        node_id: node["name"]
        for node_id, node in nodes.items()
        if node["node_type"] == "function"
    }
    evidence = {item["id"]: item for item in store.evidence()}
    receipts_by_capability: dict[str, set[str]] = {
        capability: set() for capability in capabilities
    }
    hashes: set[str] = set()
    reasons: set[str] = set()

    for edge in store.resolved_edges("actual"):
        if edge["relation"] != "carries":
            continue
        capability = function_names.get(edge["target_id"])
        if capability not in receipts_by_capability:
            continue
        carrier = nodes.get(edge["source_id"], {})
        metadata = carrier.get("metadata", {})
        if metadata.get("component_ref") != component_ref:
            continue
        if metadata.get("identity_status") != "verified":
            reasons.add("actual-self-identity-unverified")
            continue
        if not metadata.get("actual_self"):
            reasons.add("runtime-edge-not-actual-self-receipt")
            continue
        if metadata.get("scope", carrier.get("scope")) not in {None, scope}:
            reasons.add("actual-self-scope-mismatch")
            continue
        instance_scope = carrier.get("scope")
        if instance_scope != scope:
            reasons.add("actual-self-scope-mismatch")
            continue
        expires_at = metadata.get("actual_self_expires_at")
        if not isinstance(expires_at, str) or observed_at > _timestamp(
            expires_at, "actual_self_expires_at"
        ):
            reasons.add("actual-self-receipt-expired")
            continue
        if edge["status"] not in VERIFIED_ACTUAL_STATUSES:
            reasons.add("actual-self-status-not-verified")
            continue
        evidence_id = edge.get("evidence_id")
        evidence_item = evidence.get(evidence_id)
        if not evidence_item or not evidence_item.get("sha256"):
            reasons.add("actual-self-evidence-unhashed")
            continue
        if evidence_item.get("source_kind") != "actual-self-native-receipt":
            reasons.add("actual-self-evidence-kind-mismatch")
            continue
        receipts_by_capability[capability].add(evidence_id)
        hashes.add(evidence_item["sha256"])

    missing = sorted(
        capability
        for capability, receipts in receipts_by_capability.items()
        if not receipts
    )
    if missing:
        reasons.add("actual-self-capability-unobserved")
    return {
        "availability_verified": not missing and bool(capabilities),
        "verification_receipts": sorted(
            {
                receipt
                for receipts in receipts_by_capability.values()
                for receipt in receipts
            }
        ),
        "evidence_sha256": sorted(hashes),
        "rejection_reasons": sorted(reasons),
    }


def _scope_coverage_verdict(
    coverage: dict[str, Any],
    capability: str,
    scope: str,
    component_ref: str,
) -> str:
    for row in coverage["functions"]:
        if row["function"]["name"] != capability:
            continue
        for scoped in row["desired_by_scope"]:
            if scoped["scope"] != scope:
                continue
            if component_ref not in scoped["desired_component_refs"]:
                return "provider-not-desired"
            return scoped["verdict"]
    return "uncovered"


def _rank_eligible(ranking: dict[str, Any], eligible_refs: list[str]) -> list[str]:
    candidates = [
        candidate
        for candidate in ranking["candidates"]
        if candidate["ref"] in eligible_refs
    ]
    if not candidates:
        return []
    highest = max(candidate["score"] for candidate in candidates)
    return sorted(
        candidate["ref"] for candidate in candidates if candidate["score"] == highest
    )


def _evaluate_authority_gates(
    gates: list[dict[str, Any]],
    *,
    query: dict[str, Any],
    selected_ref: str | None,
    observed_at: datetime,
) -> list[dict[str, Any]]:
    results = []
    for gate in gates:
        reasons = []
        applies_to = gate["applies_to"]
        if query["query_mode"] not in applies_to["query_modes"]:
            reasons.append("query-mode-out-of-scope")
        if query["scope"] not in applies_to["scopes"]:
            reasons.append("system-scope-out-of-scope")
        if selected_ref and selected_ref not in applies_to["component_refs"]:
            reasons.append("component-out-of-scope")
        if not set(query["required_capabilities"]) <= set(
            applies_to["capabilities"]
        ):
            reasons.append("capability-out-of-scope")
        issued_at = _timestamp(gate["issued_at"], "authority_gate.issued_at")
        expires_at = _timestamp(gate["expires_at"], "authority_gate.expires_at")
        if observed_at < issued_at:
            reasons.append("authority-not-yet-effective")
        if observed_at > expires_at:
            reasons.append("authority-expired")
        if gate["conflicts"]:
            reasons.append("authority-conflict")

        if gate["authority_type"] == "delegated-avatar-decision":
            if gate.get("decision_kind") != "predicted":
                reasons.append("delegated-avatar-decision-kind-invalid")
            if not gate.get("delegation_ref"):
                reasons.append("delegation-reference-missing")
            if not gate.get("evidence_refs"):
                reasons.append("delegated-evidence-missing")
            if gate.get("confidence", 0.0) < gate.get("minimum_confidence", 1.0):
                reasons.append("delegated-confidence-below-threshold")

        results.append(
            {
                "authority_type": gate["authority_type"],
                "decision_ref": gate["decision_ref"],
                "status": "blocked" if reasons else "passed",
                "reasons": sorted(reasons),
            }
        )
    return results


def _validate_query(query: Any, resolution: dict[str, Any]) -> None:
    if not isinstance(query, dict):
        raise ValueError("search-routing query must be an object")
    unknown = sorted(set(query) - ROOT_FIELDS)
    missing = sorted(ROOT_FIELDS - set(query))
    if unknown:
        raise ValueError("search-routing query has unknown fields: " + ", ".join(unknown))
    if missing:
        raise ValueError("search-routing query is missing fields: " + ", ".join(missing))
    if query["schema"] != QUERY_SCHEMA:
        raise ValueError(f"search-routing query must use {QUERY_SCHEMA}")
    if query["content_hash"] != canonical_content_hash(query):
        raise ValueError("search-routing query content_hash mismatch")
    _nonempty_string(query["query_id"], "query_id")
    if query["query_mode"] not in QUERY_MODES:
        raise ValueError("query_mode is unsupported")
    instance = resolution.get("instance")
    if not isinstance(instance, dict) or query["scope"] != instance.get("instance_id"):
        raise ValueError("search-routing query scope does not match the resolution")
    registry = resolution.get("component_registry")
    if not isinstance(registry, dict) or registry.get("source_verification") != "verified":
        raise ValueError("resolution component registry is not source-verified")
    _timestamp(query["observed_at"], "observed_at")
    if not isinstance(query["execution_requested"], bool):
        raise ValueError("execution_requested must be boolean")

    capabilities = query["required_capabilities"]
    if not isinstance(capabilities, list):
        raise ValueError("required_capabilities must be a list")
    if query["query_mode"] != "tool-overview" and not capabilities:
        raise ValueError("search queries require at least one exact capability ID")
    _unique_strings(capabilities, "required_capabilities")
    unknown_capabilities = sorted(set(capabilities) - set(resolution["functions"]))
    if unknown_capabilities:
        raise ValueError(
            "required_capabilities are not in the resolution: "
            + ", ".join(unknown_capabilities)
        )

    exact_refs = query["exact_refs"]
    if not isinstance(exact_refs, list):
        raise ValueError("exact_refs must be a list")
    _unique_stable_refs(exact_refs, "exact_refs")

    rankings = query["ranked_candidates"]
    if not isinstance(rankings, list):
        raise ValueError("ranked_candidates must be a list")
    seen_methods = set()
    for index, ranking in enumerate(rankings):
        if not isinstance(ranking, dict) or set(ranking) != {
            "method",
            "score_domain",
            "candidates",
        }:
            raise ValueError(f"ranked_candidates[{index}] has invalid fields")
        if ranking["method"] not in RANKING_METHODS:
            raise ValueError(f"ranked_candidates[{index}].method is unsupported")
        if ranking["method"] in seen_methods:
            raise ValueError("ranked candidate methods must be unique")
        seen_methods.add(ranking["method"])
        _nonempty_string(ranking["score_domain"], f"ranked_candidates[{index}].score_domain")
        candidates = ranking["candidates"]
        if not isinstance(candidates, list) or not candidates:
            raise ValueError(f"ranked_candidates[{index}].candidates must be non-empty")
        refs = []
        for candidate_index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict) or set(candidate) != {"ref", "score"}:
                raise ValueError(
                    f"ranked_candidates[{index}].candidates[{candidate_index}] "
                    "has invalid fields"
                )
            refs.append(_stable_ref(candidate["ref"], "ranked candidate ref"))
            score = candidate["score"]
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ValueError("ranked candidate score must be numeric")
        if len(refs) != len(set(refs)):
            raise ValueError("ranked candidate refs must be unique per score domain")

    gates = query["authority_gates"]
    if not isinstance(gates, list):
        raise ValueError("authority_gates must be a list")
    for index, gate in enumerate(gates):
        _validate_authority_gate(gate, index)


def _validate_authority_gate(gate: Any, index: int) -> None:
    if not isinstance(gate, dict):
        raise ValueError(f"authority_gates[{index}] must be an object")
    base = {
        "authority_type",
        "decision_ref",
        "applies_to",
        "issued_at",
        "expires_at",
        "conflicts",
    }
    delegated = {
        "delegation_ref",
        "decision_kind",
        "confidence",
        "minimum_confidence",
        "evidence_refs",
    }
    authority_type = gate.get("authority_type")
    allowed_types = {
        "direct-user-decision",
        "policy-decision",
        "delegated-avatar-decision",
    }
    if authority_type not in allowed_types:
        raise ValueError(f"authority_gates[{index}].authority_type is unsupported")
    expected = base | (delegated if authority_type == "delegated-avatar-decision" else set())
    if set(gate) != expected:
        raise ValueError(f"authority_gates[{index}] has invalid fields")
    _stable_ref(gate["decision_ref"], f"authority_gates[{index}].decision_ref")
    issued_at = _timestamp(gate["issued_at"], f"authority_gates[{index}].issued_at")
    expires_at = _timestamp(gate["expires_at"], f"authority_gates[{index}].expires_at")
    if expires_at <= issued_at:
        raise ValueError(f"authority_gates[{index}] expires before it is effective")
    if not isinstance(gate["conflicts"], list):
        raise ValueError(f"authority_gates[{index}].conflicts must be a list")
    _unique_stable_refs(gate["conflicts"], f"authority_gates[{index}].conflicts")

    applies_to = gate["applies_to"]
    fields = {"query_modes", "scopes", "component_refs", "capabilities"}
    if not isinstance(applies_to, dict) or set(applies_to) != fields:
        raise ValueError(f"authority_gates[{index}].applies_to has invalid fields")
    _unique_strings(applies_to["query_modes"], "authority applies_to.query_modes")
    if not set(applies_to["query_modes"]) <= QUERY_MODES:
        raise ValueError("authority gate contains an unsupported query mode")
    _unique_strings(applies_to["scopes"], "authority applies_to.scopes")
    _unique_stable_refs(
        applies_to["component_refs"], "authority applies_to.component_refs"
    )
    _unique_strings(applies_to["capabilities"], "authority applies_to.capabilities")

    if authority_type == "delegated-avatar-decision":
        _stable_ref(gate["delegation_ref"], f"authority_gates[{index}].delegation_ref")
        if gate["decision_kind"] != "predicted":
            raise ValueError("delegated avatar decision_kind must be predicted")
        for field in ("confidence", "minimum_confidence"):
            value = gate[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 1
            ):
                raise ValueError(f"authority_gates[{index}].{field} must be 0..1")
        if not isinstance(gate["evidence_refs"], list) or not gate["evidence_refs"]:
            raise ValueError("delegated avatar decision requires evidence_refs")
        _unique_stable_refs(
            gate["evidence_refs"], f"authority_gates[{index}].evidence_refs"
        )


def _components(resolution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for bundle in resolution["bundles"]:
        for component in bundle["components"]:
            ref = component["ref"]
            ref = ref["ref"] if isinstance(ref, dict) else ref
            current = result.get(ref)
            if current is None:
                result[ref] = {
                    **component,
                    "ref": ref,
                    "provides": sorted(set(component.get("provides", []))),
                }
                continue
            if current["type"] != component["type"]:
                raise ValueError(f"component {ref!r} has conflicting types")
            current["provides"] = sorted(
                set(current.get("provides", [])) | set(component.get("provides", []))
            )
            if (
                current.get("registry_resolution")
                != component.get("registry_resolution")
            ):
                raise ValueError(
                    f"component {ref!r} has conflicting registry resolutions"
                )
    return result


def _unique_strings(value: Any, path: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    items = [_nonempty_string(item, path) for item in value]
    if len(items) != len(set(items)):
        raise ValueError(f"{path} must contain unique values")


def _unique_stable_refs(value: Any, path: str) -> None:
    _unique_strings(value, path)
    for item in value:
        _stable_ref(item, path)


def _stable_ref(value: Any, path: str) -> str:
    value = _nonempty_string(value, path)
    if ":" not in value or value.startswith(":") or value.endswith(":"):
        raise ValueError(f"{path} must use a stable typed reference")
    if any(character.isspace() for character in value):
        raise ValueError(f"{path} must not contain whitespace")
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{path} must contain non-empty trimmed strings")
    return value


def _timestamp(value: Any, path: str) -> datetime:
    value = _nonempty_string(value, path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{path} must include a timezone")
    return parsed.astimezone(timezone.utc)
