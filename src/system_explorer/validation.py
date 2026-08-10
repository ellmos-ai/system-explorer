"""Shared fail-closed validation primitives for signed and resolved data."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable


_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")


def nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{path} must be a non-empty trimmed string")
    return value


def stable_ref(value: Any, path: str) -> str:
    value = nonempty_string(value, path)
    if ":" not in value or value.startswith(":") or value.endswith(":"):
        raise ValueError(f"{path} must be a stable typed reference")
    if any(character.isspace() for character in value):
        raise ValueError(f"{path} must not contain whitespace")
    return value


def sha256(value: Any, path: str) -> str:
    value = nonempty_string(value, path)
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{path} must be a lowercase SHA-256 digest")
    return value


def timestamp(value: Any, path: str) -> datetime:
    value = nonempty_string(value, path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{path} must include a timezone")
    return parsed.astimezone(timezone.utc)


def exact_object(value: Any, path: str, fields: Iterable[str]) -> dict[str, Any]:
    expected = set(fields)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    unknown = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if unknown:
        raise ValueError(f"{path} has unknown fields: " + ", ".join(unknown))
    if missing:
        raise ValueError(f"{path} is missing fields: " + ", ".join(missing))
    return value


def exact_string_object(
    value: Any, path: str, fields: Iterable[str]
) -> dict[str, str]:
    result = exact_object(value, path, fields)
    for field, item in result.items():
        nonempty_string(item, f"{path}.{field}")
    return result  # type: ignore[return-value]


def unique_strings(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    result = [nonempty_string(item, path) for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{path} must contain unique values")
    return result


def _component_ref(value: Any, path: str) -> str:
    if isinstance(value, dict):
        value = value.get("ref", value.get("id", value.get("path")))
    return nonempty_string(value, path)


def validate_resolution_components(
    resolution: Any,
    *,
    path: str = "resolution",
) -> dict[str, dict[str, Any]]:
    """Validate duplicate resolution components without normalizing conflicts.

    A ref may occur in several bundles only when its type, registry binding and
    provided function set are byte-for-byte equivalent. Consumers may still
    merge non-authoritative bundle metadata after this gate has passed.
    """

    if not isinstance(resolution, dict):
        raise ValueError(f"{path} must be an object")
    bundles = resolution.get("bundles")
    if not isinstance(bundles, list):
        raise ValueError(f"{path}.bundles must be a list")
    seen: dict[str, dict[str, Any]] = {}
    for bundle_index, bundle in enumerate(bundles):
        if not isinstance(bundle, dict):
            raise ValueError(f"{path}.bundles[{bundle_index}] must be an object")
        components = bundle.get("components", [])
        if not isinstance(components, list):
            raise ValueError(
                f"{path}.bundles[{bundle_index}].components must be a list"
            )
        for component_index, component in enumerate(components):
            location = f"{path}.bundles[{bundle_index}].components[{component_index}]"
            if not isinstance(component, dict):
                raise ValueError(f"{location} must be an object")
            ref = _component_ref(component.get("ref"), f"{location}.ref")
            component_type = nonempty_string(component.get("type"), f"{location}.type")
            provides = unique_strings(
                component.get("provides", []), f"{location}.provides"
            )
            registry_resolution = component.get("registry_resolution")
            if registry_resolution is not None and not isinstance(
                registry_resolution, dict
            ):
                raise ValueError(
                    f"{location}.registry_resolution must be an object or null"
                )
            current = {
                "ref": ref,
                "type": component_type,
                "provides": tuple(sorted(provides)),
                "registry_resolution": registry_resolution,
            }
            previous = seen.get(ref)
            if previous is None:
                seen[ref] = current
                continue
            if previous["type"] != component_type:
                raise ValueError(f"component {ref!r} has conflicting types")
            if previous["registry_resolution"] != registry_resolution:
                raise ValueError(
                    f"component {ref!r} has conflicting registry resolutions"
                )
            if previous["provides"] != current["provides"]:
                raise ValueError(f"component {ref!r} has conflicting provides")
    return seen


def canonical_json(value: Any) -> str:
    """Stable JSON for exact object comparisons in validation tests."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
