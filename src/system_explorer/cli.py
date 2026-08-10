from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .actual_self import import_actual_self_receipt
from .assessment import assess
from .component_registry import (
    inspect_component_registry,
    parse_source_path_arguments,
)
from .config import database_path, load_config, write_default_config
from .coverage import coverage_report
from .deployment import (
    deployment_report,
    import_apiprober_export,
    purpose_report,
    refresh_provider_sources,
)
from .federation import export_system_map, import_system_map, tag_current_system
from .function_equivalence import (
    import_function_equivalence,
    reconcile_function_equivalence_projections,
)
from .manifests import load_manifest, new_module_manifest, validate_manifest
from .maps import graph_view, render_ascii, render_html, render_mermaid
from .media_connector import (
    build_explainer_package,
    discover_ai_media_editor,
)
from .proposals import probe_plan, propose
from .registry import find_documents, register_path
from .repo_diagrams import sync_repository_diagrams
from .receipt_trust import load_receipt_trust_store
from .resolution_bridge import import_resolution
from .resolver import resolve_system, resolve_test, validate_manifest_target
from .resources import resource_report
from .scanner import ProgressCallback, scan
from .search_authority import import_search_authority_receipt
from .search_routing import resolve_search_route
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
        if name in {"scan", "ingest"}:
            item.add_argument(
                "--time-budget-seconds",
                type=float,
                default=300.0,
                help=(
                    "Fail closed after this scan budget; 0 explicitly disables "
                    "the deadline (default: 300)."
                ),
            )
            item.add_argument(
                "--progress",
                choices=["jsonl", "off"],
                default="jsonl",
                help="Write scan progress to stderr as JSONL or disable it.",
            )
            item.add_argument(
                "--progress-interval-seconds",
                type=float,
                default=5.0,
                help="Minimum interval for repeated per-root progress events.",
            )
        if name == "coverage":
            item.add_argument(
                "--resolution",
                type=Path,
                action="append",
                dest="resolutions",
                help=(
                    "Import a system-explorer.resolution.v1 file as desired "
                    "coverage evidence before reporting; repeatable."
                ),
            )
            item.add_argument(
                "--equivalence",
                type=Path,
                action="append",
                dest="equivalences",
                help=(
                    "Import an explicit function-equivalence.v1 contract "
                    "before reporting; repeatable."
                ),
            )

    spec = sub.add_parser("import-spec")
    spec.add_argument("path", type=Path)
    spec.add_argument("--config", type=Path, required=True)

    resolution = sub.add_parser(
        "import-resolution",
        help="Import a read-only resolution.v1 projection as desired evidence.",
    )
    resolution.add_argument("path", type=Path)
    resolution.add_argument("--config", type=Path, required=True)

    actual_self = sub.add_parser(
        "import-actual-self",
        help=(
            "Import one source-verified native actual-self component receipt "
            "as exact actual coverage evidence."
        ),
    )
    actual_self.add_argument("path", type=Path)
    actual_self.add_argument("--resolution", type=Path, required=True)
    actual_self.add_argument("--config", type=Path, required=True)
    actual_self.add_argument("--evaluated-at", required=True)

    search_authority = sub.add_parser(
        "import-search-authority",
        help=(
            "Import one signed, trust-store-bound search authority receipt "
            "without accepting query-supplied authority claims."
        ),
    )
    search_authority.add_argument("path", type=Path)
    search_authority.add_argument("--resolution", type=Path, required=True)
    search_authority.add_argument("--config", type=Path, required=True)
    search_authority.add_argument("--evaluated-at", required=True)

    search_route = sub.add_parser(
        "search-route",
        help=(
            "Resolve stable-ID skill/tool candidates against exact registry "
            "identity and native actual-self coverage."
        ),
    )
    search_route.add_argument("query", type=Path)
    search_route.add_argument("--resolution", type=Path, required=True)
    search_route.add_argument(
        "--actual-self",
        type=Path,
        action="append",
        default=[],
        dest="actual_self_receipts",
    )
    search_route.add_argument(
        "--authority-receipt",
        type=Path,
        action="append",
        default=[],
        dest="authority_receipts",
    )
    search_route.add_argument("--config", type=Path, required=True)
    search_route.add_argument("--output", type=Path)

    equivalence = sub.add_parser(
        "import-function-equivalence",
        help=(
            "Import a read-only, Decision/Policy-authorized function "
            "equivalence contract."
        ),
    )
    equivalence.add_argument("path", type=Path)
    equivalence.add_argument("--config", type=Path, required=True)

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

    explainer = sub.add_parser(
        "explain-video",
        help="Create an ai-media-editor UC6 handoff from analyzed system maps.",
    )
    explainer.add_argument("--config", type=Path, required=True)
    explainer.add_argument("--output", type=Path, required=True)
    explainer.add_argument("--title")
    explainer.add_argument(
        "--view",
        action="append",
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
        dest="views",
    )
    explainer.add_argument("--system")
    explainer.add_argument("--media-editor", type=Path)
    explainer.add_argument("--probe", action="store_true")
    explainer.add_argument(
        "--no-ingest",
        action="store_true",
        help="Use the existing evidence database without refreshing sources.",
    )

    diagrams = sub.add_parser(
        "diagrams",
        help="Plan or update generated system maps in Git repositories.",
    )
    diagrams.add_argument("--repo", type=Path, action="append", dest="repositories")
    diagrams.add_argument("--bundle", type=Path, action="append", dest="bundles")
    diagrams.add_argument(
        "--output",
        type=Path,
        default=Path("docs/system-map.md"),
        help="Relative output path inside every repository.",
    )
    diagrams.add_argument("--apply", action="store_true")
    diagrams.add_argument("--allow-dirty", action="store_true")
    diagrams.add_argument("--commit", action="store_true")
    diagrams.add_argument("--push", action="store_true")
    diagrams.add_argument(
        "--commit-message",
        default="docs: update system map",
    )

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

    manifest_validate = sub.add_parser(
        "manifest-validate",
        help="Validate a V4 contract or compatible legacy manifest.",
    )
    manifest_validate.add_argument("path", type=Path)

    component_registry = sub.add_parser(
        "component-registry-check",
        help=(
            "Validate canonical component bindings, pinned sources, and "
            "declared-only activation gates."
        ),
    )
    component_registry.add_argument("bindings", type=Path)
    component_registry.add_argument(
        "--bundle",
        type=Path,
        action="append",
        default=[],
        dest="bundles",
    )
    component_registry.add_argument(
        "--bundle-root",
        type=Path,
        action="append",
        default=[],
        dest="bundle_roots",
    )
    component_registry.add_argument(
        "--source-path",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH",
    )
    component_registry.add_argument(
        "--activation-check",
        action="append",
        default=[],
        metavar="BUNDLE_ID",
    )
    component_registry.add_argument("--observed-on")
    component_registry.add_argument("--observed-at")
    component_registry.add_argument("--output", type=Path)

    system_resolve = sub.add_parser(
        "system-resolve",
        help="Resolve a pinned desired system instance without runtime actions.",
    )
    system_resolve.add_argument("instance", type=Path)
    system_resolve.add_argument(
        "--catalog",
        type=Path,
        action="append",
        required=True,
        dest="catalogs",
    )
    system_resolve.add_argument("--registry-bindings", type=Path)
    system_resolve.add_argument(
        "--registry-source-path",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH",
    )
    system_resolve.add_argument("--output", type=Path)

    test_resolve = sub.add_parser(
        "test-resolve",
        help="Resolve a read-only system-test overlay.",
    )
    test_resolve.add_argument("test", type=Path)
    test_resolve.add_argument(
        "--catalog",
        type=Path,
        action="append",
        required=True,
        dest="catalogs",
    )
    test_resolve.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except KeyboardInterrupt:
        _print_cli_error(
            args,
            "scan_interrupted",
            "interrupted; scan stopped without a success payload",
        )
        return 130
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_cli_error(args, "scan_failed", str(exc))
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
    if args.command == "diagrams":
        value = sync_repository_diagrams(
            repositories=args.repositories or (),
            bundle_paths=args.bundles or (),
            output_path=args.output,
            apply=args.apply,
            allow_dirty=args.allow_dirty,
            commit=args.commit,
            push=args.push,
            commit_message=args.commit_message,
        )
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    if args.command == "manifest-validate":
        value = validate_manifest_target(args.path)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value["valid"] else 1
    if args.command == "component-registry-check":
        bundle_paths = list(args.bundles)
        for root in args.bundle_roots:
            bundle_paths.extend(sorted(root.glob("*/bundle.v1.json")))
        if not bundle_paths:
            raise ValueError(
                "component-registry-check requires --bundle or --bundle-root"
            )
        value, exit_code = inspect_component_registry(
            args.bindings,
            bundle_paths,
            source_paths=parse_source_path_arguments(args.source_path),
            activation_bundle_ids=args.activation_check,
            observed_on=args.observed_on,
            observed_at=args.observed_at,
        )
        if args.output:
            _write_json_atomic(args.output, value)
            print(
                json.dumps(
                    {
                        "output": str(args.output),
                        "schema": value["schema"],
                        "content_hash": value["content_hash"],
                        "status": value["status"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(json.dumps(value, ensure_ascii=False, indent=2))
        return exit_code
    if args.command in {"system-resolve", "test-resolve"}:
        value = (
            resolve_system(
                args.instance,
                args.catalogs,
                registry_bindings_path=args.registry_bindings,
                registry_source_paths=parse_source_path_arguments(
                    args.registry_source_path
                ),
            )
            if args.command == "system-resolve"
            else resolve_test(args.test, args.catalogs)
        )
        if args.output:
            _write_json_atomic(args.output, value)
            print(
                json.dumps(
                    {
                        "output": str(args.output),
                        "schema": value["schema"],
                        "content_hash": value["content_hash"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0

    config = load_config(args.config)
    if args.command == "serve":
        serve(config, args.host, args.port)
        return 0

    with Store(database_path(config)) as store:
        if args.command == "scan":
            value: Any = scan(config, store, **_scan_runtime_options(args))
        elif args.command == "import-spec":
            value = import_spec(args.path, store)
            tag_current_system(config, store)
        elif args.command == "import-resolution":
            value = import_resolution(args.path, store)
        elif args.command == "import-actual-self":
            resolution_value = _read_json_object(args.resolution)
            import_resolution(args.resolution, store)
            trust_store = load_receipt_trust_store(config)
            value = import_actual_self_receipt(
                args.path,
                resolution_value,
                store,
                evaluated_at=args.evaluated_at,
                trust_store=trust_store,
            )
        elif args.command == "import-search-authority":
            resolution_value = _read_json_object(args.resolution)
            import_resolution(args.resolution, store)
            trust_store = load_receipt_trust_store(config)
            value = import_search_authority_receipt(
                args.path,
                store,
                evaluated_at=args.evaluated_at,
                expected_host_id=resolution_value["instance"]["host_id"],
                trust_store=trust_store,
            )
        elif args.command == "search-route":
            resolution_value = _read_json_object(args.resolution)
            query_value = _read_json_object(args.query)
            trust_store = load_receipt_trust_store(config)
            store.begin_immediate()
            try:
                import_resolution(
                    args.resolution,
                    store,
                    defer_commit=True,
                )
                for path in args.actual_self_receipts:
                    import_actual_self_receipt(
                        path,
                        resolution_value,
                        store,
                        evaluated_at=query_value["observed_at"],
                        trust_store=trust_store,
                        defer_commit=True,
                    )
                for path in args.authority_receipts:
                    import_search_authority_receipt(
                        path,
                        store,
                        evaluated_at=query_value["observed_at"],
                        expected_host_id=resolution_value["instance"]["host_id"],
                        trust_store=trust_store,
                        defer_commit=True,
                    )
                value = resolve_search_route(
                    query_value,
                    resolution_value,
                    store,
                    trust_store=trust_store,
                )
                store.commit()
            except BaseException:
                if store.in_transaction:
                    store.rollback()
                raise
            if args.output:
                _write_json_atomic(args.output, value)
                print(
                    json.dumps(
                        {
                            "output": str(args.output),
                            "schema": value["schema"],
                            "content_hash": value["content_hash"],
                            "result_status": value["result_status"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 0
        elif args.command == "import-function-equivalence":
            tag_current_system(config, store)
            value = import_function_equivalence(args.path, store)
        elif args.command == "import-transcripts":
            value = import_transcripts(
                args.provider, args.source, store, actor_id=args.actor
            )
            tag_current_system(config, store)
        elif args.command == "coverage":
            resolution_imports = _import_resolution_sources(
                config,
                store,
                explicit=args.resolutions or (),
            )
            equivalence_imports = _import_function_equivalence_sources(
                config,
                store,
                explicit=args.equivalences or (),
            )
            value = {
                **coverage_report(store),
                "resolution_imports": resolution_imports,
                "function_equivalence_imports": equivalence_imports,
            }
        elif args.command == "assess":
            value = assess(store)
        elif args.command == "ingest":
            value = _ingest(config, store, **_scan_runtime_options(args))
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
        elif args.command == "explain-video":
            if not args.no_ingest:
                _ingest(config, store)
            views = args.views or [
                "control",
                "function-paths",
                "coverage",
                "resources",
            ]
            graphs = {
                view: graph_view(store, view, system_id=args.system)
                for view in views
            }
            media_editor = discover_ai_media_editor(args.media_editor)
            system = config.get("system", {})
            value = build_explainer_package(
                graphs,
                args.output,
                title=args.title
                or str(system.get("name") or system.get("id") or "System"),
                media_editor=media_editor,
                probe=args.probe,
            )
        else:
            raise ValueError(f"unsupported command: {args.command}")
        print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


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


def _scan_runtime_options(args: argparse.Namespace) -> dict[str, Any]:
    budget = float(args.time_budget_seconds)
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("time budget must be finite and not negative")
    interval = float(args.progress_interval_seconds)
    if not math.isfinite(interval) or interval < 0:
        raise ValueError("progress interval must be finite and not negative")
    return {
        "time_budget_seconds": None if budget == 0 else budget,
        "progress": _emit_scan_progress if args.progress == "jsonl" else None,
        "progress_interval_seconds": interval,
    }


def _emit_scan_progress(event: dict[str, Any]) -> None:
    print(
        json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        file=sys.stderr,
        flush=True,
    )


def _print_cli_error(
    args: argparse.Namespace,
    event: str,
    message: str,
) -> None:
    if (
        getattr(args, "command", None) in {"scan", "ingest"}
        and getattr(args, "progress", None) == "jsonl"
    ):
        _emit_scan_progress(
            {
                "schema": "system-explorer.scan-progress.v1",
                "event": event,
                "message": message,
            }
        )
        return
    print(f"error: {message}", file=sys.stderr)


def _ingest(
    config: dict[str, Any],
    store: Store,
    *,
    time_budget_seconds: float | None = None,
    progress: ProgressCallback | None = None,
    progress_interval_seconds: float = 5.0,
) -> dict[str, Any]:
    base = Path(config["_base"])
    result: dict[str, Any] = {
        "scan": scan(
            config,
            store,
            time_budget_seconds=time_budget_seconds,
            progress=progress,
            progress_interval_seconds=progress_interval_seconds,
        ),
        "desired": [],
        "resolutions": [],
        "function_equivalences": [],
        "transcripts": [],
    }
    for item in config.get("desired_sources", []):
        source = item["path"] if isinstance(item, dict) else item
        result["desired"].append(
            {"path": source, "stats": import_spec(expand_path(source, base), store)}
        )
    result["resolutions"] = _import_resolution_sources(config, store)
    tag_current_system(config, store)
    result["function_equivalences"] = (
        _import_function_equivalence_sources(config, store)
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


def _import_resolution_sources(
    config: dict[str, Any],
    store: Store,
    *,
    explicit: tuple[Path, ...] | list[Path] = (),
) -> list[dict[str, Any]]:
    base = Path(config["_base"])
    paths: list[Path] = [path.resolve() for path in explicit]
    for item in config.get("desired_resolution_sources", []):
        source = item["path"] if isinstance(item, dict) else item
        paths.append(expand_path(source, base).resolve())
    imports = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        imports.append({"path": str(path), "stats": import_resolution(path, store)})
    return imports


def _import_function_equivalence_sources(
    config: dict[str, Any],
    store: Store,
    *,
    explicit: tuple[Path, ...] | list[Path] = (),
) -> list[dict[str, Any]]:
    base = Path(config["_base"])
    paths: list[Path] = [path.resolve() for path in explicit]
    for item in config.get("function_equivalence_sources", []):
        source = item["path"] if isinstance(item, dict) else item
        paths.append(expand_path(source, base).resolve())
    imports = []
    seen: set[Path] = set()
    allowed_projection_keys: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        stats = import_function_equivalence(path, store)
        imports.append({"path": str(path), "stats": stats})
        allowed_projection_keys.add(stats["projection_key"])
    reconciliation = reconcile_function_equivalence_projections(
        store, allowed_projection_keys
    )
    imports.append({"reconciliation": reconciliation})
    return imports


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_json_atomic(path: Path, value: Any) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
