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
CREATE TABLE IF NOT EXISTS component_identity_claims (
    source_uri TEXT PRIMARY KEY,
    component_ref TEXT NOT NULL,
    carrier_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(carrier_id) REFERENCES nodes(id),
    FOREIGN KEY(evidence_id) REFERENCES evidence(id)
);
CREATE INDEX IF NOT EXISTS idx_component_identity_ref
ON component_identity_claims(component_ref);
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
        self._commit_attempt_count = 0
        self._commit_count = 0
        self.db.executescript(SCHEMA)
        self._sanitize_unclaimed_software_identities()
        self.db.commit()

    def close(self) -> None:
        if self.db.in_transaction:
            self.db.rollback()
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

    def clear_component_identity_metadata(self, carrier_id: str) -> None:
        """Remove identity fields that are not backed by an identity claim."""
        claimed = self.db.execute(
            """
            SELECT 1
            FROM component_identity_claims
            WHERE carrier_id = ?
            LIMIT 1
            """,
            (carrier_id,),
        ).fetchone()
        if claimed is not None:
            return
        self._replace_node_identity_metadata(carrier_id, {})

    def clear_component_identity_claims(self, source_uri_prefix: str) -> int:
        """Remove scanner-owned identity claims below one transactional root."""
        rows = self.db.execute(
            """
            SELECT source_uri, component_ref, carrier_id
            FROM component_identity_claims
            WHERE substr(source_uri, 1, ?) = ?
            """,
            (len(source_uri_prefix), source_uri_prefix),
        ).fetchall()
        if not rows:
            return 0
        previous: dict[str, set[str]] = {}
        for row in rows:
            previous.setdefault(row["component_ref"], set()).add(row["carrier_id"])
        self.db.executemany(
            "DELETE FROM component_identity_claims WHERE source_uri = ?",
            ((row["source_uri"],) for row in rows),
        )
        for component_ref, carriers in previous.items():
            self._refresh_component_identity(component_ref, previous_carriers=carriers)
        return len(rows)

    def register_component_identity_claim(
        self,
        *,
        carrier_id: str,
        component_ref: str,
        evidence_id: str,
        source_kind: str,
        source_id: str,
    ) -> str:
        """Bind a declared stable component ID to hashed scanner evidence.

        One source URI may replace its previous claim on rescan. Multiple source
        URIs claiming the same component ref are retained as a conflict and no
        carrier receives a usable ``component_ref``.
        """
        evidence = self.db.execute(
            "SELECT uri, sha256 FROM evidence WHERE id = ?", (evidence_id,)
        ).fetchone()
        if evidence is None or not evidence["sha256"]:
            raise ValueError("component identity requires hashed evidence")
        previous = self.db.execute(
            """
            SELECT component_ref, carrier_id
            FROM component_identity_claims
            WHERE source_uri = ?
            """,
            (evidence["uri"],),
        ).fetchone()
        self.db.execute(
            """
            INSERT OR REPLACE INTO component_identity_claims
            (source_uri, component_ref, carrier_id, source_sha256, evidence_id,
             source_kind, source_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence["uri"],
                component_ref,
                carrier_id,
                evidence["sha256"],
                evidence_id,
                source_kind,
                source_id,
                utc_now(),
            ),
        )
        affected: dict[str, set[str]] = {component_ref: {carrier_id}}
        if previous is not None:
            affected.setdefault(previous["component_ref"], set()).add(
                previous["carrier_id"]
            )
        for ref, carriers in affected.items():
            self._refresh_component_identity(ref, previous_carriers=carriers)
        row = self.db.execute(
            "SELECT metadata_json FROM nodes WHERE id = ?", (carrier_id,)
        ).fetchone()
        metadata = json.loads(row["metadata_json"]) if row else {}
        return str(metadata.get("identity_status", "unbound"))

    def _refresh_component_identity(
        self,
        component_ref: str,
        *,
        previous_carriers: set[str] | None = None,
    ) -> None:
        claims = self.db.execute(
            """
            SELECT carrier_id, source_sha256, evidence_id, source_kind, source_id
            FROM component_identity_claims
            WHERE component_ref = ?
            ORDER BY evidence_id
            """,
            (component_ref,),
        ).fetchall()
        carriers = set(previous_carriers or ())
        carriers.update(row["carrier_id"] for row in claims)
        if len(claims) == 1:
            claim = claims[0]
            verified = {
                "component_ref": component_ref,
                "identity_status": "verified",
                "identity_source_kind": claim["source_kind"],
                "identity_source_id": claim["source_id"],
                "identity_source_sha256": claim["source_sha256"],
                "identity_evidence_id": claim["evidence_id"],
            }
            self._replace_node_identity_metadata(claim["carrier_id"], verified)
            for carrier_id in carriers - {claim["carrier_id"]}:
                self._clear_node_identity_metadata(
                    carrier_id, component_ref, status="superseded"
                )
            return
        if len(claims) > 1:
            conflict_claims = [
                {
                    "evidence_id": row["evidence_id"],
                    "source_kind": row["source_kind"],
                    "source_id": row["source_id"],
                    "source_sha256": row["source_sha256"],
                }
                for row in claims
            ]
            for carrier_id in carriers:
                self._replace_node_identity_metadata(
                    carrier_id,
                    {
                        "identity_status": "conflict",
                        "identity_conflict_ref": component_ref,
                        "identity_claims": conflict_claims,
                    },
                )
            return
        for carrier_id in carriers:
            self._clear_node_identity_metadata(
                carrier_id, component_ref, status="unbound"
            )

    def _replace_node_identity_metadata(
        self, carrier_id: str, values: dict[str, Any]
    ) -> None:
        row = self.db.execute(
            "SELECT metadata_json FROM nodes WHERE id = ?", (carrier_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown carrier for identity claim: {carrier_id}")
        metadata = json.loads(row["metadata_json"])
        for key in (
            "component_ref",
            "identity_status",
            "identity_source_kind",
            "identity_source_id",
            "identity_source_sha256",
            "identity_evidence_id",
            "identity_conflict_ref",
            "identity_claims",
        ):
            metadata.pop(key, None)
        metadata.update(values)
        self.db.execute(
            "UPDATE nodes SET metadata_json = ? WHERE id = ?",
            (json_dumps(metadata), carrier_id),
        )

    def _clear_node_identity_metadata(
        self, carrier_id: str, component_ref: str, *, status: str
    ) -> None:
        row = self.db.execute(
            "SELECT metadata_json FROM nodes WHERE id = ?", (carrier_id,)
        ).fetchone()
        if row is None:
            return
        metadata = json.loads(row["metadata_json"])
        if (
            metadata.get("component_ref") != component_ref
            and metadata.get("identity_conflict_ref") != component_ref
        ):
            return
        self._replace_node_identity_metadata(
            carrier_id, {"identity_status": status}
        )

    def _sanitize_unclaimed_software_identities(self) -> None:
        claimed = {
            row["carrier_id"]
            for row in self.db.execute(
                "SELECT DISTINCT carrier_id FROM component_identity_claims"
            ).fetchall()
        }
        rows = self.db.execute(
            """
            SELECT id, metadata_json
            FROM nodes
            WHERE node_type = 'software_resource'
            """
        ).fetchall()
        identity_fields = {
            "component_ref",
            "stable_ref",
            "identity_status",
            "identity_source_kind",
            "identity_source_id",
            "identity_source_sha256",
            "identity_evidence_id",
            "identity_conflict_ref",
            "identity_claims",
        }
        for row in rows:
            if row["id"] in claimed:
                continue
            metadata = json.loads(row["metadata_json"])
            if identity_fields & set(metadata):
                self._replace_node_identity_metadata(row["id"], {})

    def commit(self) -> None:
        self._commit_attempt_count += 1
        self._commit_database()
        self._commit_count += 1

    def begin_immediate(self) -> None:
        if self.db.in_transaction:
            raise RuntimeError(
                "BEGIN IMMEDIATE requires a clean Store transaction boundary"
            )
        self.db.execute("BEGIN IMMEDIATE")

    def _commit_database(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    @property
    def in_transaction(self) -> bool:
        return self.db.in_transaction

    @property
    def commit_count(self) -> int:
        return self._commit_count

    @property
    def commit_attempt_count(self) -> int:
        return self._commit_attempt_count

    def integrity_check(self) -> str:
        row = self.db.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing-result"

    def resolution_projection_state(
        self, projection_key: str
    ) -> dict[str, Any] | None:
        rows = self.db.execute(
            """
            SELECT metadata_json
            FROM evidence
            WHERE source_kind = 'system-resolution'
            """
        ).fetchall()
        states = []
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            if metadata.get("resolution_projection") != projection_key:
                continue
            generation = metadata.get("resolution_generation")
            if (
                not isinstance(generation, list)
                or len(generation) != 2
                or not all(isinstance(value, int) for value in generation)
            ):
                continue
            content_hash = metadata.get("resolution_content_hash")
            if not isinstance(content_hash, str):
                continue
            states.append(
                {
                    "generation": generation,
                    "content_hash": content_hash,
                }
            )
        if not states:
            return None
        latest_generation = max(
            tuple(state["generation"]) for state in states
        )
        latest = [
            state
            for state in states
            if tuple(state["generation"]) == latest_generation
        ]
        hashes = {state["content_hash"] for state in latest}
        if len(hashes) != 1:
            raise ValueError(
                "resolution projection has conflicting hashes at its latest generation"
            )
        return latest[0]

    def clear_resolution_projection(self, projection_key: str) -> dict[str, int]:
        edge_rows = self.db.execute(
            "SELECT id, source_id, metadata_json FROM edges WHERE mode = 'desired'"
        ).fetchall()
        edge_ids = []
        carrier_ids = set()
        for row in edge_rows:
            metadata = json.loads(row["metadata_json"])
            if metadata.get("resolution_projection") != projection_key:
                continue
            edge_ids.append(row["id"])
            carrier_ids.add(row["source_id"])
        if edge_ids:
            self.db.executemany("DELETE FROM edges WHERE id = ?", [(edge,) for edge in edge_ids])

        carrier_rows = self.db.execute(
            "SELECT id, metadata_json FROM nodes WHERE node_type = 'carrier'"
        ).fetchall()
        carrier_ids.update(
            row["id"]
            for row in carrier_rows
            if json.loads(row["metadata_json"]).get("resolution_projection")
            == projection_key
        )
        removed_carriers = 0
        for carrier_id in carrier_ids:
            row = self.db.execute(
                "SELECT metadata_json FROM nodes WHERE id = ?",
                (carrier_id,),
            ).fetchone()
            if row is None:
                continue
            metadata = json.loads(row["metadata_json"])
            if metadata.get("resolution_projection") != projection_key:
                continue
            references = self.db.execute(
                "SELECT COUNT(*) FROM edges WHERE source_id = ? OR target_id = ?",
                (carrier_id, carrier_id),
            ).fetchone()[0]
            if references == 0:
                self.db.execute("DELETE FROM nodes WHERE id = ?", (carrier_id,))
                removed_carriers += 1
            else:
                for field in (
                    "desired_statuses",
                    "consumes",
                    "provides",
                    "requirements",
                    "resolution_content_hash",
                    "resolution_host_id",
                    "resolution_projection",
                    "resolution_scope",
                    "resolution_system_id",
                    "roles",
                    "source_bundles",
                    "source_schema",
                ):
                    metadata.pop(field, None)
                metadata["desired"] = False
                self.db.execute(
                    "UPDATE nodes SET metadata_json = ? WHERE id = ?",
                    (json_dumps(metadata), carrier_id),
                )
        return {"edges": len(edge_ids), "carriers": removed_carriers}

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
