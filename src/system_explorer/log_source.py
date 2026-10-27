"""Transport-neutral, bounded log-source contract for an external owner.

The owner authenticates the actor, checks current ACL/policies and emits only
redacted structured events. This module never opens a log file or persists an
excerpt. A source pointer is not authority to read its contents.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

REQUEST_SCHEMA = "ellmos.system-log-source.request.v1"
RESULT_SCHEMA = "ellmos.system-log-source.result.v1"
SAFE_FIELDS = frozenset({"time_utc", "level", "event_code", "count"})
STATES = frozenset({"available", "empty", "missing", "stale", "denied", "unreachable"})
_ID = re.compile(r"^[MR]-[0-9]{8}-[1-9][0-9]{8}$")
_REF = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_EVENT_CODE = re.compile(r"^[A-Z][A-Z0-9_.-]{0,63}$")
_MONTH = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_UTC_INSTANT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$")
_REQUEST_FIELDS = frozenset({
    "schema", "message_id", "receipt_id", "source_ref", "owner_ref",
    "system_ref", "target_ref", "actor_ref", "purpose_ref",
    "access_policy_ref", "redaction_policy_ref", "provenance_ref",
    "retention_ref", "window", "fields", "max_entries",
})
_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})


class LogSourceContractError(ValueError):
    """Invalid caller contract; no owner text read has occurred."""


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    def public(self) -> dict[str, str]:
        return {"from_utc": _format_utc(self.start), "to_utc": _format_utc(self.end)}


@dataclass(frozen=True)
class OwnerResolution:
    """Owner-issued authorization and freshness readback, with no log text."""

    status: str
    source_ref: str = ""
    owner_ref: str = ""
    system_ref: str = ""
    target_ref: str = ""
    actor_ref: str = ""
    purpose_ref: str = ""
    access_policy_ref: str = ""
    redaction_policy_ref: str = ""
    provenance_ref: str = ""
    retention_ref: str = ""
    observed_at: datetime | None = None
    retention_from: datetime | None = None
    retention_until: datetime | None = None
    max_entries: int = 0
    allowed_fields: frozenset[str] = frozenset()
    allowed_event_codes: frozenset[str] = frozenset()


@dataclass(frozen=True)
class OwnerRedactedBatch:
    """A provider assertion that fields were redacted inside the owner boundary."""

    source_ref: str
    provenance_ref: str
    redaction_policy_ref: str
    entries: Sequence[Mapping[str, Any]]
    redaction_applied: bool


class OwnerLogProvider(Protocol):
    """Implemented by the actual source owner, never by a registry pointer.

    resolve_source must verify actor, source, target and current owner ACL and
    policy before read_redacted_excerpt is called. The latter must revalidate
    authorization and redact in the owner process before returning anything.
    """

    def resolve_source(self, request: Mapping[str, Any], window: TimeWindow) -> OwnerResolution: ...

    def read_redacted_excerpt(
        self, request: Mapping[str, Any], window: TimeWindow,
        *, limit: int, fields: frozenset[str],
    ) -> OwnerRedactedBatch: ...


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LogSourceContractError(f"{field} must be a timezone-aware UTC instant")
    if value.utcoffset() != timedelta(0):
        raise LogSourceContractError(f"{field} must use UTC")
    return value.astimezone(timezone.utc)


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not _UTC_INSTANT.fullmatch(value):
        raise LogSourceContractError(f"{field} must be RFC 3339 UTC with Z")
    try:
        return _utc(datetime.fromisoformat(value[:-1] + "+00:00"), field)
    except ValueError as exc:
        raise LogSourceContractError(f"{field} must be RFC 3339 UTC with Z") from exc


def _format_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _window(value: Any, now: datetime) -> TimeWindow:
    if not isinstance(value, Mapping) or not isinstance(value.get("kind"), str):
        raise LogSourceContractError("window must declare a kind")
    kind = value["kind"]
    if kind == "24h" and set(value) == {"kind"}:
        return TimeWindow(now - timedelta(hours=24), now)
    if kind == "monthly" and set(value) == {"kind", "month"}:
        month = value["month"]
        if not isinstance(month, str) or not _MONTH.fullmatch(month):
            raise LogSourceContractError("monthly window requires YYYY-MM")
        year, number = map(int, month.split("-"))
        try:
            start = datetime(year, number, 1, tzinfo=timezone.utc)
            end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=timezone.utc)
        except ValueError as exc:
            raise LogSourceContractError("monthly window is outside the supported calendar") from exc
        if start >= now:
            raise LogSourceContractError("monthly window cannot start in the future")
        return TimeWindow(start, min(end, now))
    if kind == "other" and set(value) == {"kind", "from_utc", "to_utc"}:
        start = _parse_utc(value["from_utc"], "from_utc")
        end = _parse_utc(value["to_utc"], "to_utc")
        if start >= end or end > now or end - start > timedelta(days=31):
            raise LogSourceContractError("other window must be bounded, past and increasing")
        return TimeWindow(start, end)
    raise LogSourceContractError("unsupported or incomplete window")


def _request(value: Mapping[str, Any], now: datetime) -> tuple[dict[str, Any], TimeWindow]:
    if not isinstance(value, Mapping) or set(value) != _REQUEST_FIELDS:
        raise LogSourceContractError("request fields are invalid")
    if value["schema"] != REQUEST_SCHEMA:
        raise LogSourceContractError("request schema is unsupported")
    for field, prefix in (("message_id", "M-"), ("receipt_id", "R-")):
        identity = value[field]
        if not isinstance(identity, str) or not identity.startswith(prefix) or not _ID.fullmatch(identity):
            raise LogSourceContractError(f"{field} is invalid")
    for field in (
        "source_ref", "owner_ref", "system_ref", "target_ref", "actor_ref",
        "purpose_ref", "access_policy_ref", "redaction_policy_ref",
        "provenance_ref", "retention_ref",
    ):
        ref = value[field]
        if not isinstance(ref, str) or not _REF.fullmatch(ref):
            raise LogSourceContractError(f"{field} must be an opaque reference")
    fields = value["fields"]
    if not isinstance(fields, list) or not fields or len(fields) > len(SAFE_FIELDS):
        raise LogSourceContractError("fields must be a small allowlist")
    if (any(not isinstance(field, str) for field in fields)
            or not set(fields) <= SAFE_FIELDS or "time_utc" not in fields):
        raise LogSourceContractError("fields contain unsafe values")
    if len(set(fields)) != len(fields):
        raise LogSourceContractError("fields contain duplicates")
    limit = value["max_entries"]
    if type(limit) is not int or not 1 <= limit <= 32:
        raise LogSourceContractError("max_entries must be between 1 and 32")
    return dict(value), _window(value["window"], now)


def _public(request: Mapping[str, Any], window: TimeWindow, status: str,
            *, entries: list[dict[str, Any]] | None = None,
            provenance_ref: str | None = None) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "message_id": request["message_id"],
        "receipt_id": request["receipt_id"],
        "source_ref": request["source_ref"],
        "window": window.public(),
        "provenance_ref": provenance_ref,
        "entries": entries or [],
    }


def _resolution(request: Mapping[str, Any], window: TimeWindow,
                provider: OwnerLogProvider, now: datetime) -> tuple[str, OwnerResolution | None]:
    try:
        resolution = provider.resolve_source(request, window)
    except Exception:
        return "unreachable", None
    if not isinstance(resolution, OwnerResolution) or resolution.status not in STATES:
        return "unreachable", None
    if resolution.status in {"missing", "denied", "unreachable"}:
        return resolution.status, None
    if resolution.status != "available":
        return "unreachable", None
    for field in (
        "source_ref", "owner_ref", "system_ref", "target_ref", "actor_ref",
        "purpose_ref", "access_policy_ref",
        "redaction_policy_ref", "provenance_ref", "retention_ref",
    ):
        if getattr(resolution, field) != request[field]:
            return "denied", None
    try:
        observed = _utc(resolution.observed_at, "observed_at")
        retained_from = _utc(resolution.retention_from, "retention_from")
        retained_until = _utc(resolution.retention_until, "retention_until")
    except LogSourceContractError:
        return "stale", None
    if (observed > now + timedelta(seconds=30) or now - observed > timedelta(minutes=5)
            or window.start < retained_from or window.end > retained_until):
        return "stale", None
    fields = frozenset(request["fields"])
    if (type(resolution.max_entries) is not int or resolution.max_entries < request["max_entries"]
            or not isinstance(resolution.allowed_fields, frozenset)
            or not fields <= resolution.allowed_fields or not resolution.allowed_fields <= SAFE_FIELDS):
        return "denied", None
    if (not isinstance(resolution.allowed_event_codes, frozenset)
            or not 1 <= len(resolution.allowed_event_codes) <= 64
            or any(not isinstance(code, str) or not _EVENT_CODE.fullmatch(code)
                   for code in resolution.allowed_event_codes)):
        return "denied", None
    return "available", resolution


def resolve_source(request: Mapping[str, Any], provider: OwnerLogProvider,
                   *, now: datetime | None = None) -> dict[str, Any]:
    """Resolve owner authorization and freshness without requesting log text."""
    current = _utc(now or datetime.now(timezone.utc), "now")
    checked, window = _request(request, current)
    status, resolution = _resolution(checked, window, provider, current)
    return _public(checked, window, status, provenance_ref=(
        resolution.provenance_ref if resolution else None
    ))


def _safe_entries(batch: OwnerRedactedBatch, request: Mapping[str, Any],
                  window: TimeWindow, resolution: OwnerResolution) -> list[dict[str, Any]] | None:
    if (not isinstance(batch, OwnerRedactedBatch) or batch.redaction_applied is not True
            or batch.source_ref != request["source_ref"]
            or batch.provenance_ref != request["provenance_ref"]
            or batch.redaction_policy_ref != request["redaction_policy_ref"]
            or not isinstance(batch.entries, Sequence) or isinstance(batch.entries, (str, bytes))
            or len(batch.entries) > request["max_entries"]):
        return None
    fields = set(request["fields"])
    safe: list[dict[str, Any]] = []
    for entry in batch.entries:
        if not isinstance(entry, Mapping) or set(entry) != fields:
            return None
        for field, value in entry.items():
            if field == "time_utc":
                try:
                    timestamp = _parse_utc(value, "time_utc")
                except LogSourceContractError:
                    return None
                if not window.start <= timestamp < window.end:
                    return None
            elif field == "level" and (not isinstance(value, str) or value not in _LEVELS):
                return None
            elif field == "event_code" and (
                not isinstance(value, str) or value not in resolution.allowed_event_codes
            ):
                return None
            elif field == "count" and (type(value) is not int or not 1 <= value <= 100_000):
                return None
        safe.append(dict(entry))
    return safe


def read_excerpt(request: Mapping[str, Any], provider: OwnerLogProvider,
                 *, now: datetime | None = None) -> dict[str, Any]:
    """Reauthorize, then ask the owner for already-redacted structured events."""
    current = _utc(now or datetime.now(timezone.utc), "now")
    checked, window = _request(request, current)
    status, resolution = _resolution(checked, window, provider, current)
    if resolution is None:
        return _public(checked, window, status)
    try:
        batch = provider.read_redacted_excerpt(
            checked, window, limit=checked["max_entries"], fields=frozenset(checked["fields"])
        )
    except Exception:
        return _public(checked, window, "unreachable")
    entries = _safe_entries(batch, checked, window, resolution)
    if entries is None:
        return _public(checked, window, "denied")
    return _public(checked, window, "available" if entries else "empty",
                   entries=entries, provenance_ref=resolution.provenance_ref)
