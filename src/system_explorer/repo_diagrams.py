from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable


GENERATED_MARKER = "generated-by: system-explorer"


def sync_repository_diagrams(
    *,
    repositories: Iterable[Path] = (),
    bundle_paths: Iterable[Path] = (),
    output_path: Path = Path("docs/system-map.md"),
    apply: bool = False,
    allow_dirty: bool = False,
    commit: bool = False,
    push: bool = False,
    commit_message: str = "docs: update system map",
) -> dict[str, Any]:
    if commit and not apply:
        raise ValueError("--commit requires --apply")
    if push and not commit:
        raise ValueError("--push requires --commit")
    if commit and allow_dirty:
        raise ValueError("--commit requires a clean repository; omit --allow-dirty")
    if output_path.is_absolute():
        raise ValueError("diagram output path must be relative to each repository")

    targets: dict[Path, dict[str, Any] | None] = {}
    skipped_refs: list[str] = []
    for repository in repositories:
        root = _git_root(repository)
        targets.setdefault(root, None)
    for bundle_path in bundle_paths:
        bundle_path = bundle_path.expanduser().resolve()
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        if bundle.get("schema") != "ellmos.bundle.v1":
            raise ValueError(f"not an ellmos.bundle.v1 manifest: {bundle_path}")
        bundle_root = _git_root(bundle_path)
        targets[bundle_root] = bundle
        for ref in _component_paths(bundle):
            candidate = (bundle_path.parent / ref).resolve() if not ref.is_absolute() else ref
            if not candidate.exists():
                skipped_refs.append(str(candidate))
                continue
            try:
                component_root = _git_root(candidate)
            except ValueError:
                skipped_refs.append(str(candidate))
                continue
            targets.setdefault(component_root, None)

    if not targets:
        raise ValueError("provide at least one --repo or --bundle")

    plans: list[dict[str, Any]] = []
    for root, bundle in sorted(targets.items(), key=lambda item: str(item[0]).casefold()):
        _assert_no_locks(root)
        target = (root / output_path).resolve()
        if root != target and root not in target.parents:
            raise ValueError(f"diagram output escapes repository root: {target}")
        graph = _bundle_graph(root, bundle) if bundle is not None else _repository_graph(root)
        body = _diagram_document(graph)
        old_body = target.read_text(encoding="utf-8") if target.exists() else None
        if old_body is not None and GENERATED_MARKER not in old_body:
            raise ValueError(f"existing diagram is not managed by system-explorer: {target}")
        action = (
            "create"
            if old_body is None
            else "unchanged"
            if old_body == body
            else "update"
        )
        plans.append(
            {
                "repo": str(root),
                "target": str(target),
                "graph": graph,
                "body": body,
                "action": action,
                "before_sha256": _sha(old_body) if old_body is not None else None,
                "after_sha256": _sha(body),
                "git_head": _git(root, "rev-parse", "HEAD").strip(),
            }
        )

    if apply:
        for plan in plans:
            if not allow_dirty:
                status = _git(Path(plan["repo"]), "status", "--porcelain", "--untracked-files=all")
                if status.strip():
                    raise ValueError(
                        f"repository is dirty; use --allow-dirty only after review: {plan['repo']}"
                    )
        for plan in plans:
            if plan["action"] == "unchanged":
                continue
            _write_atomic(Path(plan["target"]), plan["body"])
            plan["action"] = "created" if plan["action"] == "create" else "updated"
            readback = Path(plan["target"]).read_text(encoding="utf-8")
            if _sha(readback) != plan["after_sha256"]:
                raise OSError(f"diagram readback mismatch: {plan['target']}")
        if commit:
            for plan in plans:
                if plan["action"] not in {"created", "updated"}:
                    plan["commit"] = None
                    continue
                root = Path(plan["repo"])
                relative_target = Path(plan["target"]).relative_to(root)
                _git(root, "add", "--", str(relative_target))
                staged = [
                    line
                    for line in _git(root, "diff", "--cached", "--name-only").splitlines()
                    if line
                ]
                expected = relative_target.as_posix()
                if staged != [expected]:
                    raise ValueError(
                        f"unexpected staged files in {root}: {staged!r}; "
                        f"expected only {expected!r}"
                    )
                _git(root, "commit", "-m", commit_message)
                plan["commit"] = _git(root, "rev-parse", "HEAD").strip()
        if push:
            for plan in plans:
                if not plan.get("commit"):
                    plan["pushed"] = False
                    continue
                root = Path(plan["repo"])
                _git(root, "push")
                upstream = _git(root, "rev-parse", "@{upstream}").strip()
                if upstream != plan["commit"]:
                    raise OSError(
                        f"push readback mismatch in {root}: "
                        f"{plan['commit']} != {upstream}"
                    )
                plan["pushed"] = True

    return {
        "schema": "system-explorer.diagram-sync-receipt.v1",
        "applied": apply,
        "committed": commit,
        "pushed": push,
        "repositories": [
            {key: value for key, value in plan.items() if key not in {"graph", "body"}}
            for plan in plans
        ],
        "skipped_component_refs": skipped_refs,
    }


def _repository_graph(root: Path) -> dict[str, Any]:
    tracked = [
        line.strip()
        for line in _git(root, "ls-files").splitlines()
        if line.strip()
    ]
    manifest_path = root / "ellmos-module.v2.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repo_id = str(manifest.get("id") or root.name)
    repo_name = str(manifest.get("display_name") or repo_id)
    nodes = [{"id": f"repo:{repo_id}", "kind": "repository", "label": repo_name}]
    edges: list[dict[str, str]] = []

    top_level = sorted(
        {
            Path(item).parts[0]
            for item in tracked
            if len(Path(item).parts) > 1
            and Path(item).parts[0] not in {".git", ".venv", "node_modules"}
        }
    )
    for name in top_level[:12]:
        node_id = f"dir:{name}"
        nodes.append({"id": node_id, "kind": "directory", "label": f"{name}/"})
        edges.append({"source": f"repo:{repo_id}", "relation": "contains", "target": node_id})

    for name, command in sorted(manifest.get("entrypoints", {}).items()):
        node_id = f"entry:{name}"
        nodes.append(
            {
                "id": node_id,
                "kind": "entrypoint",
                "label": f"{name}: {_short(command)}",
            }
        )
        edges.append({"source": node_id, "relation": "enters", "target": f"repo:{repo_id}"})

    for capability in sorted(manifest.get("provides", [])):
        node_id = f"function:{capability}"
        nodes.append({"id": node_id, "kind": "function", "label": str(capability)})
        edges.append(
            {"source": f"repo:{repo_id}", "relation": "provides", "target": node_id}
        )
    return {
        "title": f"System map: {repo_name}",
        "kind": "repository",
        "source": ".",
        "nodes": nodes,
        "edges": edges,
    }


def _bundle_graph(root: Path, bundle: dict[str, Any]) -> dict[str, Any]:
    bundle_id = str(bundle.get("id", root.name))
    nodes = [{"id": f"bundle:{bundle_id}", "kind": "bundle", "label": bundle_id}]
    edges: list[dict[str, str]] = []
    for index, component in enumerate(bundle.get("components", []), start=1):
        ref = component.get("ref")
        ref_name = _ref_name(ref) or f"component-{index}"
        node_id = f"component:{index}:{ref_name}"
        nodes.append(
            {
                "id": node_id,
                "kind": str(component.get("type", "component")),
                "label": ref_name,
            }
        )
        edges.append(
            {
                "source": f"bundle:{bundle_id}",
                "relation": str(component.get("requirement", "contains")),
                "target": node_id,
            }
        )
        for capability in component.get("provides", []):
            function_id = f"function:{index}:{capability}"
            nodes.append(
                {"id": function_id, "kind": "function", "label": str(capability)}
            )
            edges.append(
                {"source": node_id, "relation": "provides", "target": function_id}
            )
        for capability in component.get("consumes", []):
            function_id = f"consumes:{index}:{capability}"
            nodes.append(
                {"id": function_id, "kind": "function", "label": str(capability)}
            )
            edges.append(
                {"source": node_id, "relation": "consumes", "target": function_id}
            )
    return {
        "title": f"Bundle system map: {bundle_id}",
        "kind": "bundle",
        "source": ".",
        "nodes": nodes,
        "edges": edges,
    }


def _diagram_document(graph: dict[str, Any]) -> str:
    fingerprint = hashlib.sha256(
        json.dumps(
            graph,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    aliases = {
        node["id"]: f"N{index}"
        for index, node in enumerate(graph["nodes"], start=1)
    }
    lines = [
        f"# {graph['title']}",
        "",
        f"<!-- {GENERATED_MARKER} -->",
        f"<!-- source-fingerprint: {fingerprint} -->",
        "",
        "Diese Datei wird deterministisch aus dem Repository- bzw. Bundle-Vertrag",
        "erzeugt. Änderungen erfolgen über `system-explorer diagrams`.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for node in graph["nodes"]:
        label = str(node["label"]).replace('"', "'").replace("\n", " ")
        lines.append(f'  {aliases[node["id"]]}["{label}"]')
    for edge in graph["edges"]:
        source = aliases[edge["source"]]
        target = aliases[edge["target"]]
        relation = str(edge["relation"]).replace("|", "/").replace("\n", " ")
        lines.append(f"  {source} -->|{relation}| {target}")
    lines.extend(["```", ""])
    return "\n".join(lines)


def _component_paths(bundle: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for component in bundle.get("components", []):
        ref = component.get("ref")
        if isinstance(ref, dict) and isinstance(ref.get("path"), str):
            paths.append(Path(ref["path"]))
        elif isinstance(ref, str) and ("/" in ref or "\\" in ref):
            paths.append(Path(ref))
    return paths


def _ref_name(ref: Any) -> str | None:
    if isinstance(ref, str):
        return ref
    if isinstance(ref, dict):
        for field in ("id", "ref", "path"):
            if ref.get(field):
                value = Path(str(ref[field]))
                if field == "path" and value.suffix:
                    return value.parent.name or value.stem
                return value.stem
    return None


def _git_root(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    cwd = candidate if candidate.is_dir() else candidate.parent
    completed = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"not inside a Git repository: {path}")
    return Path(completed.stdout.strip()).resolve()


def _assert_no_locks(root: Path) -> None:
    locks = sorted(
        path.name
        for path in root.glob("LOCK*.txt")
        if path.is_file()
    )
    if locks:
        raise ValueError(
            f"repository has active or unresolved lock files: {root}: "
            + ", ".join(locks)
        )


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed in {root}: {message}")
    return completed.stdout


def _write_atomic(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _short(value: Any) -> str:
    return " ".join(str(value).split())[:80]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
