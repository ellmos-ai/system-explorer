"""Optional read-only bridge for an existing ``ellmos-unified-gui`` host.

The core Explorer server deliberately keeps its proposal and registration
endpoints.  A host mount must not inherit those write surfaces: this module
creates a separate GET-only sub-application and mounts it only after the
versioned Unified GUI mount contract has been probed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.resources import files
from types import ModuleType
from typing import Any

from .assessment import assess
from .config import database_path
from .coverage import coverage_report
from .deployment import deployment_report, purpose_report
from .maps import graph_view
from .registry import find_documents
from .resources import resource_report
from .store import Store


BRIDGE_SCHEMA = "system-explorer.unified-gui-panel.v1"
HOST_CONTRACT = "ellmos-unified-gui.mount.v1"
HOST_MODULE = "ellmos-unified-gui"
MIN_HOST_VERSION = (0, 4, 0)
PANEL_ID = "system-explorer"
PANEL_CAPABILITIES = (
    "system.discovery.readonly",
    "system.mapping.readonly",
    "system.evidence.readonly",
)
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")


@dataclass(frozen=True)
class HostProbe:
    """Machine-readable compatibility result for the optional host seam."""

    compatible: bool
    status: str
    host_version: str | None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": BRIDGE_SCHEMA,
            "host": HOST_MODULE,
            "host_contract": HOST_CONTRACT,
            "host_version": self.host_version,
            "required_host_version": ".".join(map(str, MIN_HOST_VERSION)),
            "compatible": self.compatible,
            "status": self.status,
            "reason": self.reason,
            "panel": {
                "id": PANEL_ID,
                "read_only": True,
                "capabilities": list(PANEL_CAPABILITIES),
            },
        }


def panel_contract() -> dict[str, Any]:
    """Return the host-neutral panel contract without importing FastAPI."""

    return {
        "schema": BRIDGE_SCHEMA,
        "panel_id": PANEL_ID,
        "host_contract": HOST_CONTRACT,
        "host_module": HOST_MODULE,
        "minimum_host_version": ".".join(map(str, MIN_HOST_VERSION)),
        "read_only": True,
        "routes": {
            "GET": [
                "/",
                "/api/status",
                "/api/map",
                "/api/coverage",
                "/api/assessment",
                "/api/deployment",
                "/api/purposes",
                "/api/resources",
                "/api/evidence",
                "/api/documents",
            ],
            "POST": [],
            "PUT": [],
            "PATCH": [],
            "DELETE": [],
        },
        "capabilities": list(PANEL_CAPABILITIES),
    }


def probe_unified_gui_host(module: ModuleType | None = None) -> HostProbe:
    """Probe the optional host import and its stable mount surface.

    A missing, malformed, or too-old host is a normal disabled result.  No
    application is created and no route is mounted in that case.
    """

    if module is None:
        try:
            import unified_gui as module  # type: ignore[no-redef]
        except ImportError:
            return HostProbe(False, "disabled", None, "unified_gui_not_installed")

    version = getattr(module, "__version__", None)
    mount = getattr(module, "mount", None)
    if not isinstance(version, str) or not callable(mount):
        return HostProbe(False, "disabled", version if isinstance(version, str) else None,
                         "host_mount_contract_missing")
    match = _VERSION_RE.match(version)
    if match is None:
        return HostProbe(False, "disabled", version, "host_version_unparseable")
    parsed = tuple(int(part or 0) for part in match.groups())
    if parsed < MIN_HOST_VERSION:
        return HostProbe(False, "disabled", version, "host_version_too_old")
    return HostProbe(True, "compatible", version)


def create_readonly_panel(config: dict[str, Any]):
    """Create the GET-only Explorer panel for mounting into a FastAPI host."""

    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import HTMLResponse
    except ImportError as exc:  # pragma: no cover - exercised by optional install
        raise RuntimeError(
            "FastAPI is required for the optional Unified GUI panel"
        ) from exc

    db_path = database_path(config)
    app = FastAPI(
        title="system-explorer read-only panel",
        version="0.1",
        docs_url=None,
        redoc_url=None,
    )
    app.state.bridge_contract = panel_contract()
    app.state.config = config

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return files("system_explorer").joinpath("web/host-panel.html").read_text(
            encoding="utf-8"
        )

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return {
            **panel_contract(),
            "status": "ready",
            "database": str(db_path),
        }

    @app.get("/api/map")
    def map_view(
        view: str = Query("coverage"),
        system: str | None = Query(None),
    ) -> dict[str, Any]:
        system_id = None if system in {None, "", "all"} else system
        try:
            with Store(db_path) as store:
                return graph_view(store, view, system_id=system_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/coverage")
    def coverage() -> dict[str, Any]:
        with Store(db_path) as store:
            return coverage_report(store)

    @app.get("/api/assessment")
    def assessment() -> dict[str, Any]:
        with Store(db_path) as store:
            return assess(store)

    @app.get("/api/deployment")
    def deployment() -> dict[str, Any]:
        with Store(db_path) as store:
            return deployment_report(store)

    @app.get("/api/purposes")
    def purposes(target: str | None = Query(None)) -> dict[str, Any]:
        with Store(db_path) as store:
            return purpose_report(store, target)

    @app.get("/api/resources")
    def resources() -> dict[str, Any]:
        with Store(db_path) as store:
            return resource_report(store)

    @app.get("/api/evidence")
    def evidence() -> dict[str, Any]:
        with Store(db_path) as store:
            return {"evidence": store.evidence()}

    @app.get("/api/documents")
    def documents(
        role: str | None = Query(None),
        name: str | None = Query(None),
    ) -> dict[str, Any]:
        with Store(db_path) as store:
            return {"documents": find_documents(store, role=role, name=name)}

    return app


def mount_unified_gui_panel(
    host_app: Any,
    config: dict[str, Any],
    *,
    prefix: str = "/control/system-explorer",
    host_module: ModuleType | None = None,
) -> dict[str, Any]:
    """Conditionally mount the read-only panel into a verified GUI host.

    The function returns a status payload instead of raising for optional
    integration failures.  Incompatible hosts are left untouched.
    """

    if not isinstance(prefix, str) or not prefix.startswith("/") or ".." in prefix:
        return {
            **panel_contract(),
            "status": "disabled",
            "reason": "invalid_mount_prefix",
        }
    mount = getattr(host_app, "mount", None)
    if not callable(mount):
        return {
            **panel_contract(),
            "status": "disabled",
            "reason": "host_app_mount_missing",
        }
    probe = probe_unified_gui_host(host_module)
    if not probe.compatible:
        return {**probe.as_dict(), "prefix": prefix}
    try:
        panel_app = create_readonly_panel(config)
        mount(prefix.rstrip("/") or "/", panel_app, name=PANEL_ID)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            **probe.as_dict(),
            "status": "disabled",
            "reason": f"panel_mount_failed:{type(exc).__name__}",
            "prefix": prefix,
        }
    return {
        **probe.as_dict(),
        "status": "mounted",
        "prefix": prefix.rstrip("/") or "/",
    }


__all__ = [
    "BRIDGE_SCHEMA",
    "HOST_CONTRACT",
    "HostProbe",
    "create_readonly_panel",
    "mount_unified_gui_panel",
    "panel_contract",
    "probe_unified_gui_host",
]
