from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from .contracts import (
    canonical_content_hash,
    validate_contract,
    with_content_hash,
)


REGISTRY_SCHEMA = "ellmos.component-registry-bindings.v1"
RECEIPT_SCHEMA = "ellmos.component-registry-resolution-receipt.v1"


def inspect_component_registry(
    bindings_path: Path,
    bundle_paths: Iterable[Path],
    *,
    source_paths: Mapping[str, Path] | None = None,
    activation_bundle_ids: Iterable[str] = (),
    observed_on: str | None = None,
    observed_at: str | None = None,
) -> tuple[dict[str, Any], int]:
    bindings_path = Path(bindings_path).resolve()
    repository_root = _repository_root(bindings_path)
    bindings = _load_registry(bindings_path, repository_root)
    bundles = [_load_bundle(Path(path).resolve()) for path in bundle_paths]
    bundle_inventory_hash = _bundle_inventory_hash(bundles)
    binding_index = _binding_index(bindings)
    declared_only = bindings["declared_only"]
    source_paths = {
        source_id: Path(path).resolve()
        for source_id, path in (source_paths or {}).items()
    }

    errors: list[str] = []
    source_errors: list[str] = []
    occurrences: dict[str, list[dict[str, str]]] = {}
    bundle_refs: dict[str, list[dict[str, str]]] = {}
    for bundle_path, bundle in bundles:
        entries: list[dict[str, str]] = []
        for component in bundle["components"]:
            ref = _ref_name(component["ref"])
            occurrence = {
                "bundle_id": bundle["id"],
                "type": component["type"],
                "requirement": component["requirement"],
                "ref": ref,
            }
            entries.append(occurrence)
            occurrences.setdefault(ref, []).append(occurrence)
            binding = binding_index.get(ref)
            declared = declared_only.get(ref)
            if binding is None and declared is None:
                errors.append(
                    f"{bundle_path.name}: component {ref!r} has no exact "
                    "registry binding or declared-only entry"
                )
            elif binding is not None and binding["component_type"] != component["type"]:
                errors.append(
                    f"{bundle_path.name}: component {ref!r} type "
                    f"{component['type']!r} does not match binding type "
                    f"{binding['component_type']!r}"
                )
            elif declared is not None and declared["component_type"] != component["type"]:
                errors.append(
                    f"{bundle_path.name}: component {ref!r} type "
                    f"{component['type']!r} does not match declared-only type "
                    f"{declared['component_type']!r}"
                )
        bundle_refs[bundle["id"]] = entries

    expected_refs = set(occurrences)
    unused_bindings = sorted(set(binding_index) - expected_refs)
    unused_declared = sorted(set(declared_only) - expected_refs)
    if unused_bindings:
        errors.append("binding manifest contains unused component references")
    if unused_declared:
        errors.append("binding manifest contains unused declared-only references")

    resolved_sources, source_receipts, source_failures = _verify_sources(
        bindings,
        binding_index,
        repository_root,
        source_paths,
    )
    source_errors.extend(source_failures)

    activation: dict[str, Any] = {}
    activation_blocked = False
    activation_ids = sorted(set(activation_bundle_ids))
    unknown_activation_ids = sorted(set(activation_ids) - set(bundle_refs))
    for bundle_id in unknown_activation_ids:
        errors.append(f"unknown activation bundle: {bundle_id}")
    for bundle_id in activation_ids:
        if bundle_id not in bundle_refs:
            continue
        unresolved_by_requirement = {
            "required": [],
            "recommended": [],
            "optional": [],
        }
        for occurrence in bundle_refs[bundle_id]:
            if occurrence["ref"] in declared_only:
                unresolved_by_requirement[occurrence["requirement"]].append(
                    occurrence["ref"]
                )
        for refs in unresolved_by_requirement.values():
            refs.sort()
        state = _activation_state(unresolved_by_requirement)
        activation[bundle_id] = {
            "state": state,
            "required_unresolved": unresolved_by_requirement["required"],
            "recommended_unresolved": unresolved_by_requirement["recommended"],
            "optional_unresolved": unresolved_by_requirement["optional"],
        }
        activation_blocked = activation_blocked or state == "blocked"

    declared_counts: Counter[str] = Counter()
    resolved_counts: Counter[str] = Counter()
    for ref, ref_occurrences in occurrences.items():
        if ref in declared_only:
            for occurrence in ref_occurrences:
                declared_counts[occurrence["requirement"]] += 1
        else:
            for occurrence in ref_occurrences:
                resolved_counts[occurrence["type"]] += 1

    report: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "verifier": "system-explorer.component-registry.v1",
        "binding_manifest": bindings_path.relative_to(repository_root).as_posix(),
        "binding_content_hash": bindings["content_hash"],
        "contract_content_hash": bindings["contract"]["content_hash"],
        "bundle_set_sha256": bundle_inventory_hash,
        "bundle_count": len(bundle_refs),
        "component_occurrences": sum(len(items) for items in bundle_refs.values()),
        "unique_component_references": len(expected_refs),
        "resolved_occurrences_by_type": dict(sorted(resolved_counts.items())),
        "declared_only_occurrences_by_requirement": dict(
            sorted(declared_counts.items())
        ),
        "unused_binding_references": unused_bindings,
        "unused_declared_only_references": unused_declared,
        "source_verification_requested": bool(source_paths),
        "source_verification_complete": resolved_sources,
        "source_receipts": source_receipts,
        "activation": activation,
        "errors": sorted(set(errors)),
        "source_errors": sorted(set(source_errors)),
    }
    if observed_on is not None or observed_at is not None:
        if not observed_on:
            errors.append("observed_on is required when native receipt metadata is used")
        if not observed_at:
            errors.append("observed_at is required when native receipt metadata is used")
        if observed_on:
            report["observed_on"] = observed_on
        if observed_at:
            report["observed_at"] = observed_at
    report["errors"] = sorted(set(errors))
    report["status"] = (
        "invalid"
        if report["errors"]
        else "source-verification-failed"
        if report["source_errors"]
        else "activation-blocked"
        if activation_blocked
        else "verified"
    )
    report = with_content_hash(report)
    exit_code = (
        1
        if report["errors"]
        else 2
        if report["source_errors"]
        else 3
        if activation_blocked
        else 0
    )
    return report, exit_code


def apply_component_registry_gate(
    resolution: dict[str, Any],
    bindings_path: Path,
    *,
    resolution_root: Path,
    source_paths: Mapping[str, Path] | None = None,
    emit_blocked_resolution: bool = False,
) -> dict[str, Any]:
    bindings_path = Path(bindings_path).resolve()
    bindings = _load_registry(bindings_path, _repository_root(bindings_path))
    binding_index = _binding_index(bindings)
    declared_only = bindings["declared_only"]
    used_sources: set[str] = set()
    gated = deepcopy(resolution)
    activation_by_node: dict[int, dict[str, Any]] = {}
    blocked: list[tuple[str, str, list[str]]] = []

    def gate_node(node: dict[str, Any], scope: str) -> None:
        activation: dict[str, Any] = {}
        bundles = node.get("bundles")
        if not isinstance(bundles, list):
            raise ValueError(f"{scope}.bundles must be an array")
        for bundle in bundles:
            unresolved_by_requirement = {
                "required": [],
                "recommended": [],
                "optional": [],
            }
            for component in bundle["components"]:
                ref = _ref_name(component["ref"])
                binding = binding_index.get(ref)
                declared = declared_only.get(ref)
                if binding is None and declared is None:
                    raise ValueError(
                        f"component {ref!r} has no exact registry binding or "
                        "declared-only entry"
                    )
                if binding is not None:
                    if binding["component_type"] != component["type"]:
                        raise ValueError(
                            f"component {ref!r} type {component['type']!r} does not "
                            f"match registry type {binding['component_type']!r}"
                        )
                    used_sources.add(binding["source"])
                    if binding.get("crosswalk_source"):
                        used_sources.add(binding["crosswalk_source"])
                    component["registry_resolution"] = {
                        key: binding[key]
                        for key in (
                            "source",
                            "record_id",
                            "profile",
                            "crosswalk_source",
                            "crosswalk_record_id",
                        )
                        if key in binding
                    }
                    component["registry_resolution"]["class"] = "native-binding"
                    continue
                if declared["component_type"] != component["type"]:
                    raise ValueError(
                        f"component {ref!r} type {component['type']!r} does not "
                        f"match declared-only type {declared['component_type']!r}"
                    )
                requirement = component["requirement"]
                unresolved_by_requirement[requirement].append(ref)
                component["registry_resolution"] = {
                    "class": "declared-only",
                    "reason": declared["reason"],
                    "runtime_authority": False,
                    "may_satisfy_actual_coverage": False,
                }
                component["desired_status"] = "unavailable"

            for refs in unresolved_by_requirement.values():
                refs.sort()
            state = _activation_state(unresolved_by_requirement)
            if state == "blocked" and emit_blocked_resolution:
                for component in bundle["components"]:
                    component["activation_quarantine"] = {
                        "reason": "bundle-has-required-declared-only-components",
                        "declared_desired_status": component["desired_status"],
                        "declared_provides": list(component.get("provides", [])),
                    }
                    component["desired_status"] = "unavailable"
                    component["provides"] = []
            activation[bundle["id"]] = {
                "state": state,
                "required_unresolved": unresolved_by_requirement["required"],
                "recommended_unresolved": unresolved_by_requirement["recommended"],
                "optional_unresolved": unresolved_by_requirement["optional"],
            }
            if state == "blocked" and emit_blocked_resolution:
                activation[bundle["id"]]["quarantined"] = True
            if state == "blocked":
                blocked.append(
                    (scope, bundle["id"], unresolved_by_requirement["required"])
                )
        activation_by_node[id(node)] = activation

        subsystems = node.get("subsystems", [])
        if not isinstance(subsystems, list):
            raise ValueError(f"{scope}.subsystems must be an array")
        for index, subsystem in enumerate(subsystems):
            if not isinstance(subsystem, dict) or not isinstance(
                subsystem.get("resolution"), dict
            ):
                raise ValueError(
                    f"{scope}.subsystems[{index}].resolution must be an object"
                )
            child = subsystem["resolution"]
            child_id = child.get("system", {}).get("id", str(index))
            gate_node(child, f"{scope}.subsystems[{child_id}]")

    root_id = gated.get("system", {}).get("id", "root")
    gate_node(gated, f"resolution[{root_id}]")

    repository_root = _repository_root(bindings_path)
    resolved, _, failures = _verify_sources(
        bindings,
        binding_index,
        repository_root,
        {
            source_id: Path(path).resolve()
            for source_id, path in (source_paths or {}).items()
        },
        required_source_ids=used_sources,
    )
    if not resolved or failures:
        raise ValueError(
            "component registry source verification failed: "
            + "; ".join(sorted(set(failures)))
        )

    if blocked and not emit_blocked_resolution:
        details = "; ".join(
            f"{scope}/{bundle_id}: {', '.join(refs)}"
            for scope, bundle_id, refs in sorted(blocked)
        )
        raise ValueError(
            "component registry activation blocked by required declared-only "
            f"components: {details}"
        )

    def finalize(node: dict[str, Any]) -> dict[str, Any]:
        for subsystem in node.get("subsystems", []):
            subsystem["resolution"] = finalize(subsystem["resolution"])
        component_registry = {
            "schema": bindings["schema"],
            "id": bindings["id"],
            "version": bindings["version"],
            "content_hash": bindings["content_hash"],
            "activation": activation_by_node[id(node)],
            "source_verification": "verified",
        }
        if emit_blocked_resolution and any(
            item["state"] == "blocked"
            for item in activation_by_node[id(node)].values()
        ):
            component_registry["activation_enforcement"] = (
                "blocked-evidence-only"
            )
        node["component_registry"] = component_registry
        node["functions"] = sorted(
            {
                function
                for bundle in node["bundles"]
                for component in bundle["components"]
                for function in component.get("provides", [])
                if component.get("desired_status")
                not in {"suppressed", "unavailable"}
            }
        )
        node.pop("content_hash", None)
        return with_content_hash(node)

    if blocked and emit_blocked_resolution:
        gated.setdefault("warnings", []).append(
            "Bundles with required declared-only component gaps remain blocked and "
            "all of their components are quarantined from operational resolution."
        )
    return finalize(gated)


def parse_source_path_arguments(values: Iterable[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        source_id, separator, path = value.partition("=")
        if not separator or not source_id or not path:
            raise ValueError(
                "--source-path must use SOURCE_ID=PATH with non-empty values"
            )
        if source_id in result:
            raise ValueError(f"duplicate --source-path source ID: {source_id}")
        result[source_id] = Path(path)
    return result


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_registry(path: Path, repository_root: Path) -> dict[str, Any]:
    value = _read_object(path)
    if value.get("schema") != REGISTRY_SCHEMA:
        raise ValueError(f"{path.name} must use {REGISTRY_SCHEMA}")
    errors = validate_contract(value)
    if errors:
        raise ValueError(f"invalid {path.name}: " + "; ".join(errors))
    contract_path = _contained_path(
        repository_root,
        value["contract"]["path"],
        "$.contract.path",
    )
    contract = _read_object(contract_path)
    if contract.get("schema") != "ellmos.component-registry-resolution-contract.v1":
        raise ValueError(
            "component registry contract uses an unsupported schema"
        )
    expected_contract_ref = f"contract:{contract.get('id', '')}"
    if value["contract"]["ref"] != expected_contract_ref:
        raise ValueError(
            "component registry contract ref does not match the loaded contract ID"
        )
    contract_hash = canonical_content_hash(contract)
    if contract.get("content_hash") != contract_hash:
        raise ValueError("component registry contract content_hash mismatch")
    if value["contract"]["content_hash"] != contract_hash:
        raise ValueError("component registry pins the wrong contract content_hash")
    return value


def _load_bundle(path: Path) -> tuple[Path, dict[str, Any]]:
    bundle = _read_object(path)
    if bundle.get("schema") != "ellmos.bundle.v1":
        raise ValueError(f"{path.name} must use ellmos.bundle.v1")
    errors = validate_contract(bundle)
    if errors:
        raise ValueError(f"invalid {path.name}: " + "; ".join(errors))
    return path, bundle


def _binding_index(bindings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for component_type, entries in bindings["bindings"].items():
        for ref, binding in entries.items():
            if ref in index:
                raise ValueError(f"duplicate component registry binding: {ref}")
            item = deepcopy(binding)
            item["component_type"] = component_type
            index[ref] = item
    return index


def _verify_sources(
    bindings: dict[str, Any],
    binding_index: dict[str, dict[str, Any]],
    repository_root: Path,
    source_paths: Mapping[str, Path],
    *,
    required_source_ids: set[str] | None = None,
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    if not source_paths and required_source_ids is None:
        return False, [], []
    source_receipts: list[dict[str, Any]] = []
    failures: list[str] = []
    source_ids = (
        set(bindings["sources"])
        if required_source_ids is None
        else set(required_source_ids)
    )
    unknown_paths = sorted(set(source_paths) - set(bindings["sources"]))
    for source_id in unknown_paths:
        failures.append(f"{source_id}: source path has no manifest declaration")
    missing_paths = sorted(source_ids - set(source_paths))
    for source_id in missing_paths:
        source = bindings["sources"][source_id]
        if urlsplit(source["uri"]).scheme.casefold() == "repo":
            continue
        failures.append(f"{source_id}: source path was not supplied")

    records_by_source: dict[str, set[str]] = {}
    crosswalks_by_source: dict[str, dict[str, Any]] = {}
    for source_id in sorted(source_ids):
        source = bindings["sources"][source_id]
        source_path = source_paths.get(source_id)
        if source_path is None and urlsplit(source["uri"]).scheme.casefold() == "repo":
            source_path = _contained_path(
                repository_root,
                _repo_uri_path(source["uri"]),
                f"$.sources[{source_id!r}].uri",
            )
        if source_path is None:
            continue
        if not source_path.is_file():
            failures.append(f"{source_id}: source file is missing")
            continue
        observed_hash = _file_hash(source_path)
        receipt: dict[str, Any] = {
            "source_id": source_id,
            "uri": source["uri"],
            "expected_sha256": source["sha256"],
            "observed_sha256": observed_hash,
            "hash_match": observed_hash == source["sha256"],
        }
        if not receipt["hash_match"]:
            failures.append(f"{source_id}: source sha256 mismatch")
        source_data = _read_object(source_path)
        if "record_collection" in source:
            collection = source_data.get(source["record_collection"])
            if isinstance(collection, list):
                record_ids = [
                    str(record[source["record_id_field"]])
                    for record in collection
                    if isinstance(record, dict)
                    and source["record_id_field"] in record
                ]
                ids = set(record_ids)
                duplicate_ids = sorted(
                    record_id
                    for record_id, count in Counter(record_ids).items()
                    if count > 1
                )
                if duplicate_ids:
                    failures.append(
                        f"{source_id}: duplicate record IDs: "
                        + ", ".join(duplicate_ids)
                    )
                records_by_source[source_id] = ids
                receipt["record_count"] = len(ids)
                receipt["duplicate_record_ids"] = duplicate_ids
            elif isinstance(collection, dict):
                crosswalks_by_source[source_id] = collection
                receipt["record_count"] = len(collection)
            else:
                failures.append(
                    f"{source_id}: record collection is missing or unsupported"
                )
        else:
            observed_record_id = _root_record_id(source_data)
            receipt["observed_record_id"] = observed_record_id
            if observed_record_id != source["record_id"]:
                failures.append(f"{source_id}: source record ID mismatch")
            records_by_source[source_id] = {observed_record_id}
        source_receipts.append(receipt)

    for ref, binding in sorted(binding_index.items()):
        source_id = binding["source"]
        if source_id not in source_ids:
            continue
        records = records_by_source.get(source_id)
        if records is not None and binding["record_id"] not in records:
            failures.append(
                f"{source_id}: binding {ref!r} record_id "
                f"{binding['record_id']!r} is missing"
            )
        crosswalk_source = binding.get("crosswalk_source")
        if crosswalk_source and crosswalk_source in source_ids:
            crosswalk = crosswalks_by_source.get(crosswalk_source)
            crosswalk_record_id = binding["crosswalk_record_id"]
            if crosswalk is None or crosswalk_record_id not in crosswalk:
                failures.append(
                    f"{crosswalk_source}: binding {ref!r} crosswalk record "
                    f"{crosswalk_record_id!r} is missing"
                )
            else:
                record = crosswalk[crosswalk_record_id]
                if (
                    not isinstance(record, dict)
                    or record.get("registry_component_id") != binding["record_id"]
                ):
                    failures.append(
                        f"{crosswalk_source}: binding {ref!r} does not match "
                        "its registry_component_id"
                    )
                if crosswalk_record_id != ref:
                    failures.append(
                        f"{crosswalk_source}: binding {ref!r} uses a different "
                        "crosswalk identity"
                    )
    return not failures, source_receipts, failures


def _activation_state(unresolved: dict[str, list[str]]) -> str:
    if unresolved["required"]:
        return "blocked"
    if unresolved["recommended"]:
        return "degraded"
    if unresolved["optional"]:
        return "resolved-with-optional-gaps"
    return "identity-resolved"


def _bundle_inventory_hash(
    bundles: list[tuple[Path, dict[str, Any]]],
) -> str:
    digest = hashlib.sha256()
    for path, bundle in sorted(bundles, key=lambda item: item[1]["id"]):
        digest.update(bundle["id"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(
            json.dumps(
                bundle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    return digest.hexdigest()


def _repository_root(path: Path) -> Path:
    for candidate in (path.parent, *path.parents):
        if (candidate / ".git").exists():
            return candidate.resolve()
    return path.parent.resolve()


def _contained_path(root: Path, value: str, label: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError(f"{label} must be repository-relative")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes its repository") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} does not resolve to a file: {value}")
    return resolved


def _repo_uri_path(uri: str) -> str:
    parsed = urlsplit(uri)
    return f"{parsed.netloc}{parsed.path}".lstrip("/")


def _root_record_id(value: dict[str, Any]) -> str:
    for field in ("id", "name"):
        candidate = value.get(field)
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=_strict_object_pairs,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be an object")
    return value


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _ref_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for field in ("ref", "id", "path"):
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate:
                return candidate
    return ""
