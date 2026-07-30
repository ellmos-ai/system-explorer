from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .contracts import canonical_content_hash
from .store import Store
from .util import file_effective_date, sha256_file


REQUIREMENTS = ("required", "recommended", "optional")


def import_resolution(path: Path, store: Store) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _validate_resolution(value)
    resolution_hash = value["content_hash"]
    source_digest = sha256_file(path)
    effective_at = file_effective_date(path)
    system = value["system"]
    instance = value.get("instance")
    evidence_id = store.add_evidence(
        uri=path.resolve().as_uri(),
        source_kind="system-resolution",
        sha256=source_digest,
        effective_at=effective_at,
        modified_at=str(path.stat().st_mtime),
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
        },
    )

    carriers: dict[str, dict[str, Any]] = {}
    provider_sources: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    function_requirements: dict[str, set[str]] = defaultdict(set)
    empty_provides = 0

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
            for function in provides:
                function_requirements[function].add(requirement)
                provider_sources[(ref, function)].append(
                    {
                        **bundle_source,
                        "requirement": requirement,
                        "desired_status": desired_status,
                    }
                )

    scope = instance.get("instance_id") if instance else system["id"]
    for ref, carrier in sorted(carriers.items()):
        store.add_node(
            "carrier",
            ref,
            node_id=_carrier_id(ref),
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
            },
        )

    for function, requirements in sorted(function_requirements.items()):
        store.add_node(
            "function",
            function,
            node_id=_function_id(function),
            scope=scope,
            metadata={
                "desired": True,
                "requirements": sorted(requirements, key=_requirement_sort_key),
                "effective_requirement": _strongest_requirement(requirements),
                "source_schema": value["schema"],
                "resolution_content_hash": resolution_hash,
            },
        )

    for (ref, function), sources in sorted(provider_sources.items()):
        requirements = {source["requirement"] for source in sources}
        desired_statuses = {source["desired_status"] for source in sources}
        store.add_edge(
            _carrier_id(ref),
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
            },
        )

    store.commit()
    providers_by_function: dict[str, set[str]] = defaultdict(set)
    for ref, function in provider_sources:
        providers_by_function[function].add(ref)
    return {
        "schema": "system-explorer.resolution-import.v1",
        "source_schema": value["schema"],
        "content_hash": resolution_hash,
        "source_sha256": source_digest,
        "system_id": system["id"],
        "instance_id": instance.get("instance_id") if instance else None,
        "carriers": len(carriers),
        "functions": len(function_requirements),
        "desired_edges": len(provider_sources),
        "empty_provides": empty_provides,
        "duplicate_provider_functions": sum(
            1 for providers in providers_by_function.values() if len(providers) > 1
        ),
        "runtime_actions": [],
        "target_mutations": [],
    }


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
    if not isinstance(value.get("bundles"), list):
        raise ValueError("resolution bundles must be an array")
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
            for field in ("provides", "consumes"):
                items = component.get(field, [])
                if not isinstance(items, list) or not all(
                    isinstance(item, str) and item for item in items
                ):
                    raise ValueError(
                        f"{location} {field} must be an array of non-empty strings"
                    )


def _carrier_id(ref: str) -> str:
    return f"carrier:{ref}"


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
