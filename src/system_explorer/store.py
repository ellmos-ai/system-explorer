from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .util import json_dumps, stable_id, utc_now


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    uri TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    sha256 TEXT,
    locator TEXT,
    observed_at TEXT NOT NULL,
    effective_at TEXT,
    modified_at TEXT,
    confidence REAL NOT NULL,
    sensitivity TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_uri ON evidence(uri);
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    scope TEXT,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    target_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_id TEXT,
    effective_at TEXT,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_id) REFERENCES nodes(id),
    FOREIGN KEY(target_id) REFERENCES nodes(id),
    FOREIGN KEY(evidence_id) REFERENCES evidence(id)
);
CREATE INDEX IF NOT EXISTS idx_edges_key ON edges(source_id, relation, target_id, mode);
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    config_hash TEXT,
    stats_json TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def add_evidence(
        self,
        *,
        uri: str,
        source_kind: str,
        sha256: str | None = None,
        locator: str | None = None,
        effective_at: str | None = None,
        modified_at: str | None = None,
        confidence: float = 1.0,
        sensitivity: str = "user-local",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        evidence_id = stable_id(
            "evidence", uri, source_kind, sha256 or "", locator or "", effective_at or ""
        )
        self.db.execute(
            """
            INSERT OR REPLACE INTO evidence
            (id, uri, source_kind, sha256, locator, observed_at, effective_at,
             modified_at, confidence, sensitivity, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                uri,
                source_kind,
                sha256,
                locator,
                utc_now(),
                effective_at,
                modified_at,
                confidence,
                sensitivity,
                json_dumps(metadata or {}),
            ),
        )
        return evidence_id

    def add_node(
        self,
        node_type: str,
        name: str,
        *,
        node_id: str | None = None,
        scope: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        node_id = node_id or stable_id(node_type, scope or "", name)
        existing = self.db.execute(
            "SELECT metadata_json FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        merged = json.loads(existing["metadata_json"]) if existing else {}
        merged.update(metadata or {})
        self.db.execute(
            """
            INSERT OR REPLACE INTO nodes
            (id, node_type, name, scope, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM nodes WHERE id=?), ?))
            """,
            (node_id, node_type, name, scope, json_dumps(merged), node_id, utc_now()),
        )
        return node_id

    def add_edge(
        self,
        source_id: str,
        relation: str,
        target_id: str,
        *,
        mode: str = "actual",
        status: str = "observed",
        confidence: float = 1.0,
        evidence_id: str | None = None,
        effective_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        edge_id = stable_id(
            "edge",
            source_id,
            relation,
            target_id,
            mode,
            evidence_id or "",
            effective_at or "",
            status,
        )
        self.db.execute(
            """
            INSERT OR REPLACE INTO edges
            (id, source_id, relation, target_id, mode, status, confidence,
             evidence_id, effective_at, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge_id,
                source_id,
                relation,
                target_id,
                mode,
                status,
                confidence,
                evidence_id,
                effective_at,
                json_dumps(metadata or {}),
                utc_now(),
            ),
        )
        return edge_id

    def commit(self) -> None:
        self.db.commit()

    def nodes(self, node_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM nodes"
        args: tuple[Any, ...] = ()
        if node_type:
            query += " WHERE node_type = ?"
            args = (node_type,)
        rows = self.db.execute(query + " ORDER BY node_type, name", args).fetchall()
        return [self._node(row) for row in rows]

    def evidence(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM evidence ORDER BY observed_at DESC").fetchall()
        return [self._evidence(row) for row in rows]

    def resolved_edges(self, mode: str | None = None) -> list[dict[str, Any]]:
        query = """
        SELECT e.*, COALESCE(ev.effective_at, e.effective_at, '') AS rank_effective,
               COALESCE(ev.modified_at, '') AS rank_modified
        FROM edges e LEFT JOIN evidence ev ON ev.id = e.evidence_id
        """
        args: tuple[Any, ...] = ()
        if mode:
            query += " WHERE e.mode = ?"
            args = (mode,)
        rows = self.db.execute(query, args).fetchall()
        winners: dict[tuple[str, str, str, str], sqlite3.Row] = {}
        for row in rows:
            key = (row["source_id"], row["relation"], row["target_id"], row["mode"])
            rank = (
                row["rank_effective"],
                row["rank_modified"],
                float(row["confidence"]),
                row["created_at"],
            )
            current = winners.get(key)
            if current is None:
                winners[key] = row
                continue
            current_rank = (
                current["rank_effective"],
                current["rank_modified"],
                float(current["confidence"]),
                current["created_at"],
            )
            if rank > current_rank:
                winners[key] = row
        return [self._edge(row) for row in winners.values()]

    def graph(self, mode: str | None = None) -> dict[str, Any]:
        edges = self.resolved_edges(mode)
        node_ids = {item for edge in edges for item in (edge["source_id"], edge["target_id"])}
        nodes = [node for node in self.nodes() if node["id"] in node_ids or not edges]
        return {"nodes": nodes, "edges": edges}

    def _node(self, row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["metadata"] = json.loads(value.pop("metadata_json"))
        return value

    def _edge(self, row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["metadata"] = json.loads(value.pop("metadata_json"))
        value.pop("rank_effective", None)
        value.pop("rank_modified", None)
        return value

    def _evidence(self, row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["metadata"] = json.loads(value.pop("metadata_json"))
        return value
