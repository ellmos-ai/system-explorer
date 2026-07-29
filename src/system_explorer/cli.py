from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .assessment import assess
from .config import database_path, load_config, write_default_config
from .coverage import coverage_report
from .deployment import (
    deployment_report,
    import_apiprober_export,
    purpose_report,
    refresh_provider_sources,
)
from .federation import export_system_map, import_system_map, tag_current_system
from .manifests import load_manifest, new_module_manifest, validate_manifest
from .maps import graph_view, render_ascii, render_html, render_mermaid
from .proposals import probe_plan, propose
from .registry import find_documents, register_path
from .resources import resource_report
from .scanner import scan
from .server import serve
from .specs import desired_template, import_spec
from .store import Store
from .transcripts import SUPPORTED_PROVIDERS, import_transcripts
from .util import expand_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="system-explorer",
        description="Evidence-backed maps of desired functions and their actual carriers.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a neutral starter configuration and desired spec.")
    init.add_argument("--config", type=Path, default=Path("system-explorer.json"))
    init.add_argument("--desired", type=Path)

    for name in ("scan", "ingest", "coverage", "assess", "doctor"):
        item = sub.add_parser(name)
        item.add_argument("--config", type=Path, required=True)

    spec = sub.add_parser("import-spec")
    spec.add_argument("path", type=Path)
    spec.add_argument("--config", type=Path, required=True)

    transcripts = sub.add_parser("import-transcripts")
    transcripts.add_argument("source", type=Path)
    transcripts.add_argument("--provider", choices=sorted(SUPPORTED_PROVIDERS), required=True)
    transcripts.add_argument("--actor")
    transcripts.add_argument("--config", type=Path, required=True)

    mapping = sub.add_parser("map")
    mapping.add_argument("--config", type=Path, required=True)
    mapping.add_argument(
        "--view",
        choices=[
            "actual",
            "desired",
            "diff",
            "coverage",
            "control",
            "tree",
            "data",
            "deployment",
            "purpose",
            "federation",
            "llm-traces",
            "llm-actions",
            "function-paths",
            "resources",
        ],
        default="coverage",
    )
    mapping.add_argument("--format", choices=["json", "ascii", "mermaid", "html"], default="ascii")
    mapping.add_argument("--output", type=Path)
    mapping.add_argument("--system", help="Origin system id; omit for all mapped systems.")

    map_export = sub.add_parser("map-export")
    map_export.add_argument("--config", type=Path, required=True)
    map_export.add_argument("--view", default="all")
    map_export.add_argument("--output", type=Path, required=True)

    map_import = sub.add_parser("map-import")
    map_import.add_argument("path", type=Path)
    map_import.add_argument("--config", type=Path, required=True)

    server_check = sub.add_parser("server-check")
    server_check.add_argument("--config", type=Path, required=True)

    resources = sub.add_parser("resources")
    resources.add_argument("--config", type=Path, required=True)

    purpose_check = sub.add_parser("purpose-check")
    purpose_check.add_argument("--target")
    purpose_check.add_argument("--config", type=Path, required=True)

    provider_refresh = sub.add_parser("provider-refresh")
    provider_refresh.add_argument("--config", type=Path, required=True)
    provider_refresh.add_argument("--timeout", type=float, default=15)
    provider_refresh.add_argument("--max-bytes", type=int, default=2_000_000)

    apiprober_import = sub.add_parser("import-apiprober")
    apiprober_import.add_argument("path", type=Path)
    apiprober_import.add_argument("--server", required=True)
    apiprober_import.add_argument("--config", type=Path, required=True)

    query = sub.add_parser("query")
    query.add_argument("--config", type=Path, required=True)
    query.add_argument("--kind", choices=["nodes", "edges", "evidence"], default="nodes")

    proposal = sub.add_parser("propose")
    proposal.add_argument("prompt")
    proposal.add_argument("--config", type=Path, required=True)

    register = sub.add_parser("register")
    register.add_argument("path", type=Path)
    register.add_argument(
        "--role",
        choices=[
            "control",
            "policy",
            "decision",
            "documentation",
            "memory",
            "runtime-log",
            "architecture",
            "cloud-readiness",
            "entry",
        ],
        required=True,
    )
    register.add_argument("--name")
    register.add_argument("--entry", action="store_true")
    register.add_argument("--config", type=Path, required=True)

    documents = sub.add_parser("documents")
    documents.add_argument("--config", type=Path, required=True)
    documents.add_argument("--role")
    documents.add_argument("--name")

    probe = sub.add_parser("probe-plan")
    probe.add_argument("--path", required=True)
    probe.add_argument("--task", required=True)
    probe.add_argument("--repetitions", type=int, default=3)
    probe.add_argument("--max-steps", type=int, default=20)

    web = sub.add_parser("serve")
    web.add_argument("--config", type=Path, required=True)
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)

    manifest = sub.add_parser("manifest")
    manifest_sub = manifest.add_subparsers(dest="manifest_command", required=True)
    inspect = manifest_sub.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    validate = manifest_sub.add_parser("validate")
    validate.add_argument("path", type=Path)
    create = manifest_sub.add_parser("create")
    create.add_argument("path", type=Path)
    create.add_argument("--id", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--category", default="control")
    create.add_argument("--kind", default="tool")
    create.add_argument("--repository")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.command == "init":
        if args.config.exists():
            raise ValueError(f"config already exists: {args.config}")
        write_default_config(args.config)
        desired = args.desired or args.config.with_name("desired-system.json")
        if desired.exists():
            raise ValueError(f"desired spec already exists: {desired}")
        _write_json(desired, desired_template())
        print(json.dumps({"config": str(args.config), "desired": str(desired)}))
        return 0
    if args.command == "probe-plan":
        print(
            json.dumps(
                probe_plan(args.path, args.task, args.repetitions, args.max_steps),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "manifest":
        return _manifest(args)

    config = load_config(args.config)
    if args.command == "serve":
        serve(config, args.host, args.port)
        return 0

    with Store(database_path(config)) as store:
        if args.command == "scan":
            value: Any = scan(config, store)
        elif args.command == "import-spec":
            value = import_spec(args.path, store)
            tag_current_system(config, store)
        elif args.command == "import-transcripts":
            value = import_transcripts(
                args.provider, args.source, store, actor_id=args.actor
            )
            tag_current_system(config, store)
        elif args.command == "coverage":
            value = coverage_report(store)
        elif args.command == "assess":
            value = assess(store)
        elif args.command == "ingest":
            value = _ingest(config, store)
        elif args.command == "query":
            value = (
                store.nodes()
                if args.kind == "nodes"
                else store.resolved_edges()
                if args.kind == "edges"
                else store.evidence()
            )
        elif args.command == "propose":
            value = propose(args.prompt, store)
        elif args.command == "register":
            value = register_path(
                args.path,
                args.role,
                store,
                config=config,
                name=args.name,
                entry=args.entry,
            )
            tag_current_system(config, store)
        elif args.command == "documents":
            value = find_documents(store, role=args.role, name=args.name)
        elif args.command == "doctor":
            value = _doctor(config, store)
        elif args.command == "server-check":
            value = deployment_report(store)
        elif args.command == "purpose-check":
            value = purpose_report(store, args.target)
        elif args.command == "resources":
            value = resource_report(store)
        elif args.command == "provider-refresh":
            value = refresh_provider_sources(
                config,
                store,
                timeout_seconds=args.timeout,
                max_bytes=args.max_bytes,
            )
            tag_current_system(config, store)
        elif args.command == "import-apiprober":
            value = import_apiprober_export(args.path, store, server_id=args.server)
            tag_current_system(config, store)
        elif args.command == "map-import":
            value = import_system_map(args.path, store)
            tag_current_system(config, store)
        elif args.command == "map-export":
            tag_current_system(config, store)
            value = export_system_map(
                store, system=config.get("system", {"id": "current-system"}), view=args.view
            )
            _write_json(args.output, value)
            value = {
                "output": str(args.output),
                "system": value["system"]["id"],
                "nodes": len(value["nodes"]),
                "edges": len(value["edges"]),
            }
        elif args.command == "map":
            graph = graph_view(store, args.view, system_id=args.system)
            rendered = _render(graph, args.format)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
                value = {"output": str(args.output), "nodes": len(graph["nodes"]), "edges": len(graph["edges"])}
            else:
                print(rendered, end="")
                return 0
        else:
            raise ValueError(f"unsupported command: {args.command}")
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0


def _manifest(args: argparse.Namespace) -> int:
    if args.manifest_command == "create":
        if args.path.exists():
            raise ValueError(f"manifest already exists: {args.path}")
        value = new_module_manifest(
            module_id=args.id,
            display_name=args.name,
            category=args.category,
            kind=args.kind,
            repository=args.repository,
        )
        _write_json(args.path, value)
        print(json.dumps({"created": str(args.path)}, ensure_ascii=False))
        return 0
    value = load_manifest(args.path)
    errors = validate_manifest(value)
    if args.manifest_command == "inspect":
        print(json.dumps({"manifest": value, "validation_errors": errors}, ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def _render(graph: dict[str, Any], format_name: str) -> str:
    if format_name == "json":
        return json.dumps(graph, ensure_ascii=False, indent=2) + "\n"
    if format_name == "ascii":
        return render_ascii(graph)
    if format_name == "mermaid":
        return render_mermaid(graph)
    return render_html(graph)


def _doctor(config: dict[str, Any], store: Store) -> dict[str, Any]:
    roots = []
    for item in config.get("roots", []):
        path = Path(config["_base"], item["path"]).resolve() if not Path(item["path"]).is_absolute() else Path(item["path"])
        roots.append({"id": item.get("id"), "path": str(path), "exists": path.exists()})
    return {
        "schema": config.get("schema"),
        "database": str(store.path),
        "database_writable": store.path.exists(),
        "roots": roots,
        "privacy": config.get("privacy", {}),
        "raw_content_storage": False,
    }


def _ingest(config: dict[str, Any], store: Store) -> dict[str, Any]:
    base = Path(config["_base"])
    result: dict[str, Any] = {"scan": scan(config, store), "desired": [], "transcripts": []}
    for item in config.get("desired_sources", []):
        source = item["path"] if isinstance(item, dict) else item
        result["desired"].append(
            {"path": source, "stats": import_spec(expand_path(source, base), store)}
        )
    for item in config.get("transcripts", []):
        source = expand_path(item["source"], base)
        result["transcripts"].append(
            {
                "provider": item["provider"],
                "source": str(source),
                "stats": import_transcripts(
                    item["provider"],
                    source,
                    store,
                    actor_id=item.get("actor"),
                    sensitivity=item.get("sensitivity", "sensitive"),
                ),
            }
        )
    tag_current_system(config, store)
    return result


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
