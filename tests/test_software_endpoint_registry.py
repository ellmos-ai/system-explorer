from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import jsonschema

from system_explorer.cli import main
from system_explorer.contracts import canonical_content_hash
from system_explorer.resources import (
    register_software_resources,
    software_endpoint_registry,
)
from system_explorer.store import Store


ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path):
    executable = tmp_path / "bridge-tool.py"
    executable.write_text("print('bridge')\n", encoding="utf-8")
    return {
        "schema": "system-explorer.config.v1",
        "_base": str(tmp_path),
        "database": str(tmp_path / "state" / "evidence.db"),
        "roots": [],
        "system": {"id": "OCEAN-DEV", "name": "OCEAN Dev"},
        "software_resources": [
            {
                "id": "bridge-tool",
                "name": "Bridge tool",
                "kind": "script",
                "path": str(executable),
                "interfaces": [
                    {
                        "method": "cli",
                        "entrypoint": "python bridge-tool.py",
                        "actors": [
                            {"id": "codex", "name": "Codex", "provider": "openai"}
                        ],
                    },
                    {"method": "mcp", "entrypoint": "bridge_tool.run"},
                ],
                "functions": [
                    {"id": "bridge.run", "name": "Run the bridge"},
                ],
            },
            {
                "id": "missing-tool",
                "name": "Missing tool",
                "command": "system-explorer-definitely-missing",
                "interfaces": [{"method": "cli", "entrypoint": "missing-tool"}],
                "functions": ["missing.run"],
            },
        ],
    }


def test_registry_is_deterministic_typed_and_truthful(tmp_path):
    config = _config(tmp_path)
    with Store(Path(config["database"])) as store:
        register_software_resources(config, store)
        first = software_endpoint_registry(store)
        second = software_endpoint_registry(store)

    assert first == second
    assert first["schema"] == "system-explorer.software-endpoint-registry.v1"
    assert first["authority"] == {
        "kind": "evidence-store-projection",
        "runtime_authority": False,
    }
    assert first["privacy"] == {
        "raw_content_included": False,
        "credential_values_included": False,
    }
    assert first["content_hash"] == canonical_content_hash(first)
    schema = json.loads(
        (ROOT / "schemas" / "software-endpoint-registry.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(first, schema)
    assert first["summary"] == {
        "resources": 2,
        "installed_resources": 1,
        "endpoints": 3,
        "methods": {"cli": 2, "mcp": 1},
    }
    assert [row["id"] for row in first["endpoints"]] == sorted(
        row["id"] for row in first["endpoints"]
    )

    cli = next(row for row in first["endpoints"] if row["method"] == "cli" and row["installed"])
    assert cli["resource_id"] == "software:bridge-tool"
    assert cli["entrypoint"] == "python bridge-tool.py"
    assert cli["readiness"] == "native"
    assert cli["actors"] == [
        {"id": "actor:codex", "name": "Codex", "provider": "openai"}
    ]
    assert cli["functions"] == [
        {"id": "function:bridge.run", "name": "Run the bridge", "status": "observed"}
    ]
    assert "resolved_path" not in cli

    missing = next(row for row in first["endpoints"] if not row["installed"])
    assert missing["status"] == "declared"
    assert missing["functions"][0]["status"] == "unproven"


def test_cli_can_refresh_and_emit_registry_without_a_prior_full_scan(tmp_path):
    config = _config(tmp_path)
    config_path = tmp_path / "explorer.json"
    config_for_disk = {key: value for key, value in config.items() if key != "_base"}
    config_path.write_text(json.dumps(config_for_disk), encoding="utf-8")

    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = main(
            ["software-endpoints", "--config", str(config_path), "--refresh"]
        )

    assert exit_code == 0
    report = json.loads(output.getvalue())
    assert report["schema"] == "system-explorer.software-endpoint-registry.v1"
    assert report["summary"]["endpoints"] == 3
    assert report["refresh"]["software_resources"] == 2
