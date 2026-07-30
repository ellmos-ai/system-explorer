from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import canonical_content_hash
from .store import Store
from .util import file_effective_date, json_dumps, stable_id, utc_now


SCHEMA = "system-explorer.function-equivalence.v1"
HASH_RE = re.compile(r"\A[0-9a-f]{64}\Z")
URI_RE = re.compile(r"\A[a-z][a-z0-9+.-]*://", re.IGNORECASE)
COMPONENT_PREFIXES = ("module:", "skill:", "software:")
POSITIVE_ACTUAL_STATUSES = {"observed", "partial", "full", "fulfilled"}
POSITIVE_FUNCTION_EVIDENCE_KINDS = {
    "apiprober-export",
    "command-resolution",
    "native-probe",
    "path-resolution",
    "runtime-readback",
}
TOP_LEVEL_FIELDS = {
    "schema",
    "id",
    "version",
    "status",
    "scope",
    "mappings",
    "runtime_actions",
    "target_mutations",
    "content_hash",
}
SCOPE_FIELDS = {
    "template": {"kind"},
    "host-override": {"kind", "host_id", "reason"},
}
MAPPING_FIELDS = {
    "relation",
    "direction",
    "component_ref",
    "desired_function",
    "actual_function",
    "desired_contract",
    "actual_contract",
    "authority_ref",
    "evidence",
}
DESIRED_CONTRACT_FIELDS = {"schema", "id", "version", "content_hash"}
ACTUAL_CONTRACT_FIELDS = {"schema", "version", "content_hash"}
EVIDENCE_FIELDS = {"uri", "sha256", "source_kind", "authority_ref"}


def import_function_equivalence(path: Path, store: Store) -> dict[str, Any]:
    source_bytes, source_stat = _read_snapshot(path)
    value = json.loads(source_bytes.decode("utf-8"))
    _validate_contract(value)
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    effective_at = file_effective_date(
        path,
        fallback_timestamp=source_stat.st_mtime,
    )
    generation = _generation(effective_at, source_stat.st_mtime_ns)
    scope = value["scope"]
    scope_key = (
        "template"
        if scope["kind"] == "template"
        else f"host:{scope['host_id']}"
    )
    projection_key = (
        f"function-equivalence:{scope_key}:{value['id']}"
    )

    store.begin_immediate()
    try:
        state = _projection_state(store, projection_key)
        if state:
            active_generation = tuple(state["generation"])
            if generation < active_generation:
                result = _result(
                    value,
                    projection_key=projection_key,
                    source_digest=source_digest,
                    status="stale-ignored",
                    materialization=_current_materialization(store),
                )
                store.rollback()
                return result
            if generation == active_generation:
                if state["content_hash"] != value["content_hash"]:
                    raise ValueError(
                        "function equivalence generation conflicts with "
                        "the active projection"
                    )
                materialization = _rebuild_materialized_equivalences(store)
                store.commit()
                return _result(
                    value,
                    projection_key=projection_key,
                    source_digest=source_digest,
                    status="unchanged",
                    materialization=materialization,
                )

        evidence_id = store.add_evidence(
            uri=path.resolve().as_uri(),
            source_kind="function-equivalence",
            sha256=source_digest,
            effective_at=effective_at,
            modified_at=str(source_stat.st_mtime),
            confidence=1.0,
            sensitivity="user-local",
            metadata={
                "source_schema": SCHEMA,
                "contract_id": value["id"],
                "contract_content_hash": value["content_hash"],
                "scope": scope,
                "projection_key": projection_key,
                "generation": list(generation),
            },
        )
        store.db.execute(
            "DELETE FROM function_equivalence_claims WHERE projection_key = ?",
            (projection_key,),
        )
        for mapping in value["mappings"]:
            claim_id = stable_id(
                "function-equivalence-claim",
                projection_key,
                mapping["component_ref"],
                mapping["desired_function"],
            )
            store.db.execute(
                """
                INSERT INTO function_equivalence_claims
                (id, projection_key, source_uri, generation_json,
                 contract_content_hash, scope_kind, scope_host_id,
                 component_ref, desired_function, actual_function,
                 desired_contract_json, actual_contract_json, authority_ref,
                 mapping_evidence_json, evidence_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    projection_key,
                    path.resolve().as_uri(),
                    json_dumps(list(generation)),
                    value["content_hash"],
                    scope["kind"],
                    scope.get("host_id"),
                    mapping["component_ref"],
                    mapping["desired_function"],
                    mapping["actual_function"],
                    json_dumps(mapping["desired_contract"]),
                    json_dumps(mapping["actual_contract"]),
                    mapping["authority_ref"],
                    json_dumps(mapping["evidence"]),
                    evidence_id,
                    utc_now(),
                ),
            )
        materialization = _rebuild_materialized_equivalences(store)
        store.commit()
        return _result(
            value,
            projection_key=projection_key,
            source_digest=source_digest,
            status="imported",
            materialization=materialization,
        )
    except BaseException:
        if store.in_transaction:
            store.rollback()
        raise


def reconcile_function_equivalence_projections(
    store: Store, allowed_projection_keys: set[str]
) -> dict[str, Any]:
    store.begin_immediate()
    try:
        existing = {
            row["projection_key"]
            for row in store.db.execute(
                """
                SELECT DISTINCT projection_key
                FROM function_equivalence_claims
                """
            ).fetchall()
        }
        removed = sorted(existing - allowed_projection_keys)
        if removed:
            store.db.executemany(
                """
                DELETE FROM function_equivalence_claims
                WHERE projection_key = ?
                """,
                ((projection,) for projection in removed),
            )
        materialization = _rebuild_materialized_equivalences(store)
        store.commit()
        return {
            "removed_projections": removed,
            **materialization,
            "runtime_actions": [],
            "target_mutations": [],
        }
    except BaseException:
        if store.in_transaction:
            store.rollback()
        raise


def _projection_state(
    store: Store, projection_key: str
) -> dict[str, Any] | None:
    rows = store.db.execute(
        """
        SELECT DISTINCT generation_json, contract_content_hash
        FROM function_equivalence_claims
        WHERE projection_key = ?
        """,
        (projection_key,),
    ).fetchall()
    if not rows:
        return None
    states = [
        {
            "generation": json.loads(row["generation_json"]),
            "content_hash": row["contract_content_hash"],
        }
        for row in rows
    ]
    generations = {tuple(state["generation"]) for state in states}
    hashes = {state["content_hash"] for state in states}
    if len(generations) != 1 or len(hashes) != 1:
        raise ValueError(
            "function equivalence projection has conflicting active state"
        )
    return states[0]


def _rebuild_materialized_equivalences(store: Store) -> dict[str, Any]:
    _clear_materialized_edges(store)
    claims = [
        _claim_from_row(row)
        for row in store.db.execute(
            """
            SELECT *
            FROM function_equivalence_claims
            ORDER BY component_ref, desired_function, projection_key
            """
        ).fetchall()
    ]
    nodes = {node["id"]: node for node in store.nodes()}
    evidence = {item["id"]: item for item in store.evidence()}
    evidence_refs = {
        (item["uri"], item.get("sha256"), item.get("source_kind")): item["id"]
        for item in evidence.values()
    }
    desired_edges = [
        edge
        for edge in store.resolved_edges("desired")
        if edge["relation"] == "carries"
    ]
    actual_edges = [
        edge
        for edge in store.resolved_edges("actual")
        if edge["relation"] == "carries"
        and not edge.get("metadata", {}).get(
            "function_equivalence_projection"
        )
    ]

    applicable: dict[
        tuple[str, str, str, str], list[dict[str, Any]]
    ] = defaultdict(list)
    missing_desired = []
    missing_evidence = []
    for claim in claims:
        if any(
            (item["uri"], item["sha256"], item["source_kind"])
            not in evidence_refs
            for item in claim["mapping_evidence"]
        ):
            missing_evidence.append(_claim_summary(claim))
            continue
        matches = [
            edge
            for edge in desired_edges
            if edge["target_id"]
            == _function_id(claim["desired_function"])
            and _desired_edge_matches(edge, nodes, claim)
        ]
        if not matches:
            missing_desired.append(_claim_summary(claim))
            continue
        for edge in matches:
            host_id = edge.get("metadata", {}).get("resolution_host_id")
            key = (
                str(host_id),
                claim["component_ref"],
                claim["desired_function"],
                claim["desired_contract"]["content_hash"],
            )
            applicable[key].append({**claim, "host_id": host_id})

    conflicts = []
    missing_actual = []
    materialized = 0
    for key, group in sorted(applicable.items()):
        if len(group) != 1:
            conflicts.append(
                {
                    "host_id": key[0],
                    "component_ref": key[1],
                    "desired_function": key[2],
                    "desired_contract_hash": key[3],
                    "projection_keys": sorted(
                        claim["projection_key"] for claim in group
                    ),
                }
            )
            continue
        claim = group[0]
        matching_actual = [
            edge
            for edge in actual_edges
            if edge["target_id"] == _function_id(claim["actual_function"])
            and edge["status"] in POSITIVE_ACTUAL_STATUSES
            and _actual_edge_evidence_matches(edge, evidence)
            and _actual_carrier_matches(
                nodes.get(edge["source_id"], {}), claim, evidence
            )
        ]
        if not matching_actual:
            missing_actual.append(_claim_summary(claim))
            continue
        for actual_edge in matching_actual:
            store.add_edge(
                actual_edge["source_id"],
                "carries",
                _function_id(claim["desired_function"]),
                mode="actual",
                status=actual_edge["status"],
                confidence=min(float(actual_edge["confidence"]), 1.0),
                evidence_id=claim["evidence_id"],
                metadata={
                    "function_equivalence_projection": claim[
                        "projection_key"
                    ],
                    "function_equivalence_contract_hash": claim[
                        "contract_content_hash"
                    ],
                    "function_equivalence_relation": "exact-equivalence",
                    "function_equivalence_direction": (
                        "actual-satisfies-desired"
                    ),
                    "component_ref": claim["component_ref"],
                    "desired_function": claim["desired_function"],
                    "actual_function": claim["actual_function"],
                    "host_id": claim["host_id"],
                    "desired_contract": claim["desired_contract"],
                    "actual_contract": claim["actual_contract"],
                    "authority_ref": claim["authority_ref"],
                    "mapping_evidence_ids": sorted(
                        evidence_refs[
                            (
                                item["uri"],
                                item["sha256"],
                                item["source_kind"],
                            )
                        ]
                        for item in claim["mapping_evidence"]
                    ),
                    "source_actual_edge_id": actual_edge["id"],
                    "source_actual_evidence_id": actual_edge.get(
                        "evidence_id"
                    ),
                },
            )
            materialized += 1
    return {
        "active_claims": len(claims),
        "materialized_edges": materialized,
        "conflicts": conflicts,
        "missing_evidence": missing_evidence,
        "missing_desired": missing_desired,
        "missing_actual": missing_actual,
    }


def _desired_edge_matches(
    edge: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    claim: dict[str, Any],
) -> bool:
    metadata = edge.get("metadata", {})
    host_id = metadata.get("resolution_host_id")
    if not isinstance(host_id, str) or not host_id:
        return False
    if (
        claim["scope_kind"] == "host-override"
        and claim["scope_host_id"] != host_id
    ):
        return False
    if claim["component_ref"] not in _node_refs(
        nodes.get(edge["source_id"], {})
    ):
        return False
    desired_contract = claim["desired_contract"]
    return any(
        source.get("bundle_schema") == desired_contract["schema"]
        and source.get("bundle_id") == desired_contract["id"]
        and source.get("bundle_version") == desired_contract["version"]
        and source.get("bundle_content_hash")
        == desired_contract["content_hash"]
        for source in metadata.get("sources", [])
        if isinstance(source, dict)
    )


def _actual_carrier_matches(
    node: dict[str, Any],
    claim: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> bool:
    metadata = node.get("metadata", {})
    actual_contract = claim["actual_contract"]
    identity_evidence = evidence.get(metadata.get("identity_evidence_id"))
    return (
        metadata.get("origin_system") == claim["host_id"]
        and metadata.get("identity_status") == "verified"
        and metadata.get("component_ref") == claim["component_ref"]
        and metadata.get("identity_contract_schema")
        == actual_contract["schema"]
        and metadata.get("identity_contract_version")
        == actual_contract["version"]
        and metadata.get("identity_source_sha256")
        == actual_contract["content_hash"]
        and identity_evidence is not None
        and identity_evidence.get("source_kind")
        in {"manifest", "entrypoint"}
        and identity_evidence.get("sha256")
        == actual_contract["content_hash"]
    )


def _actual_edge_evidence_matches(
    edge: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> bool:
    actual_evidence = evidence.get(edge.get("evidence_id"))
    if actual_evidence is None:
        return False
    source_kind = actual_evidence.get("source_kind")
    if not isinstance(source_kind, str):
        return False
    kind_allowed = (
        source_kind in POSITIVE_FUNCTION_EVIDENCE_KINDS
        or source_kind.startswith(
            ("probe:", "readback:", "runtime:", "transcript:")
        )
    )
    return kind_allowed and bool(
        HASH_RE.fullmatch(str(actual_evidence.get("sha256", "")))
    )


def _clear_materialized_edges(store: Store) -> None:
    rows = store.db.execute(
        """
        SELECT id, metadata_json
        FROM edges
        WHERE relation = 'carries' AND mode = 'actual'
        """
    ).fetchall()
    edge_ids = [
        row["id"]
        for row in rows
        if json.loads(row["metadata_json"]).get(
            "function_equivalence_projection"
        )
    ]
    if edge_ids:
        store.db.executemany(
            "DELETE FROM edges WHERE id = ?",
            ((edge_id,) for edge_id in edge_ids),
        )


def _current_materialization(store: Store) -> dict[str, Any]:
    claims = store.db.execute(
        "SELECT COUNT(*) FROM function_equivalence_claims"
    ).fetchone()[0]
    rows = store.db.execute(
        """
        SELECT metadata_json
        FROM edges
        WHERE relation = 'carries' AND mode = 'actual'
        """
    ).fetchall()
    materialized = sum(
        1
        for row in rows
        if json.loads(row["metadata_json"]).get(
            "function_equivalence_projection"
        )
    )
    return {
        "active_claims": claims,
        "materialized_edges": materialized,
        "conflicts": [],
        "missing_evidence": [],
        "missing_desired": [],
        "missing_actual": [],
    }


def _claim_from_row(row: Any) -> dict[str, Any]:
    claim = dict(row)
    claim["desired_contract"] = json.loads(
        claim.pop("desired_contract_json")
    )
    claim["actual_contract"] = json.loads(
        claim.pop("actual_contract_json")
    )
    claim["mapping_evidence"] = json.loads(
        claim.pop("mapping_evidence_json")
    )
    return claim


def _result(
    value: dict[str, Any],
    *,
    projection_key: str,
    source_digest: str,
    status: str,
    materialization: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "system-explorer.function-equivalence-import.v1",
        "source_schema": value["schema"],
        "contract_id": value["id"],
        "content_hash": value["content_hash"],
        "source_sha256": source_digest,
        "projection_key": projection_key,
        "scope": value["scope"],
        "status": status,
        "mappings": len(value["mappings"]),
        **materialization,
        "runtime_actions": [],
        "target_mutations": [],
    }


def _claim_summary(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "projection_key": claim["projection_key"],
        "scope_kind": claim["scope_kind"],
        "scope_host_id": claim["scope_host_id"],
        "host_id": claim.get("host_id"),
        "component_ref": claim["component_ref"],
        "desired_function": claim["desired_function"],
        "actual_function": claim["actual_function"],
    }


def _node_refs(node: dict[str, Any]) -> set[str]:
    metadata = node.get("metadata", {})
    refs = set()
    for field in ("component_ref", "stable_ref"):
        value = metadata.get(field)
        if isinstance(value, str) and value:
            refs.add(value)
    return refs


def _function_id(function_name: str) -> str:
    return f"function:{function_name}"


def _read_snapshot(path: Path) -> tuple[bytes, os.stat_result]:
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        source = handle.read()
        after = os.fstat(handle.fileno())
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or len(source) != after.st_size:
        raise ValueError(
            "function equivalence source changed while it was being read"
        )
    return source, after


def _generation(
    effective_at: str, source_mtime_ns: int
) -> tuple[int, int]:
    effective_ns = int(
        datetime.fromisoformat(effective_at).timestamp() * 1_000_000_000
    )
    return effective_ns, source_mtime_ns


def _validate_contract(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("function equivalence contract must be an object")
    unknown = set(value) - TOP_LEVEL_FIELDS
    missing = TOP_LEVEL_FIELDS - set(value)
    if unknown:
        raise ValueError(
            "function equivalence contract has unknown fields: "
            + ", ".join(sorted(unknown))
        )
    if missing:
        raise ValueError(
            "function equivalence contract is missing fields: "
            + ", ".join(sorted(missing))
        )
    if value["schema"] != SCHEMA:
        raise ValueError("unsupported function equivalence schema")
    if (
        not isinstance(value["id"], str)
        or not value["id"].startswith("function-equivalence:")
    ):
        raise ValueError(
            "function equivalence id must start with function-equivalence:"
        )
    if not isinstance(value["version"], str) or not value["version"]:
        raise ValueError("function equivalence version must be non-empty")
    if value["status"] != "active":
        raise ValueError("only active function equivalence contracts import")
    _validate_scope(value["scope"])
    if value["runtime_actions"] != [] or value["target_mutations"] != []:
        raise ValueError(
            "function equivalence contracts cannot contain runtime actions "
            "or target mutations"
        )
    mappings = value["mappings"]
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("function equivalence mappings must be non-empty")
    seen: set[tuple[str, str]] = set()
    for index, mapping in enumerate(mappings):
        _validate_mapping(mapping, index)
        key = (mapping["component_ref"], mapping["desired_function"])
        if key in seen:
            raise ValueError(
                "function equivalence contract has duplicate mapping target"
            )
        seen.add(key)
    _validate_hash(value["content_hash"], "content_hash")
    if canonical_content_hash(value) != value["content_hash"]:
        raise ValueError("function equivalence content_hash mismatch")


def _validate_scope(scope: Any) -> None:
    if not isinstance(scope, dict) or scope.get("kind") not in SCOPE_FIELDS:
        raise ValueError("function equivalence scope is invalid")
    if set(scope) != SCOPE_FIELDS[scope["kind"]]:
        raise ValueError(
            "function equivalence scope fields do not match its kind"
        )
    if scope["kind"] == "host-override":
        _validate_token(scope["host_id"], "scope.host_id")
        if not isinstance(scope["reason"], str) or not scope["reason"].strip():
            raise ValueError("scope.reason must be non-empty")


def _validate_mapping(mapping: Any, index: int) -> None:
    if not isinstance(mapping, dict):
        raise ValueError(f"mappings[{index}] must be an object")
    if set(mapping) != MAPPING_FIELDS:
        raise ValueError(
            f"mappings[{index}] must contain exactly the contract fields"
        )
    if mapping["relation"] != "exact-equivalence":
        raise ValueError(
            f"mappings[{index}].relation must be exact-equivalence"
        )
    if mapping["direction"] != "actual-satisfies-desired":
        raise ValueError(
            f"mappings[{index}].direction must be "
            "actual-satisfies-desired"
        )
    component_ref = mapping["component_ref"]
    if (
        not isinstance(component_ref, str)
        or not component_ref.startswith(COMPONENT_PREFIXES)
    ):
        raise ValueError(
            f"mappings[{index}].component_ref must be a typed component ref"
        )
    _validate_token(
        mapping["desired_function"],
        f"mappings[{index}].desired_function",
    )
    _validate_token(
        mapping["actual_function"],
        f"mappings[{index}].actual_function",
    )
    if mapping["desired_function"] == mapping["actual_function"]:
        raise ValueError(
            f"mappings[{index}] must not restate an identical function id"
        )
    _validate_contract_pin(
        mapping["desired_contract"],
        DESIRED_CONTRACT_FIELDS,
        f"mappings[{index}].desired_contract",
    )
    _validate_contract_pin(
        mapping["actual_contract"],
        ACTUAL_CONTRACT_FIELDS,
        f"mappings[{index}].actual_contract",
    )
    if (
        not isinstance(mapping["authority_ref"], str)
        or not mapping["authority_ref"].startswith(
            ("decision:", "policy:")
        )
    ):
        raise ValueError(
            f"mappings[{index}].authority_ref must be a typed decision "
            "or policy ref"
        )
    evidence = mapping["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"mappings[{index}].evidence must be non-empty")
    authority_kind = mapping["authority_ref"].split(":", 1)[0]
    expected_source_kind = f"document:{authority_kind}"
    authority_evidence_present = False
    for evidence_index, item in enumerate(evidence):
        if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
            raise ValueError(
                f"mappings[{index}].evidence[{evidence_index}] is invalid"
            )
        if (
            not isinstance(item["uri"], str)
            or not URI_RE.match(item["uri"])
        ):
            raise ValueError(
                f"mappings[{index}].evidence[{evidence_index}].uri "
                "must be absolute"
            )
        if item["source_kind"] not in {
            "document:decision",
            "document:policy",
        }:
            raise ValueError(
                f"mappings[{index}].evidence[{evidence_index}].source_kind "
                "must be decision or policy evidence"
            )
        if item["source_kind"] == expected_source_kind:
            authority_evidence_present = True
        if item["authority_ref"] != mapping["authority_ref"]:
            raise ValueError(
                f"mappings[{index}].evidence[{evidence_index}] must bind "
                "the mapping authority_ref"
            )
        _validate_hash(
            item["sha256"],
            f"mappings[{index}].evidence[{evidence_index}].sha256",
        )
    if not authority_evidence_present:
        raise ValueError(
            f"mappings[{index}].evidence must include evidence matching "
            "authority_ref"
        )


def _validate_contract_pin(
    value: Any, required_fields: set[str], field: str
) -> None:
    if not isinstance(value, dict) or set(value) != required_fields:
        raise ValueError(f"{field} fields are invalid")
    _validate_token(value["schema"], f"{field}.schema")
    if "id" in required_fields:
        _validate_token(value["id"], f"{field}.id")
    _validate_token(value["version"], f"{field}.version")
    _validate_hash(value["content_hash"], f"{field}.content_hash")


def _validate_token(value: Any, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{field} must be a non-whitespace token")


def _validate_hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256")
