from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from typing import Any
from urllib.parse import unquote, urlsplit


CONTRACT_SCHEMAS = {
    "ellmos.bundle.v1",
    "ellmos.bundles.catalog.v1",
    "ellmos.system.v1",
    "ellmos.system-instance.v1",
    "ellmos.system-test.v1",
    "ellmos.fleet.v1",
}
OPERATIONAL_STATUSES = {
    "registered",
    "available",
    "installed",
    "configured",
    "enabled",
    "active",
    "healthy",
    "suppressed",
    "experimental",
    "unavailable",
}
LIFECYCLE_STATUSES = {"draft", "active", "deprecated"}
VISIBILITIES = {"public", "private", "commercial"}
COMPONENT_TYPES = {
    "module",
    "skill",
    "software_app",
    "interface",
    "data_endpoint",
    "access_surface",
    "policy_document",
    "decision_record",
    "prompt_asset",
    "human_context_profile",
}
REQUIREMENTS = {"required", "recommended", "optional"}
TEST_MODES = {"resolution-only", "isolated-runtime"}
OUTPUT_KINDS = {
    "one_off_report",
    "decision_request",
    "decision_synthesis",
    "automation_summary",
    "runtime_log",
    "audit_receipt",
}
MATERIALIZATION_STATES = {"resolution-only-unmaterialized"}
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
URI_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
INVALID_PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9a-f]{2})", re.IGNORECASE)
MAX_PERCENT_DECODE_PASSES = 8
SECRET_KEYS = {
    "api_key",
    "apikey",
    "credential_value",
    "password",
    "private_key",
    "secret",
    "token",
}
SECRET_KEY_SUFFIXES = {
    "accesstoken",
    "apikey",
    "authtoken",
    "clientsecret",
    "credential",
    "credentials",
    "credentialvalue",
    "password",
    "passwd",
    "privatekey",
    "pwd",
    "secret",
    "secretvalue",
    "token",
}
SECRET_KEY_MARKERS = {
    "accesstoken",
    "apikey",
    "authtoken",
    "clientsecret",
    "credentialvalue",
    "password",
    "passwd",
    "privatekey",
    "secretvalue",
}
SECRET_PATH_KEY_MARKERS = {
    "accesstoken",
    "apikey",
    "authtoken",
    "clientsecret",
    "credential",
    "password",
    "passwd",
    "privatekey",
    "pwd",
    "secret",
    "token",
}
REFERENCE_KEY_SUFFIXES = {
    "ref",
}
OUTPUT_BINDING_FIELDS = {
    "kind",
    "owner_ref",
    "storage_uri",
    "visibility",
    "raw_content_allowed",
    "retention",
    "backup_uri",
    "desktop_shortcut",
    "materialization",
}


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    canonical = deepcopy(value)
    canonical.pop("content_hash", None)
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_content_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def with_content_hash(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result["content_hash"] = canonical_content_hash(result)
    return result


def validate_contract(value: dict[str, Any]) -> list[str]:
    if not isinstance(value, dict):
        return ["manifest root must be an object"]
    schema = value.get("schema")
    if schema not in CONTRACT_SCHEMAS:
        return [f"unsupported contract schema: {schema!r}"]

    errors: list[str] = []
    _validate_common(value, errors)
    _reject_secret_values(value, "$", errors)
    validator = {
        "ellmos.bundle.v1": _validate_bundle,
        "ellmos.bundles.catalog.v1": _validate_catalog,
        "ellmos.system.v1": _validate_system,
        "ellmos.system-instance.v1": _validate_instance,
        "ellmos.system-test.v1": _validate_system_test,
        "ellmos.fleet.v1": _validate_fleet,
    }[schema]
    validator(value, errors)
    return sorted(set(errors))


def _validate_common(value: dict[str, Any], errors: list[str]) -> None:
    required = {
        "schema",
        "id",
        "version",
        "status",
        "lifecycle",
        "authority",
        "provenance",
        "content_hash",
    }
    _require(value, required, "$", errors)
    _nonempty_string(value.get("id"), "$.id", errors)
    _nonempty_string(value.get("version"), "$.version", errors)
    _enum(value.get("status"), OPERATIONAL_STATUSES, "$.status", errors)
    _enum(value.get("lifecycle"), LIFECYCLE_STATUSES, "$.lifecycle", errors)
    _object(value.get("authority"), "$.authority", errors)
    _object(value.get("provenance"), "$.provenance", errors)
    content_hash = value.get("content_hash")
    if not isinstance(content_hash, str) or not HASH_RE.fullmatch(content_hash):
        errors.append("$.content_hash must be a lowercase SHA-256 digest")
    elif content_hash != canonical_content_hash(value):
        errors.append("$.content_hash does not match canonical content")


def _validate_bundle(value: dict[str, Any], errors: list[str]) -> None:
    _require(
        value,
        {
            "display_name",
            "purpose",
            "visibility",
            "assurance_contract",
            "components",
            "profiles",
        },
        "$",
        errors,
    )
    _nonempty_string(value.get("display_name"), "$.display_name", errors)
    _string_list(value.get("purpose"), "$.purpose", errors, nonempty=True)
    _enum(value.get("visibility"), VISIBILITIES, "$.visibility", errors)
    _validate_ref(
        value.get("assurance_contract"),
        "$.assurance_contract",
        errors,
        pinned=False,
    )
    components = value.get("components")
    if not isinstance(components, list):
        errors.append("$.components must be an array")
    else:
        refs: list[str] = []
        for index, component in enumerate(components):
            path = f"$.components[{index}]"
            if not isinstance(component, dict):
                errors.append(f"{path} must be an object")
                continue
            _require(
                component,
                {
                    "type",
                    "ref",
                    "role",
                    "requirement",
                    "provides",
                    "consumes",
                },
                path,
                errors,
            )
            _enum(component.get("type"), COMPONENT_TYPES, f"{path}.type", errors)
            ref = _ref_name(component.get("ref"))
            if not ref:
                errors.append(f"{path}.ref must identify a component")
            else:
                refs.append(ref)
            _nonempty_string(component.get("role"), f"{path}.role", errors)
            _enum(
                component.get("requirement"),
                REQUIREMENTS,
                f"{path}.requirement",
                errors,
            )
            _string_list(component.get("provides"), f"{path}.provides", errors)
            _string_list(component.get("consumes"), f"{path}.consumes", errors)
            _validate_component_pin(component, path, errors)
            if "fallback" in component:
                _validate_ref(
                    component["fallback"],
                    f"{path}.fallback",
                    errors,
                    pinned=False,
                )
        if len(refs) != len(set(refs)):
            errors.append("$.components contains duplicate refs")
    _validate_profiles(value.get("profiles"), "$.profiles", errors)


def _validate_catalog(value: dict[str, Any], errors: list[str]) -> None:
    _require(value, {"bundles"}, "$", errors)
    bundles = value.get("bundles")
    if not isinstance(bundles, list):
        errors.append("$.bundles must be an array")
        return
    ids: list[str] = []
    for index, entry in enumerate(bundles):
        path = f"$.bundles[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{path} must be an object")
            continue
        _require(
            entry,
            {"id", "path", "manifest", "visibility", "status"},
            path,
            errors,
        )
        _nonempty_string(entry.get("id"), f"{path}.id", errors)
        _nonempty_string(entry.get("path"), f"{path}.path", errors)
        _nonempty_string(entry.get("manifest"), f"{path}.manifest", errors)
        _enum(entry.get("visibility"), VISIBILITIES, f"{path}.visibility", errors)
        _enum(entry.get("status"), OPERATIONAL_STATUSES, f"{path}.status", errors)
        if isinstance(entry.get("id"), str):
            ids.append(entry["id"])
    if len(ids) != len(set(ids)):
        errors.append("$.bundles contains duplicate ids")


def _validate_system(value: dict[str, Any], errors: list[str]) -> None:
    _require(
        value,
        {
            "purpose",
            "bundle_refs",
            "stack_refs",
            "profiles",
            "bindings",
            "output_bindings",
            "assurance_contract",
        },
        "$",
        errors,
    )
    _string_list(value.get("purpose"), "$.purpose", errors, nonempty=True)
    _validate_ref_list(value.get("bundle_refs"), "$.bundle_refs", errors, pinned=True)
    _validate_ref_list(value.get("stack_refs"), "$.stack_refs", errors, pinned=True)
    _validate_profiles(value.get("profiles"), "$.profiles", errors)
    if not isinstance(value.get("bindings"), list):
        errors.append("$.bindings must be an array")
    _validate_output_bindings(value.get("output_bindings"), "$.output_bindings", errors)
    _validate_ref(
        value.get("assurance_contract"),
        "$.assurance_contract",
        errors,
        pinned=False,
    )


def _validate_instance(value: dict[str, Any], errors: list[str]) -> None:
    _require(
        value,
        {
            "instance_id",
            "system_ref",
            "host_id",
            "desired_profile",
            "component_states",
            "desired_sources",
            "evidence_refs",
            "output_bindings",
        },
        "$",
        errors,
    )
    _nonempty_string(value.get("instance_id"), "$.instance_id", errors)
    _validate_ref(value.get("system_ref"), "$.system_ref", errors, pinned=True)
    _nonempty_string(value.get("host_id"), "$.host_id", errors)
    _nonempty_string(value.get("desired_profile"), "$.desired_profile", errors)
    _object(value.get("component_states"), "$.component_states", errors)
    if isinstance(value.get("component_states"), dict):
        for ref, state in value["component_states"].items():
            if not isinstance(ref, str) or not ref:
                errors.append("$.component_states keys must be non-empty refs")
            if not isinstance(state, dict):
                errors.append(f"$.component_states[{ref!r}] must be an object")
                continue
            if "status" in state:
                _enum(
                    state.get("status"),
                    OPERATIONAL_STATUSES,
                    f"$.component_states[{ref!r}].status",
                    errors,
                )
            forbidden = {"actual", "observed", "runtime_value"} & set(state)
            for field in sorted(forbidden):
                errors.append(
                    f"$.component_states[{ref!r}].{field} is not allowed in desired state"
                )
    for field in sorted(
        key
        for key in value
        if key.casefold() == "actual" or key.casefold().startswith("actual_")
    ):
        errors.append(f"$.{field} is not allowed in a desired instance contract")
    _validate_ref_list(
        value.get("desired_sources"),
        "$.desired_sources",
        errors,
        pinned=False,
    )
    _validate_ref_list(
        value.get("evidence_refs"),
        "$.evidence_refs",
        errors,
        pinned=False,
    )
    _validate_output_bindings(value.get("output_bindings"), "$.output_bindings", errors)


def _validate_system_test(value: dict[str, Any], errors: list[str]) -> None:
    _require(
        value,
        {
            "base_system_ref",
            "base_hash",
            "mode",
            "suppressions",
            "expected_functions",
            "expected_absent_functions",
            "tolerated_gaps",
            "writeback_to_base",
        },
        "$",
        errors,
    )
    _validate_ref(value.get("base_system_ref"), "$.base_system_ref", errors, pinned=True)
    if not isinstance(value.get("base_hash"), str) or not HASH_RE.fullmatch(
        value.get("base_hash", "")
    ):
        errors.append("$.base_hash must be a lowercase SHA-256 digest")
    _enum(value.get("mode"), TEST_MODES, "$.mode", errors)
    suppressions = value.get("suppressions")
    if not isinstance(suppressions, list):
        errors.append("$.suppressions must be an array")
    else:
        refs: list[str] = []
        for index, suppression in enumerate(suppressions):
            path = f"$.suppressions[{index}]"
            if not isinstance(suppression, dict):
                errors.append(f"{path} must be an object")
                continue
            _require(suppression, {"ref", "reason"}, path, errors)
            ref = _ref_name(suppression.get("ref"))
            if not ref:
                errors.append(f"{path}.ref must identify a resolved item")
            else:
                refs.append(ref)
            _nonempty_string(suppression.get("reason"), f"{path}.reason", errors)
        if len(refs) != len(set(refs)):
            errors.append("$.suppressions contains duplicate refs")
    _string_list(value.get("expected_functions"), "$.expected_functions", errors)
    _string_list(
        value.get("expected_absent_functions"),
        "$.expected_absent_functions",
        errors,
    )
    _string_list(value.get("tolerated_gaps"), "$.tolerated_gaps", errors)
    if value.get("writeback_to_base") is not False:
        errors.append("$.writeback_to_base must be false")


def _validate_fleet(value: dict[str, Any], errors: list[str]) -> None:
    _require(
        value,
        {"systems", "roles", "handoffs", "dependencies", "host_overrides"},
        "$",
        errors,
    )
    _validate_ref_list(value.get("systems"), "$.systems", errors, pinned=True)
    for field in ("roles", "handoffs", "dependencies", "host_overrides"):
        if not isinstance(value.get(field), list):
            errors.append(f"$.{field} must be an array")
    dependencies = value.get("dependencies")
    if isinstance(dependencies, list):
        edges: dict[str, list[str]] = {}
        nodes = {
            name
            for item in value.get("systems", [])
            if (name := _ref_name(item))
        }
        for index, dependency in enumerate(dependencies):
            path = f"$.dependencies[{index}]"
            if not isinstance(dependency, dict):
                errors.append(f"{path} must be an object")
                continue
            source = dependency.get("source", dependency.get("from"))
            target = dependency.get("target", dependency.get("to"))
            _nonempty_string(source, f"{path}.source", errors)
            _nonempty_string(target, f"{path}.target", errors)
            if isinstance(source, str) and isinstance(target, str):
                unknown = {source, target} - nodes
                if unknown:
                    errors.append(
                        f"{path} references unknown systems: "
                        + ", ".join(sorted(unknown))
                    )
                edges.setdefault(source, []).append(target)
        cycle = _find_cycle(nodes, edges)
        if cycle:
            errors.append("$.dependencies cycle: " + " -> ".join(cycle))


def _validate_output_bindings(
    value: Any, path: str, errors: list[str]
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return
    for index, binding in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(binding, dict):
            errors.append(f"{item_path} must be an object")
            continue
        _require(
            binding,
            {
                "kind",
                "owner_ref",
                "storage_uri",
                "visibility",
                "raw_content_allowed",
            },
            item_path,
            errors,
        )
        for field in sorted(set(binding) - OUTPUT_BINDING_FIELDS):
            errors.append(f"{item_path}.{field} is unsupported")
        _enum(binding.get("kind"), OUTPUT_KINDS, f"{item_path}.kind", errors)
        _nonempty_string(binding.get("owner_ref"), f"{item_path}.owner_ref", errors)
        _nonempty_string(binding.get("storage_uri"), f"{item_path}.storage_uri", errors)
        if isinstance(binding.get("storage_uri"), str) and not URI_RE.match(
            _normalized_uri(binding["storage_uri"])
        ):
            errors.append(f"{item_path}.storage_uri must be a typed URI")
        _enum(binding.get("visibility"), VISIBILITIES, f"{item_path}.visibility", errors)
        if not isinstance(binding.get("raw_content_allowed"), bool):
            errors.append(f"{item_path}.raw_content_allowed must be boolean")
        if "materialization" in binding:
            _enum(
                binding["materialization"],
                MATERIALIZATION_STATES,
                f"{item_path}.materialization",
                errors,
            )
        for field in ("retention", "backup_uri", "desktop_shortcut"):
            if field in binding:
                _nonempty_string(binding[field], f"{item_path}.{field}", errors)
        for field in ("backup_uri", "desktop_shortcut"):
            if (
                isinstance(binding.get(field), str)
                and not URI_RE.match(_normalized_uri(binding[field]))
            ):
                errors.append(f"{item_path}.{field} must be a typed URI")
        _validate_output_binding_policy(binding, item_path, errors)


def _validate_output_binding_policy(
    binding: dict[str, Any], path: str, errors: list[str]
) -> None:
    kind = binding.get("kind")
    storage = str(binding.get("storage_uri", ""))
    storage_normalized = _normalized_uri(storage)
    storage_scheme = urlsplit(storage_normalized).scheme.casefold()
    owner = str(binding.get("owner_ref", ""))
    raw_allowed = binding.get("raw_content_allowed") is True
    desktop_target = _uri_targets_named_location(storage_normalized, "desktop")
    onedrive_target = _uri_targets_named_location(storage_normalized, "onedrive")

    if kind == "runtime_log":
        if owner == "ellmos-memory-human-context-bundle":
            errors.append(f"{path}.owner_ref may not assign logs to the memory bundle")
        if raw_allowed and storage_scheme != "host-local":
            errors.append(
                f"{path}.storage_uri must use host-local:// for raw runtime logs"
            )
        if raw_allowed and (
            desktop_target
            or onedrive_target
            or "desktop" in storage_normalized
            or "onedrive" in storage_normalized
        ):
            errors.append(f"{path} may not place raw runtime logs on OneDrive or Desktop")
        if raw_allowed:
            for field in ("backup_uri", "desktop_shortcut"):
                if field in binding:
                    errors.append(
                        f"{path}.{field} is not allowed for raw runtime logs"
                    )
    if raw_allowed and desktop_target:
        errors.append(f"{path} may not use Desktop as a raw-content target")
    if kind in {"decision_request", "decision_synthesis"} and not storage_normalized.startswith(
        "control-center://_decisions"
    ):
        errors.append(
            f"{path}.storage_uri must use control-center://_DECISIONS for decisions"
        )
    if kind == "automation_summary":
        if raw_allowed:
            errors.append(
                f"{path}.raw_content_allowed must be false for automation summaries"
            )
        if owner != "ellmos-automation-control-bundle":
            errors.append(
                f"{path}.owner_ref must be ellmos-automation-control-bundle"
            )
        if not storage_normalized.startswith("user://.usr/logs/automation"):
            errors.append(
                f"{path}.storage_uri must use user://.USR/logs/automation"
            )
    if kind == "audit_receipt" and owner != "ellmos-governance-assurance-bundle":
        errors.append(
            f"{path}.owner_ref must be ellmos-governance-assurance-bundle"
        )
    if kind == "one_off_report" and desktop_target:
        backup = _normalized_uri(str(binding.get("backup_uri", "")))
        if not backup.startswith("user://.usr/"):
            errors.append(
                f"{path}.backup_uri must use user://.USR/ when Desktop is the report target"
            )


def _validate_profiles(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")
        return
    for name, profile in value.items():
        item_path = f"{path}.{name}"
        if not isinstance(name, str) or not name:
            errors.append(f"{path} keys must be non-empty profile names")
        if not isinstance(profile, dict):
            errors.append(f"{item_path} must be an object")
            continue
        unknown = set(profile) - {"include", "exclude", "overrides"}
        for field in sorted(unknown):
            errors.append(f"{item_path}.{field} is unsupported")
        _string_list(profile.get("include", []), f"{item_path}.include", errors)
        _string_list(profile.get("exclude", []), f"{item_path}.exclude", errors)
        _object(profile.get("overrides", {}), f"{item_path}.overrides", errors)
        if isinstance(profile.get("overrides"), dict):
            for ref, override in profile["overrides"].items():
                if not isinstance(override, dict):
                    errors.append(f"{item_path}.overrides[{ref!r}] must be an object")
                elif "status" in override:
                    _enum(
                        override["status"],
                        OPERATIONAL_STATUSES,
                        f"{item_path}.overrides[{ref!r}].status",
                        errors,
                    )


def _validate_ref_list(
    value: Any, path: str, errors: list[str], *, pinned: bool
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return
    for index, item in enumerate(value):
        _validate_ref(item, f"{path}[{index}]", errors, pinned=pinned)


def _validate_ref(
    value: Any, path: str, errors: list[str], *, pinned: bool
) -> None:
    if isinstance(value, str):
        if not value:
            errors.append(f"{path} must be a non-empty ref")
        if pinned:
            errors.append(f"{path} must be an object with a version, commit, or content_hash pin")
        return
    if not isinstance(value, dict):
        errors.append(f"{path} must be a string or object ref")
        return
    if not _ref_name(value):
        errors.append(f"{path} must contain ref, id, or path")
    if pinned and not any(value.get(field) for field in ("version", "commit", "content_hash")):
        errors.append(f"{path} requires a version, commit, or content_hash pin")
    if "content_hash" in value and (
        not isinstance(value["content_hash"], str)
        or not HASH_RE.fullmatch(value["content_hash"])
    ):
        errors.append(f"{path}.content_hash must be a lowercase SHA-256 digest")
    if "depends_on" in value:
        _string_list(value["depends_on"], f"{path}.depends_on", errors)


def _validate_component_pin(
    component: dict[str, Any], path: str, errors: list[str]
) -> None:
    ref = component.get("ref")
    nested_pinned = isinstance(ref, dict) and any(
        ref.get(field) for field in ("version", "commit")
    )
    if not nested_pinned and not any(
        component.get(field) for field in ("version", "commit")
    ):
        errors.append(f"{path} requires a version or commit pin")


def _ref_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        for field in ("ref", "id", "path"):
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate:
                return candidate
    return None


def _reject_secret_values(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_key(str(key))
            if (
                _is_secret_path_key(normalized)
                and isinstance(child, str)
                and _is_absolute_filesystem_path(child)
            ):
                errors.append(
                    f"{path}.{key} may not contain an absolute secret path"
                )
            elif _is_secret_value_key(normalized):
                errors.append(f"{path}.{key} may not contain a secret value")
            _reject_secret_values(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_values(child, f"{path}[{index}]", errors)


def _require(
    value: dict[str, Any], fields: set[str], path: str, errors: list[str]
) -> None:
    for field in sorted(fields - set(value)):
        errors.append(f"{path}.{field} is required")


def _object(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")


def _nonempty_string(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")


def _string_list(
    value: Any,
    path: str,
    errors: list[str],
    *,
    nonempty: bool = False,
) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        errors.append(f"{path} must be an array of non-empty strings")
    elif nonempty and not value:
        errors.append(f"{path} must not be empty")


def _enum(value: Any, allowed: set[str], path: str, errors: list[str]) -> None:
    if value not in allowed:
        errors.append(f"{path} must be one of {', '.join(sorted(allowed))}")


def _find_cycle(nodes: set[str], edges: dict[str, list[str]]) -> list[str]:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        if state.get(node) == 2:
            return []
        if state.get(node) == 1:
            start = stack.index(node)
            return stack[start:] + [node]
        state[node] = 1
        stack.append(node)
        for target in sorted(edges.get(node, [])):
            cycle = visit(target)
            if cycle:
                return cycle
        stack.pop()
        state[node] = 2
        return []

    for node in sorted(nodes):
        cycle = visit(node)
        if cycle:
            return cycle
    return []


def _normalized_uri(value: str) -> str:
    normalized = _bounded_unquote(value.strip())
    if normalized is None:
        return ""
    return normalized.replace("\\", "/").casefold()


def _uri_targets_named_location(value: str, name: str) -> bool:
    parsed = urlsplit(value)
    if parsed.scheme.casefold() == name:
        return True
    segments = [
        part
        for part in re.split(r"[/@:?&=#]+", f"{parsed.netloc}/{parsed.path}")
        if part
    ]
    return name.casefold() in segments


def _normalized_key(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        unicodedata.normalize("NFKC", value).casefold(),
    )


def _is_secret_value_key(value: str) -> bool:
    if value in {_normalized_key(key) for key in SECRET_KEYS}:
        return True
    if any(value.endswith(suffix) for suffix in REFERENCE_KEY_SUFFIXES):
        return False
    return any(value.endswith(suffix) for suffix in SECRET_KEY_SUFFIXES) or any(
        marker in value for marker in SECRET_KEY_MARKERS
    )


def _is_secret_path_key(value: str) -> bool:
    return value.endswith(("file", "location", "path", "uri")) and any(
        marker in value for marker in SECRET_PATH_KEY_MARKERS
    )


def _is_absolute_filesystem_path(value: str) -> bool:
    normalized = _bounded_unquote(value.strip())
    if normalized is None:
        return True
    return bool(re.match(r"^(?:[a-z]:[\\/]|[\\/]{2}|/)", normalized, re.IGNORECASE))


def _bounded_unquote(value: str) -> str | None:
    current = unicodedata.normalize("NFKC", value)
    for _ in range(MAX_PERCENT_DECODE_PASSES):
        if INVALID_PERCENT_ESCAPE_RE.search(current):
            return None
        decoded = unicodedata.normalize("NFKC", unquote(current))
        if decoded == current:
            return current
        current = decoded
    return None
