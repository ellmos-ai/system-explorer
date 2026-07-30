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
    "ellmos.component-registry-bindings.v1",
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
    "contract",
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
COMPONENT_REF_PREFIXES = {
    "contract": "contract:",
    "module": "module:",
    "skill": "skill:",
    "software_app": "software:",
    "interface": "interface:",
    "data_endpoint": "data_endpoint:",
    "access_surface": "access_surface:",
    "policy_document": "policy:",
    "decision_record": "decision:",
    "prompt_asset": "prompt:",
    "human_context_profile": "human_context:",
}
REGISTRY_SOURCE_KINDS = {
    "access-surface-manifest",
    "contract-registry",
    "module-registry",
    "skill-crosswalk",
    "skill-registry",
    "software-catalog",
}
REGISTRY_SOURCE_KINDS_BY_COMPONENT_TYPE = {
    "access_surface": {"access-surface-manifest"},
    "contract": {"contract-registry"},
    "module": {"module-registry"},
    "skill": {"skill-registry"},
    "software_app": {"software-catalog"},
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
ACTIVATION_STATES = {"blocked", "ready-disabled", "shadow-pilot", "reviewed-activation"}
PEER_TRANSFER_STATES = {"sftp-over-ssh"}
NETWORK_PATH_STATES = {"direct-or-tailscale"}
PEER_VERIFICATION_STATES = {"signed-registry-and-pinned-host-key"}
DESTINATION_POLICY_STATES = {"normalized-allowlisted-no-overwrite"}
PUBLISHED_PAYLOAD_STATES = {"signed-path-metadata-only"}
COMPONENT_STATE_FIELDS = {
    "status",
    "desired_profile",
    "publisher_slot",
    "publishes",
    "peer_transfer",
    "network_path",
    "peer_verification",
    "destination_policy",
    "activation",
    "database_allowlist",
    "live_database_in_sync",
}
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
        "ellmos.component-registry-bindings.v1": _validate_component_registry,
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
                expected_prefix = COMPONENT_REF_PREFIXES.get(component.get("type"))
                if (
                    component.get("type") == "contract"
                    and expected_prefix
                    and not ref.startswith(expected_prefix)
                ):
                    errors.append(
                        f"{path}.ref must use {expected_prefix!r} for "
                        f"type {component.get('type')!r}"
                    )
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


def _validate_component_registry(
    value: dict[str, Any], errors: list[str]
) -> None:
    allowed = {
        "schema",
        "id",
        "version",
        "status",
        "lifecycle",
        "authority",
        "provenance",
        "contract",
        "sources",
        "bindings",
        "declared_only",
        "declared_only_policy",
        "content_hash",
    }
    _require(
        value,
        {
            "contract",
            "sources",
            "bindings",
            "declared_only",
            "declared_only_policy",
        },
        "$",
        errors,
    )
    for field in sorted(set(value) - allowed):
        errors.append(f"$.{field} is unsupported")
    if isinstance(value.get("authority"), dict):
        _require(
            value["authority"],
            {"kind", "runtime_authority"},
            "$.authority",
            errors,
        )
        for field in sorted(
            set(value["authority"]) - {"kind", "runtime_authority"}
        ):
            errors.append(f"$.authority.{field} is unsupported")
        if value["authority"].get("kind") != "external-registry-reference":
            errors.append(
                "$.authority.kind must be 'external-registry-reference'"
            )
        if value["authority"].get("runtime_authority") is not False:
            errors.append("$.authority.runtime_authority must be false")
    if isinstance(value.get("provenance"), dict):
        _require(
            value["provenance"],
            {"source_plan", "repository"},
            "$.provenance",
            errors,
        )
        for field in sorted(
            set(value["provenance"]) - {"source_plan", "repository"}
        ):
            errors.append(
                f"$.provenance.{field} is unsupported; component registry "
                "bindings are host-neutral"
            )
        _nonempty_string(
            value["provenance"].get("source_plan"),
            "$.provenance.source_plan",
            errors,
        )
        _nonempty_string(
            value["provenance"].get("repository"),
            "$.provenance.repository",
            errors,
        )

    contract = value.get("contract")
    if not isinstance(contract, dict):
        errors.append("$.contract must be an object")
    else:
        _require(contract, {"ref", "path", "content_hash"}, "$.contract", errors)
        for field in sorted(set(contract) - {"ref", "path", "content_hash"}):
            errors.append(f"$.contract.{field} is unsupported")
        _nonempty_string(contract.get("ref"), "$.contract.ref", errors)
        if isinstance(contract.get("ref"), str) and not contract["ref"].startswith(
            "contract:"
        ):
            errors.append("$.contract.ref must use the 'contract:' prefix")
        _relative_path(contract.get("path"), "$.contract.path", errors)
        _sha256(contract.get("content_hash"), "$.contract.content_hash", errors)

    sources = value.get("sources")
    source_kinds: dict[str, str] = {}
    if not isinstance(sources, dict) or not sources:
        errors.append("$.sources must be a non-empty object")
    else:
        for source_id, source in sources.items():
            path = f"$.sources[{source_id!r}]"
            if not isinstance(source_id, str) or not source_id:
                errors.append("$.sources keys must be non-empty source IDs")
            if not isinstance(source, dict):
                errors.append(f"{path} must be an object")
                continue
            allowed_source = {
                "kind",
                "uri",
                "record_collection",
                "record_id",
                "record_id_field",
                "sha256",
            }
            _require(source, {"kind", "uri", "sha256"}, path, errors)
            for field in sorted(set(source) - allowed_source):
                errors.append(f"{path}.{field} is unsupported")
            _enum(
                source.get("kind"),
                REGISTRY_SOURCE_KINDS,
                f"{path}.kind",
                errors,
            )
            if isinstance(source.get("kind"), str):
                source_kinds[source_id] = source["kind"]
            _nonempty_string(source.get("uri"), f"{path}.uri", errors)
            if isinstance(source.get("uri"), str) and not URI_RE.match(source["uri"]):
                errors.append(f"{path}.uri must be a typed URI")
            _sha256(source.get("sha256"), f"{path}.sha256", errors)
            has_collection = any(
                field in source for field in ("record_collection", "record_id_field")
            )
            if has_collection:
                _require(
                    source,
                    {"record_collection", "record_id_field"},
                    path,
                    errors,
                )
                _nonempty_string(
                    source.get("record_collection"),
                    f"{path}.record_collection",
                    errors,
                )
                _nonempty_string(
                    source.get("record_id_field"),
                    f"{path}.record_id_field",
                    errors,
                )
                if "record_id" in source:
                    errors.append(
                        f"{path}.record_id may not accompany a record collection"
                    )
            else:
                _nonempty_string(source.get("record_id"), f"{path}.record_id", errors)

    bindings = value.get("bindings")
    bound_refs: set[str] = set()
    if not isinstance(bindings, dict):
        errors.append("$.bindings must be an object")
    else:
        for component_type, entries in bindings.items():
            type_path = f"$.bindings[{component_type!r}]"
            _enum(component_type, COMPONENT_TYPES, type_path, errors)
            if not isinstance(entries, dict):
                errors.append(f"{type_path} must be an object")
                continue
            for ref, binding in entries.items():
                path = f"{type_path}[{ref!r}]"
                if ref in bound_refs:
                    errors.append(f"{path} duplicates a binding for {ref!r}")
                bound_refs.add(ref)
                expected_prefix = COMPONENT_REF_PREFIXES.get(component_type)
                if (
                    not isinstance(ref, str)
                    or not expected_prefix
                    or not ref.startswith(expected_prefix)
                ):
                    errors.append(
                        f"{path} must use the component type's canonical prefix"
                    )
                if not isinstance(binding, dict):
                    errors.append(f"{path} must be an object")
                    continue
                allowed_binding = {
                    "source",
                    "record_id",
                    "profile",
                    "crosswalk_source",
                    "crosswalk_record_id",
                }
                _require(binding, {"source", "record_id"}, path, errors)
                for field in sorted(set(binding) - allowed_binding):
                    errors.append(f"{path}.{field} is unsupported")
                _nonempty_string(binding.get("source"), f"{path}.source", errors)
                _nonempty_string(binding.get("record_id"), f"{path}.record_id", errors)
                if "profile" in binding:
                    _nonempty_string(binding["profile"], f"{path}.profile", errors)
                source_id = binding.get("source")
                if isinstance(source_id, str) and source_id not in source_kinds:
                    errors.append(f"{path}.source references an unknown source")
                elif isinstance(source_id, str):
                    compatible = REGISTRY_SOURCE_KINDS_BY_COMPONENT_TYPE.get(
                        component_type
                    )
                    if compatible is None:
                        errors.append(
                            f"{path} has no approved native source kind for "
                            f"{component_type!r}; use declared_only"
                        )
                    elif source_kinds[source_id] not in compatible:
                        errors.append(
                            f"{path}.source kind {source_kinds[source_id]!r} "
                            f"cannot bind {component_type!r}"
                        )
                crosswalk_fields = {
                    "crosswalk_source",
                    "crosswalk_record_id",
                } & set(binding)
                if crosswalk_fields and crosswalk_fields != {
                    "crosswalk_source",
                    "crosswalk_record_id",
                }:
                    errors.append(
                        f"{path} must declare crosswalk_source and "
                        "crosswalk_record_id together"
                    )
                if crosswalk_fields:
                    if component_type != "skill":
                        errors.append(
                            f"{path} may use a crosswalk only for skill bindings"
                        )
                    crosswalk_source = binding.get("crosswalk_source")
                    if (
                        not isinstance(crosswalk_source, str)
                        or source_kinds.get(crosswalk_source) != "skill-crosswalk"
                    ):
                        errors.append(
                            f"{path}.crosswalk_source must reference a "
                            "skill-crosswalk source"
                        )
                    _nonempty_string(
                        binding.get("crosswalk_record_id"),
                        f"{path}.crosswalk_record_id",
                        errors,
                    )

    declared_only = value.get("declared_only")
    if not isinstance(declared_only, dict):
        errors.append("$.declared_only must be an object")
    else:
        for ref, declaration in declared_only.items():
            path = f"$.declared_only[{ref!r}]"
            if ref in bound_refs:
                errors.append(f"{path} is also present in $.bindings")
            if not isinstance(declaration, dict):
                errors.append(f"{path} must be an object")
                continue
            _require(declaration, {"component_type", "reason"}, path, errors)
            for field in sorted(set(declaration) - {"component_type", "reason"}):
                errors.append(f"{path}.{field} is unsupported")
            component_type = declaration.get("component_type")
            _enum(component_type, COMPONENT_TYPES, f"{path}.component_type", errors)
            expected_prefix = COMPONENT_REF_PREFIXES.get(component_type)
            if expected_prefix and (
                not isinstance(ref, str) or not ref.startswith(expected_prefix)
            ):
                errors.append(
                    f"{path} must use {expected_prefix!r} for "
                    f"type {component_type!r}"
                )
            _nonempty_string(declaration.get("reason"), f"{path}.reason", errors)

    policy = value.get("declared_only_policy")
    if not isinstance(policy, dict):
        errors.append("$.declared_only_policy must be an object")
    else:
        required_policy = {
            "resolution_class": "declared-only",
            "runtime_authority": False,
            "activation_status": "blocked-until-native-registry-record",
            "may_satisfy_actual_coverage": False,
        }
        _require(policy, set(required_policy), "$.declared_only_policy", errors)
        for field in sorted(set(policy) - set(required_policy)):
            errors.append(f"$.declared_only_policy.{field} is unsupported")
        for field, expected in required_policy.items():
            if policy.get(field) != expected:
                errors.append(
                    f"$.declared_only_policy.{field} must be {expected!r}"
                )


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
            _validate_component_state(state, f"$.component_states[{ref!r}]", errors)
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


def _validate_component_state(
    state: dict[str, Any], path: str, errors: list[str]
) -> None:
    for field in sorted(set(state) - COMPONENT_STATE_FIELDS):
        errors.append(f"{path}.{field} is unsupported")
    if "status" in state:
        _enum(state["status"], OPERATIONAL_STATUSES, f"{path}.status", errors)
    for field in ("desired_profile", "publisher_slot"):
        if field in state:
            _nonempty_string(state[field], f"{path}.{field}", errors)
    if "publishes" in state:
        _enum(state["publishes"], PUBLISHED_PAYLOAD_STATES, f"{path}.publishes", errors)
    if "peer_transfer" in state:
        _enum(
            state["peer_transfer"],
            PEER_TRANSFER_STATES,
            f"{path}.peer_transfer",
            errors,
        )
    if "network_path" in state:
        _enum(
            state["network_path"],
            NETWORK_PATH_STATES,
            f"{path}.network_path",
            errors,
        )
    if "peer_verification" in state:
        _enum(
            state["peer_verification"],
            PEER_VERIFICATION_STATES,
            f"{path}.peer_verification",
            errors,
        )
    if "destination_policy" in state:
        _enum(
            state["destination_policy"],
            DESTINATION_POLICY_STATES,
            f"{path}.destination_policy",
            errors,
        )
    peer_fields = {
        "publisher_slot",
        "publishes",
        "peer_transfer",
        "network_path",
        "peer_verification",
        "destination_policy",
    }
    if peer_fields & set(state) and not peer_fields <= set(state):
        errors.append(f"{path} must declare the complete trusted-peer state together")
    if "activation" in state:
        _enum(state["activation"], ACTIVATION_STATES, f"{path}.activation", errors)
    if "database_allowlist" in state:
        _string_list(
            state["database_allowlist"],
            f"{path}.database_allowlist",
            errors,
        )
        if isinstance(state["database_allowlist"], list) and len(
            state["database_allowlist"]
        ) != len(set(state["database_allowlist"])):
            errors.append(f"{path}.database_allowlist must not contain duplicates")
    if "live_database_in_sync" in state and not isinstance(
        state["live_database_in_sync"], bool
    ):
        errors.append(f"{path}.live_database_in_sync must be a boolean")
    database_fields = {"activation", "database_allowlist", "live_database_in_sync"}
    if database_fields & set(state) and not database_fields <= set(state):
        errors.append(
            f"{path} must declare activation, database_allowlist, and live_database_in_sync together"
        )
    if state.get("activation") == "ready-disabled":
        if state.get("database_allowlist") != []:
            errors.append(f"{path}.ready-disabled requires database_allowlist=[]")
        if state.get("live_database_in_sync") is not False:
            errors.append(f"{path}.ready-disabled requires live_database_in_sync=false")


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


def _relative_path(value: Any, path: str, errors: list[str]) -> None:
    _nonempty_string(value, path, errors)
    if not isinstance(value, str) or not value:
        return
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[a-zA-Z]:", normalized):
        errors.append(f"{path} must be repository-relative")
    if any(part == ".." for part in normalized.split("/")):
        errors.append(f"{path} may not escape its repository")


def _sha256(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        errors.append(f"{path} must be a lowercase SHA-256 digest")


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
