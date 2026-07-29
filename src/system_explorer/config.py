from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .util import expand_path


DEFAULT_CONFIG: dict[str, Any] = {
    "schema": "system-explorer.config.v1",
    "database": "~/.system-explorer/evidence.db",
    "roots": [
        {
            "id": "current-project",
            "path": ".",
            "max_depth": 5,
            "include": [
                "*.md",
                "*.txt",
                "*.json",
                "*.toml",
                "*.yaml",
                "*.yml",
                "pyproject.toml",
            ],
            "exclude_dirs": [
                ".git",
                ".venv",
                "node_modules",
                "__pycache__",
                ".pytest_cache",
                "dist",
                "build",
            ],
        }
    ],
    "transcripts": [],
    "desired_sources": [],
    "function_rules": [],
    "control_documents": [
        {"pattern": "AGENTS.md", "role": "control", "entry": True},
        {"pattern": "CLAUDE.md", "role": "control", "entry": True},
        {"pattern": "GPT.md", "role": "control", "entry": True},
        {"pattern": "GEMINI.md", "role": "control", "entry": True},
        {"pattern": "KIMI.md", "role": "control", "entry": True},
        {"pattern": "README.md", "role": "documentation", "entry": False},
        {"pattern": "DECISIONS.md", "role": "decision", "entry": False},
        {"pattern": "*POLICY*.md", "role": "policy", "entry": False},
    ],
    "entry_directories": [],
    "privacy": {
        "store_raw_text": False,
        "store_prompt_text": False,
        "sensitivity": "user-local",
    },
}


def write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema") != "system-explorer.config.v1":
        raise ValueError("Unsupported config schema")
    config["_config_path"] = str(path.resolve())
    config["_base"] = str(path.resolve().parent)
    return config


def database_path(config: dict[str, Any]) -> Path:
    return expand_path(config["database"], Path(config["_base"]))
