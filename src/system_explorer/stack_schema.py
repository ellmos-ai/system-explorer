"""Fail-closed verification of a pinned external ``ellmos.stack.v2`` source."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PIN_SCHEMA = "system-explorer.stack-schema-pin.v1"
REPORT_SCHEMA = "system-explorer.stack-schema-verification.v1"
TARGET_SCHEMA = "ellmos.stack.v2"
HASH_LENGTH = 64


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _now(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise ValueError("verification time must be timezone-aware")
    return result.astimezone(timezone.utc)


def validate_stack_schema_pin(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["pin must be an object"]
    errors: list[str] = []
    if value.get("schema") != PIN_SCHEMA:
        errors.append(f"schema must be {PIN_SCHEMA}")
    required = {"id", "target_schema", "version", "scope", "source_uri", "source_path", "content_hash"}
    missing = sorted(required - set(value))
    if missing:
        errors.append("pin is missing: " + ", ".join(missing))
    if value.get("target_schema") != TARGET_SCHEMA:
        errors.append(f"target_schema must be {TARGET_SCHEMA}")
    for field in ("id", "version", "scope", "source_uri", "source_path"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            errors.append(f"{field} must be a non-empty string")
    digest = value.get("content_hash")
    if not isinstance(digest, str) or len(digest) != HASH_LENGTH or digest.lower() != digest:
        errors.append("content_hash must be lowercase SHA-256")
    if value.get("expires_at") is not None:
        try:
            _timestamp(value["expires_at"], "expires_at")
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def verify_pinned_stack_schema(
    stack_path: Path,
    pin_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify a stack against an external schema artifact named by a pin.

    The schema artifact is read for verification only.  Its content is never
    copied into the repository or evidence store.
    """
    try:
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        errors = validate_stack_schema_pin(pin)
        if errors:
            return _blocked("invalid-stack-schema-pin", errors)
        current = _now(now)
        if pin.get("expires_at") is not None and _timestamp(pin["expires_at"], "expires_at") <= current:
            return _blocked("expired-stack-schema-pin", [])
        source_path = (pin_path.parent / pin["source_path"]).resolve()
        try:
            source_path.relative_to(pin_path.parent.resolve())
        except ValueError:
            return _blocked("stack-schema-source-escapes-pin-root", [])
        if not source_path.is_file():
            return _blocked("stack-schema-source-unavailable", [])
        source_bytes = source_path.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        if source_hash != pin["content_hash"]:
            return _blocked("stack-schema-source-hash-mismatch", [])
        source = json.loads(source_bytes.decode("utf-8"))
        if not isinstance(source, dict) or source.get("schema") != TARGET_SCHEMA:
            return _blocked("stack-schema-source-incompatible", [])
        if source.get("version") != pin["version"]:
            return _blocked("stack-schema-version-mismatch", [])
        stack = json.loads(stack_path.read_text(encoding="utf-8"))
        if not isinstance(stack, dict) or stack.get("schema") != TARGET_SCHEMA:
            return _blocked("stack-manifest-incompatible", [])
        if stack.get("version") != pin["version"]:
            return _blocked("stack-manifest-version-mismatch", [])
        return {
            "schema": REPORT_SCHEMA,
            "status": "verified",
            "target_schema": TARGET_SCHEMA,
            "pin": {
                "id": pin["id"],
                "version": pin["version"],
                "scope": pin["scope"],
                "content_hash": pin["content_hash"],
                "source_uri": pin["source_uri"],
            },
            "source_sha256": source_hash,
            "stack_id": stack.get("id"),
            "stack_version": stack.get("version"),
            "errors": [],
            "runtime_actions": [],
            "target_mutations": [],
        }
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return _blocked("stack-schema-verification-error", [str(exc)])


def _blocked(reason: str, errors: list[str]) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "blocked",
        "target_schema": TARGET_SCHEMA,
        "reason": reason,
        "errors": errors,
        "runtime_actions": [],
        "target_mutations": [],
    }


__all__ = [
    "PIN_SCHEMA",
    "REPORT_SCHEMA",
    "TARGET_SCHEMA",
    "validate_stack_schema_pin",
    "verify_pinned_stack_schema",
]
