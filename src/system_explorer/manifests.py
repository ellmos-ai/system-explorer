from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    CONTRACT_SCHEMAS,
    HASH_RE,
    canonical_content_hash,
    validate_contract,
)


MODULE_REQUIRED = {
    "schema",
    "id",
    "category",
    "kind",
    "status",
    "visibility",
    "provides",
    "requires",
    "optional",
    "conflicts",
    "surfaces",
    "state",
    "boundaries",
    "source_of_truth",
}
SURFACES = {
    "library",
    "cli",
    "service",
    "ui",
    "workflow",
    "skill",
    "dataset",
    "template",
    "mcp-adapter",
}
NETWORK_BOUNDARIES = {"none", "local", "listed", "optional", "transport-defined"}
DATA_BOUNDARIES = {"none", "public", "user-local", "sensitive", "application-defined"}
PLATFORMS = {"windows", "macos", "linux", "web"}
STACK_PROJECTION_SCHEMA = "ellmos.stack-projection.v1"
STACK_PROJECTION_FIELDS = {
    "schema",
    "id",
    "version",
    "purpose",
    "contract",
    "bundle_refs",
    "optional_bundle_refs",
    "profiles",
    "identity",
    "authority",
    "lifecycle",
    "status",
    "system_ref",
    "access_surfaces",
    "decision_refs",
    "activation_gate",
    "manifest_kind",
    "content_hash",
}


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Manifest root must be an object")
    return value


def validate_manifest(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schema = value.get("schema")
    if schema in CONTRACT_SCHEMAS:
        return validate_contract(value)
    if schema == "ellmos.module.v2":
        missing = sorted(MODULE_REQUIRED - set(value))
        errors.extend(f"missing field: {field}" for field in missing)
        if not isinstance(value.get("provides", []), list):
            errors.append("provides must be a list")
        if not isinstance(value.get("entrypoints", {}), dict):
            errors.append("entrypoints must be an object")
        surfaces = value.get("surfaces", [])
        if not isinstance(surfaces, list) or any(item not in SURFACES for item in surfaces):
            errors.append("surfaces contains an unsupported value")
        state = value.get("state")
        if isinstance(state, dict):
            if set(state) - {"ownership", "location"}:
                errors.append("state contains unsupported fields")
            if state.get("ownership") not in {"module", "external", "none"}:
                errors.append("state.ownership is unsupported")
            if state.get("location") not in {"user-home", "project", "external", "none"}:
                errors.append("state.location is unsupported")
        boundaries = value.get("boundaries")
        if isinstance(boundaries, dict):
            if set(boundaries) - {"network", "data", "platforms"}:
                errors.append("boundaries contains unsupported fields")
            if boundaries.get("network") not in NETWORK_BOUNDARIES:
                errors.append("boundaries.network is unsupported")
            if boundaries.get("data") not in DATA_BOUNDARIES:
                errors.append("boundaries.data is unsupported")
            platforms = boundaries.get("platforms", [])
            if not isinstance(platforms, list) or not platforms or any(
                item not in PLATFORMS for item in platforms
            ):
                errors.append("boundaries.platforms is unsupported")
        adapters = value.get("adapters", [])
        if not isinstance(adapters, list) or any(not isinstance(item, dict) for item in adapters):
            errors.append("adapters must contain objects")
    elif schema == STACK_PROJECTION_SCHEMA:
        _validate_stack_projection(value, errors)
    elif schema == "ellmos.stack.v2":
        if not value.get("id"):
            errors.append("missing field: id")
    else:
        errors.append(f"unsupported schema: {schema!r}")
    return errors


def _validate_stack_projection(value: dict[str, Any], errors: list[str]) -> None:
    required = {"id", "version", "purpose", "bundle_refs", "content_hash"}
    errors.extend(f"missing field: {field}" for field in sorted(required - set(value)))
    errors.extend(
        f"unsupported field: {field}"
        for field in sorted(set(value) - STACK_PROJECTION_FIELDS)
    )
    for field in ("id", "version", "purpose"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            errors.append(f"{field} must be a non-empty string")

    _validate_projection_refs(
        value.get("bundle_refs"),
        "bundle_refs",
        errors,
        pinned=True,
        nonempty=True,
    )
    if "optional_bundle_refs" in value:
        _validate_projection_refs(
            value["optional_bundle_refs"],
            "optional_bundle_refs",
            errors,
            pinned=False,
            nonempty=False,
        )
    for field in ("access_surfaces", "decision_refs"):
        if field in value and (
            not isinstance(value[field], list)
            or any(not isinstance(item, str) or not item for item in value[field])
        ):
            errors.append(f"{field} must be an array of non-empty strings")
    if "profiles" in value and not isinstance(value["profiles"], dict):
        errors.append("profiles must be an object")
    for field in ("identity", "status", "system_ref", "activation_gate"):
        if field in value and (
            not isinstance(value[field], str) or not value[field].strip()
        ):
            errors.append(f"{field} must be a non-empty string")
    if "lifecycle" in value and value["lifecycle"] not in {
        "draft",
        "active",
        "deprecated",
    }:
        errors.append("lifecycle is unsupported")
    if "manifest_kind" in value and value["manifest_kind"] != "deployment-projection":
        errors.append("manifest_kind is unsupported")
    if "authority" in value:
        authority = value["authority"]
        if not isinstance(authority, dict):
            errors.append("authority must be an object")
        elif authority.get("runtime_authority") is not False:
            errors.append("authority.runtime_authority must be false")
    if "contract" in value and not _projection_ref_name(value["contract"]):
        errors.append("contract must identify a reference")

    content_hash = value.get("content_hash")
    if not isinstance(content_hash, str) or not HASH_RE.fullmatch(content_hash):
        errors.append("content_hash must be a lowercase SHA-256 digest")
    elif content_hash != canonical_content_hash(value):
        errors.append("content_hash does not match canonical content")


def _validate_projection_refs(
    value: Any,
    field: str,
    errors: list[str],
    *,
    pinned: bool,
    nonempty: bool,
) -> None:
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return
    if nonempty and not value:
        errors.append(f"{field} must not be empty")
    names: list[str] = []
    for index, item in enumerate(value):
        path = f"{field}[{index}]"
        name = _projection_ref_name(item)
        if not name:
            errors.append(f"{path} must identify a reference")
            continue
        names.append(name)
        if pinned and not isinstance(item, dict):
            errors.append(f"{path} must be a pinned object")
            continue
        if pinned and not any(item.get(key) for key in ("version", "commit", "content_hash")):
            errors.append(f"{path} requires a version, commit, or content_hash pin")
        if isinstance(item, dict) and "content_hash" in item:
            digest = item["content_hash"]
            if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
                errors.append(f"{path}.content_hash must be a lowercase SHA-256 digest")
    if len(names) != len(set(names)):
        errors.append(f"{field} contains duplicate refs")


def _projection_ref_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        for field in ("ref", "id", "path"):
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate:
                return candidate
    return None


def new_module_manifest(
    *,
    module_id: str,
    display_name: str,
    category: str,
    kind: str,
    repository: str | None,
    visibility: str = "private",
) -> dict[str, Any]:
    return {
        "schema": "ellmos.module.v2",
        "id": module_id,
        "display_name": display_name,
        "version": "0.1.0",
        "category": category,
        "kind": kind,
        "status": "development",
        "visibility": visibility,
        "description": "",
        "package": module_id.replace("-", "_"),
        "entrypoints": {"cli": f"{module_id} --help"},
        "provides": [],
        "requires": [],
        "optional": [],
        "conflicts": [],
        "surfaces": ["library", "cli"],
        "state": {"ownership": "module", "location": "user-home"},
        "boundaries": {
            "network": "none",
            "data": "user-local",
            "platforms": ["windows", "macos", "linux"],
        },
        "source_of_truth": {
            "type": "git-repository" if repository else "local-directory",
            "path": ".",
            "repository": repository,
        },
        "adapters": [],
    }
