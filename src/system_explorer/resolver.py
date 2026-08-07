from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .component_registry import apply_component_registry_gate
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


def resolve_system(
    instance_path: Path,
    catalog_paths: Iterable[Path],
    *,
    registry_bindings_path: Path | None = None,
    registry_source_paths: dict[str, Path] | None = None,
    emit_blocked_resolution: bool = False,
) -> dict[str, Any]:
    instance_path = instance_path.resolve()
    catalog_paths = tuple(Path(path).resolve() for path in catalog_paths)
    registry_bindings_path = (
        Path(registry_bindings_path).resolve()
        if registry_bindings_path is not None
        else None
    )
    resolution_inputs = (instance_path, *catalog_paths)
    if registry_bindings_path is not None:
        resolution_inputs = (*resolution_inputs, registry_bindings_path)
    resolution_root = _resolution_root(resolution_inputs)
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
    resolution = _resolve_system_document(
        system,
        system_path,
        catalogs,
        desired_profile=instance["desired_profile"],
        component_states=instance["component_states"],
        instance=instance,
        resolution_root=resolution_root,
    )
    if registry_bindings_path is not None:
        resolution = apply_component_registry_gate(
            resolution,
            registry_bindings_path,
            resolution_root=resolution_root,
            source_paths=registry_source_paths,
            emit_blocked_resolution=emit_blocked_resolution,
        )
    return resolution


def resolve_fleet(
    fleet_path: Path,
    catalog_paths: Iterable[Path],
    *,
    registry_bindings_path: Path | None = None,
    registry_source_paths: dict[str, Path] | None = None,
    emit_blocked_resolution: bool = False,
) -> dict[str, Any]:
    fleet_path = fleet_path.resolve()
    catalog_paths = tuple(Path(path).resolve() for path in catalog_paths)
    registry_bindings_path = (
        Path(registry_bindings_path).resolve()
        if registry_bindings_path is not None
        else None
    )
    resolution_inputs = (fleet_path, *catalog_paths)
    if registry_bindings_path is not None:
        resolution_inputs = (*resolution_inputs, registry_bindings_path)
    resolution_root = _resolution_root(resolution_inputs)
    fleet = _load_contract(fleet_path, "ellmos.fleet.v1")
    if fleet["status"] not in RESOLVABLE_STATUSES:
        raise ValueError(
            f"fleet {fleet['id']!r} has non-resolvable status {fleet['status']!r}"
        )
    catalogs = _load_catalogs(catalog_paths, resolution_root)
    manifest_index = _manifest_id_index(
        resolution_root,
        {"ellmos.system.v1", "ellmos.system-instance.v1"},
    )

    descriptors = _fleet_descriptors(fleet, resolution_root, manifest_index)
    alias_targets: dict[str, set[str]] = {}
    for descriptor in descriptors:
        for alias in descriptor["aliases"]:
            alias_targets.setdefault(alias, set()).add(descriptor["member_id"])

    overrides_by_host, host_bindings = _fleet_host_overrides(
        fleet, descriptors, alias_targets
    )

    members: list[dict[str, Any]] = []
    function_members: dict[str, list[str]] = {}
    fleet_blocking_gaps: list[dict[str, str]] = []
    for descriptor in sorted(descriptors, key=lambda item: item["member_id"]):
        member = _resolve_fleet_member(
            descriptor,
            catalogs,
            resolution_root=resolution_root,
            override=overrides_by_host.get(descriptor["host_id"], {}),
            registry_bindings_path=registry_bindings_path,
            registry_source_paths=registry_source_paths,
            emit_blocked_resolution=emit_blocked_resolution,
        )
        for function in member["functions"]:
            function_members.setdefault(function, []).append(member["id"])
        for function in member["blocking_required_gaps"]:
            fleet_blocking_gaps.append(
                {"member": member["id"], "function": function}
            )
        members.append(member)

    dependencies = _fleet_dependencies(fleet, alias_targets)
    function_coverage = [
        {
            "function": function,
            "members": sorted(member_list),
            "member_count": len(member_list),
            "single_provider": len(member_list) == 1,
        }
        for function, member_list in sorted(function_members.items())
    ]
    quarantined_members = sorted(
        member["id"] for member in members if member["quarantined_bundles"]
    )
    return with_content_hash(
        {
            "schema": "system-explorer.fleet-resolution.v1",
            "fleet": {
                "id": fleet["id"],
                "version": fleet["version"],
                "status": fleet["status"],
                "lifecycle": fleet["lifecycle"],
                "content_hash": fleet["content_hash"],
            },
            "members": members,
            "functions": sorted(function_members),
            "function_coverage": function_coverage,
            "blocking_required_gaps": _sorted_objects(fleet_blocking_gaps),
            "quarantined_members": quarantined_members,
            "coverage_status": (
                "blocking-gap"
                if fleet_blocking_gaps
                else "tolerated-gap"
                if any(member["open_tolerated_gaps"] for member in members)
                else "covered"
            ),
            "roles": _sorted_objects(fleet.get("roles", [])),
            "handoffs": _sorted_objects(fleet.get("handoffs", [])),
            "host_bindings": _sorted_objects(host_bindings),
            "dependencies": _sorted_objects(dependencies),
            "runtime_actions": [],
            "target_mutations": [],
        }
    )


def _fleet_descriptors(
    fleet: dict[str, Any],
    resolution_root: Path,
    manifest_index: dict[str, list[Path]],
) -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    member_ids: set[str] = set()
    for index, fleet_ref in enumerate(fleet["systems"]):
        label = f"$.systems[{index}]"
        target_path = _resolve_fleet_manifest_ref(
            fleet_ref, resolution_root, manifest_index, label
        )
        target = _read_object(target_path)
        _verify_pin(fleet_ref, target, label)
        schema = target.get("schema")
        instance: dict[str, Any] | None = None
        if schema == "ellmos.system-instance.v1":
            instance = _load_contract(target_path, "ellmos.system-instance.v1")
            if instance["status"] not in RESOLVABLE_STATUSES:
                raise ValueError(
                    f"{label} instance {instance['id']!r} has non-resolvable "
                    f"status {instance['status']!r}"
                )
            system_path = _resolve_contained_ref(
                instance["system_ref"], resolution_root, f"{label}.system_ref"
            )
            system = _load_contract(system_path, "ellmos.system.v1")
            _verify_pin(instance["system_ref"], system, f"{label}.system_ref")
            default_member_id = instance["instance_id"]
            host_id = instance["host_id"]
        elif schema == "ellmos.system.v1":
            system = _load_contract(target_path, "ellmos.system.v1")
            system_path = target_path
            default_member_id = system["id"]
            host_id = None
        else:
            raise ValueError(
                f"{label} must resolve to ellmos.system.v1 or "
                "ellmos.system-instance.v1"
            )

        member_id = _fleet_member_id(fleet_ref, default_member_id)
        if member_id in member_ids:
            raise ValueError(f"duplicate fleet member id: {member_id}")
        member_ids.add(member_id)
        aliases = _resolver_ref_aliases(fleet_ref)
        aliases.update({member_id, target["id"], system["id"]})
        if instance:
            aliases.update({instance["instance_id"], instance["host_id"]})
        descriptors.append(
            {
                "member_id": member_id,
                "fleet_ref": deepcopy(fleet_ref),
                "aliases": aliases,
                "manifest": target,
                "manifest_path": target_path,
                "system": system,
                "system_path": system_path,
                "instance": instance,
                "host_id": host_id,
            }
        )
    return descriptors


def _fleet_host_overrides(
    fleet: dict[str, Any],
    descriptors: list[dict[str, Any]],
    alias_targets: dict[str, set[str]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    entries = fleet.get("host_overrides", [])
    desired_overrides = [item for item in entries if "host_id" in item]
    overrides_by_host: dict[str, dict[str, Any]] = {}
    for item in desired_overrides:
        host_id = item["host_id"]
        if host_id in overrides_by_host:
            raise ValueError(f"duplicate host_overrides entry for host {host_id!r}")
        overrides_by_host[host_id] = item
    known_hosts = {
        descriptor["host_id"]
        for descriptor in descriptors
        if descriptor["host_id"] is not None
    }
    unknown_hosts = sorted(set(overrides_by_host) - known_hosts)
    if unknown_hosts:
        raise ValueError(
            "host_overrides references unresolved hosts: " + ", ".join(unknown_hosts)
        )

    descriptors_by_member = {
        descriptor["member_id"]: descriptor for descriptor in descriptors
    }
    host_bindings: list[dict[str, str]] = []
    for index, binding in enumerate(entries):
        if "host" not in binding:
            continue
        member_id = _resolve_fleet_alias(
            binding.get("ref"), alias_targets, f"$.host_overrides[{index}].ref"
        )
        descriptor = descriptors_by_member[member_id]
        if descriptor["host_id"] != binding["host"]:
            raise ValueError(
                f"host binding {binding['host']!r} does not match fleet member "
                f"{member_id!r} host {descriptor['host_id']!r}"
            )
        host_bindings.append({"host_id": binding["host"], "member": member_id})
    return overrides_by_host, host_bindings


def _resolve_fleet_member(
    descriptor: dict[str, Any],
    catalogs: dict[str, dict[str, Any]],
    *,
    resolution_root: Path,
    override: dict[str, Any],
    registry_bindings_path: Path | None,
    registry_source_paths: dict[str, Path] | None,
    emit_blocked_resolution: bool,
) -> dict[str, Any]:
    instance = descriptor["instance"]
    if instance:
        desired_profile = override.get(
            "desired_profile", instance["desired_profile"]
        )
        component_states = deepcopy(instance["component_states"])
        component_states.update(deepcopy(override.get("component_states", {})))
    else:
        desired_profile = _fleet_profile(
            descriptor["fleet_ref"], descriptor["system"]
        )
        component_states = deepcopy(override.get("component_states", {}))
    resolution = _resolve_system_document(
        descriptor["system"],
        descriptor["system_path"],
        catalogs,
        desired_profile=desired_profile,
        component_states=component_states,
        instance=instance,
        resolution_root=resolution_root,
    )
    if registry_bindings_path is not None:
        resolution = apply_component_registry_gate(
            resolution,
            registry_bindings_path,
            resolution_root=resolution_root,
            source_paths=registry_source_paths,
            emit_blocked_resolution=emit_blocked_resolution,
        )

    functions = set(_resolution_functions(resolution))
    required = _declared_required_functions(resolution)
    tolerated = set(override.get("tolerated_gaps", []))
    blocking_required = sorted(required - functions - tolerated)
    open_tolerated = sorted(tolerated - functions)
    quarantined = _quarantined_bundles(resolution)
    return {
        "id": descriptor["member_id"],
        "manifest": {
            "schema": descriptor["manifest"]["schema"],
            "id": descriptor["manifest"]["id"],
            "version": descriptor["manifest"]["version"],
            "content_hash": descriptor["manifest"]["content_hash"],
        },
        "system_id": descriptor["system"]["id"],
        "host_id": descriptor["host_id"],
        "desired_profile": desired_profile,
        "host_override": deepcopy(override) if override else None,
        "coverage_status": (
            "blocking-gap"
            if blocking_required
            else "tolerated-gap"
            if open_tolerated
            else "covered"
        ),
        "functions": sorted(functions),
        "root_functions": list(resolution["functions"]),
        "blocking_required_gaps": blocking_required,
        "open_tolerated_gaps": open_tolerated,
        "covered_tolerances": sorted(tolerated & functions),
        "quarantined_bundles": quarantined,
        "resolution": resolution,
    }


def _declared_required_functions(resolution: dict[str, Any]) -> set[str]:
    """Required functions a system promises, quarantine included.

    A bundle quarantined by the component-registry gate has its components
    emptied: ``provides`` becomes ``[]`` and the declared value moves into
    ``activation_quarantine.declared_provides``. Reading ``provides`` alone
    would therefore make a fully blocked member look covered, because it
    promises nothing any more. The declared value is what the member was
    supposed to deliver, so that is what a gap is measured against.
    """

    functions: set[str] = set()
    for bundle in resolution["bundles"]:
        for component in bundle["components"]:
            if component.get("requirement") != "required":
                continue
            quarantine = component.get("activation_quarantine")
            declared = (
                quarantine.get("declared_provides", [])
                if isinstance(quarantine, dict)
                else component.get("provides", [])
            )
            functions.update(declared)
    for subsystem in resolution.get("subsystems", []):
        functions.update(_declared_required_functions(subsystem["resolution"]))
    return functions


def _quarantined_bundles(
    resolution: dict[str, Any], *, scope: str = ""
) -> list[dict[str, Any]]:
    quarantined: list[dict[str, Any]] = []
    activation = (resolution.get("component_registry") or {}).get("activation", {})
    system_id = resolution.get("system", {}).get("id", "")
    prefix = f"{scope}/{system_id}" if scope else system_id
    for bundle_id, entry in sorted(activation.items()):
        if entry.get("state") != "blocked":
            continue
        quarantined.append(
            {
                "scope": prefix,
                "bundle": bundle_id,
                "state": entry["state"],
                "quarantined": bool(entry.get("quarantined", False)),
                "required_unresolved": list(entry.get("required_unresolved", [])),
            }
        )
    for subsystem in resolution.get("subsystems", []):
        quarantined.extend(
            _quarantined_bundles(subsystem["resolution"], scope=prefix)
        )
    return quarantined


def _fleet_dependencies(
    fleet: dict[str, Any], alias_targets: dict[str, set[str]]
) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    for index, dependency in enumerate(fleet.get("dependencies", [])):
        source = dependency.get("source", dependency.get("from"))
        target = dependency.get("target", dependency.get("to"))
        normalized = {
            key: deepcopy(value)
            for key, value in dependency.items()
            if key not in {"source", "from", "target", "to"}
        }
        normalized.update(
            {
                "source": _resolve_fleet_alias(
                    source, alias_targets, f"$.dependencies[{index}].source"
                ),
                "target": _resolve_fleet_alias(
                    target, alias_targets, f"$.dependencies[{index}].target"
                ),
                "declared_source": source,
                "declared_target": target,
            }
        )
        dependencies.append(normalized)
    return dependencies


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
    functions = _resolution_functions(suppressed)
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
            "subsystems": suppressed.get("subsystems", []),
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
    ancestry_paths: tuple[Path, ...] = (),
    ancestry_system_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    system_path = system_path.resolve()
    if system_path in ancestry_paths:
        cycle = (*ancestry_paths[ancestry_paths.index(system_path) :], system_path)
        raise ValueError(
            "subsystem reference cycle: "
            + " -> ".join(path.as_posix() for path in cycle)
        )
    if system["id"] in ancestry_system_ids:
        cycle = (*ancestry_system_ids[ancestry_system_ids.index(system["id"]) :], system["id"])
        raise ValueError("subsystem identity cycle: " + " -> ".join(cycle))
    child_ancestry_paths = (*ancestry_paths, system_path)
    child_ancestry_system_ids = (*ancestry_system_ids, system["id"])
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
    considered_component_refs: set[str] = set()
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
            considered_refs=considered_component_refs,
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

    # Validate against every component the profile actually offered, not only
    # the ones that survived. A state of "suppressed" removes its own component
    # from the resolved set, so checking the survivors would report the very
    # state that did the suppressing as an unresolved reference.
    unknown_states = sorted(set(component_states) - considered_component_refs)
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
    output_bindings = _merge_output_bindings(
        system.get("output_bindings", []),
        instance.get("output_bindings", []) if instance else [],
    )

    subsystems: list[dict[str, Any]] = []
    seen_subsystem_ids: set[str] = set()
    for index, subsystem_ref in enumerate(system.get("subsystem_refs", [])):
        label = f"$.subsystem_refs[{index}]"
        child_path = _resolve_contained_ref(subsystem_ref, resolution_root, label)
        child_system = _load_contract(child_path, "ellmos.system.v1")
        _verify_pin(subsystem_ref, child_system, label)
        child_id = child_system["id"]
        if child_id in seen_subsystem_ids:
            raise ValueError(f"duplicate resolved subsystem id: {child_id}")
        seen_subsystem_ids.add(child_id)
        child_resolution = _resolve_system_document(
            child_system,
            child_path,
            catalogs,
            desired_profile=subsystem_ref["profile"],
            component_states={},
            instance=None,
            resolution_root=resolution_root,
            ancestry_paths=child_ancestry_paths,
            ancestry_system_ids=child_ancestry_system_ids,
        )
        source_ref = {
            field: subsystem_ref[field]
            for field in ("path", "version", "commit", "content_hash")
            if field in subsystem_ref
        }
        subsystems.append(
            {
                "role": subsystem_ref["role"],
                "profile": subsystem_ref["profile"],
                "source_ref": source_ref,
                "resolution": child_resolution,
            }
        )

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
        "output_bindings": output_bindings,
        "subsystems": sorted(
            subsystems,
            key=lambda item: (
                item["resolution"]["system"]["id"],
                item["role"],
                item["profile"],
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


def _merge_output_bindings(*groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    exact: dict[str, dict[str, Any]] = {}
    policies: dict[tuple[str, str, str], str] = {}
    for binding in (item for group in groups for item in group):
        canonical = json.dumps(
            binding,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        policy_key = (
            str(binding.get("kind", "")),
            str(binding.get("owner_ref", "")),
            str(binding.get("storage_uri", "")),
        )
        previous = policies.get(policy_key)
        if previous is not None and previous != canonical:
            raise ValueError(
                "conflicting output binding policy for "
                f"kind={policy_key[0]!r}, owner_ref={policy_key[1]!r}, "
                f"storage_uri={policy_key[2]!r}"
            )
        policies[policy_key] = canonical
        exact.setdefault(canonical, deepcopy(binding))
    return sorted(
        exact.values(),
        key=lambda item: (
            item.get("kind", ""),
            item.get("owner_ref", ""),
            item.get("storage_uri", ""),
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ),
    )


def _resolved_components(
    bundle: dict[str, Any],
    *,
    desired_profile: str,
    component_states: dict[str, Any],
    considered_refs: set[str] | None = None,
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
        if considered_refs is not None:
            considered_refs.add(ref)
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
    def collect_available(node: dict[str, Any]) -> None:
        for bundle in node["bundles"]:
            available.add(bundle["id"])
            available.update(
                _ref_name(item["ref"]) for item in bundle["components"]
            )
        for subsystem in node.get("subsystems", []):
            collect_available(subsystem["resolution"])

    collect_available(result)
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
    def suppress_node(node: dict[str, Any]) -> None:
        bundles: list[dict[str, Any]] = []
        for bundle in node["bundles"]:
            if bundle["id"] in requested:
                continue
            item = deepcopy(bundle)
            item["components"] = [
                component
                for component in item["components"]
                if _ref_name(component["ref"]) not in requested
            ]
            bundles.append(item)
        node["bundles"] = bundles
        node["functions"] = _resolution_functions(node, include_subsystems=False)
        for subsystem in node.get("subsystems", []):
            suppress_node(subsystem["resolution"])

    suppress_node(result)
    return result


def _resolution_functions(
    resolution: dict[str, Any], *, include_subsystems: bool = True
) -> list[str]:
    functions = {
        function
        for bundle in resolution["bundles"]
        for component in bundle["components"]
        for function in component.get("provides", [])
        if component.get("desired_status") not in {"suppressed", "unavailable"}
    }
    if include_subsystems:
        for subsystem in resolution.get("subsystems", []):
            functions.update(_resolution_functions(subsystem["resolution"]))
    return sorted(functions)


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


def _manifest_id_index(root: Path, schemas: set[str]) -> dict[str, list[Path]]:
    root = root.resolve()
    index: dict[str, list[Path]] = {}
    for candidate in sorted(root.rglob("*.json"), key=lambda item: item.as_posix()):
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if not resolved.is_file():
            continue
        try:
            value = _read_object(resolved)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        manifest_id = value.get("id")
        if value.get("schema") not in schemas or not isinstance(manifest_id, str):
            continue
        if resolved not in index.setdefault(manifest_id, []):
            index[manifest_id].append(resolved)
    return index


def _resolve_fleet_manifest_ref(
    ref: Any,
    root: Path,
    manifest_index: dict[str, list[Path]],
    label: str,
) -> Path:
    if isinstance(ref, dict) and isinstance(ref.get("path"), str):
        return _contained_path(root.resolve(), ref["path"], label)
    name = _ref_name(ref)
    if not name:
        raise ValueError(f"{label} does not identify a system manifest")
    indexed = manifest_index.get(name, [])
    candidate = Path(name)
    file_candidate: Path | None = None
    if candidate.is_absolute():
        return _contained_path(root.resolve(), name, label)
    resolved_candidate = (root / candidate).resolve()
    try:
        resolved_candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes its manifest root") from exc
    if resolved_candidate.is_file():
        file_candidate = resolved_candidate
    matches = set(indexed)
    if file_candidate is not None:
        matches.add(file_candidate)
    if not matches:
        raise ValueError(f"{label} does not resolve to a system manifest: {name}")
    if len(matches) > 1:
        raise ValueError(
            f"{label} is ambiguous across system manifests: "
            + ", ".join(sorted(path.relative_to(root).as_posix() for path in matches))
        )
    return next(iter(matches))


def _resolver_ref_aliases(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if not isinstance(value, dict):
        return set()
    aliases: set[str] = set()
    for field in ("ref", "id", "path"):
        candidate = value.get(field)
        if isinstance(candidate, str) and candidate:
            aliases.add(candidate)
    return aliases


def _resolve_fleet_alias(
    value: Any, alias_targets: dict[str, set[str]], label: str
) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty fleet member reference")
    targets = alias_targets.get(value, set())
    if not targets:
        raise ValueError(f"{label} references an unresolved fleet member: {value}")
    if len(targets) > 1:
        raise ValueError(
            f"{label} is ambiguous across fleet members: {value} -> "
            + ", ".join(sorted(targets))
        )
    return next(iter(targets))


def _fleet_member_id(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        candidate = value.get("id")
        if isinstance(candidate, str) and candidate:
            return candidate
    return fallback


def _fleet_profile(fleet_ref: Any, system: dict[str, Any]) -> str:
    if isinstance(fleet_ref, dict):
        selected = fleet_ref.get("profile")
        if isinstance(selected, str) and selected:
            return selected
    profiles = sorted(system.get("profiles", {}))
    if "default" in profiles:
        return "default"
    return profiles[0] if profiles else "default"


def _sorted_objects(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (deepcopy(item) for item in values),
        key=lambda item: json.dumps(
            item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    )
