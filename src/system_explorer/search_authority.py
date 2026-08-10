from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .receipt_trust import ReceiptTrustStore, verify_signed_receipt
from .store import Store
from .validation import (
    exact_string_object as _exact_object,
    sha256 as _sha256,
    stable_ref as _stable_ref,
    timestamp as _timestamp,
    unique_strings as _unique_strings,
)


RECEIPT_SCHEMA = "ellmos.search-authority-receipt.v1"
AUTHORITY_TYPES = {
    "direct-user-decision",
    "policy-decision",
    "delegated-avatar-decision",
}
QUERY_MODES = {"skill-search", "tool-search", "tool-overview"}
AUTHORITY_EVIDENCE_SOURCE_KINDS = {"document:decision", "document:policy"}
AUTHORITY_REQUIRED_SOURCE_KIND = {
    "direct-user-decision": "document:decision",
    "policy-decision": "document:policy",
    "delegated-avatar-decision": "document:decision",
}
ROOT_FIELDS = {
    "schema",
    "receipt_ref",
    "authority_type",
    "decision_ref",
    "delegation_ref",
    "decision_kind",
    "confidence",
    "minimum_confidence",
    "issuer",
    "scope",
    "evidence",
    "issued_at",
    "expires_at",
    "conflicts",
    "signature",
    "content_hash",
}


def import_search_authority_receipt(
    path: Path,
    store: Store,
    *,
    evaluated_at: str,
    expected_host_id: str,
    trust_store: ReceiptTrustStore,
    defer_commit: bool = False,
) -> dict[str, Any]:
    owns_transaction = not store.in_transaction
    if defer_commit and owns_transaction:
        raise RuntimeError(
            "defer_commit requires an active outer Store transaction"
        )
    path = Path(path).resolve()
    source_bytes = path.read_bytes()
    receipt = json.loads(source_bytes.decode("utf-8"))
    trust_verification = validate_search_authority_receipt(
        receipt,
        evaluated_at=evaluated_at,
        expected_host_id=expected_host_id,
        trust_store=trust_store,
    )
    verified_evidence = _verify_local_evidence(store, receipt)
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_uri = (
        "search-authority://"
        + quote(expected_host_id, safe="")
        + "/"
        + quote(receipt["receipt_ref"], safe="")
    )
    metadata = {
        "receipt_schema": RECEIPT_SCHEMA,
        "receipt_ref": receipt["receipt_ref"],
        "receipt_content_hash": receipt["content_hash"],
        "authority_type": receipt["authority_type"],
        "decision_ref": receipt["decision_ref"],
        "delegation_ref": receipt["delegation_ref"],
        "decision_kind": receipt["decision_kind"],
        "confidence": receipt["confidence"],
        "minimum_confidence": receipt["minimum_confidence"],
        "issuer_ref": receipt["issuer"]["ref"],
        "issuer_adapter_id": receipt["issuer"]["adapter_id"],
        "issuer_signer_id": receipt["issuer"]["signer_id"],
        "host_id": receipt["issuer"]["host_id"],
        "scope": receipt["scope"],
        "evidence": receipt["evidence"],
        "issued_at": receipt["issued_at"],
        "expires_at": receipt["expires_at"],
        "conflicts": receipt["conflicts"],
        "verified_evidence": verified_evidence,
        "signed_receipt": receipt,
        **trust_verification,
    }
    evidence_id = store.add_evidence(
        uri=source_uri,
        source_kind="search-authority-receipt",
        sha256=source_sha256,
        locator=receipt["receipt_ref"],
        effective_at=receipt["issued_at"],
        confidence=1.0,
        sensitivity="user-local",
        metadata=metadata,
    )
    if owns_transaction:
        store.commit()
    return {
        "schema": "system-explorer.search-authority-import.v1",
        "status": "imported",
        "receipt_ref": receipt["receipt_ref"],
        "authority_type": receipt["authority_type"],
        "decision_ref": receipt["decision_ref"],
        "delegation_ref": receipt["delegation_ref"],
        "evidence_id": evidence_id,
        "source_sha256": source_sha256,
        "signer_id": receipt["issuer"]["signer_id"],
        "trust_store_content_hash": trust_store.content_hash,
    }


def resolve_authority_receipts(
    store: Store,
    receipt_refs: list[str],
    *,
    query_mode: str,
    scope: str,
    component_ref: str | None,
    capabilities: list[str],
    observed_at: str,
    trust_store: ReceiptTrustStore,
    expected_host_id: str,
) -> list[dict[str, Any]]:
    observed = _timestamp(observed_at, "observed_at")
    evidence = [
        item
        for item in store.evidence()
        if item["source_kind"] == "search-authority-receipt"
        and item.get("metadata", {}).get("signature_verified") is True
    ]
    results = []
    for receipt_ref in receipt_refs:
        matches = [
            item
            for item in evidence
            if item["metadata"].get("receipt_ref") == receipt_ref
        ]
        if not matches:
            results.append(
                {
                    "receipt_ref": receipt_ref,
                    "authority_type": None,
                    "decision_ref": None,
                    "evidence_id": None,
                    "status": "blocked",
                    "reasons": ["authority-receipt-not-found"],
                }
            )
            continue
        verified_matches = []
        for item in matches:
            signed_receipt = item["metadata"].get("signed_receipt")
            try:
                if (
                    not isinstance(signed_receipt, dict)
                    or signed_receipt.get("receipt_ref") != receipt_ref
                ):
                    raise ValueError("stored authority receipt does not match ref")
                issued = _timestamp(
                    signed_receipt["issued_at"],
                    "authority.issued_at",
                )
                validate_search_authority_receipt(
                    signed_receipt,
                    evaluated_at=signed_receipt["issued_at"],
                    expected_host_id=expected_host_id,
                    trust_store=trust_store,
                )
                _verify_local_evidence(store, signed_receipt)
                verified_matches.append((item, signed_receipt, issued))
            except (KeyError, TypeError, ValueError):
                continue
        if not verified_matches:
            results.append(
                {
                    "receipt_ref": receipt_ref,
                    "authority_type": None,
                    "decision_ref": None,
                    "evidence_id": None,
                    "status": "blocked",
                    "reasons": ["authority-receipt-reverification-failed"],
                }
            )
            continue
        newest_time = max(item[2] for item in verified_matches)
        newest = [item for item in verified_matches if item[2] == newest_time]
        if len({item[1]["content_hash"] for item in newest}) != 1:
            results.append(
                {
                    "receipt_ref": receipt_ref,
                    "authority_type": None,
                    "decision_ref": None,
                    "evidence_id": None,
                    "status": "blocked",
                    "reasons": ["authority-receipt-revision-conflict"],
                }
            )
            continue
        item, signed_receipt, _ = newest[0]
        reasons = []
        authority = signed_receipt
        receipt_scope = authority["scope"]
        if query_mode not in receipt_scope["query_modes"]:
            reasons.append("query-mode-out-of-scope")
        if scope not in receipt_scope["system_instance_ids"]:
            reasons.append("system-scope-out-of-scope")
        if expected_host_id not in receipt_scope["host_ids"]:
            reasons.append("host-out-of-scope")
        if component_ref and component_ref not in receipt_scope["component_refs"]:
            reasons.append("component-out-of-scope")
        if not set(capabilities) <= set(receipt_scope["capabilities"]):
            reasons.append("capability-out-of-scope")
        if observed < _timestamp(authority["issued_at"], "authority.issued_at"):
            reasons.append("authority-not-yet-effective")
        if observed > _timestamp(authority["expires_at"], "authority.expires_at"):
            reasons.append("authority-expired")
        if authority["conflicts"]:
            reasons.append("authority-conflict")
        if (
            authority["authority_type"] == "delegated-avatar-decision"
            and authority["confidence"] < authority["minimum_confidence"]
        ):
            reasons.append("delegated-confidence-below-threshold")
        results.append(
            {
                "receipt_ref": receipt_ref,
                "authority_type": authority["authority_type"],
                "decision_ref": authority["decision_ref"],
                "delegation_ref": authority["delegation_ref"],
                "evidence_id": item["id"],
                "status": "blocked" if reasons else "passed",
                "reasons": sorted(reasons),
            }
        )
    return results


def validate_search_authority_receipt(
    receipt: Any,
    *,
    evaluated_at: str,
    expected_host_id: str,
    trust_store: ReceiptTrustStore,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ValueError("search authority receipt must be an object")
    unknown = sorted(set(receipt) - ROOT_FIELDS)
    missing = sorted(ROOT_FIELDS - set(receipt))
    if unknown:
        raise ValueError(
            "search authority receipt has unknown fields: " + ", ".join(unknown)
        )
    if missing:
        raise ValueError(
            "search authority receipt is missing fields: " + ", ".join(missing)
        )
    if receipt["schema"] != RECEIPT_SCHEMA:
        raise ValueError(f"search authority receipt must use {RECEIPT_SCHEMA}")
    _stable_ref(receipt["receipt_ref"], "receipt_ref")
    authority_type = receipt["authority_type"]
    if authority_type not in AUTHORITY_TYPES:
        raise ValueError("search authority receipt authority_type is unsupported")
    _stable_ref(receipt["decision_ref"], "decision_ref")
    delegation_ref = receipt["delegation_ref"]
    if authority_type == "delegated-avatar-decision":
        _stable_ref(delegation_ref, "delegation_ref")
        if receipt["decision_kind"] != "predicted":
            raise ValueError("delegated avatar decision_kind must be predicted")
    else:
        if delegation_ref is not None:
            raise ValueError("direct and policy authority must not use delegation_ref")
        if receipt["decision_kind"] != "explicit":
            raise ValueError("direct and policy authority decision_kind must be explicit")
    for field in ("confidence", "minimum_confidence"):
        value = receipt[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 1
        ):
            raise ValueError(f"{field} must be between 0 and 1")

    issuer = _exact_object(
        receipt["issuer"],
        "issuer",
        {"ref", "adapter_id", "signer_id", "host_id"},
    )
    _stable_ref(issuer["ref"], "issuer.ref")
    _stable_ref(issuer["signer_id"], "issuer.signer_id")
    if issuer["host_id"] != expected_host_id:
        raise ValueError("search authority issuer host_id mismatch")

    scope = receipt["scope"]
    scope_fields = {
        "query_modes",
        "system_instance_ids",
        "host_ids",
        "component_refs",
        "capabilities",
    }
    if not isinstance(scope, dict) or set(scope) != scope_fields:
        raise ValueError("search authority scope has invalid fields")
    _unique_strings(scope["query_modes"], "scope.query_modes")
    if not set(scope["query_modes"]) <= QUERY_MODES:
        raise ValueError("search authority scope has unsupported query mode")
    _unique_strings(scope["system_instance_ids"], "scope.system_instance_ids")
    _unique_strings(scope["host_ids"], "scope.host_ids")
    if expected_host_id not in scope["host_ids"]:
        raise ValueError("search authority scope does not include expected host")
    _unique_refs(scope["component_refs"], "scope.component_refs")
    _unique_strings(scope["capabilities"], "scope.capabilities")

    evidence = receipt["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("search authority evidence must be non-empty")
    _validate_evidence_items(evidence, "evidence")
    conflicts = receipt["conflicts"]
    if not isinstance(conflicts, list):
        raise ValueError("search authority conflicts must be a list")
    _validate_evidence_items(conflicts, "conflicts")

    issued_at = _timestamp(receipt["issued_at"], "issued_at")
    expires_at = _timestamp(receipt["expires_at"], "expires_at")
    evaluated = _timestamp(evaluated_at, "evaluated_at")
    if evaluated < issued_at:
        raise ValueError("search authority receipt is not yet effective")
    if evaluated > expires_at:
        raise ValueError("search authority receipt is expired")
    return verify_signed_receipt(
        receipt,
        trust_store,
        receipt_schema=RECEIPT_SCHEMA,
        actor=issuer,
        actor_kind="issuer",
        host_id=expected_host_id,
        issued_at=issued_at,
        expires_at=expires_at,
        authority_type=authority_type,
        delegation_ref=delegation_ref,
    )


def _verify_local_evidence(
    store: Store,
    receipt: dict[str, Any],
) -> list[dict[str, str]]:
    """Bind every authority reference to one local, hashed decision artifact."""

    required_kind = AUTHORITY_REQUIRED_SOURCE_KIND[receipt["authority_type"]]
    verified: list[dict[str, str]] = []
    required_kind_seen = False
    local_evidence = store.evidence()
    for field in ("evidence", "conflicts"):
        for index, reference in enumerate(receipt[field]):
            matches = []
            for candidate in local_evidence:
                metadata = candidate.get("metadata", {})
                candidate_refs = {
                    candidate.get("id"),
                    candidate.get("uri"),
                    candidate.get("locator"),
                    metadata.get("evidence_ref"),
                    metadata.get("ref"),
                }
                if reference["ref"] in candidate_refs:
                    matches.append(candidate)
            location = f"{field}[{index}]"
            if len(matches) != 1:
                raise ValueError(
                    f"{location} reference {reference['ref']!r} is not uniquely "
                    "present in the local evidence store"
                )
            candidate = matches[0]
            if candidate.get("sha256") != reference["sha256"]:
                raise ValueError(
                    f"{location} reference {reference['ref']!r} SHA-256 mismatch"
                )
            source_kind = candidate.get("source_kind")
            if source_kind not in AUTHORITY_EVIDENCE_SOURCE_KINDS:
                raise ValueError(
                    f"{location} reference {reference['ref']!r} has a non-authorizing "
                    f"evidence kind: {source_kind!r}"
                )
            metadata = candidate.get("metadata", {})
            if metadata.get("external") is True or metadata.get("read_only") is True:
                raise ValueError(
                    f"{location} reference {reference['ref']!r} is external/read-only"
                )
            required_kind_seen = required_kind_seen or source_kind == required_kind
            verified.append(
                {
                    "ref": reference["ref"],
                    "sha256": reference["sha256"],
                    "source_kind": source_kind,
                    "evidence_id": str(candidate["id"]),
                    "source_uri": str(candidate["uri"]),
                }
            )
    if not required_kind_seen:
        raise ValueError(
            f"authority receipt requires at least one {required_kind} evidence item"
        )
    return verified


def _validate_evidence_items(items: list[Any], path: str) -> None:
    seen = set()
    for index, item in enumerate(items):
        value = _exact_object(item, f"{path}[{index}]", {"ref", "sha256"})
        ref = _stable_ref(value["ref"], f"{path}[{index}].ref")
        _sha256(value["sha256"], f"{path}[{index}].sha256")
        if ref in seen:
            raise ValueError(f"{path} contains duplicate refs")
        seen.add(ref)


def _unique_refs(value: Any, path: str) -> None:
    _unique_strings(value, path)
    for item in value:
        _stable_ref(item, path)
