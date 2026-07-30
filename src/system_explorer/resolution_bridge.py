from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import OPERATIONAL_STATUSES, canonical_content_hash
from .store import Store
from .util import file_effective_date, stable_id


REQUIREMENTS = ("required", "recommended", "optional")


def import_resolution(path: Path, store: Store) -> dict[str, Any]:
    source_bytes, source_stat = _read_resolution_snapshot(path)
    value = json.loads(source_bytes.decode("utf-8"))
    _validate_resolution(value)
    resolution_hash = value["content_hash"]
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    effective_at = file_effective_date(
        path,
        fallback_timestamp=source_stat.st_mtime,
    )
    generation = _generation(effective_at, source_stat.st_mtime_ns)
    system = value["system"]
    instance = value.get("instance")
    scope = instance.get("instance_id") if instance else system["id"]
    host_id = instance.get("host_id") if instance else None
    projection_key = f"resolution:{scope}"

    carriers: dict[str, dict[str, Any]] = {}
    provider_sources: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    function_requirements: dict[str, set[str]] = defaultdict(set)
    empty_provides = 0
    inactive_provides = 0

    for bundle in value["bundles"]:
        bundle_source = {
            "bundle_id": bundle["id"],
            "bundle_content_hash": bundle.get("content_hash"),
        }
        for component in bundle.get("components", []):
            ref = _ref_name(component["ref"])
            requirement = component["requirement"]
            desired_status = component["desired_status"]
            provides = list(component.get("provides", []))
            consumes = list(component.get("consumes", []))
            if not provides:
                empty_provides += 1
            carrier = carriers.setdefault(
                ref,
                {
                    "types": set(),
                    "requirements": set(),
                    "desired_statuses": set(),
                    "roles": set(),
                    "provides": set(),
                    "consumes": set(),
                    "bundles": set(),
                },
            )
            carrier["types"].add(component["type"])
            carrier["requirements"].add(requirement)
            carrier["desired_statuses"].add(desired_status)
            carrier["roles"].add(component.get("role", ""))
            carrier["provides"].update(provides)
            carrier["consumes"].update(consumes)
            carrier["bundles"].add(bundle["id"])
            if desired_status in {"suppressed", "unavailable"}:
                inactive_provides += len(provides)
                continue
            for function in provides:
                function_requirements[function].add(requirement)
                provider_sources[(ref, function)].append(
                    {
                        **bundle_source,
                        "requirement": requirement,
                        "desired_status": desired_status,
                    }
                )

    declared_functions = set(value["functions"])
    active_provides = set(function_requirements)
    if active_provides != declared_functions:
        raise ValueError(
            "resolution functions do not match active component provides"
        )

    active_projection = store.resolution_projection_state(projection_key)
    if active_projection:
        active_generation = tuple(active_projection["generation"])
        if generation < active_generation:
            return _import_result(
                value,
                source_digest=source_digest,
                carriers=carriers,
                function_requirements=function_requirements,
                provider_sources=provider_sources,
                empty_provides=empty_provides,
                inactive_provides=inactive_provides,
                status="stale-ignored",
            )
        if generation == active_generation:
            if active_projection["content_hash"] != resolution_hash:
                raise ValueError(
                    "resolution generation conflicts with the active projection"
                )
            return _import_result(
                value,
                source_digest=source_digest,
                carriers=carriers,
                function_requirements=function_requirements,
                provider_sources=provider_sources,
                empty_provides=empty_provides,
                inactive_provides=inactive_provides,
                status="unchanged",
            )

    evidence_id = store.add_evidence(
        uri=path.resolve().as_uri(),
        source_kind="system-resolution",
        sha256=source_digest,
        effective_at=effective_at,
        modified_at=str(source_stat.st_mtime),
        confidence=1.0,
        sensitivity="user-local",
        metadata={
            "source_schema": value["schema"],
            "resolution_content_hash": resolution_hash,
            "system_id": system["id"],
            "system_content_hash": system.get("content_hash"),
            "instance_id": instance.get("instance_id") if instance else None,
            "instance_content_hash": instance.get("content_hash") if instance else None,
            "desired_profile": value.get("desired_profile"),
            "resolution_scope": scope,
            "resolution_projection": projection_key,
            "resolution_generation": list(generation),
        },
    )
    superseded = store.clear_resolution_projection(projection_key)
    for ref, carrier in sorted(carriers.items()):
        store.add_node(
            "carrier",
            ref,
            node_id=_carrier_id(scope, ref),
            scope=scope,
            metadata={
                "carrier_kind": _single_or_mixed(carrier["types"]),
                "component_ref": ref,
                "desired": True,
                "requirements": sorted(
                    carrier["requirements"], key=_requirement_sort_key
                ),
                "desired_statuses": sorted(carrier["desired_statuses"]),
                "roles": sorted(role for role in carrier["roles"] if role),
                "provides": sorted(carrier["provides"]),
                "consumes": sorted(carrier["consumes"]),
                "source_bundles": sorted(carrier["bundles"]),
                "source_schema": value["schema"],
                "resolution_content_hash": resolution_hash,
                "resolution_scope": scope,
                "resolution_projection": projection_key,
                "resolution_generation": list(generation),
                "resolution_host_id": host_id,
                "resolution_system_id": system["id"],
            },
        )

    existing_function_ids = {node["id"] for node in store.nodes("function")}
    for function in sorted(function_requirements):
        function_id = _function_id(function)
        if function_id not in existing_function_ids:
            store.add_node(
                "function",
                function,
                node_id=function_id,
                scope=None,
                metadata={},
            )
            existing_function_ids.add(function_id)

    for (ref, function), sources in sorted(provider_sources.items()):
        requirements = {source["requirement"] for source in sources}
        desired_statuses = {source["desired_status"] for source in sources}
        store.add_edge(
            _carrier_id(scope, ref),
            "carries",
            _function_id(function),
            mode="desired",
            status="full",
            confidence=1.0,
            evidence_id=evidence_id,
            effective_at=effective_at,
            metadata={
                "requirement": _strongest_requirement(requirements),
                "requirements": sorted(requirements, key=_requirement_sort_key),
                "desired_status": _single_or_mixed(desired_statuses),
                "desired_statuses": sorted(desired_statuses),
                "sources": sorted(
                    sources,
                    key=lambda item: (
                        item["bundle_id"],
                        item["requirement"],
                        item["desired_status"],
                    ),
                ),
                "method": "resolution-v1-bridge",
                "source_schema": value["schema"],
                "resolution_content_hash": resolution_hash,
                "resolution_scope": scope,
                "resolution_projection": projection_key,
                "resolution_generation": list(generation),
                "resolution_host_id": host_id,
                "resolution_system_id": system["id"],
            },
        )

    store.commit()
    return _import_result(
        value,
        source_digest=source_digest,
        carriers=carriers,
        function_requirements=function_requirements,
        provider_sources=provider_sources,
        empty_provides=empty_provides,
        inactive_provides=inactive_provides,
        status="imported",
        superseded=superseded,
    )


def _import_result(
    value: dict[str, Any],
    *,
    source_digest: str,
    carriers: dict[str, dict[str, Any]],
    function_requirements: dict[str, set[str]],
    provider_sources: dict[tuple[str, str], list[dict[str, Any]]],
    empty_provides: int,
    inactive_provides: int,
    status: str,
    superseded: dict[str, int] | None = None,
) -> dict[str, Any]:
    instance = value.get("instance")
    providers_by_function: dict[str, set[str]] = defaultdict(set)
    for ref, function in provider_sources:
        providers_by_function[function].add(ref)
    return {
        "schema": "system-explorer.resolution-import.v1",
        "source_schema": value["schema"],
        "content_hash": value["content_hash"],
        "source_sha256": source_digest,
        "system_id": value["system"]["id"],
        "instance_id": instance.get("instance_id") if instance else None,
        "status": status,
        "carriers": len(carriers),
        "functions": len(function_requirements),
        "desired_edges": len(provider_sources),
        "empty_provides": empty_provides,
        "inactive_provides": inactive_provides,
        "duplicate_provider_functions": sum(
            1 for providers in providers_by_function.values() if len(providers) > 1
        ),
        "runtime_actions": [],
        "target_mutations": [],
        "superseded": superseded or {"edges": 0, "carriers": 0},
    }


def _read_resolution_snapshot(path: Path) -> tuple[bytes, os.stat_result]:
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
        raise ValueError("resolution source changed while it was being read")
    return source, after


def _generation(effective_at: str, source_mtime_ns: int) -> tuple[int, int]:
    effective_ns = int(datetime.fromisoformat(effective_at).timestamp() * 1_000_000_000)
    return effective_ns, source_mtime_ns


def _validate_resolution(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("resolution must be a JSON object")
    if value.get("schema") != "system-explorer.resolution.v1":
        raise ValueError("unsupported resolution schema")
    declared_hash = value.get("content_hash")
    if not isinstance(declared_hash, str) or declared_hash != canonical_content_hash(
        value
    ):
        raise ValueError("resolution content_hash does not match canonical content")
    for field in ("runtime_actions", "target_mutations"):
        if value.get(field) != []:
            raise ValueError(f"resolution {field} must be an explicit empty array")
    if not isinstance(value.get("system"), dict) or not value["system"].get("id"):
        raise ValueError("resolution system.id is required")
    instance = value.get("instance")
    if instance is not None:
        if not isinstance(instance, dict):
            raise ValueError("resolution instance must be an object")
        for field in ("id", "instance_id", "host_id"):
            if not isinstance(instance.get(field), str) or not instance[field]:
                raise ValueError(f"resolution instance requires non-empty {field}")
    if not isinstance(value.get("bundles"), list):
        raise ValueError("resolution bundles must be an array")
    if not isinstance(value.get("functions"), list) or not all(
        isinstance(function, str) and function for function in value["functions"]
    ):
        raise ValueError("resolution functions must be an array of non-empty strings")
    for bundle_index, bundle in enumerate(value["bundles"]):
        if not isinstance(bundle, dict) or not isinstance(bundle.get("id"), str):
            raise ValueError(f"resolution bundle {bundle_index} requires an id")
        components = bundle.get("components", [])
        if not isinstance(components, list):
            raise ValueError(
                f"resolution bundle {bundle['id']!r} components must be an array"
            )
        for component_index, component in enumerate(components):
            location = f"bundle {bundle['id']!r} component {component_index}"
            if not isinstance(component, dict):
                raise ValueError(f"{location} must be an object")
            if not _ref_name(component.get("ref")):
                raise ValueError(f"{location} requires a resolvable ref")
            for field in ("type", "requirement", "desired_status"):
                if not isinstance(component.get(field), str) or not component[field]:
                    raise ValueError(f"{location} requires non-empty {field}")
            if component["requirement"] not in REQUIREMENTS:
                raise ValueError(f"{location} has unsupported requirement")
            if component["desired_status"] not in OPERATIONAL_STATUSES:
                raise ValueError(f"{location} has unsupported desired_status")
            for field in ("provides", "consumes"):
                items = component.get(field, [])
                if not isinstance(items, list) or not all(
                    isinstance(item, str) and item for item in items
                ):
                    raise ValueError(
                        f"{location} {field} must be an array of non-empty strings"
                    )


def _carrier_id(scope: str, ref: str) -> str:
    return stable_id("carrier", scope, ref)


def _ref_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for field in ("ref", "id", "path"):
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate:
                return candidate
    return ""


def _function_id(function: str) -> str:
    return f"function:{function}"


def _strongest_requirement(requirements: set[str]) -> str:
    return min(requirements, key=_requirement_sort_key)


def _requirement_sort_key(requirement: str) -> int:
    return REQUIREMENTS.index(requirement)


def _single_or_mixed(values: set[str]) -> str:
    return next(iter(values)) if len(values) == 1 else "mixed"
