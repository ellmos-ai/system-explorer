from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .store import Store
from .util import extract_paths, sha256_file, sha256_text, stable_id, walk_scalars


SUPPORTED_PROVIDERS = {"claude-code", "claude-desktop", "codex", "gemini", "kimi", "generic"}
TOOL_KEYS = {"tool_name", "name", "function", "command"}
TOOL_CALL_TYPES = {"tool_use", "function_call", "tool_call", "context.append_loop_event"}
TOOL_RESULT_TYPES = {"tool_result", "function_call_output", "tool_output", "result"}


def import_transcripts(
    provider: str,
    source: Path,
    store: Store,
    *,
    actor_id: str | None = None,
    sensitivity: str = "sensitive",
) -> dict[str, int]:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    stats = {"files": 0, "records": 0, "tool_calls": 0, "tool_results": 0, "paths": 0}
    files = _source_files(provider, source)
    actor_name = actor_id or provider
    actor_node = store.add_node(
        "actor",
        actor_name,
        node_id=f"actor:{actor_name}",
        metadata={"provider": provider, "carrier_kind": "actor"},
    )
    for path in files:
        digest = sha256_file(path)
        stats["files"] += 1
        call_tools: dict[str, str] = {}
        for sequence, record in enumerate(_records(provider, path), start=1):
            stats["records"] += 1
            event = _normalize_event(provider, record, sequence)
            if event["kind"] == "tool_call" and event.get("call_id") and event.get("tool_name"):
                call_tools[event["call_id"]] = event["tool_name"]
            if event["kind"] == "tool_result" and not event.get("tool_name"):
                event["tool_name"] = call_tools.get(event.get("call_id"))
            locator = event["locator"]
            evidence_id = store.add_evidence(
                uri=path.resolve().as_uri(),
                source_kind=f"transcript:{provider}",
                sha256=digest,
                locator=locator,
                effective_at=event.get("timestamp"),
                modified_at=str(path.stat().st_mtime),
                confidence=event["confidence"],
                sensitivity=sensitivity,
                metadata={
                    "provider": provider,
                    "event_kind": event["kind"],
                    "content_retained": False,
                    "prompt_sha256": event.get("prompt_sha256"),
                    "parser_version": "system-explorer/0.1",
                },
            )
            session_name = event.get("session_id") or f"{provider}:{path.stem}"
            session_node = store.add_node(
                "session",
                session_name,
                node_id=f"session:{stable_id('s', provider, session_name)}",
                metadata={"provider": provider},
            )
            store.add_edge(
                actor_node,
                "participates_in",
                session_node,
                status="observed",
                confidence=event["confidence"],
                evidence_id=evidence_id,
                effective_at=event.get("timestamp"),
            )
            if event.get("entrypoint"):
                entry_id = store.add_node(
                    "entrypoint",
                    event["entrypoint"],
                    metadata={"provider": provider, "observed": True},
                )
                store.add_edge(
                    actor_node,
                    "enters_at",
                    entry_id,
                    status="observed",
                    evidence_id=evidence_id,
                )
            tool_name = event.get("tool_name")
            if tool_name:
                tool_id = store.add_node(
                    "carrier",
                    tool_name,
                    node_id=f"carrier:tool:{tool_name}",
                    metadata={"carrier_kind": "command", "provider": provider},
                )
                relation = "invoked" if event["kind"] == "tool_call" else "returned_from"
                status = "error" if event.get("is_error") else "observed"
                store.add_edge(
                    session_node,
                    relation,
                    tool_id,
                    status=status,
                    confidence=event["confidence"],
                    evidence_id=evidence_id,
                    effective_at=event.get("timestamp"),
                    metadata={"call_id": event.get("call_id")},
                )
                if event["kind"] == "tool_call":
                    stats["tool_calls"] += 1
                else:
                    stats["tool_results"] += 1
            for path_ref in event.get("path_refs", []):
                path_node = store.add_node(
                    "artifact_reference",
                    Path(path_ref).name or path_ref,
                    node_id=stable_id("path", path_ref),
                    metadata={"path_ref": path_ref},
                )
                store.add_edge(
                    session_node,
                    "references",
                    path_node,
                    status="observed",
                    confidence=0.7,
                    evidence_id=evidence_id,
                )
                if event["kind"] in {"tool_call", "tool_result"}:
                    carrier = _carrier_for_path(path_ref, store)
                    if carrier:
                        store.add_edge(
                            session_node,
                            "used",
                            carrier["id"],
                            status="observed" if not event.get("is_error") else "error",
                            confidence=0.7,
                            evidence_id=evidence_id,
                            effective_at=event.get("timestamp"),
                            metadata={"inference": "tool-event-path-within-carrier-scope"},
                        )
                stats["paths"] += 1
    store.commit()
    return stats


def _source_files(provider: str, source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    patterns = ["*.db"] if provider == "gemini" else ["*.jsonl"]
    values: list[Path] = []
    for pattern in patterns:
        values.extend(source.rglob(pattern))
    return sorted(path for path in values if path.is_file())


def _records(provider: str, path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix.lower() == ".db":
        yield from _sqlite_records(path)
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                value["_locator"] = f"line:{line_no}"
                yield value


def _sqlite_records(path: Path) -> Iterable[dict[str, Any]]:
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            try:
                rows = db.execute(f"SELECT rowid, * FROM {quoted}")
            except sqlite3.DatabaseError:
                continue
            for row in rows:
                value: dict[str, Any] = {"_table": table, "_locator": f"{table}:rowid:{row[0]}"}
                for key in row.keys():
                    item = row[key]
                    if isinstance(item, bytes):
                        try:
                            item = item.decode("utf-8")
                        except UnicodeDecodeError:
                            item = {"blob_sha256": sha256_text(item.hex())}
                    value[key] = item
                yield value
    finally:
        db.close()


def _normalize_event(provider: str, record: dict[str, Any], sequence: int) -> dict[str, Any]:
    flattened = list(walk_scalars(record))
    type_values = [
        str(value)
        for key, value in flattened
        if key in {"type", "event_type", "kind", "step_type"}
    ]
    kind = "event"
    joined_types = " ".join(type_values).lower()
    if any(value in joined_types for value in TOOL_CALL_TYPES):
        kind = "tool_call"
    if any(value in joined_types for value in TOOL_RESULT_TYPES):
        kind = "tool_result"

    tool_name = None
    call_id = None
    timestamp = None
    session_id = None
    entrypoint = None
    is_error = False
    texts: list[str] = []
    for key, value in flattened:
        lower = key.lower()
        if isinstance(value, str):
            if lower in TOOL_KEYS and _looks_like_tool(value):
                tool_name = tool_name or value
            if lower in {"call_id", "tool_use_id", "toolcallid"}:
                call_id = value
            if lower in {"timestamp", "ts", "created_at", "time"}:
                timestamp = timestamp or value
            if lower in {"sessionid", "session_id", "conversation_id"}:
                session_id = session_id or value
            if lower == "entrypoint":
                entrypoint = value
            if lower in {"text", "content", "input", "prompt", "output", "arguments", "args"}:
                texts.append(value)
        if lower in {"is_error", "error"} and bool(value):
            is_error = True

    raw_text = "\n".join(texts)
    role = _role(record)
    if role == "user" and raw_text:
        kind = "prompt"
    if provider == "codex":
        payload = record.get("payload", {})
        if record.get("type") == "response_item" and isinstance(payload, dict):
            payload_type = payload.get("type")
            if payload_type == "function_call":
                kind = "tool_call"
                tool_name = payload.get("name") or tool_name
                call_id = payload.get("call_id") or call_id
            elif payload_type == "function_call_output":
                kind = "tool_result"
                call_id = payload.get("call_id") or call_id
    if provider in {"claude-code", "claude-desktop"}:
        tool_event = _find_event_dict(record, {"tool_use", "tool_result"})
        if tool_event:
            if tool_event.get("type") == "tool_use":
                kind = "tool_call"
                tool_name = tool_event.get("name") or tool_name
                call_id = tool_event.get("id") or call_id
            else:
                kind = "tool_result"
                call_id = tool_event.get("tool_use_id") or call_id
    if provider == "claude-desktop" and str(
        record.get("event_type", "")
    ).casefold() == "command_lifecycle":
        phase = " ".join(
            str(record.get(key, "")).casefold()
            for key in ("phase", "status", "kind", "state")
        )
        kind = (
            "tool_result"
            if any(
                word in phase
                for word in ("complete", "finish", "result", "error")
            )
            else "tool_call"
        )
    if provider == "gemini" and str(record.get("step_type")) == "14":
        kind = "prompt"
    if provider == "kimi":
        record_type = str(record.get("type", "")).casefold()
        if record_type in {"turn.prompt", "turn.steer"}:
            kind = "prompt"
            prompt = record.get("prompt") or record.get("text") or ""
            if isinstance(prompt, str):
                raw_text = prompt
    return {
        "kind": kind,
        "locator": str(record.get("_locator", f"record:{sequence}")),
        "timestamp": timestamp,
        "session_id": session_id,
        "entrypoint": entrypoint,
        "tool_name": tool_name,
        "call_id": call_id,
        "is_error": is_error,
        "path_refs": extract_paths(raw_text),
        "prompt_sha256": sha256_text(raw_text) if kind == "prompt" and raw_text else None,
        "confidence": 0.85 if kind in {"tool_call", "tool_result", "prompt"} else 0.55,
    }


def _role(value: Any) -> str | None:
    if isinstance(value, dict):
        role = value.get("role")
        if isinstance(role, str):
            return role
        for child in value.values():
            found = _role(child)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = _role(child)
            if found:
                return found
    return None


def _looks_like_tool(value: str) -> bool:
    return bool(value and len(value) < 256 and ("_" in value or "." in value or value.isidentifier()))


def _find_event_dict(value: Any, event_types: set[str]) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("type") in event_types:
            return value
        for child in value.values():
            found = _find_event_dict(child, event_types)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_event_dict(child, event_types)
            if found:
                return found
    return None


def _carrier_for_path(path_ref: str, store: Store) -> dict[str, Any] | None:
    candidate = str(Path(path_ref)).casefold().replace("/", "\\")
    matches = []
    for node in store.nodes("carrier"):
        scope = node.get("scope") or node.get("metadata", {}).get("path")
        if not scope:
            continue
        normalized = str(Path(scope)).casefold().replace("/", "\\").rstrip("\\")
        if candidate == normalized or candidate.startswith(normalized + "\\"):
            matches.append((len(normalized), node))
    return max(matches, default=(0, None), key=lambda item: item[0])[1]
