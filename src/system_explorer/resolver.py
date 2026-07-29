from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    CONTRACT_SCHEMAS,
    OPERATIONAL_STATUSES,
    canonical_content_hash,
    validate_contract,
    with_content_hash,
)
from .manifests import validate_manifest


RESOLVABLE_STATUSES = OPERATIONAL_STATUSES - {"suppressed", "unavailable"}
PROFILE_OVERRIDE_FIELDS = {
    "consumes",
    "fallback",
    "provides",
    "requirement",
    "role",
    "status",
}


def validate_manifest_path(path: Path) -> dict[str, Any]:
    path = path.resolve()
    value = _read_object(path)
    errors = (
        validate_contract(value)
        if value.get("schema") in CONTRACT_SCHEMAS
        else validate_manifest(value)
    )
    computed_hash = canonical_content_hash(value)
    declared_hash = value.get("content_hash")
    if declared_hash is not None and declared_hash != computed_hash:
        errors.append("$.content_hash does not match canonical content")
    return {
        "path": path.name,
        "schema": value.get("schema"),
        "id": value.get("id"),
        "valid": not errors,
        "errors": sorted(set(errors)),
        "computed_content_hash": computed_hash,
    }


def validate_manifest_target(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if path.is_file():
        return validate_manifest_path(path)
    if not path.is_dir():
        raise ValueError(f"manifest target does not exist: {path}")

    results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for candidate in sorted(path.rglob("*.json"), key=lambda item: item.as_posix()):
        try:
            value = _read_object(candidate)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            results.append(
                {
                    "path": candidate.relative_to(path).as_posix(),
                    "schema": None,
                    "id": None,
                    "valid": False,
                    "errors": [str(exc)],
                    "computed_content_hash": None,
                }
            )
            continue
        schema = value.get("schema")
        if schema not in CONTRACT_SCHEMAS | {"ellmos.module.v2", "ellmos.stack.v2"}:
            if isinstance(schema, str) and schema.startswith("ellmos."):
                skipped.append(
                    {
                        "path": candidate.relative_to(path).as_posix(),
                        "schema": schema,
                        "reason": "schema is outside this validator's contract set",
                    }
                )
            continue
        result = validate_manifest_path(candidate)
        result["path"] = candidate.relative_to(path).as_posix()
        results.append(result)
    invalid = sum(not item["valid"] for item in results)
    return {
        "schema": "system-explorer.manifest-validation.v1",
        "target": path.name,
        "valid": invalid == 0,
        "validated": len(results),
        "invalid": invalid,
        "skipped": skipped,
        "results": results,
    }


def resolve_system(instance_path: Path, catalog_paths: Iterable[Path]) -> dict[str, Any]:
    instance_path = instance_path.resolve()
    catalog_paths = tuple(Path(path).resolve() for path in catalog_paths)
    resolution_root = _resolution_root((instance_path, *catalog_paths))
    instance = _load_contract(instance_path, "ellmos.system-instance.v1")
    if instance["status"] not in RESOLVABLE_STATUSES:
        raise ValueError(
            f"instance {instance['id']!r} has non-resolvable status "
            f"{instance['status']!r}"
        )
    system_path = _resolve_contained_ref(
        instance["system_ref"],
        resolution_root,
        "$.system_ref",
    )
    system = _load_contract(system_path, "ellmos.system.v1")
    _verify_pin(instance["system_ref"], system, "$.system_ref")
    catalogs = _load_catalogs(catalog_paths, resolution_root)
    return _resolve_system_document(
        system,
        system_path,
        catalogs,
        desired_profile=instance["desired_profile"],
        component_states=instance["component_states"],
        instance=instance,
        resolution_root=resolution_root,
    )


def resolve_test(test_path: Path, catalog_paths: Iterable[Path]) -> dict[str, Any]:
    test_path = test_path.resolve()
    catalog_paths = tuple(Path(path).resolve() for path in catalog_paths)
    resolution_root = _resolution_root((test_path, *catalog_paths))
    test = _load_contract(test_path, "ellmos.system-test.v1")
    base_path = _resolve_contained_ref(
        test["base_system_ref"],
        resolution_root,
        "$.base_system_ref",
    )
    base = _read_object(base_path)
    _verify_pin(test["base_system_ref"], base, "$.base_system_ref")
    if test["base_hash"] != base.get("content_hash"):
        raise ValueError("$.base_hash does not match the referenced base manifest")

    catalogs = _load_catalogs(catalog_paths, resolution_root)
    if base.get("schema") == "ellmos.system-instance.v1":
        instance = _load_contract(base_path, "ellmos.system-instance.v1")
        system_path = _resolve_contained_ref(
            instance["system_ref"],
            resolution_root,
            "$.base_system_ref.system_ref",
        )
        system = _load_contract(system_path, "ellmos.system.v1")
        _verify_pin(instance["system_ref"], system, "$.base_system_ref.system_ref")
        resolution = _resolve_system_document(
            system,
            system_path,
            catalogs,
            desired_profile=instance["desired_profile"],
            component_states=instance["component_states"],
            instance=instance,
            resolution_root=resolution_root,
        )
    elif base.get("schema") == "ellmos.system.v1":
        system = _load_contract(base_path, "ellmos.system.v1")
        profile_names = sorted(system.get("profiles", {}))
        desired_profile = (
            "default"
            if "default" in system.get("profiles", {})
            else profile_names[0]
            if profile_names
            else "default"
        )
        resolution = _resolve_system_document(
            system,
            base_path,
            catalogs,
            desired_profile=desired_profile,
            component_states={},
            instance=None,
            resolution_root=resolution_root,
        )
    else:
        raise ValueError(
            "$.base_system_ref must resolve to ellmos.system.v1 or "
            "ellmos.system-instance.v1"
        )

    suppressed = _apply_test_suppressions(resolution, test["suppressions"])
    functions = sorted(
        {
            function
            for bundle in suppressed["bundles"]
            for component in bundle["components"]
            for function in component.get("provides", [])
            if component.get("desired_status") not in {"suppressed", "unavailable"}
        }
    )
    expected = set(test["expected_functions"])
    tolerated = set(test["tolerated_gaps"])
    missing = sorted(expected - set(functions))
    blocking_missing = sorted(set(missing) - tolerated)
    unexpectedly_present = sorted(
        set(test["expected_absent_functions"]) & set(functions)
    )
    if blocking_missing:
        raise ValueError(
            "expected functions are missing: " + ", ".join(blocking_missing)
        )
    if unexpectedly_present:
        raise ValueError(
            "expected-absent functions are present: "
            + ", ".join(unexpectedly_present)
        )

    return with_content_hash(
        {
            "schema": "system-explorer.test-resolution.v1",
            "test": {
                "id": test["id"],
                "version": test["version"],
                "content_hash": test["content_hash"],
                "mode": test["mode"],
            },
            "base_resolution_hash": resolution["content_hash"],
            "desired_profile": suppressed["desired_profile"],
            "bundles": suppressed["bundles"],
            "functions": functions,
            "suppressions": sorted(
                test["suppressions"], key=lambda item: _ref_name(item["ref"])
            ),
            "expectations": {
                "missing": missing,
                "tolerated_gaps": sorted(tolerated & set(missing)),
                "unexpectedly_present": unexpectedly_present,
            },
            "runtime_actions": [],
            "writeback_to_base": False,
        }
    )


def _resolve_system_document(
    system: dict[str, Any],
    system_path: Path,
    catalogs: dict[str, dict[str, Any]],
    *,
    desired_profile: str,
    component_states: dict[str, Any],
    instance: dict[str, Any] | None,
    resolution_root: Path,
) -> dict[str, Any]:
    if system["status"] not in RESOLVABLE_STATUSES:
        raise ValueError(
            f"system {system['id']!r} has non-resolvable status {system['status']!r}"
        )
    profiles = system.get("profiles", {})
    if profiles and desired_profile not in profiles:
        raise ValueError(
            f"desired profile {desired_profile!r} is not declared by system {system['id']!r}"
        )
    selected_profile = profiles.get(
        desired_profile,
        {"include": [], "exclude": [], "overrides": {}},
    )

    bundle_refs = deepcopy(system["bundle_refs"])
    stack_summaries: list[dict[str, Any]] = []
    for index, stack_ref in enumerate(system.get("stack_refs", [])):
        path = _resolve_contained_ref(
            stack_ref,
            resolution_root,
            f"$.stack_refs[{index}]",
        )
        stack = _read_object(path)
        stack_errors = validate_manifest(stack)
        if stack_errors:
            raise ValueError(
                f"invalid ellmos.stack.v2 reference {path.name}: "
                + "; ".join(stack_errors)
            )
        if stack.get("schema") != "ellmos.stack.v2":
            raise ValueError(f"{path.name} is not ellmos.stack.v2")
        _verify_pin(stack_ref, stack, f"$.stack_refs[{index}]")
        declared = stack.get("bundle_refs", [])
        if not isinstance(declared, list):
            raise ValueError(f"{path.name}.bundle_refs must be an array when present")
        bundle_refs.extend(deepcopy(declared))
        stack_summaries.append(
            {
                "id": stack["id"],
                "version": stack.get("version"),
                "content_hash": stack.get("content_hash")
                or canonical_content_hash(stack),
            }
        )

    selected_refs = _apply_profile(
        bundle_refs,
        selected_profile,
        key=_ref_name,
        label=f"system profile {desired_profile!r}",
        protected={"ref", "id", "path", "version", "commit", "content_hash"},
    )
    _check_ref_dependency_cycles(selected_refs, "bundle dependency")
    _check_binding_cycles(system.get("bindings", []))

    bundles: list[dict[str, Any]] = []
    seen_bundle_ids: set[str] = set()
    for index, bundle_ref in enumerate(selected_refs):
        bundle_id = _ref_name(bundle_ref)
        if bundle_id in seen_bundle_ids:
            raise ValueError(f"duplicate resolved bundle ref: {bundle_id}")
        seen_bundle_ids.add(bundle_id)
        if (
            isinstance(bundle_ref, dict)
            and bundle_ref.get("status", "configured") not in RESOLVABLE_STATUSES
        ):
            raise ValueError(
                f"bundle {bundle_id!r} has non-resolvable desired status "
                f"{bundle_ref['status']!r}"
            )
        catalog_item = catalogs.get(bundle_id)
        if catalog_item is None:
            raise ValueError(f"bundle ref is not present in supplied catalogs: {bundle_id}")
        if catalog_item["catalog_status"] not in RESOLVABLE_STATUSES:
            raise ValueError(
                f"bundle {bundle_id!r} has non-resolvable catalog status "
                f"{catalog_item['catalog_status']!r}"
            )
        bundle = catalog_item["manifest"]
        _verify_pin(bundle_ref, bundle, f"$.bundle_refs[{index}]")
        if bundle["status"] not in RESOLVABLE_STATUSES:
            raise ValueError(
                f"bundle {bundle_id!r} has non-resolvable status {bundle['status']!r}"
            )
        components = _resolved_components(
            bundle,
            desired_profile=desired_profile,
            component_states=component_states,
        )
        bundles.append(
            {
                "id": bundle["id"],
                "version": bundle["version"],
                "status": bundle["status"],
                "lifecycle": bundle["lifecycle"],
                "visibility": bundle["visibility"],
                "content_hash": bundle["content_hash"],
                "catalog": catalog_item["catalog_id"],
                "components": components,
            }
        )

    known_component_refs = {
        _ref_name(component["ref"])
        for bundle in bundles
        for component in bundle["components"]
    }
    unknown_states = sorted(set(component_states) - known_component_refs)
    if unknown_states:
        raise ValueError(
            "component_states references unresolved components: "
            + ", ".join(unknown_states)
        )
    functions = sorted(
        {
            function
            for bundle in bundles
            for component in bundle["components"]
            for function in component.get("provides", [])
            if component.get("desired_status") not in {"suppressed", "unavailable"}
        }
    )
    output_bindings = list(system.get("output_bindings", []))
    if instance:
        output_bindings.extend(instance.get("output_bindings", []))

    result: dict[str, Any] = {
        "schema": "system-explorer.resolution.v1",
        "system": {
            "id": system["id"],
            "version": system["version"],
            "status": system["status"],
            "lifecycle": system["lifecycle"],
            "content_hash": system["content_hash"],
        },
        "desired_profile": desired_profile,
        "stacks": sorted(stack_summaries, key=lambda item: item["id"]),
        "bundles": sorted(bundles, key=lambda item: item["id"]),
        "functions": functions,
        "output_bindings": sorted(
            output_bindings,
            key=lambda item: (
                item.get("kind", ""),
                item.get("owner_ref", ""),
                item.get("storage_uri", ""),
            ),
        ),
        "runtime_actions": [],
        "target_mutations": [],
        "warnings": [
            "ellmos.stack.v2 is consumed tolerantly through bundle_refs only; "
            "its authoritative schema remains external."
        ]
        if stack_summaries
        else [],
    }
    if instance:
        result["instance"] = {
            "id": instance["id"],
            "instance_id": instance["instance_id"],
            "host_id": instance["host_id"],
            "version": instance["version"],
            "content_hash": instance["content_hash"],
        }
    return with_content_hash(result)


def _resolved_components(
    bundle: dict[str, Any],
    *,
    desired_profile: str,
    component_states: dict[str, Any],
) -> list[dict[str, Any]]:
    profile = bundle.get("profiles", {}).get(
        desired_profile,
        {"include": [], "exclude": [], "overrides": {}},
    )
    components = _apply_profile(
        deepcopy(bundle["components"]),
        profile,
        key=lambda item: _ref_name(item["ref"]),
        label=f"bundle {bundle['id']!r} profile {desired_profile!r}",
        protected={"ref", "type", "version", "commit"},
    )
    resolved: list[dict[str, Any]] = []
    for component in components:
        ref = _ref_name(component["ref"])
        item = deepcopy(component)
        state = deepcopy(component_states.get(ref, {}))
        desired_status = state.get("status", item.pop("status", "configured"))
        if desired_status not in OPERATIONAL_STATUSES:
            raise ValueError(
                f"component {ref!r} has unsupported desired status {desired_status!r}"
            )
        if desired_status == "suppressed":
            continue
        if desired_status == "unavailable" and item["requirement"] == "required":
            raise ValueError(f"required component {ref!r} is unavailable")
        item["desired_status"] = desired_status
        if state:
            item["component_state"] = state
        resolved.append(item)
    component_refs = {_ref_name(component["ref"]) for component in resolved}
    fallback_edges: dict[str, list[str]] = {}
    for item in resolved:
        ref = _ref_name(item["ref"])
        fallback = item.get("fallback")
        if fallback is not None:
            fallback_ref = _ref_name(fallback)
            if fallback_ref not in component_refs:
                raise ValueError(
                    f"component {ref!r} fallback is unresolved: {fallback_ref!r}"
                )
            fallback_edges.setdefault(ref, []).append(fallback_ref)
    _check_cycles(
        {_ref_name(component["ref"]) for component in resolved},
        fallback_edges,
        f"bundle {bundle['id']!r} fallback",
    )
    return sorted(resolved, key=lambda item: _ref_name(item["ref"]))


def _apply_profile(
    items: list[Any],
    profile: dict[str, Any],
    *,
    key: Any,
    label: str,
    protected: set[str],
) -> list[Any]:
    by_key: dict[str, Any] = {}
    for item in items:
        item_key = key(item)
        if not item_key:
            raise ValueError(f"{label} contains an unidentified ref")
        if item_key in by_key:
            raise ValueError(f"{label} contains duplicate ref {item_key!r}")
        by_key[item_key] = item
    include = set(profile.get("include", []))
    exclude = set(profile.get("exclude", []))
    overrides = profile.get("overrides", {})
    unknown = (include | exclude | set(overrides)) - set(by_key)
    if unknown:
        raise ValueError(
            f"{label} references unknown entries: {', '.join(sorted(unknown))}"
        )
    selected = include if include else set(by_key)
    selected -= exclude
    result: list[Any] = []
    for item_key in sorted(selected):
        item = deepcopy(by_key[item_key])
        override = overrides.get(item_key, {})
        if not isinstance(override, dict):
            raise ValueError(f"{label} override for {item_key!r} must be an object")
        forbidden = protected & set(override)
        if forbidden:
            raise ValueError(
                f"{label} may not override pinned identity fields for {item_key!r}: "
                + ", ".join(sorted(forbidden))
            )
        unsupported = set(override) - PROFILE_OVERRIDE_FIELDS
        if unsupported:
            raise ValueError(
                f"{label} has unsupported overrides for {item_key!r}: "
                + ", ".join(sorted(unsupported))
            )
        if isinstance(item, dict):
            item.update(override)
            if item.get("status") == "suppressed":
                continue
        result.append(item)
    return result


def _load_catalogs(
    catalog_paths: Iterable[Path], resolution_root: Path
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for catalog_path in sorted(
        (Path(path).resolve() for path in catalog_paths),
        key=str,
    ):
        catalog = _load_contract(catalog_path, "ellmos.bundles.catalog.v1")
        if catalog["status"] not in RESOLVABLE_STATUSES:
            raise ValueError(
                f"catalog {catalog['id']!r} has non-resolvable status "
                f"{catalog['status']!r}"
            )
        for entry in sorted(catalog["bundles"], key=lambda item: item["id"]):
            entry_root = _contained_path(
                resolution_root,
                entry["path"],
                "$.bundles[].path",
            )
            if entry_root.suffix.casefold() == ".json":
                manifest_path = entry_root
            else:
                manifest_path = _contained_path(
                    resolution_root,
                    str(Path(entry["path"]) / entry["manifest"]),
                    "$.bundles[].manifest",
                )
            bundle = _load_contract(manifest_path, "ellmos.bundle.v1")
            if entry["id"] != bundle["id"]:
                raise ValueError(
                    f"catalog id {entry['id']!r} does not match bundle id "
                    f"{bundle['id']!r}"
                )
            if entry["visibility"] != bundle["visibility"]:
                raise ValueError(
                    f"catalog visibility for {entry['id']!r} does not match manifest"
                )
            if entry["id"] in index:
                raise ValueError(f"duplicate bundle id across catalogs: {entry['id']}")
            index[entry["id"]] = {
                "manifest": bundle,
                "catalog_id": catalog["id"],
                "catalog_status": entry["status"],
            }
    return index


def _apply_test_suppressions(
    resolution: dict[str, Any], suppressions: list[dict[str, Any]]
) -> dict[str, Any]:
    result = deepcopy(resolution)
    available: set[str] = {result["system"]["id"]}
    if result.get("instance"):
        available.update(
            {
                result["instance"]["id"],
                result["instance"]["instance_id"],
            }
        )
    for bundle in result["bundles"]:
        available.add(bundle["id"])
        available.update(_ref_name(item["ref"]) for item in bundle["components"])
    requested = {_ref_name(item["ref"]) for item in suppressions}
    unknown = sorted(requested - available)
    if unknown:
        raise ValueError(
            "test suppressions reference unresolved items: " + ", ".join(unknown)
        )
    if result["system"]["id"] in requested or (
        result.get("instance")
        and {
            result["instance"]["id"],
            result["instance"]["instance_id"],
        }
        & requested
    ):
        raise ValueError("a system-test may not suppress its base system or instance")
    bundles: list[dict[str, Any]] = []
    for bundle in result["bundles"]:
        if bundle["id"] in requested:
            continue
        item = deepcopy(bundle)
        item["components"] = [
            component
            for component in item["components"]
            if _ref_name(component["ref"]) not in requested
        ]
        bundles.append(item)
    result["bundles"] = bundles
    return result


def _check_ref_dependency_cycles(items: list[Any], label: str) -> None:
    nodes = {_ref_name(item) for item in items}
    edges: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        source = _ref_name(item)
        dependencies = item.get("depends_on", [])
        unknown = set(dependencies) - nodes
        if unknown:
            raise ValueError(
                f"{label} {source!r} references unknown dependencies: "
                + ", ".join(sorted(unknown))
            )
        edges[source] = list(dependencies)
    _check_cycles(nodes, edges, label)


def _check_binding_cycles(bindings: list[Any]) -> None:
    nodes: set[str] = set()
    edges: dict[str, list[str]] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        source = binding.get("source", binding.get("from"))
        target = binding.get("target", binding.get("to"))
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        nodes.update((source, target))
        edges.setdefault(source, []).append(target)
    _check_cycles(nodes, edges, "system binding")


def _check_cycles(
    nodes: set[str], edges: dict[str, list[str]], label: str
) -> None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        marker = state.get(node, 0)
        if marker == 2:
            return
        if marker == 1:
            start = stack.index(node)
            cycle = stack[start:] + [node]
            raise ValueError(f"{label} cycle: {' -> '.join(cycle)}")
        state[node] = 1
        stack.append(node)
        for target in sorted(edges.get(node, [])):
            visit(target)
        stack.pop()
        state[node] = 2

    for node in sorted(nodes):
        visit(node)


def _verify_pin(ref: Any, manifest: dict[str, Any], label: str) -> None:
    if not isinstance(ref, dict):
        raise ValueError(f"{label} is not pinned")
    expected_version = ref.get("version")
    if expected_version and expected_version != manifest.get("version"):
        raise ValueError(
            f"{label} version pin {expected_version!r} does not match "
            f"{manifest.get('version')!r}"
        )
    expected_commit = ref.get("commit")
    actual_commit = manifest.get("commit")
    if not actual_commit and isinstance(manifest.get("provenance"), dict):
        actual_commit = manifest["provenance"].get("commit")
    if expected_commit and expected_commit != actual_commit:
        raise ValueError(
            f"{label} commit pin {expected_commit!r} does not match "
            f"{actual_commit!r}"
        )
    computed_hash = canonical_content_hash(manifest)
    declared_hash = manifest.get("content_hash")
    if declared_hash is not None:
        if not isinstance(declared_hash, str):
            raise ValueError(f"{label} referenced manifest content_hash must be a string")
        if declared_hash != computed_hash:
            raise ValueError(
                f"{label} referenced manifest content_hash does not match "
                "canonical content"
            )
    expected_hash = ref.get("content_hash")
    if expected_hash and expected_hash != computed_hash:
        raise ValueError(f"{label} content_hash pin does not match referenced manifest")


def _resolve_contained_ref(ref: Any, root: Path, label: str) -> Path:
    name = _ref_name(ref)
    if not name:
        raise ValueError(f"{label} does not contain a path")
    return _contained_path(root.resolve(), name, label)


def _contained_path(root: Path, value: str, label: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError(f"{label} must be relative to its manifest root")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes its manifest root") from exc
    if not resolved.is_file() and resolved.suffix:
        raise ValueError(f"{label} does not resolve to a file: {value}")
    if not resolved.exists():
        raise ValueError(f"{label} does not exist: {value}")
    return resolved


def _resolution_root(paths: Iterable[Path]) -> Path:
    resolved = tuple(Path(path).resolve() for path in paths)
    if not resolved:
        raise ValueError("at least one manifest path is required")
    repository_roots = {_git_root(path) for path in resolved}
    concrete_roots = {path for path in repository_roots if path is not None}
    if concrete_roots:
        if len(concrete_roots) != 1 or None in repository_roots:
            raise ValueError("all resolver inputs must belong to the same repository root")
        return concrete_roots.pop()
    return Path(os.path.commonpath([str(path.parent) for path in resolved])).resolve()


def _git_root(path: Path) -> Path | None:
    for candidate in (path.parent, *path.parents):
        if (candidate / ".git").exists():
            return candidate.resolve()
    return None


def _load_contract(path: Path, schema: str) -> dict[str, Any]:
    value = _read_object(path)
    if value.get("schema") != schema:
        raise ValueError(f"{path.name} must use {schema}")
    errors = validate_contract(value)
    if errors:
        raise ValueError(f"invalid {path.name}: " + "; ".join(errors))
    return value


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def _ref_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for field in ("ref", "id", "path"):
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate:
                return candidate
    return ""
