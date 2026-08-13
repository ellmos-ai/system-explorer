"""Import external probe results as referential, non-authoritative receipts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import canonical_content_hash
from .store import Store


SCHEMA = "system-explorer.probe-receipt.v1"
HASH_RE = re.compile(r"\A[0-9a-f]{64}\Z")
OUTCOME_STATUSES = {"success", "failure", "uncertain"}


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


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def validate_probe_receipt(value: Any) -> list[str]:
    """Return all contract violations without retaining receipt payloads."""
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["receipt must be an object"]
    required = {
        "schema",
        "receipt_id",
        "version",
        "source",
        "runner",
        "task",
        "experiment",
        "repetitions",
        "steps",
        "outcome",
        "metrics",
        "observed_at",
        "source_hash",
        "content_hash",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append("missing fields: " + ", ".join(missing))
    if value.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    for field in ("receipt_id", "version"):
        if field in value:
            try:
                _nonempty(value[field], field)
            except ValueError as exc:
                errors.append(str(exc))
    for field in ("source", "runner", "task", "experiment"):
        section = value.get(field)
        if not isinstance(section, dict):
            errors.append(f"{field} must be an object")
            continue
        try:
            _nonempty(section.get("id", section.get("ref")), f"{field}.id")
        except ValueError as exc:
            errors.append(str(exc))
    repetitions = value.get("repetitions")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        errors.append("repetitions must be a positive integer")
    steps = value.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty array")
    elif not all(isinstance(step, dict) for step in steps):
        errors.append("steps must contain objects")
    outcome = value.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("status") not in OUTCOME_STATUSES:
        errors.append("outcome.status must be success, failure or uncertain")
    metrics = value.get("metrics")
    if not isinstance(metrics, dict) or any(
        not isinstance(key, str) or not isinstance(metric, (int, float)) or isinstance(metric, bool)
        for key, metric in (metrics.items() if isinstance(metrics, dict) else ())
    ):
        errors.append("metrics must be an object of numeric values")
    try:
        _timestamp(value.get("observed_at"), "observed_at")
    except ValueError as exc:
        errors.append(str(exc))
    for field in ("source_hash", "content_hash"):
        if not HASH_RE.fullmatch(str(value.get(field, ""))):
            errors.append(f"{field} must be lowercase SHA-256")
    if isinstance(value.get("content_hash"), str):
        canonical = dict(value)
        canonical.pop("content_hash", None)
        if value["content_hash"] != canonical_content_hash(canonical):
            errors.append("content_hash does not match canonical content")
    source = value.get("source")
    if isinstance(source, dict):
        source_hash = source.get("sha256", source.get("content_hash"))
        if source_hash != value.get("source_hash"):
            errors.append("source.sha256 must match source_hash")
        try:
            _nonempty(source.get("uri"), "source.uri")
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def import_probe_receipt(
    path: Path,
    store: Store,
    *,
    expected_source_sha256: str | None = None,
    expected_runner_id: str | None = None,
    expected_task_id: str | None = None,
    expected_experiment_id: str | None = None,
) -> dict[str, Any]:
    """Validate and index one receipt without persisting its raw result payload."""
    source_bytes = path.read_bytes()
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    value = json.loads(source_bytes.decode("utf-8"))
    errors = validate_probe_receipt(value)
    if errors:
        raise ValueError("invalid probe receipt: " + "; ".join(errors))
    if expected_source_sha256 is not None and value["source_hash"] != expected_source_sha256:
        raise ValueError("probe receipt source hash is not authorized")
    identifiers = {
        "runner": value["runner"].get("id", value["runner"].get("ref")),
        "task": value["task"].get("id", value["task"].get("ref")),
        "experiment": value["experiment"].get("id", value["experiment"].get("ref")),
    }
    expected = {
        "runner": expected_runner_id,
        "task": expected_task_id,
        "experiment": expected_experiment_id,
    }
    for key, expected_value in expected.items():
        if expected_value is not None and identifiers[key] != expected_value:
            raise ValueError(f"probe receipt {key} identity is not authorized")

    receipt_id = value["receipt_id"]
    existing = store.db.execute(
        "SELECT * FROM probe_receipts WHERE receipt_id = ?", (receipt_id,)
    ).fetchone()
    if existing is not None:
        if (
            existing["content_hash"] != value["content_hash"]
            or existing["source_sha256"] != value["source_hash"]
            or existing["source_uri"] != value["source"]["uri"]
        ):
            raise ValueError("probe receipt identity conflicts with an imported receipt")
        return _result(value, source_digest, existing["evidence_id"], "unchanged")

    owns_transaction = not store.in_transaction
    if owns_transaction:
        store.begin_immediate()
    try:
        source = value["source"]
        source_uri = source["uri"]
        evidence_id = store.add_evidence(
            uri=source_uri,
            source_kind="probe-receipt",
            sha256=source_digest,
            locator=receipt_id,
            effective_at=value["observed_at"],
            modified_at=str(path.stat().st_mtime),
            confidence=1.0,
            sensitivity="user-local",
            metadata={
                "receipt_schema": SCHEMA,
                "receipt_id": receipt_id,
                "receipt_version": value["version"],
                "runner_id": identifiers["runner"],
                "task_id": identifiers["task"],
                "experiment_id": identifiers["experiment"],
                "repetitions": value["repetitions"],
                "step_count": len(value["steps"]),
                "outcome_status": value["outcome"]["status"],
                "metric_names": sorted(value["metrics"]),
                "source_hash": value["source_hash"],
                "receipt_content_hash": value["content_hash"],
                "raw_result_stored": False,
            },
        )
        store.db.execute(
            """
            INSERT INTO probe_receipts
            (receipt_id, source_uri, source_sha256, content_hash, runner_id,
             task_id, experiment_id, observed_at, evidence_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_id,
                source_uri,
                value["source_hash"],
                value["content_hash"],
                identifiers["runner"],
                identifiers["task"],
                identifiers["experiment"],
                value["observed_at"],
                evidence_id,
                value["observed_at"],
            ),
        )
        if owns_transaction:
            store.commit()
        return _result(value, source_digest, evidence_id, "imported")
    except BaseException:
        if owns_transaction and store.in_transaction:
            store.rollback()
        raise


def _result(value: dict[str, Any], source_digest: str, evidence_id: str, status: str) -> dict[str, Any]:
    return {
        "schema": "system-explorer.probe-receipt-import.v1",
        "receipt_id": value["receipt_id"],
        "content_hash": value["content_hash"],
        "source_sha256": source_digest,
        "evidence_id": evidence_id,
        "status": status,
        "outcome_status": value["outcome"]["status"],
        "repetitions": value["repetitions"],
        "step_count": len(value["steps"]),
        "runtime_actions": [],
        "target_mutations": [],
        "coverage_claim": False,
        "actual_self_claim": False,
        "authorization_claim": False,
    }


__all__ = ["SCHEMA", "import_probe_receipt", "validate_probe_receipt"]
