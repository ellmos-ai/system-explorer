from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-_](\d{2})[-_](\d{2})(?!\d)")
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\r\n\"'<>|?*]+")
POSIX_PATH_RE = re.compile(r"(?<![\w:])/(?:[^/\s\"']+/)+[^/\s\"']+")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def expand_path(value: str, base: Path | None = None) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(value))
    path = Path(expanded)
    if not path.is_absolute() and base is not None:
        path = base / path
    return path.resolve()


def file_effective_date(
    path: Path,
    text_hint: str | None = None,
    *,
    fallback_timestamp: float | None = None,
) -> str:
    candidates: list[tuple[int, int, int]] = []
    for value in (path.name, text_hint or ""):
        for match in DATE_RE.finditer(value):
            candidates.append(tuple(int(part) for part in match.groups()))
    if candidates:
        year, month, day = max(candidates)
        return datetime(year, month, day, tzinfo=timezone.utc).isoformat()
    timestamp = (
        fallback_timestamp
        if fallback_timestamp is not None
        else path.stat().st_mtime
    )
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def extract_paths(text: str) -> list[str]:
    values = WINDOWS_PATH_RE.findall(text) + POSIX_PATH_RE.findall(text)
    cleaned = {value.rstrip(".,;:)]}") for value in values if len(value) < 2048}
    return sorted(cleaned)


def walk_scalars(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                yield from walk_scalars(child)
            else:
                yield str(key), child
    elif isinstance(value, list):
        for child in value:
            yield from walk_scalars(child)


def safe_json_loads(value: str) -> Any | None:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
