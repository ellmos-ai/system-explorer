from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Manifest root must be an object")
    return value


def validate_manifest(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schema = value.get("schema")
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
    elif schema in {"ellmos.stack.v2", "ellmos.system-instance.v1"}:
        if not value.get("id"):
            errors.append("missing field: id")
    else:
        errors.append(f"unsupported schema: {schema!r}")
    return errors


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
