"""Referential, fail-closed evaluation of external composition cardinalities.

The explorer consumes a pinned rule document but never copies it into the
local evidence graph as a second authority.  Rule availability, freshness and
identity are part of the returned report so a proposal can show why a
cardinality claim is blocked.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .contracts import canonical_content_hash


SCHEMA = "system-explorer.composition-rules.v1"
PIN_SCHEMA = "system-explorer.composition-rule-pin.v1"
REPORT_SCHEMA = "system-explorer.cardinality-report.v1"
HASH_LENGTH = 64


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise ValueError("cardinality evaluation time must be timezone-aware")
    return result.astimezone(timezone.utc)


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


def _blocked(reason: str, *, source: dict[str, Any] | None = None, errors: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "blocked",
        "reason": reason,
        "source": source or {},
        "findings": [],
        "errors": errors or [],
        "runtime_actions": [],
        "target_mutations": [],
    }


def load_pinned_composition_rules(
    path: Path,
    pin: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read one externally-owned rule document and verify its explicit pin."""
    if not isinstance(pin, dict) or pin.get("schema") != PIN_SCHEMA:
        raise ValueError(f"composition rule pin must use {PIN_SCHEMA}")
    required_pin = {"id", "version", "scope", "content_hash", "source_uri"}
    missing = sorted(required_pin - set(pin))
    if missing:
        raise ValueError("composition rule pin is missing: " + ", ".join(missing))
    if not isinstance(pin["content_hash"], str) or len(pin["content_hash"]) != HASH_LENGTH:
        raise ValueError("composition rule pin content_hash must be a SHA-256 hex string")
    if pin.get("expires_at") is not None and _timestamp(pin["expires_at"], "pin.expires_at") <= _utc(now):
        raise ValueError("composition rule pin is expired")
    source_bytes = path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source_hash != pin["content_hash"]:
        raise ValueError("composition rule source hash does not match its pin")
    value = json.loads(source_bytes.decode("utf-8"))
    errors = validate_composition_rules(value)
    if errors:
        raise ValueError("invalid composition rule document: " + "; ".join(errors))
    if value.get("version") != pin["version"]:
        raise ValueError("composition rule version does not match its pin")
    if value.get("scope") != pin["scope"]:
        raise ValueError("composition rule scope does not match its pin")
    return {
        **value,
        "_pin": {
            "id": pin["id"],
            "version": pin["version"],
            "scope": pin["scope"],
            "content_hash": pin["content_hash"],
            "source_uri": pin["source_uri"],
        },
    }


def validate_composition_rules(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["document must be an object"]
    if value.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    for field in ("id", "version", "scope"):
        if not isinstance(value.get(field), (str, list)) or not value[field]:
            errors.append(f"{field} is required")
    rules = value.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("rules must be a non-empty array")
        rules = []
    canonical_value = {key: item for key, item in value.items() if not key.startswith("_")}
    if "content_hash" in value and value.get("content_hash") != canonical_content_hash(canonical_value):
        errors.append("content_hash does not match canonical content")
    if value.get("expires_at") is not None:
        try:
            _timestamp(value["expires_at"], "expires_at")
        except ValueError as exc:
            errors.append(str(exc))
    for index, rule in enumerate(rules):
        label = f"rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{label} must be an object")
            continue
        if not any(field in rule for field in ("exact", "min", "max")):
            errors.append(f"{label} needs exact, min or max")
        values: dict[str, int] = {}
        for field in ("exact", "min", "max"):
            if field not in rule:
                continue
            value_number = rule[field]
            if isinstance(value_number, bool) or not isinstance(value_number, int) or value_number < 0:
                errors.append(f"{label}.{field} must be a non-negative integer")
            else:
                values[field] = value_number
        if "exact" in values and any(
            bound in values and values[bound] != values["exact"]
            for bound in ("min", "max")
        ):
            errors.append(f"{label} exact conflicts with min/max")
        if "min" in values and "max" in values and values["min"] > values["max"]:
            errors.append(f"{label} min exceeds max")
        for field in ("scope", "provider", "component_ref", "function"):
            if field in rule and not isinstance(rule[field], str):
                errors.append(f"{label}.{field} must be a string")
    return errors


def _identity(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"scope": None, "provider": None, "component_ref": None, "function": None}
    return {
        "scope": item.get("scope"),
        "provider": item.get("provider", item.get("provider_id", item.get("carrier"))),
        "component_ref": item.get("component_ref", item.get("component")),
        "function": item.get("function", item.get("function_id")),
        "identity": item.get("identity", item.get("id")),
    }


def _matches(item: dict[str, Any], rule: dict[str, Any]) -> bool:
    for field in ("scope", "provider", "component_ref", "function"):
        expected = rule.get(field)
        if expected in (None, "*"):
            continue
        if item.get(field) != expected:
            return False
    return True


def _bounds(rule: dict[str, Any]) -> tuple[int, int]:
    if "exact" in rule:
        return int(rule["exact"]), int(rule["exact"])
    return int(rule.get("min", 0)), int(rule.get("max", 2**31 - 1))


def evaluate_cardinality(
    rules: dict[str, Any] | None,
    *,
    desired: Iterable[dict[str, Any]] = (),
    actual: Iterable[dict[str, Any]] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compare desired/actual identities against one pinned rule document."""
    current = _utc(now)
    if rules is None:
        return _blocked("missing-authoritative-composition-rules")
    errors = validate_composition_rules(rules)
    if errors:
        return _blocked("invalid-or-conflicting-composition-rules", errors=errors)
    if rules.get("expires_at") is not None and _timestamp(rules["expires_at"], "expires_at") <= current:
        return _blocked("expired-authoritative-composition-rules")
    pin = rules.get("_pin")
    if not isinstance(pin, dict):
        return _blocked("unpinned-authoritative-composition-rules")
    source = {
        "id": pin.get("id"),
        "version": pin.get("version"),
        "scope": pin.get("scope"),
        "content_hash": pin.get("content_hash"),
        "source_uri": pin.get("source_uri"),
    }
    desired_items = [_identity(item) for item in desired]
    actual_items = [_identity(item) for item in actual]
    findings: list[dict[str, Any]] = []
    for index, rule in enumerate(rules["rules"]):
        desired_matches = [item for item in desired_items if _matches(item, rule)]
        actual_matches = [item for item in actual_items if _matches(item, rule)]
        minimum, maximum = _bounds(rule)
        actual_count = len(actual_matches)
        desired_count = len(desired_matches)
        overlap = desired_count > 1 or actual_count > 1
        identity_values = [
            tuple(item.get(field) for field in ("scope", "provider", "component_ref", "function", "identity"))
            for item in actual_matches
        ]
        duplicate = len(identity_values) != len(set(identity_values))
        if duplicate:
            classification = "duplicate-assignment"
            status = "conflict"
        elif actual_count < minimum or actual_count > maximum:
            classification = "cardinality-conflict"
            status = "conflict"
        elif overlap and rule.get("allow_overlap"):
            classification = "intentional-overlap"
            status = "review"
        else:
            classification = "within-cardinality"
            status = "pass"
        findings.append(
            {
                "rule_index": index,
                "scope": rule.get("scope"),
                "provider": rule.get("provider"),
                "component_ref": rule.get("component_ref"),
                "function": rule.get("function"),
                "minimum": minimum,
                "maximum": maximum,
                "desired_count": desired_count,
                "actual_count": actual_count,
                "classification": classification,
                "status": status,
                "source": source,
            }
        )
    statuses = {item["status"] for item in findings}
    report_status = "conflict" if "conflict" in statuses else "review" if "review" in statuses else "verified"
    return {
        "schema": REPORT_SCHEMA,
        "status": report_status,
        "source": source,
        "findings": findings,
        "errors": [],
        "runtime_actions": [],
        "target_mutations": [],
    }


__all__ = [
    "PIN_SCHEMA",
    "REPORT_SCHEMA",
    "SCHEMA",
    "evaluate_cardinality",
    "load_pinned_composition_rules",
    "validate_composition_rules",
]
