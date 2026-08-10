"""Opt-in, content-minimal provider-native live-hook adapters.

The adapter deliberately accepts only normalized event metadata.  A native
provider integration may observe richer call/result payloads, but those
payloads are rejected at this boundary and are never copied to the Store.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import timezone
from typing import Any

from .store import Store
from .util import stable_id
from .validation import nonempty_string, sha256, timestamp


HOOK_SCHEMA = "system-explorer.provider-hook-event.v1"
HOOK_SOURCE_KIND = "provider-hook-event"
EVENT_KINDS = {"call", "result", "error"}
READBACK_STATUSES = {"not-applicable", "observed", "success", "partial", "failed", "unknown"}
_RETENTION_RE = re.compile(r"\AP(?:[1-9][0-9]*)D\Z")
_TOKEN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_ALLOWED_FIELDS = {
    "event_kind",
    "kind",
    "timestamp",
    "occurred_at",
    "source_sha256",
    "source_hash",
    "call_id",
    "readback_status",
    "uncertain",
    "error_code",
}
_PROHIBITED_KEY_PARTS = {
    "api_key",
    "argument",
    "authorization",
    "content",
    "credential",
    "input",
    "message",
    "output",
    "password",
    "payload",
    "prompt",
    "raw",
    "response",
    "secret",
    "token",
}


class ProviderHookError(ValueError):
    """A provider hook event was denied or failed closed validation."""


@dataclass(frozen=True)
class ProviderHookPolicy:
    """Explicit gates for a provider-native hook.

    All gates default to false.  Enabling an adapter therefore requires both
    explicit user consent and an external authorization decision.  Retention
    is metadata only; no raw event content is retained by this module.
    """

    enabled: bool = False
    consent_granted: bool = False
    authorized: bool = False
    retention: str = "P30D"

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ProviderHookError("provider hook enabled must be boolean")
        if not isinstance(self.consent_granted, bool):
            raise ProviderHookError("provider hook consent_granted must be boolean")
        if not isinstance(self.authorized, bool):
            raise ProviderHookError("provider hook authorized must be boolean")
        retention = nonempty_string(self.retention, "provider hook retention")
        if not _RETENTION_RE.fullmatch(retention):
            raise ProviderHookError("provider hook retention must use a positive day duration")


class ProviderHookAdapter:
    """Normalize call/result/error events without retaining their content."""

    def __init__(
        self,
        provider: str,
        adapter_id: str,
        *,
        policy: ProviderHookPolicy | None = None,
        store: Store | None = None,
    ) -> None:
        self.provider = _adapter_token(provider, "provider")
        self.adapter_id = _adapter_token(adapter_id, "adapter_id")
        self.policy = policy or ProviderHookPolicy()
        self.store = store

    def deactivate(self) -> None:
        """Disable this adapter for all subsequent events.

        Deactivation is one-way for the adapter instance.  Re-enabling a hook
        requires constructing a new instance with fresh explicit consent and
        authorization, so a stale authorization cannot silently reactivate it.
        """

        self.policy = replace(
            self.policy,
            enabled=False,
            consent_granted=False,
            authorized=False,
        )

    def on_call(
        self,
        *,
        timestamp: str,
        source_sha256: str,
        call_id: str | None = None,
        uncertain: bool = True,
    ) -> dict[str, Any]:
        return self.ingest(
            {
                "event_kind": "call",
                "timestamp": timestamp,
                "source_sha256": source_sha256,
                "call_id": call_id,
                "uncertain": uncertain,
            }
        )

    def on_result(
        self,
        *,
        timestamp: str,
        source_sha256: str,
        readback_status: str,
        call_id: str | None = None,
        uncertain: bool | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "event_kind": "result",
            "timestamp": timestamp,
            "source_sha256": source_sha256,
            "readback_status": readback_status,
            "call_id": call_id,
        }
        if uncertain is not None:
            event["uncertain"] = uncertain
        return self.ingest(event)

    def on_error(
        self,
        *,
        timestamp: str,
        source_sha256: str,
        error_code: str = "provider-error",
        call_id: str | None = None,
        uncertain: bool = True,
    ) -> dict[str, Any]:
        return self.ingest(
            {
                "event_kind": "error",
                "timestamp": timestamp,
                "source_sha256": source_sha256,
                "error_code": error_code,
                "call_id": call_id,
                "uncertain": uncertain,
            }
        )

    def ingest(self, event: Mapping[str, Any]) -> dict[str, Any]:
        if not self.policy.enabled:
            return {
                "schema": HOOK_SCHEMA,
                "status": "disabled",
                "stored": False,
                "provider": self.provider,
                "adapter_id": self.adapter_id,
                "reason": "disabled-by-default",
            }
        if not self.policy.consent_granted or not self.policy.authorized:
            raise ProviderHookError(
                "provider hook requires explicit consent and authorization"
            )
        normalized = self._normalize(event)
        evidence_id = None
        if self.store is not None:
            evidence_id = self._store(normalized)
        result = {
            **normalized,
            "status": "accepted",
            "stored": evidence_id is not None,
        }
        if evidence_id is not None:
            result["evidence_id"] = evidence_id
        return result

    def _normalize(self, event: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(event, Mapping):
            raise ProviderHookError("provider hook event must be an object")
        if _contains_prohibited_key(event):
            raise ProviderHookError("provider hook event contains prohibited content")
        if set(event) - _ALLOWED_FIELDS:
            raise ProviderHookError("provider hook event has unsupported fields")
        for first, second in (
            ("event_kind", "kind"),
            ("timestamp", "occurred_at"),
            ("source_sha256", "source_hash"),
        ):
            if first in event and second in event and event[first] != event[second]:
                raise ProviderHookError("provider hook event contains conflicting aliases")

        kind_value = event.get("event_kind", event.get("kind"))
        kind = _adapter_token(kind_value, "event_kind")
        if kind not in EVENT_KINDS:
            raise ProviderHookError("provider hook event_kind is unsupported")
        occurred_value = event.get("timestamp", event.get("occurred_at"))
        occurred_at = _utc_timestamp(occurred_value, "timestamp")
        source_value = event.get("source_sha256", event.get("source_hash"))
        try:
            source_hash = sha256(source_value, "source_sha256")
        except ValueError as error:
            raise ProviderHookError("provider hook source_sha256 is invalid") from error

        call_id = event.get("call_id")
        if call_id is not None:
            call_id = _adapter_token(call_id, "call_id")
        uncertain = event.get(
            "uncertain",
            kind != "result"
            or event.get("readback_status", "unknown") in {"unknown", "partial"},
        )
        if not isinstance(uncertain, bool):
            raise ProviderHookError("provider hook uncertain must be boolean")

        if kind == "call":
            readback_status = "not-applicable"
            outcome = "pending"
            error_status = "not-applicable"
        elif kind == "result":
            readback_status = _readback_status(event.get("readback_status", "unknown"))
            outcome = (
                "success"
                if readback_status == "success"
                else "error"
                if readback_status == "failed"
                else "unknown"
            )
            error_status = "not-applicable"
        else:
            readback_status = _readback_status(event.get("readback_status", "not-applicable"))
            outcome = "error"
            error_status = _adapter_token(
                event.get("error_code", "provider-error"), "error_code"
            )

        event_id = stable_id(
            "provider-hook",
            self.provider,
            self.adapter_id,
            kind,
            call_id or "",
            occurred_at,
            source_hash,
        )
        normalized = {
            "schema": HOOK_SCHEMA,
            "event_id": event_id,
            "provider": self.provider,
            "adapter_id": self.adapter_id,
            "event_kind": kind,
            "occurred_at": occurred_at,
            "source_sha256": source_hash,
            "retention": self.policy.retention,
            "outcome": outcome,
            "readback_status": readback_status,
            "error_status": error_status,
            "uncertain": uncertain,
            "redacted": True,
        }
        if call_id is not None:
            normalized["call_id"] = call_id
        return normalized

    def _store(self, event: dict[str, Any]) -> str:
        assert self.store is not None
        owns_transaction = not self.store.in_transaction
        try:
            evidence_id = self.store.add_evidence(
                uri=(
                    f"provider-hook://{self.provider}/{self.adapter_id}/"
                    f"{event['event_id']}"
                ),
                source_kind=HOOK_SOURCE_KIND,
                sha256=event["source_sha256"],
                locator=event["event_id"],
                effective_at=event["occurred_at"],
                confidence=1.0 if not event["uncertain"] else 0.5,
                sensitivity="user-local",
                metadata=event,
            )
            if owns_transaction:
                self.store.commit()
            return evidence_id
        except BaseException:
            if owns_transaction and self.store.in_transaction:
                self.store.rollback()
            raise


def _adapter_token(value: Any, path: str) -> str:
    try:
        value = nonempty_string(value, path)
    except ValueError as error:
        raise ProviderHookError(f"{path} must be a bounded token") from error
    if not _TOKEN_RE.fullmatch(value):
        raise ProviderHookError(f"{path} must be a bounded token")
    return value


def _readback_status(value: Any) -> str:
    value = _adapter_token(value, "readback_status")
    if value not in READBACK_STATUSES:
        raise ProviderHookError("provider hook readback_status is unsupported")
    return value


def _utc_timestamp(value: Any, path: str) -> str:
    try:
        parsed = timestamp(value, path)
    except ValueError as error:
        raise ProviderHookError(f"provider hook {path} is invalid") from error
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _contains_prohibited_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if any(part == normalized or part in normalized for part in _PROHIBITED_KEY_PARTS):
                return True
            if _contains_prohibited_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_prohibited_key(child) for child in value)
    return False
