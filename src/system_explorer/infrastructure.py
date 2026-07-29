from __future__ import annotations

import fnmatch
import json
import sqlite3
from pathlib import Path
from typing import Any

from .store import Store
from .util import expand_path, sha256_file, stable_id


DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
REGISTRY_KEYS = {
    "registry",
    "catalog",
    "entries",
    "records",
    "items",
    "modules",
    "providers",
    "inventory",
    "components",
}
CLOUD_SYMBOLS = {"direct": "☁", "indirect-mirror": "⇄☁", "local": "⌂"}
AUTO_CLOUD_PATHS = {
    "onedrive": ("onedrive",),
    "dropbox": ("dropbox",),
    "google-drive": ("google drive", "googledrive"),
    "icloud": ("iclouddrive", "icloud drive"),
}


def registry_profile(path: Path) -> dict[str, Any] | None:
    if path.suffix.casefold() != ".json" or path.stat().st_size > 5_000_000:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    collections: list[dict[str, Any]] = []
    if isinstance(value, list):
        collections.append({"name": "root", "entries": len(value), "kind": "array"})
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, list) and key.casefold() in REGISTRY_KEYS:
                collections.append(
                    {"name": str(key), "entries": len(item), "kind": "array"}
                )
            elif isinstance(item, dict) and key.casefold() in REGISTRY_KEYS:
                collections.append(
                    {"name": str(key), "entries": len(item), "kind": "object"}
                )
        if not collections and len(value) >= 2 and all(
            isinstance(item, dict)
            and any(field in item for field in ("id", "name", "key", "type"))
            for item in value.values()
        ):
            collections.append(
                {"name": "root", "entries": len(value), "kind": "record-map"}
            )
    return {
        "root_kind": "array"
        if isinstance(value, list)
        else "object"
        if isinstance(value, dict)
        else type(value).__name__,
        "collections": collections,
    }


def is_registry_file(
    path: Path, config: dict[str, Any], profile: dict[str, Any] | None = None
) -> bool:
    patterns = config.get(
        "registry_documents",
        ["*registry*", "*catalog*.json", "*inventory*.json"],
    )
    if any(
        fnmatch.fnmatch(path.name.casefold(), str(pattern).casefold())
        for pattern in patterns
    ):
        return True
    profile = profile if profile is not None else registry_profile(path)
    return bool(profile and profile["collections"])


def register_registry_file(
    path: Path,
    node_id: str,
    evidence_id: str,
    config: dict[str, Any],
    store: Store,
) -> dict[str, int]:
    profile = registry_profile(path)
    if not is_registry_file(path, config, profile):
        return {"registries": 0, "collections": 0, "edges": 0}
    registry_id = store.add_node(
        "registry",
        path.name,
        node_id=node_id,
        scope=str(path.parent),
        metadata={
            "path": str(path),
            "uri": path.resolve().as_uri(),
            "registry_kind": path.suffix.casefold().lstrip(".") or "text",
            "purpose": "index-or-registry",
            "root_kind": profile["root_kind"] if profile else "unknown",
            "collection_count": len(profile["collections"]) if profile else 0,
        },
    )
    stats = {"registries": 1, "collections": 0, "edges": 0}
    for collection in (profile or {}).get("collections", []):
        collection_id = store.add_node(
            "registry_collection",
            collection["name"],
            node_id=stable_id("registry-collection", str(path.resolve()), collection["name"]),
            scope=str(path),
            metadata={
                "entries": collection["entries"],
                "collection_kind": collection["kind"],
            },
        )
        store.add_edge(
            registry_id,
            "contains_collection",
            collection_id,
            status="observed",
            evidence_id=evidence_id,
        )
        stats["collections"] += 1
        stats["edges"] += 1
    return stats


def register_database_file(
    path: Path,
    node_id: str,
    evidence_id: str,
    store: Store,
    declared: dict[str, Any] | None = None,
) -> dict[str, int]:
    declared = declared or {}
    database_id = store.add_node(
        "database",
        declared.get("name") or path.name,
        node_id=node_id,
        scope=str(path.parent),
        metadata={
            "path": str(path),
            "uri": path.resolve().as_uri(),
            "database_kind": declared.get("kind", "sqlite"),
            "purpose": declared.get("purpose"),
            "fill_purpose": declared.get("fill_purpose"),
            "retrieval_purpose": declared.get("retrieval_purpose"),
            "cloud_ready": declared.get("cloud_ready", False),
            "cloud_symbol": "☁✓" if declared.get("cloud_ready", False) else "☁×",
        },
    )
    table_overrides = {
        item["name"]: item for item in declared.get("tables", []) if item.get("name")
    }
    tables = inspect_sqlite(path) if path.exists() else []
    for configured_name, item in table_overrides.items():
        if not any(table["name"] == configured_name for table in tables):
            tables.append({"name": configured_name, "columns": [], "declared_only": True})
    for table in tables:
        override = table_overrides.get(table["name"], {})
        table_id = store.add_node(
            "database_table",
            table["name"],
            node_id=stable_id("database-table", str(path.resolve()), table["name"]),
            scope=str(path),
            metadata={
                "columns": table.get("columns", []),
                "declared_only": table.get("declared_only", False),
                "fill_purpose": override.get("fill_purpose"),
                "retrieval_purpose": override.get("retrieval_purpose"),
            },
        )
        store.add_edge(
            database_id,
            "contains_table",
            table_id,
            status="observed" if not table.get("declared_only") else "declared",
            evidence_id=evidence_id,
        )
    return {"databases": 1, "tables": len(tables), "edges": len(tables)}


def inspect_sqlite(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() not in DATABASE_SUFFIXES:
        return []
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result = []
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [
                {"name": row[1], "type": row[2]}
                for row in db.execute(f"PRAGMA table_info({quoted})")
            ]
            result.append({"name": table, "columns": columns})
        return result
    except sqlite3.DatabaseError:
        return []
    finally:
        db.close()


def register_declared_infrastructure(
    config: dict[str, Any], store: Store
) -> dict[str, int]:
    stats = {
        "cloud_providers": 0,
        "cloud_paths": 0,
        "credentials": 0,
        "databases": 0,
        "tables": 0,
        "registries": 0,
        "relations": 0,
    }
    base = Path(config["_base"])
    evidence_id = _config_evidence(config, store)
    providers: dict[str, str] = {}
    for item in config.get("cloud", {}).get("providers", []):
        provider_id = _cloud_provider(item.get("id") or item["name"], item, store)
        providers[item.get("id") or item["name"]] = provider_id
        stats["cloud_providers"] += 1
    credentials: dict[str, str] = {}
    for item in config.get("credentials", []):
        credential_id = store.add_node(
            "credential_reference",
            item["id"],
            node_id=f"credential:{item['id']}",
            metadata={
                "provider": item.get("provider"),
                "storage": item.get("storage"),
                "location_hint": item.get("location_hint"),
                "value_retained": False,
            },
        )
        credentials[item["id"]] = credential_id
        stats["credentials"] += 1
    for item in config.get("cloud", {}).get("paths", []):
        path = expand_path(item["path"], base)
        directory_id = store.add_node(
            "directory",
            item.get("name") or path.name,
            node_id=stable_id("directory", str(path.resolve())),
            scope=str(path.parent),
            metadata={**_cloud_metadata(item), "path": str(path)},
        )
        provider_name = item.get("provider")
        if provider_name:
            provider_id = providers.get(provider_name) or _cloud_provider(
                provider_name, {}, store
            )
            store.add_edge(
                directory_id,
                "mirrors_to"
                if item.get("mode") == "indirect-mirror"
                else "connects_to",
                provider_id,
                status="configured",
                evidence_id=evidence_id,
                metadata={
                    "mode": item.get("mode", "direct"),
                    "transfer": item.get("transfer"),
                    "remote_ref": item.get("remote_ref"),
                },
            )
            stats["relations"] += 1
        credential = item.get("credential_ref")
        if credential:
            credential_id = credentials.get(credential) or store.add_node(
                "credential_reference",
                credential,
                node_id=f"credential:{credential}",
                metadata={"value_retained": False},
            )
            store.add_edge(
                directory_id,
                "uses_credential",
                credential_id,
                status="configured",
                evidence_id=evidence_id,
            )
            stats["relations"] += 1
        stats["cloud_paths"] += 1
    for item in config.get("cloud", {}).get("links", []):
        if item.get("node_id"):
            target_id = item["node_id"]
            if not any(node["id"] == target_id for node in store.nodes()):
                store.add_node(
                    "mapping_point",
                    item.get("name") or target_id,
                    node_id=target_id,
                    metadata={"declared_only": True},
                )
        else:
            path = expand_path(item["path"], base)
            target_id = store.add_node(
                item.get("node_type", "mapping_point"),
                item.get("name") or path.name,
                node_id=stable_id("path", str(path.resolve())),
                scope=str(path.parent),
                metadata={"path": str(path), "declared_only": not path.exists()},
            )
        _connect_cloud_target(
            target_id,
            item,
            providers,
            credentials,
            store,
            evidence_id,
            stats,
        )
    _apply_automatic_cloud_metadata(store, providers, evidence_id, stats)
    for item in config.get("registries", []):
        path = expand_path(item["path"], base)
        registry_id = store.add_node(
            "registry",
            item.get("name") or path.name,
            node_id=stable_id("path", str(path.resolve())),
            scope=str(path.parent),
            metadata={
                "path": str(path),
                "purpose": item.get("purpose"),
                "registry_kind": item.get("kind", path.suffix.lstrip(".")),
            },
        )
        _connect_data_roles(registry_id, item, store, evidence_id, stats)
        _connect_entrypoints(registry_id, item, store, evidence_id, stats)
        _connect_cloud_target(
            registry_id,
            item,
            providers,
            credentials,
            store,
            evidence_id,
            stats,
        )
        stats["registries"] += 1
    for item in config.get("databases", []):
        path = expand_path(item["path"], base)
        db_id = stable_id("path", str(path.resolve()))
        result = register_database_file(path, db_id, evidence_id, store, item)
        stats["databases"] += result["databases"]
        stats["tables"] += result["tables"]
        stats["relations"] += result["edges"]
        _connect_data_roles(db_id, item, store, evidence_id, stats)
        _connect_entrypoints(db_id, item, store, evidence_id, stats)
        _connect_cloud_target(
            db_id,
            item,
            providers,
            credentials,
            store,
            evidence_id,
            stats,
        )
    store.commit()
    return stats


def _connect_data_roles(
    target_id: str,
    item: dict[str, Any],
    store: Store,
    evidence_id: str,
    stats: dict[str, int],
) -> None:
    fields = (
        ("writers_actual", "fills", "actual"),
        ("writers_desired", "fills", "desired"),
        ("readers_actual", "reads", "actual"),
        ("readers_desired", "reads", "desired"),
    )
    for field, relation, mode in fields:
        for actor in item.get(field, []):
            actor_id = store.add_node(
                "data_actor",
                actor,
                node_id=stable_id("data-actor", actor),
                metadata={"role_source": field},
            )
            store.add_edge(
                actor_id,
                relation,
                target_id,
                mode=mode,
                status="observed" if mode == "actual" else "required",
                evidence_id=evidence_id,
            )
            stats["relations"] += 1


def _connect_entrypoints(
    target_id: str,
    item: dict[str, Any],
    store: Store,
    evidence_id: str,
    stats: dict[str, int],
) -> None:
    for name, target in item.get("entrypoints", {}).items():
        entry_id = store.add_node(
            "entrypoint",
            name,
            node_id=stable_id("data-entrypoint", target_id, name),
            metadata={"target": target, "data_entrypoint": True},
        )
        store.add_edge(
            entry_id,
            "accesses",
            target_id,
            status="configured",
            evidence_id=evidence_id,
        )
        stats["relations"] += 1


def _connect_cloud_target(
    target_id: str,
    item: dict[str, Any],
    providers: dict[str, str],
    credentials: dict[str, str],
    store: Store,
    evidence_id: str,
    stats: dict[str, int],
) -> None:
    provider_name = item.get("cloud_provider") or item.get("provider")
    if provider_name:
        provider_id = providers.get(provider_name) or _cloud_provider(
            provider_name, {}, store
        )
        mode = item.get("cloud_mode") or item.get("mode", "direct")
        store.add_edge(
            target_id,
            "mirrors_to" if mode == "indirect-mirror" else "connects_to",
            provider_id,
            status="configured",
            evidence_id=evidence_id,
            metadata={
                "mode": mode,
                "transfer": item.get("transfer"),
                "cloud_ready": item.get("cloud_ready", mode != "local"),
            },
        )
        stats["relations"] += 1
    credential = item.get("credential_ref")
    if credential:
        credential_id = credentials.get(credential) or store.add_node(
            "credential_reference",
            credential,
            node_id=f"credential:{credential}",
            metadata={"value_retained": False},
        )
        store.add_edge(
            target_id,
            "uses_credential",
            credential_id,
            status="configured",
            evidence_id=evidence_id,
        )
        stats["relations"] += 1


def _cloud_provider(name: str, item: dict[str, Any], store: Store) -> str:
    return store.add_node(
        "cloud_provider",
        item.get("name") or name,
        node_id=f"cloud:{name}",
        metadata={
            "provider_kind": item.get("kind"),
            "endpoint_ref": item.get("endpoint_ref"),
            "cloud_symbol": "☁",
        },
    )


def _cloud_metadata(item: dict[str, Any]) -> dict[str, Any]:
    mode = item.get("mode", "local")
    return {
        "path": item.get("path"),
        "cloud_mode": mode,
        "cloud_provider": item.get("provider"),
        "cloud_ready": mode != "local",
        "cloud_symbol": CLOUD_SYMBOLS.get(mode, "?"),
        "transfer": item.get("transfer"),
        "configured": True,
    }


def _apply_automatic_cloud_metadata(
    store: Store,
    providers: dict[str, str],
    evidence_id: str,
    stats: dict[str, int],
) -> None:
    for node in store.nodes("directory"):
        if node.get("metadata", {}).get("configured"):
            continue
        path = str(node.get("metadata", {}).get("path", "")).casefold()
        for provider, needles in AUTO_CLOUD_PATHS.items():
            if not any(needle in path for needle in needles):
                continue
            store.add_node(
                "directory",
                node["name"],
                node_id=node["id"],
                scope=node.get("scope"),
                metadata={
                    "cloud_mode": "indirect-mirror",
                    "cloud_provider": provider,
                    "cloud_ready": True,
                    "cloud_symbol": CLOUD_SYMBOLS["indirect-mirror"],
                    "cloud_inferred": True,
                },
            )
            provider_id = providers.get(provider) or _cloud_provider(
                provider, {}, store
            )
            store.add_edge(
                node["id"],
                "mirrors_to",
                provider_id,
                status="inferred",
                confidence=0.6,
                evidence_id=evidence_id,
            )
            stats["relations"] += 1
            break


def _config_evidence(config: dict[str, Any], store: Store) -> str:
    path = Path(config["_config_path"])
    return store.add_evidence(
        uri=path.as_uri(),
        source_kind="system-explorer-config",
        sha256=sha256_file(path),
        modified_at=str(path.stat().st_mtime),
        sensitivity="sensitive",
        metadata={"content_retained": False},
    )
