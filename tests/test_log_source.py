"""Synthetic owner-provider contract tests; no real logs or BACH API calls."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from system_explorer.log_source import (
    REQUEST_SCHEMA, LogSourceContractError, OwnerRedactedBatch, OwnerResolution,
    read_excerpt, resolve_source,
)

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def request(**changes):
    value = {
        "schema": REQUEST_SCHEMA,
        "message_id": "M-20261027-123456789",
        "receipt_id": "R-20261027-123456789",
        "source_ref": "log:synthetic",
        "owner_ref": "owner:synthetic",
        "system_ref": "system:synthetic",
        "target_ref": "target:synthetic",
        "actor_ref": "actor:synthetic",
        "purpose_ref": "purpose:discussion",
        "access_policy_ref": "policy:access",
        "redaction_policy_ref": "policy:redaction",
        "provenance_ref": "evidence:synthetic",
        "retention_ref": "retention:synthetic",
        "window": {"kind": "24h"},
        "fields": ["time_utc", "level", "event_code", "count"],
        "max_entries": 2,
    }
    value.update(changes)
    return value


class SyntheticOwner:
    def __init__(self, *, status="available", entries=None):
        self.status = status
        self.entries = entries
        self.calls = []
        self.override = {}

    def resolve_source(self, req, window):
        self.calls.append("authorize")
        if self.status != "available":
            return OwnerResolution(status=self.status)
        values = {key: req[key] for key in (
            "source_ref", "owner_ref", "system_ref", "target_ref", "actor_ref",
            "purpose_ref", "access_policy_ref", "redaction_policy_ref",
            "provenance_ref", "retention_ref",
        )}
        values.update(self.override)
        return OwnerResolution(
            status="available", observed_at=NOW,
            retention_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
            retention_until=NOW, max_entries=2,
            allowed_fields=frozenset(req["fields"]),
            allowed_event_codes=frozenset({"SYNC_DELAY", "SAFE_EVENT"}), **values,
        )

    def read_redacted_excerpt(self, req, window, *, limit, fields):
        self.calls.append("read")
        assert limit <= 2 and fields <= {"time_utc", "level", "event_code", "count"}
        entries = self.entries
        if entries is None:
            entries = [{
                "time_utc": (window.end - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                "level": "warning", "event_code": "SYNC_DELAY", "count": 1,
            }]
        return OwnerRedactedBatch(
            source_ref=req["source_ref"], provenance_ref=req["provenance_ref"],
            redaction_policy_ref=req["redaction_policy_ref"],
            entries=entries, redaction_applied=True,
        )


def test_rolling_24h_resolution_and_bounded_redacted_read():
    owner = SyntheticOwner()
    resolved = resolve_source(request(), owner, now=NOW)
    assert resolved["status"] == "available"
    assert resolved["window"] == {
        "from_utc": "2026-10-26T12:00:00Z", "to_utc": "2026-10-27T12:00:00Z",
    }
    assert owner.calls == ["authorize"]
    result = read_excerpt(request(), owner, now=NOW)
    assert result["status"] == "available"
    assert result["entries"] == [{
        "time_utc": "2026-10-27T11:00:00Z", "level": "warning",
        "event_code": "SYNC_DELAY", "count": 1,
    }]
    assert (result["message_id"], result["receipt_id"]) == (
        "M-20261027-123456789", "R-20261027-123456789",
    )
    assert owner.calls == ["authorize", "authorize", "read"]


def test_monthly_and_other_use_exact_utc_half_open_ranges():
    owner = SyntheticOwner()
    previous = read_excerpt(request(window={"kind": "monthly", "month": "2026-09"}), owner, now=NOW)
    assert previous["window"] == {
        "from_utc": "2026-09-01T00:00:00Z", "to_utc": "2026-10-01T00:00:00Z",
    }
    current = resolve_source(request(window={"kind": "monthly", "month": "2026-10"}), owner, now=NOW)
    assert current["window"]["to_utc"] == "2026-10-27T12:00:00Z"
    custom = read_excerpt(request(window={
        "kind": "other", "from_utc": "2026-10-26T10:00:00Z",
        "to_utc": "2026-10-26T12:00:00Z",
    }), owner, now=NOW)
    assert custom["status"] == "available"
    assert custom["window"]["to_utc"] == "2026-10-26T12:00:00Z"


@pytest.mark.parametrize("status", ["missing", "denied", "unreachable"])
def test_non_available_owner_states_never_read(status):
    owner = SyntheticOwner(status=status)
    assert read_excerpt(request(), owner, now=NOW)["status"] == status
    assert owner.calls == ["authorize"]


def test_empty_is_distinct_from_missing_and_unreachable():
    owner = SyntheticOwner(entries=[])
    result = read_excerpt(request(), owner, now=NOW)
    assert result["status"] == "empty" and result["entries"] == []
    assert owner.calls == ["authorize", "read"]


def test_owner_exception_is_unreachable_without_error_text():
    class OfflineOwner:
        def resolve_source(self, _request, _window):
            raise OSError("synthetic private transport detail")

    result = read_excerpt(request(), OfflineOwner(), now=NOW)
    assert result["status"] == "unreachable"
    assert "private transport detail" not in repr(result)


@pytest.mark.parametrize("field,wrong", [
    ("actor_ref", "actor:other"), ("owner_ref", "owner:other"),
    ("system_ref", "system:other"), ("target_ref", "target:other"),
    ("purpose_ref", "purpose:other"), ("access_policy_ref", "policy:other"),
    ("redaction_policy_ref", "policy:other"), ("provenance_ref", "evidence:other"),
    ("retention_ref", "retention:other"),
])
def test_owner_binding_mismatch_denies_before_text_read(field, wrong):
    owner = SyntheticOwner()
    owner.override[field] = wrong
    result = read_excerpt(request(), owner, now=NOW)
    assert result["status"] == "denied" and result["entries"] == []
    assert owner.calls == ["authorize"]


def test_stale_provenance_and_retention_block_read():
    owner = SyntheticOwner()
    original = owner.resolve_source

    def stale(req, window):
        return replace(original(req, window), observed_at=NOW - timedelta(minutes=6))

    owner.resolve_source = stale
    assert read_excerpt(request(), owner, now=NOW)["status"] == "stale"
    assert "read" not in owner.calls
    owner = SyntheticOwner()
    original = owner.resolve_source

    def expired(req, window):
        return replace(original(req, window), retention_from=NOW - timedelta(hours=1))

    owner.resolve_source = expired
    assert read_excerpt(request(), owner, now=NOW)["status"] == "stale"
    assert "read" not in owner.calls


def test_unsafe_fields_never_leave_owner_boundary_in_result():
    for unsafe in (
        {"raw_text": "raw chat transcript"},
        {"event_code": "TOKEN=private-secret"},
        {"event_code": "PRIVATESECRET123"},
        {"event_code": "C:/Users/private/logs"},
        {"event_code": "person@example.org"},
    ):
        entry = {
            "time_utc": "2026-10-27T11:00:00Z", "level": "info",
            "event_code": "SAFE_EVENT", "count": 1,
        }
        entry.update(unsafe)
        result = read_excerpt(request(), SyntheticOwner(entries=[entry]), now=NOW)
        assert result["status"] == "denied" and result["entries"] == []
        assert all(text not in repr(result) for text in (
            "raw chat", "private-secret", "PRIVATESECRET123", "C:/", "@",
        ))


def test_owner_redaction_assertion_and_field_policy_are_required():
    owner = SyntheticOwner()
    original_resolution = owner.resolve_source

    def narrow_fields(req, window):
        return replace(original_resolution(req, window), allowed_fields=frozenset({"time_utc"}))

    owner.resolve_source = narrow_fields
    assert read_excerpt(request(), owner, now=NOW)["status"] == "denied"
    assert owner.calls == ["authorize"]

    owner = SyntheticOwner()
    original = owner.read_redacted_excerpt

    def unredacted(req, window, *, limit, fields):
        return replace(original(req, window, limit=limit, fields=fields), redaction_applied=False)

    owner.read_redacted_excerpt = unredacted
    result = read_excerpt(request(), owner, now=NOW)
    assert result["status"] == "denied" and result["entries"] == []


def test_current_owner_decision_is_read_again_for_each_call():
    owner = SyntheticOwner()
    assert resolve_source(request(), owner, now=NOW)["status"] == "available"
    owner.status = "denied"
    assert read_excerpt(request(), owner, now=NOW)["status"] == "denied"
    assert owner.calls == ["authorize", "authorize"]


def test_invalid_requests_stop_before_owner_access():
    for bad in (
        request(source_ref="C:/logs/private"),
        request(fields=["raw_text"]),
        request(fields=["event_code"]),
        request(max_entries=10_000),
        request(window={"kind": "monthly"}),
        request(window={"kind": "monthly", "month": "9999-12"}),
        request(window={"kind": "other", "from_utc": "2026-10-26T10:00:00Z",
                        "to_utc": "2026-10-27T13:00:00Z"}),
    ):
        owner = SyntheticOwner()
        with pytest.raises(LogSourceContractError):
            read_excerpt(bad, owner, now=NOW)
        assert owner.calls == []
