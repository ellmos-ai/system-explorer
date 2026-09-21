"""Optional Unified-GUI mount: compatibility handshake and GET-only surface."""
from __future__ import annotations

import types
from pathlib import Path

import pytest

from system_explorer.host_bridge import (
    BRIDGE_SCHEMA,
    create_readonly_panel,
    mount_unified_gui_panel,
    panel_contract,
    probe_unified_gui_host,
)
from system_explorer.store import Store


def _config(tmp_path: Path) -> dict:
    return {
        "database": "evidence.db",
        "_base": str(tmp_path),
    }


def _host_module(version: str = "0.4.0") -> types.SimpleNamespace:
    return types.SimpleNamespace(__version__=version, mount=lambda *_args, **_kwargs: None)


def test_missing_or_old_host_disables_without_mounting() -> None:
    missing = probe_unified_gui_host(types.SimpleNamespace())
    assert missing.status == "disabled"
    assert missing.reason == "host_mount_contract_missing"

    old = probe_unified_gui_host(_host_module("0.3.9"))
    assert old.status == "disabled"
    assert old.reason == "host_version_too_old"


def test_panel_contract_is_explicitly_get_only() -> None:
    contract = panel_contract()
    assert contract["schema"] == BRIDGE_SCHEMA
    assert contract["read_only"] is True
    assert contract["routes"]["POST"] == []
    assert all(path.startswith("/") for path in contract["routes"]["GET"])


def test_panel_exposes_read_only_status_and_rejects_writes(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    with Store(tmp_path / "evidence.db"):
        pass
    app = create_readonly_panel(_config(tmp_path))
    from fastapi.testclient import TestClient

    client = TestClient(app)
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["schema"] == BRIDGE_SCHEMA
    assert status.json()["read_only"] is True
    assert client.post("/api/proposals", json={"prompt": "must not write"}).status_code == 404


def test_compatible_host_gets_mounted_panel(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    with Store(tmp_path / "evidence.db"):
        pass
    host = FastAPI()
    result = mount_unified_gui_panel(
        host,
        _config(tmp_path),
        prefix="/control/system-explorer",
        host_module=_host_module(),
    )
    assert result["status"] == "mounted"
    assert result["prefix"] == "/control/system-explorer"
    client = TestClient(host)
    assert client.get("/control/system-explorer/").status_code == 200
    assert client.post("/control/system-explorer/api/register", json={}).status_code == 404
