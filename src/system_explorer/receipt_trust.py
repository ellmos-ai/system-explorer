from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .contracts import canonical_content_hash
from .util import expand_path


TRUST_STORE_SCHEMA = "system-explorer.receipt-trust-store.v1"
SIGNATURE_ALGORITHM = "ed25519"


@dataclass(frozen=True)
class ReceiptTrustStore:
    path: Path
    file_sha256: str
    content_hash: str
    signers: dict[str, dict[str, Any]]


def load_receipt_trust_store(
    config: dict[str, Any],
) -> ReceiptTrustStore:
    configured = config.get("receipt_trust_store")
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError(
            "config receipt_trust_store is required for signed runtime receipts"
        )
    path = expand_path(configured, Path(config["_base"])).resolve()
    source_bytes = path.read_bytes()
    file_sha256 = hashlib.sha256(source_bytes).hexdigest()
    expected_sha256 = config.get("receipt_trust_store_sha256")
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError(
            "config receipt_trust_store_sha256 must pin a lowercase SHA-256"
        )
    if file_sha256 != expected_sha256:
        raise ValueError("receipt trust store does not match configured SHA-256 pin")
    value = json.loads(source_bytes.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("receipt trust store must be an object")
    if value.get("schema") != TRUST_STORE_SCHEMA:
        raise ValueError(f"receipt trust store must use {TRUST_STORE_SCHEMA}")
    if value.get("content_hash") != canonical_content_hash(value):
        raise ValueError("receipt trust store content_hash mismatch")
    if set(value) != {"schema", "version", "signers", "content_hash"}:
        raise ValueError("receipt trust store has unsupported fields")
    if not isinstance(value.get("version"), str) or not value["version"]:
        raise ValueError("receipt trust store version is required")
    signers = value.get("signers")
    if not isinstance(signers, list) or not signers:
        raise ValueError("receipt trust store signers must be non-empty")
    index: dict[str, dict[str, Any]] = {}
    for position, signer in enumerate(signers):
        _validate_signer(signer, position, path.parent)
        signer_id = signer["signer_id"]
        if signer_id in index:
            raise ValueError(f"duplicate receipt trust signer: {signer_id}")
        index[signer_id] = dict(signer)
    return ReceiptTrustStore(
        path=path,
        file_sha256=file_sha256,
        content_hash=value["content_hash"],
        signers=index,
    )


def verify_signed_receipt(
    receipt: dict[str, Any],
    trust_store: ReceiptTrustStore,
    *,
    receipt_schema: str,
    actor: dict[str, Any],
    actor_kind: str,
    host_id: str,
    issued_at: datetime,
    expires_at: datetime,
    authority_type: str | None = None,
    delegation_ref: str | None = None,
) -> dict[str, Any]:
    signature = receipt.get("signature")
    if not isinstance(signature, dict) or set(signature) != {
        "algorithm",
        "signer_id",
        "value",
    }:
        raise ValueError("signed receipt requires an exact signature object")
    if signature["algorithm"] != SIGNATURE_ALGORITHM:
        raise ValueError("signed receipt algorithm must be ed25519")
    signer_id = signature.get("signer_id")
    if not isinstance(signer_id, str) or not signer_id:
        raise ValueError("signed receipt signer_id is required")
    if actor.get("signer_id") != signer_id:
        raise ValueError("receipt actor signer_id does not match signature")
    signer = trust_store.signers.get(signer_id)
    if signer is None:
        raise ValueError("receipt signer is not in the configured trust store")
    if receipt_schema not in signer["allowed_receipt_schemas"]:
        raise ValueError("receipt schema is not allowed for this signer")
    if host_id not in signer["allowed_host_ids"]:
        raise ValueError("receipt host is not allowed for this signer")

    if actor_kind == "producer":
        if actor.get("ref") not in signer["allowed_actor_refs"]:
            raise ValueError("receipt producer ref is not allowed for this signer")
        if actor.get("adapter_id") not in signer["allowed_adapter_ids"]:
            raise ValueError("receipt adapter is not allowed for this signer")
    elif actor_kind == "issuer":
        if actor.get("ref") not in signer["allowed_actor_refs"]:
            raise ValueError("authority issuer ref is not allowed for this signer")
        if actor.get("adapter_id") not in signer["allowed_adapter_ids"]:
            raise ValueError("authority adapter is not allowed for this signer")
        if authority_type not in signer["allowed_authority_types"]:
            raise ValueError("authority type is not allowed for this signer")
        if (
            authority_type == "delegated-avatar-decision"
            and delegation_ref not in signer["allowed_delegation_refs"]
        ):
            raise ValueError("delegation ref is not allowed for this signer")
    else:
        raise ValueError("unsupported signed receipt actor kind")

    ttl_seconds = (expires_at - issued_at).total_seconds()
    if ttl_seconds <= 0:
        raise ValueError("signed receipt expiry must be after issuance")
    if ttl_seconds > signer["max_ttl_seconds"]:
        raise ValueError("signed receipt exceeds signer max_ttl_seconds")

    payload = signed_payload_bytes(receipt)
    expected_hash = hashlib.sha256(payload).hexdigest()
    if receipt.get("content_hash") != expected_hash:
        raise ValueError("signed receipt content_hash mismatch")
    try:
        signature_bytes = base64.b64decode(
            signature["value"],
            validate=True,
        )
    except (binascii.Error, TypeError) as error:
        raise ValueError("signed receipt signature is not valid base64") from error
    public_key = _public_key(signer, trust_store.path.parent)
    try:
        public_key.verify(signature_bytes, payload)
    except InvalidSignature as error:
        raise ValueError("signed receipt signature verification failed") from error
    return {
        "signer_id": signer_id,
        "trust_store_content_hash": trust_store.content_hash,
        "trust_store_file_sha256": trust_store.file_sha256,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "signature_verified": True,
        "max_ttl_seconds": signer["max_ttl_seconds"],
    }


def signed_payload_bytes(receipt: dict[str, Any]) -> bytes:
    payload = dict(receipt)
    payload.pop("content_hash", None)
    payload.pop("signature", None)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def signed_content_hash(receipt: dict[str, Any]) -> str:
    return hashlib.sha256(signed_payload_bytes(receipt)).hexdigest()


def _validate_signer(
    signer: Any,
    position: int,
    trust_root: Path,
) -> None:
    fields = {
        "signer_id",
        "algorithm",
        "public_key_path",
        "allowed_receipt_schemas",
        "allowed_actor_refs",
        "allowed_adapter_ids",
        "allowed_host_ids",
        "allowed_authority_types",
        "allowed_delegation_refs",
        "max_ttl_seconds",
    }
    if not isinstance(signer, dict) or set(signer) != fields:
        raise ValueError(f"receipt trust signer {position} has invalid fields")
    for field in ("signer_id", "public_key_path"):
        if not isinstance(signer[field], str) or not signer[field].strip():
            raise ValueError(f"receipt trust signer {position} requires {field}")
    if signer["algorithm"] != SIGNATURE_ALGORITHM:
        raise ValueError("receipt trust signers must use ed25519")
    for field in (
        "allowed_receipt_schemas",
        "allowed_actor_refs",
        "allowed_adapter_ids",
        "allowed_host_ids",
        "allowed_authority_types",
        "allowed_delegation_refs",
    ):
        values = signer[field]
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value for value in values
        ):
            raise ValueError(f"receipt trust signer {position} {field} is invalid")
        if len(values) != len(set(values)):
            raise ValueError(f"receipt trust signer {position} {field} has duplicates")
    ttl = signer["max_ttl_seconds"]
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0:
        raise ValueError("receipt trust signer max_ttl_seconds must be positive")
    _public_key(signer, trust_root)


def _public_key(
    signer: dict[str, Any],
    trust_root: Path,
) -> Ed25519PublicKey:
    key_path = (trust_root / signer["public_key_path"]).resolve()
    try:
        key_path.relative_to(trust_root.resolve())
    except ValueError as error:
        raise ValueError("receipt signer public key escapes trust store root") from error
    value = serialization.load_pem_public_key(key_path.read_bytes())
    if not isinstance(value, Ed25519PublicKey):
        raise ValueError("receipt signer public key must be Ed25519")
    return value
