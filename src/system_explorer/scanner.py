from __future__ import annotations

import fnmatch
import json
import math
import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .deployment import register_deployment
from .federation import register_federation
from .infrastructure import (
    DATABASE_SUFFIXES,
    register_database_file,
    register_declared_infrastructure,
    register_registry_file,
)
from .manifests import load_manifest, validate_manifest
from .resources import register_software_resources
from .store import Store
from .util import (
    expand_path,
    file_effective_date,
    sha256_file,
    stable_id,
)

ENTRY_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GPT.md",
    "GEMINI.md",
    "KIMI.md",
    "START.md",
    "SKILL.md",
    "llms.txt",
}
MANIFEST_NAMES = {
    "ellmos-module.v2.json",
    "ellmos.module.v2.json",
    "stack.v2.json",
    "server.json",
}
MANIFEST_SCHEMAS = {
    "ellmos.bundle.v1",
    "ellmos.bundles.catalog.v1",
    "ellmos.fleet.v1",
    "ellmos.module.v2",
    "ellmos.stack.v2",
    "ellmos.system-instance.v1",
    "ellmos.system-test.v1",
    "ellmos.system.v1",
}
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
MODULE_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
QUOTED_REF_RE = re.compile(
    r"""["'`]((?:[A-Za-z]:[\\/]|\.{1,2}[\\/])?[\w.-]+(?:[\\/][\w .-]+)*\.(?:md|txt|json|toml|ya?ml))(?:#[^"'`]*)?["'`]""",
    re.IGNORECASE,
)
BARE_REF_RE = re.compile(
    r"""(?<![\w])(?:\.\.?[\\/])?[\w.-]+(?:[\\/][\w.-]+)*\.(?:md|txt|json|toml|ya?ml)(?:#[\w.-]+)?""",
    re.IGNORECASE,
)
WINDOWS_DOC_RE = re.compile(
    r"""[A-Za-z]:\\[^\r\n"'`<>|?*]+?\.(?:md|txt|json|toml|ya?ml)(?:#[\w.-]+)?""",
    re.IGNORECASE,
)
QUOTED_DIRECTORY_RE = re.compile(
    r"""["'`]([A-Za-z]:\\[^"'`<>|?*]+|\.{1,2}[\\/][^"'`]+)["'`]"""
)


ProgressCallback = Callable[[dict[str, Any]], None]


class ScanTimeBudgetExceeded(ValueError):
    def __init__(
        self,
        *,
        elapsed_seconds: float,
        budget_seconds: float,
        phase: str,
        root_id: str | None,
        completed_roots: int,
        total_roots: int,
    ):
        self.elapsed_seconds = elapsed_seconds
        self.budget_seconds = budget_seconds
        self.phase = phase
        self.root_id = root_id
        self.completed_roots = completed_roots
        self.total_roots = total_roots
        root_text = f" for root {root_id!r}" if root_id else ""
        super().__init__(
            "scan time budget exceeded "
            f"after {elapsed_seconds:.3f}s (budget {budget_seconds:.3f}s) "
            f"during {phase}{root_text}; "
            f"{completed_roots}/{total_roots} roots checkpointed"
        )


@dataclass
class _ScanRuntime:
    budget_seconds: float | None
    progress: ProgressCallback | None
    progress_interval_seconds: float
    total_roots: int
    clock: Callable[[], float]
    started_at: float = field(init=False)
    last_progress_at: float = field(init=False)
    completed_roots: int = 0

    def __post_init__(self) -> None:
        if self.budget_seconds is not None and (
            not math.isfinite(self.budget_seconds) or self.budget_seconds <= 0
        ):
            raise ValueError("time_budget_seconds must be finite and greater than zero")
        if (
            not math.isfinite(self.progress_interval_seconds)
            or self.progress_interval_seconds < 0
        ):
            raise ValueError(
                "progress_interval_seconds must be finite and not negative"
            )
        self.started_at = self.clock()
        self.last_progress_at = self.started_at

    def _payload(
        self,
        event: str,
        *,
        phase: str,
        elapsed: float,
        stats: dict[str, int],
        root: Path | None,
        root_id: str | None,
        root_index: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": "system-explorer.scan-progress.v1",
            "event": event,
            "phase": phase,
            "elapsed_seconds": round(elapsed, 3),
            "completed_roots": self.completed_roots,
            "total_roots": self.total_roots,
            "stats": dict(stats),
        }
        if root is not None:
            payload["root"] = {
                "id": root_id,
                "path": str(root),
                "index": root_index,
                "total": self.total_roots,
            }
        return payload

    def checkpoint(
        self,
        event: str,
        *,
        phase: str,
        stats: dict[str, int],
        root: Path | None = None,
        root_id: str | None = None,
        root_index: int | None = None,
        force: bool = False,
        check_budget: bool = True,
    ) -> None:
        now = self.clock()
        elapsed = max(0.0, now - self.started_at)
        if (
            check_budget
            and self.budget_seconds is not None
            and elapsed >= self.budget_seconds
        ):
            error = ScanTimeBudgetExceeded(
                elapsed_seconds=elapsed,
                budget_seconds=self.budget_seconds,
                phase=phase,
                root_id=root_id,
                completed_roots=self.completed_roots,
                total_roots=self.total_roots,
            )
            if self.progress is not None:
                self.progress(
                    self._payload(
                        "scan_timed_out",
                        phase=phase,
                        elapsed=elapsed,
                        stats=stats,
                        root=root,
                        root_id=root_id,
                        root_index=root_index,
                    )
                )
                self.last_progress_at = now
            raise error
        if self.progress is None:
            return
        if not force and now - self.last_progress_at < self.progress_interval_seconds:
            return
        self.progress(
            self._payload(
                event,
                phase=phase,
                elapsed=elapsed,
                stats=stats,
                root=root,
                root_id=root_id,
                root_index=root_index,
            )
        )
        self.last_progress_at = now


def scan(
    config: dict[str, Any],
    store: Store,
    *,
    time_budget_seconds: float | None = None,
    progress: ProgressCallback | None = None,
    progress_interval_seconds: float = 5.0,
    _clock: Callable[[], float] = time.monotonic,
) -> dict[str, int]:
    stats = {
        "files": 0,
        "directories": 0,
        "evidence": 0,
        "nodes": 0,
        "edges": 0,
        "errors": 0,
        "registries": 0,
        "registry_collections": 0,
        "databases": 0,
        "database_tables": 0,
        "servers": 0,
        "server_surfaces": 0,
        "purposes": 0,
        "provider_documents": 0,
        "cost_offers": 0,
        "federated_systems": 0,
        "map_imports": 0,
        "map_import_errors": 0,
        "software_resources": 0,
        "software_interfaces": 0,
        "software_functions": 0,
    }
    base = Path(config["_base"])
    roots = list(config.get("roots", []))
    runtime = _ScanRuntime(
        budget_seconds=None if time_budget_seconds == 0 else time_budget_seconds,
        progress=progress,
        progress_interval_seconds=progress_interval_seconds,
        total_roots=len(roots),
        clock=_clock,
    )
    runtime.checkpoint(
        "scan_started",
        phase="initialization",
        stats=stats,
        force=True,
    )
    for root_index, root_config in enumerate(roots, start=1):
        root = expand_path(root_config["path"], base)
        root_id_value = str(root_config.get("id", root.name))
        before_root = dict(stats)
        commit_attempts_before_root = store.commit_attempt_count
        runtime.checkpoint(
            "root_started",
            phase="root",
            stats=stats,
            root=root,
            root_id=root_id_value,
            root_index=root_index,
            force=True,
        )
        if not root.exists():
            try:
                removed_claims = store.clear_component_identity_claims(
                    root.resolve().as_uri().rstrip("/") + "/"
                )
                if removed_claims:
                    store.commit()
            except BaseException:
                if store.in_transaction:
                    store.rollback()
                raise
            stats["errors"] += 1
            runtime.completed_roots += 1
            runtime.checkpoint(
                "root_missing",
                phase="root",
                stats=stats,
                root=root,
                root_id=root_id_value,
                root_index=root_index,
                force=True,
                check_budget=False,
            )
            continue
        try:
            store.clear_component_identity_claims(
                root.resolve().as_uri().rstrip("/") + "/"
            )
            root_id = store.add_node(
                "system",
                root_id_value,
                scope=str(root),
                metadata={"path": str(root), "carrier_kind": "system"},
            )
            directory_ids = _scan_directories(
                root,
                root_id,
                root_config,
                config,
                store,
                stats,
                runtime=lambda phase, root=root, root_id=root_id_value, index=root_index: runtime.checkpoint(
                    "root_progress",
                    phase=phase,
                    stats=stats,
                    root=root,
                    root_id=root_id,
                    root_index=index,
                ),
            )
            if (root / ".git").exists():
                repository_id = store.add_node(
                    "carrier",
                    root.name,
                    node_id=f"carrier:repository:{stable_id(str(root.resolve()))}",
                    scope=str(root),
                    metadata={"path": str(root), "carrier_kind": "repository"},
                )
                store.add_edge(root_id, "contains", repository_id, status="observed")
                stats["nodes"] += 1
                stats["edges"] += 1
            for path in _walk(root, root_config):
                runtime.checkpoint(
                    "root_progress",
                    phase="files",
                    stats=stats,
                    root=root,
                    root_id=root_id_value,
                    root_index=root_index,
                )
                try:
                    _scan_file(
                        path,
                        root,
                        root_id,
                        directory_ids,
                        config,
                        store,
                        stats,
                    )
                except (OSError, UnicodeError, json.JSONDecodeError):
                    stats["errors"] += 1
            runtime.checkpoint(
                "root_progress",
                phase="root-finalize",
                stats=stats,
                root=root,
                root_id=root_id_value,
                root_index=root_index,
            )
        except BaseException:
            commit_attempted_during_root = (
                store.commit_attempt_count > commit_attempts_before_root
            )
            if store.in_transaction:
                store.rollback()
            if commit_attempted_during_root:
                event = "root_commit_state_uncertain"
            else:
                stats.clear()
                stats.update(before_root)
                event = "root_rolled_back"
            runtime.checkpoint(
                event,
                phase="root-rollback",
                stats=stats,
                root=root,
                root_id=root_id_value,
                root_index=root_index,
                force=True,
                check_budget=False,
            )
            raise
        root_commit_started = False
        try:
            root_commit_started = True
            store.commit()
        except BaseException:
            if store.in_transaction:
                store.rollback()
            if root_commit_started:
                runtime.checkpoint(
                    "root_commit_state_uncertain",
                    phase="root-commit",
                    stats=stats,
                    root=root,
                    root_id=root_id_value,
                    root_index=root_index,
                    force=True,
                    check_budget=False,
                )
            else:
                stats.clear()
                stats.update(before_root)
                runtime.checkpoint(
                    "root_rolled_back",
                    phase="root-commit",
                    stats=stats,
                    root=root,
                    root_id=root_id_value,
                    root_index=root_index,
                    force=True,
                    check_budget=False,
                )
            raise
        runtime.completed_roots += 1
        runtime.checkpoint(
            "root_completed",
            phase="root",
            stats=stats,
            root=root,
            root_id=root_id_value,
            root_index=root_index,
            force=True,
            check_budget=False,
        )
    if config.get("_config_path"):
        _run_post_scan_phase(
            "declared-infrastructure",
            lambda: register_declared_infrastructure(config, store),
            (
                ("registries", "registries"),
                ("databases", "databases"),
                ("database_tables", "tables"),
            ),
            runtime,
            store,
            stats,
        )
        _run_post_scan_phase(
            "deployment",
            lambda: register_deployment(config, store),
            (
                ("servers", "servers"),
                ("server_surfaces", "surfaces"),
                ("purposes", "purposes"),
                ("provider_documents", "provider_documents"),
                ("cost_offers", "cost_offers"),
            ),
            runtime,
            store,
            stats,
        )
        _run_post_scan_phase(
            "software-resources",
            lambda: register_software_resources(config, store),
            (
                ("software_resources", "software_resources"),
                ("software_interfaces", "software_interfaces"),
                ("software_functions", "software_functions"),
            ),
            runtime,
            store,
            stats,
        )
        _run_post_scan_phase(
            "federation",
            lambda: register_federation(config, store),
            (
                ("federated_systems", "systems"),
                ("map_imports", "map_imports"),
                ("map_import_errors", "map_import_errors"),
                ("errors", "map_import_errors"),
            ),
            runtime,
            store,
            stats,
        )
    runtime.checkpoint(
        "scan_finalizing",
        phase="complete",
        stats=stats,
    )
    runtime.checkpoint(
        "scan_completed",
        phase="complete",
        stats=stats,
        force=True,
        check_budget=False,
    )
    return stats


def _run_post_scan_phase(
    phase: str,
    operation: Callable[[], dict[str, int]],
    stat_fields: tuple[tuple[str, str], ...],
    runtime: _ScanRuntime,
    store: Store,
    stats: dict[str, int],
) -> None:
    runtime.checkpoint(
        "phase_started",
        phase=phase,
        stats=stats,
        force=True,
    )
    before_phase = dict(stats)
    commit_attempts_before_phase = store.commit_attempt_count
    phase_commit_started = False
    try:
        result = operation()
        for target, source in stat_fields:
            stats[target] += result[source]
        phase_commit_started = True
        store.commit()
    except BaseException:
        commit_attempted_during_phase = (
            phase_commit_started
            or store.commit_attempt_count > commit_attempts_before_phase
        )
        if store.in_transaction:
            store.rollback()
        if commit_attempted_during_phase:
            event = "phase_commit_state_uncertain"
        else:
            stats.clear()
            stats.update(before_phase)
            event = "phase_rolled_back"
        runtime.checkpoint(
            event,
            phase=phase,
            stats=stats,
            force=True,
            check_budget=False,
        )
        raise
    runtime.checkpoint(
        "phase_completed",
        phase=phase,
        stats=stats,
        force=True,
        check_budget=False,
    )
    runtime.checkpoint(
        "phase_checkpoint",
        phase=phase,
        stats=stats,
    )


def _walk(root: Path, root_config: dict[str, Any]) -> Iterable[Path]:
    max_depth = int(root_config.get("max_depth", 5))
    includes = root_config.get("include", ["*"])
    excludes = set(root_config.get("exclude_dirs", []))
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        dirs[:] = [
            name for name in dirs if name not in excludes and depth < max_depth
        ]
        for name in files:
            if any(fnmatch.fnmatch(name, pattern) for pattern in includes):
                yield current_path / name


def _scan_directories(
    root: Path,
    root_id: str,
    root_config: dict[str, Any],
    config: dict[str, Any],
    store: Store,
    stats: dict[str, int],
    runtime: Callable[[str], None] | None = None,
) -> dict[Path, str]:
    max_depth = int(root_config.get("max_depth", 5))
    excludes = set(root_config.get("exclude_dirs", []))
    entry_specs = config.get("entry_directories", []) + root_config.get(
        "entry_directories", []
    )
    ids: dict[Path, str] = {}
    resolved_root = root.resolve()
    for current, dirs, _ in os.walk(root):
        if runtime:
            runtime("directories")
        path = Path(current).resolve()
        depth = len(path.relative_to(resolved_root).parts)
        dirs[:] = [
            name for name in dirs if name not in excludes and depth < max_depth
        ]
        entry = _matches_directory_spec(path, resolved_root, entry_specs)
        node_id = stable_id("directory", str(path))
        ids[path] = store.add_node(
            "directory",
            path.name or str(path),
            node_id=node_id,
            scope=str(path.parent),
            metadata={
                "path": str(path),
                "relative_path": str(path.relative_to(resolved_root)),
                "entry_directory": entry,
            },
        )
        parent_id = ids.get(path.parent, root_id)
        store.add_edge(parent_id, "contains", node_id, status="observed")
        if entry:
            store.add_edge(root_id, "enters_at", node_id, status="configured")
            stats["edges"] += 1
        stats["directories"] += 1
        stats["nodes"] += 1
        stats["edges"] += 1
    return ids


def _scan_file(
    path: Path,
    root: Path,
    root_id: str,
    directory_ids: dict[Path, str],
    config: dict[str, Any],
    store: Store,
    stats: dict[str, int],
) -> None:
    role, configured_entry = document_role(path, config)
    digest = sha256_file(path)
    modified = path.stat().st_mtime
    effective = file_effective_date(path)
    uri = path.resolve().as_uri()
    evidence_id = store.add_evidence(
        uri=uri,
        source_kind=_source_kind(path, role),
        sha256=digest,
        effective_at=effective,
        modified_at=str(modified),
        sensitivity=config.get("privacy", {}).get("sensitivity", "user-local"),
        metadata={
            "relative_path": str(path.relative_to(root)),
            "document_role": role,
        },
    )
    stats["files"] += 1
    stats["evidence"] += 1

    artifact_id = store.add_node(
        document_node_type(role),
        path.name,
        node_id=stable_id("path", str(path.resolve())),
        scope=str(path.parent),
        metadata={
            "uri": uri,
            "path": str(path),
            "extension": path.suffix.lower(),
            "document_role": role,
            "important_system_document": role is not None,
        },
    )
    parent_id = directory_ids.get(path.parent.resolve(), root_id)
    store.add_edge(parent_id, "contains", artifact_id, evidence_id=evidence_id)
    stats["nodes"] += 1
    stats["edges"] += 1

    if path.name in MANIFEST_NAMES or _is_schema_manifest(path):
        _scan_manifest(path, root_id, evidence_id, store, stats)
    registry_stats = register_registry_file(
        path, artifact_id, evidence_id, config, store
    )
    stats["registries"] += registry_stats["registries"]
    stats["registry_collections"] += registry_stats["collections"]
    stats["nodes"] += registry_stats["collections"]
    stats["edges"] += registry_stats["edges"]
    if path.suffix.casefold() in DATABASE_SUFFIXES:
        database_stats = register_database_file(
            path, artifact_id, evidence_id, store
        )
        stats["databases"] += database_stats["databases"]
        stats["database_tables"] += database_stats["tables"]
        stats["nodes"] += database_stats["tables"]
        stats["edges"] += database_stats["edges"]
    if path.name == "SKILL.md":
        _scan_skill(path, root_id, evidence_id, store, stats)
    if path.name in ENTRY_NAMES or configured_entry:
        entry_id = store.add_node(
            "entrypoint",
            path.name,
            scope=str(path.parent),
            metadata={
                "path": str(path),
                "entry_kind": _entry_kind(path.name),
                "configured": configured_entry,
            },
        )
        store.add_edge(root_id, "enters_at", entry_id, evidence_id=evidence_id)
        store.add_edge(
            entry_id,
            "points_to",
            artifact_id,
            status="configured" if configured_entry else "conventional",
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 2
    if path.suffix.lower() in {".md", ".txt"} and path.stat().st_size <= 2_000_000:
        _scan_document_pointers(
            path, artifact_id, role, evidence_id, config, store, stats
        )


def _scan_manifest(
    path: Path, root_id: str, evidence_id: str, store: Store, stats: dict[str, int]
) -> None:
    value = load_manifest(path)
    schema = value.get("schema", "")
    carrier_kind = {
        "ellmos.bundle.v1": "bundle",
        "ellmos.bundles.catalog.v1": "bundle-catalog",
        "ellmos.fleet.v1": "fleet",
        "ellmos.module.v2": "module",
        "ellmos.stack.v2": "stack",
        "ellmos.system-instance.v1": "system-instance",
        "ellmos.system-test.v1": "system-test",
        "ellmos.system.v1": "system",
    }.get(schema, "manifest")
    carrier_id = store.add_node(
        "carrier",
        value.get("display_name")
        or value.get("name")
        or value.get("id")
        or path.parent.name,
        node_id=f"carrier:{value.get('id', stable_id('anon', path))}",
        scope=str(path.parent),
        metadata={
            "carrier_kind": carrier_kind,
            "manifest_schema": schema,
            "status": value.get("status"),
            "entrypoints": value.get("entrypoints", {}),
            "surfaces": value.get("surfaces", []),
            "encapsulation": value.get("encapsulation", "unproven"),
        },
    )
    store.add_edge(root_id, "contains", carrier_id, evidence_id=evidence_id)
    stats["nodes"] += 1
    stats["edges"] += 1
    manifest_id = value.get("id")
    if (
        schema == "ellmos.module.v2"
        and isinstance(manifest_id, str)
        and MODULE_ID_RE.fullmatch(manifest_id)
        and not validate_manifest(value)
    ):
        store.register_component_identity_claim(
            carrier_id=carrier_id,
            component_ref=f"module:{manifest_id}",
            evidence_id=evidence_id,
            source_kind="ellmos.module.v2",
            source_id=manifest_id,
        )
    for capability in value.get("provides", []):
        function_id = store.add_node(
            "function",
            capability,
            node_id=f"function:{capability}",
            metadata={"desired": False},
        )
        store.add_edge(
            carrier_id,
            "carries",
            function_id,
            mode="actual",
            status="declared",
            confidence=0.75,
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 1
    entrypoints = value.get("entrypoints", {})
    if not isinstance(entrypoints, dict):
        entrypoints = {}
    for name, target in entrypoints.items():
        entry_id = store.add_node(
            "entrypoint",
            name,
            scope=str(path.parent),
            metadata={"target": target, "carrier": carrier_id},
        )
        store.add_edge(carrier_id, "enters_at", entry_id, evidence_id=evidence_id)
        stats["nodes"] += 1
        stats["edges"] += 1
    for surface in value.get("surfaces", []):
        item = surface if isinstance(surface, dict) else {"name": str(surface)}
        name = str(item.get("name") or item.get("id") or "surface")
        interface_id = store.add_node(
            "interface",
            name,
            node_id=f"interface:{stable_id(carrier_id, name)}",
            scope=str(path.parent),
            metadata={**item, "interface_kind": "surface"},
        )
        store.add_edge(
            carrier_id,
            "exposes_interface",
            interface_id,
            status="declared",
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 1
    for index, output in enumerate(value.get("outputs", []), start=1):
        item = output if isinstance(output, dict) else {"name": str(output)}
        name = str(item.get("name") or item.get("id") or f"output-{index}")
        output_id = store.add_node(
            "output",
            name,
            node_id=f"output:{stable_id(carrier_id, name)}",
            scope=str(path.parent),
            metadata=dict(item),
        )
        store.add_edge(
            carrier_id,
            "produces",
            output_id,
            status="declared",
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 1
        for consumer in item.get("consumers", []):
            consumer_id = _declared_carrier(str(consumer), store)
            store.add_edge(
                output_id,
                "delivers_to",
                consumer_id,
                status="declared",
                evidence_id=evidence_id,
            )
            stats["nodes"] += 1
            stats["edges"] += 1
    for index, handoff in enumerate(value.get("handoffs", []), start=1):
        item = handoff if isinstance(handoff, dict) else {"target": str(handoff)}
        name = str(item.get("name") or item.get("purpose") or f"handoff-{index}")
        handoff_id = store.add_node(
            "handoff",
            name,
            node_id=f"module-handoff:{stable_id(carrier_id, name)}",
            scope=str(path.parent),
            metadata={**item, "handoff_kind": "module"},
        )
        store.add_edge(
            carrier_id,
            "hands_off",
            handoff_id,
            status="declared",
            evidence_id=evidence_id,
        )
        target = item.get("target")
        if target:
            target_id = _declared_carrier(str(target), store)
            store.add_edge(
                handoff_id,
                "assigned_to",
                target_id,
                status="declared",
                evidence_id=evidence_id,
            )
            stats["nodes"] += 1
            stats["edges"] += 1
        stats["nodes"] += 1
        stats["edges"] += 1
    for alternative in value.get("alternative_paths", []):
        item = (
            alternative
            if isinstance(alternative, dict)
            else {"target": str(alternative)}
        )
        target = item.get("target")
        if not target:
            continue
        target_id = _declared_carrier(str(target), store)
        store.add_edge(
            carrier_id,
            "alternative_to",
            target_id,
            status="declared",
            evidence_id=evidence_id,
            metadata=dict(item),
        )
        stats["nodes"] += 1
        stats["edges"] += 1


def _declared_carrier(name: str, store: Store) -> str:
    node_id = name if name.startswith("carrier:") else f"carrier:{name}"
    store.add_node(
        "carrier",
        name.removeprefix("carrier:"),
        node_id=node_id,
        metadata={"carrier_kind": "declared-reference"},
    )
    return node_id


def _scan_skill(
    path: Path, root_id: str, evidence_id: str, store: Store, stats: dict[str, int]
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = FRONTMATTER_RE.match(text)
    metadata = _simple_frontmatter(match.group(1) if match else "")
    name = metadata.get("name") or path.parent.name
    carrier_id = store.add_node(
        "carrier",
        name,
        node_id=f"carrier:skill:{name}",
        scope=str(path.parent),
        metadata={
            "carrier_kind": "skill",
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
        },
    )
    store.add_edge(root_id, "contains", carrier_id, evidence_id=evidence_id)
    stats["nodes"] += 1
    stats["edges"] += 1
    component_ref = metadata.get("component_ref")
    if _is_explicit_component_ref(component_ref, prefix="skill:"):
        store.register_component_identity_claim(
            carrier_id=carrier_id,
            component_ref=component_ref,
            evidence_id=evidence_id,
            source_kind="skill-frontmatter-component-ref",
            source_id=str(component_ref),
        )
    for tag in metadata.get("tags", []):
        function_name = f"skill.{str(tag).strip().lower().replace(' ', '-')}"
        function_id = store.add_node(
            "function", function_name, node_id=f"function:{function_name}"
        )
        store.add_edge(
            carrier_id,
            "carries",
            function_id,
            status="inferred",
            confidence=0.5,
            evidence_id=evidence_id,
        )
        stats["nodes"] += 1
        stats["edges"] += 1


def _is_explicit_component_ref(value: Any, *, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(prefix)
        and value == value.strip()
        and len(value) > len(prefix)
        and not any(character.isspace() for character in value)
    )


def _scan_document_pointers(
    path: Path,
    source_id: str,
    source_role: str | None,
    evidence_id: str,
    config: dict[str, Any],
    store: Store,
    stats: dict[str, int],
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    targets = _extract_document_refs(text)
    seen: set[tuple[str, int | None]] = set()
    for raw_target, line, syntax in targets:
        target = raw_target.strip().strip("<>").split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "#")):
            continue
        key = (target.casefold(), line)
        if key in seen:
            continue
        seen.add(key)
        resolved = _resolve_reference(path.parent, target)
        exists = resolved is not None and resolved.exists()
        if exists and resolved:
            target_role, _ = document_role(resolved, config)
            target_id = store.add_node(
                document_node_type(target_role),
                resolved.name,
                node_id=stable_id("path", str(resolved.resolve())),
                scope=str(resolved.parent),
                metadata={
                    "path": str(resolved),
                    "uri": resolved.as_uri(),
                    "document_role": target_role,
                    "pointer_target": True,
                },
            )
        else:
            target_id = store.add_node(
                "artifact_reference",
                Path(target).name or target,
                node_id=stable_id("reference", str(path.parent), target),
                scope=str(path.parent),
                metadata={"target": target, "resolved": False},
            )
        store.add_edge(
            source_id,
            "points_to"
            if source_role in {"control", "entrypoint"}
            else "references",
            target_id,
            status="declared",
            confidence=0.85 if exists else 0.55,
            evidence_id=evidence_id,
            metadata={
                "target": target,
                "resolved": exists,
                "line": line,
                "syntax": syntax,
            },
        )
        stats["nodes"] += 1
        stats["edges"] += 1


def _simple_frontmatter(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            result[key.strip()] = [
                item.strip() for item in value[1:-1].split(",") if item.strip()
            ]
        else:
            result[key.strip()] = value.strip("\"'")
    return result


def _source_kind(path: Path, role: str | None) -> str:
    if path.name in MANIFEST_NAMES or _is_schema_manifest(path):
        return "manifest"
    if role:
        return f"document:{role}"
    if path.name in ENTRY_NAMES:
        return "entrypoint"
    if path.suffix.lower() in {".md", ".txt"}:
        return "documentation"
    return "file"


def _is_schema_manifest(path: Path) -> bool:
    if path.suffix.lower() != ".json" or path.stat().st_size > 2_000_000:
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(value, dict) and (
        value.get("schema") in MANIFEST_SCHEMAS
        or (
            isinstance(value.get("schema"), str)
            and value["schema"].startswith(("ellmos.module.", "ellmos.stack."))
        )
    )


def document_role(
    path: Path, config: dict[str, Any]
) -> tuple[str | None, bool]:
    for item in config.get("control_documents", []):
        pattern = item if isinstance(item, str) else item.get("pattern", "")
        if pattern and (
            fnmatch.fnmatch(path.name.casefold(), pattern.casefold())
            or fnmatch.fnmatch(str(path).casefold(), pattern.casefold())
        ):
            role = (
                "control" if isinstance(item, str) else item.get("role", "control")
            )
            entry = (
                True if isinstance(item, str) else bool(item.get("entry", False))
            )
            return role, entry
    value = "/".join(part.casefold() for part in path.parts)
    name = path.name.casefold()
    rules = (
        ("policy", ("policy", "policies", "rules")),
        ("decision", ("decision", "decisions", "adr-", "adr_")),
        ("memory", ("memory", "preferences", "preference")),
        ("runtime-log", ("log", "receipt", "runbook")),
        (
            "architecture",
            ("architecture", "ontology", "system-manifest", "manifest"),
        ),
        ("cloud-readiness", ("cloud", "deployment", "hosting", "readiness")),
        (
            "control",
            ("agents.md", "claude.md", "gpt.md", "gemini.md", "kimi.md"),
        ),
        ("documentation", ("readme.md", "docs", "documentation")),
    )
    for role, needles in rules:
        if any(needle in name or f"/{needle}/" in value for needle in needles):
            return role, role == "control"
    return None, False


def document_node_type(role: str | None) -> str:
    return {
        "control": "control_document",
        "entrypoint": "control_document",
        "policy": "policy_document",
        "decision": "decision_document",
        "memory": "memory_document",
        "runtime-log": "runtime_document",
    }.get(role or "", "documentation" if role else "artifact")


def _extract_document_refs(text: str) -> list[tuple[str, int | None, str]]:
    result: list[tuple[str, int | None, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in LINK_RE.finditer(line):
            result.append((match.group(1), line_number, "markdown-link"))
        for match in QUOTED_REF_RE.finditer(line):
            result.append((match.group(1), line_number, "quoted-path"))
        for match in BARE_REF_RE.finditer(line):
            result.append((match.group(0), line_number, "bare-path"))
        for match in WINDOWS_DOC_RE.finditer(line):
            result.append((match.group(0), line_number, "windows-path"))
        for match in QUOTED_DIRECTORY_RE.finditer(line):
            result.append((match.group(1), line_number, "quoted-directory"))
    return result


def _resolve_reference(parent: Path, value: str) -> Path | None:
    cleaned = os.path.expandvars(os.path.expanduser(value.strip()))
    try:
        path = Path(cleaned)
        return path.resolve() if path.is_absolute() else (parent / path).resolve()
    except (OSError, ValueError):
        return None


def _matches_directory_spec(
    path: Path, root: Path, specs: list[Any]
) -> bool:
    relative = str(path.relative_to(root))
    for item in specs:
        pattern = (
            item
            if isinstance(item, str)
            else item.get("path") or item.get("pattern", "")
        )
        if not pattern:
            continue
        if fnmatch.fnmatch(relative.casefold(), pattern.casefold()):
            return True
        expanded = Path(os.path.expandvars(os.path.expanduser(pattern)))
        if expanded.is_absolute() and path == expanded.resolve():
            return True
    return False


def _entry_kind(name: str) -> str:
    if name == "SKILL.md":
        return "skill"
    if name == "START.md":
        return "workflow"
    if name == "llms.txt":
        return "llm-index"
    return "provider-boot"
