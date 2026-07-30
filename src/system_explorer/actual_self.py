from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .contracts import canonical_content_hash
from .store import Store
from .util import stable_id


RECEIPT_SCHEMA = "ellmos.actual-self-component-receipt.v1"
FUNCTION_STATUSES = {"observed", "full", "partial", "negative"}
COMPONENT_TYPES = {"module", "skill", "software_app", "interface", "access_surface"}
ROOT_FIELDS = {
    "schema",
    "receipt_id",
    "component_ref",
    "component_type",
    "scope",
    "registry_binding",
    "producer",
    "observed_at",
    "expires_at",
    "functions",
    "content_hash",
}


def import_actual_self_receipt(
    path: Path,
    resolution: dict[str, Any],
    store: Store,
    *,
    evaluated_at: str,
) -> dict[str, Any]:
    """Import one native, stable-ID-bound runtime readback.

    The receipt is intentionally narrow: it carries no raw tool response,
    prompt, credential, or search text. Registry identity is checked against
    the already source-verified resolution before any actual coverage edge is
    written.
    """

    path = Path(path).resolve()
    source_bytes = path.read_bytes()
    receipt = json.loads(source_bytes.decode("utf-8"))
    _validate_receipt(receipt, resolution, evaluated_at=evaluated_at)

    scope = receipt["scope"]
    component_ref = receipt["component_ref"]
    source_uri = (
        "actual-self://"
        + quote(scope["host_id"], safe="")
        + "/"
        + quote(component_ref, safe="")
    )
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    carrier_id = stable_id(
        "actual-self-carrier",
        scope["instance_id"],
        component_ref,
    )

    store.begin_immediate()
    try:
        evidence_id = store.add_evidence(
            uri=source_uri,
            source_kind="actual-self-native-receipt",
            sha256=source_sha256,
            locator=receipt["receipt_id"],
            effective_at=receipt["observed_at"],
            confidence=1.0,
            sensitivity="user-local",
            metadata={
                "receipt_schema": RECEIPT_SCHEMA,
                "receipt_id": receipt["receipt_id"],
                "receipt_content_hash": receipt["content_hash"],
                "component_ref": component_ref,
                "component_type": receipt["component_type"],
                "system_id": scope["system_id"],
                "instance_id": scope["instance_id"],
                "host_id": scope["host_id"],
                "producer_ref": receipt["producer"]["ref"],
                "probe_kind": receipt["producer"]["probe_kind"],
                "observed_at": receipt["observed_at"],
                "expires_at": receipt["expires_at"],
                "registry_content_hash": receipt["registry_binding"][
                    "registry_content_hash"
                ],
            },
        )
        store.add_node(
            "carrier",
            component_ref,
            node_id=carrier_id,
            scope=scope["instance_id"],
            metadata={
                "carrier_kind": receipt["component_type"],
                "origin_system": scope["host_id"],
                "actual_self": True,
                "actual_self_receipt_id": receipt["receipt_id"],
                "actual_self_observed_at": receipt["observed_at"],
                "actual_self_expires_at": receipt["expires_at"],
                "producer_ref": receipt["producer"]["ref"],
            },
        )
        identity_status = store.register_component_identity_claim(
            carrier_id=carrier_id,
            component_ref=component_ref,
            evidence_id=evidence_id,
            source_kind="actual-self-native-receipt",
            source_id=receipt["registry_binding"]["record_id"],
        )
        if identity_status != "verified":
            raise ValueError(
                f"actual-self component identity is {identity_status}, not verified"
            )

        edge_ids = []
        for function in receipt["functions"]:
            function_id = f"function:{function['id']}"
            store.add_node(
                "function",
                function["id"],
                node_id=function_id,
                metadata={"desired": False},
            )
            edge_ids.append(
                store.add_edge(
                    carrier_id,
                    "carries",
                    function_id,
                    mode="actual",
                    status=function["status"],
                    confidence=1.0,
                    evidence_id=evidence_id,
                    effective_at=receipt["observed_at"],
                    metadata={
                        "method": "actual-self-native-receipt-v1",
                        "receipt_id": receipt["receipt_id"],
                        "readback_sha256": function["readback_sha256"],
                        "probe_id": function["probe_id"],
                        "producer_ref": receipt["producer"]["ref"],
                        "expires_at": receipt["expires_at"],
                    },
                )
            )
        store.commit()
    except BaseException:
        if store.in_transaction:
            store.rollback()
        raise

    return {
        "schema": "system-explorer.actual-self-import.v1",
        "status": "imported",
        "receipt_id": receipt["receipt_id"],
        "component_ref": component_ref,
        "scope": scope["instance_id"],
        "host_id": scope["host_id"],
        "identity_status": "verified",
        "evidence_id": evidence_id,
        "function_edges": len(edge_ids),
        "source_sha256": source_sha256,
    }


def _validate_receipt(
    receipt: Any,
    resolution: dict[str, Any],
    *,
    evaluated_at: str,
) -> None:
    if not isinstance(receipt, dict):
        raise ValueError("actual-self receipt must be an object")
    unknown = sorted(set(receipt) - ROOT_FIELDS)
    missing = sorted(ROOT_FIELDS - set(receipt))
    if unknown:
        raise ValueError("actual-self receipt has unknown fields: " + ", ".join(unknown))
    if missing:
        raise ValueError("actual-self receipt is missing fields: " + ", ".join(missing))
    if receipt["schema"] != RECEIPT_SCHEMA:
        raise ValueError(f"actual-self receipt must use {RECEIPT_SCHEMA}")
    if receipt["content_hash"] != canonical_content_hash(receipt):
        raise ValueError("actual-self receipt content_hash mismatch")
    _nonempty_string(receipt["receipt_id"], "receipt_id")
    _nonempty_string(receipt["component_ref"], "component_ref")
    if receipt["component_type"] not in COMPONENT_TYPES:
        raise ValueError("actual-self receipt component_type is unsupported")

    observed_at = _timestamp(receipt["observed_at"], "observed_at")
    expires_at = _timestamp(receipt["expires_at"], "expires_at")
    evaluated = _timestamp(evaluated_at, "evaluated_at")
    if expires_at <= observed_at:
        raise ValueError("actual-self receipt expires_at must be after observed_at")
    if evaluated < observed_at:
        raise ValueError("actual-self receipt is not yet effective")
    if evaluated > expires_at:
        raise ValueError("actual-self receipt is expired")

    scope = _object_with_fields(
        receipt["scope"],
        "scope",
        {"system_id", "instance_id", "host_id"},
    )
    instance = resolution.get("instance")
    if not isinstance(instance, dict):
        raise ValueError("actual-self receipts require a host-bound resolution")
    expected_scope = {
        "system_id": resolution["system"]["id"],
        "instance_id": instance["instance_id"],
        "host_id": instance["host_id"],
    }
    if scope != expected_scope:
        raise ValueError("actual-self receipt scope does not match the resolution")

    registry = resolution.get("component_registry")
    if not isinstance(registry, dict) or registry.get("source_verification") != "verified":
        raise ValueError("resolution component registry is not source-verified")
    binding = _object_with_fields(
        receipt["registry_binding"],
        "registry_binding",
        {"registry_content_hash", "source", "record_id"},
    )
    if binding["registry_content_hash"] != registry.get("content_hash"):
        raise ValueError("actual-self receipt registry_content_hash mismatch")

    component = _resolution_component(resolution, receipt["component_ref"])
    if component is None:
        raise ValueError("actual-self receipt component_ref is not in the resolution")
    if component["type"] != receipt["component_type"]:
        raise ValueError("actual-self receipt component_type mismatch")
    registry_resolution = component.get("registry_resolution")
    if (
        not isinstance(registry_resolution, dict)
        or registry_resolution.get("class") != "native-binding"
    ):
        raise ValueError("actual-self receipt component is not natively registry-bound")
    for field in ("source", "record_id"):
        if binding[field] != registry_resolution.get(field):
            raise ValueError(f"actual-self receipt registry {field} mismatch")

    producer = _object_with_fields(
        receipt["producer"],
        "producer",
        {"ref", "probe_kind"},
    )
    _stable_ref(producer["ref"], "producer.ref")
    if producer["probe_kind"] != "native-runtime-readback":
        raise ValueError("actual-self receipt producer must use native-runtime-readback")

    functions = receipt["functions"]
    if not isinstance(functions, list) or not functions:
        raise ValueError("actual-self receipt functions must be a non-empty list")
    allowed_functions = set(component.get("provides", []))
    seen = set()
    for index, function in enumerate(functions):
        item = _object_with_fields(
            function,
            f"functions[{index}]",
            {"id", "status", "probe_id", "readback_sha256"},
        )
        function_id = _nonempty_string(item["id"], f"functions[{index}].id")
        if function_id in seen:
            raise ValueError(f"duplicate actual-self function: {function_id}")
        seen.add(function_id)
        if function_id not in allowed_functions:
            raise ValueError(
                f"actual-self function {function_id!r} is not provided by the component"
            )
        if item["status"] not in FUNCTION_STATUSES:
            raise ValueError(f"functions[{index}].status is unsupported")
        _nonempty_string(item["probe_id"], f"functions[{index}].probe_id")
        _sha256(item["readback_sha256"], f"functions[{index}].readback_sha256")


def _resolution_component(
    resolution: dict[str, Any], component_ref: str
) -> dict[str, Any] | None:
    matches = []
    for bundle in resolution.get("bundles", []):
        for component in bundle.get("components", []):
            ref = component.get("ref")
            ref = ref.get("ref") if isinstance(ref, dict) else ref
            if ref == component_ref:
                matches.append(component)
    if not matches:
        return None
    first = matches[0]
    for component in matches[1:]:
        if component["type"] != first["type"]:
            raise ValueError("component_ref has conflicting types in resolution")
    return first


def _object_with_fields(value: Any, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown:
        raise ValueError(f"{path} has unknown fields: " + ", ".join(unknown))
    if missing:
        raise ValueError(f"{path} is missing fields: " + ", ".join(missing))
    for field in fields:
        _nonempty_string(value[field], f"{path}.{field}")
    return value


def _stable_ref(value: Any, path: str) -> str:
    value = _nonempty_string(value, path)
    if ":" not in value or value.startswith(":") or value.endswith(":"):
        raise ValueError(f"{path} must be a stable typed reference")
    if any(character.isspace() for character in value):
        raise ValueError(f"{path} must not contain whitespace")
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{path} must be a non-empty trimmed string")
    return value


def _sha256(value: Any, path: str) -> str:
    value = _nonempty_string(value, path)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _timestamp(value: Any, path: str) -> datetime:
    value = _nonempty_string(value, path)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{path} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{path} must include a timezone")
    return parsed.astimezone(timezone.utc)
