from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .maps import render_mermaid


REQUIRED_MEDIA_CAPABILITIES = {
    "domain.media.editing",
    "workflow.media.pipeline",
}


@dataclass(frozen=True)
class MediaEditorInfo:
    root: Path
    version: str
    manifest: dict[str, Any]


def discover_ai_media_editor(path: Path | None = None) -> MediaEditorInfo:
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    configured = os.environ.get("AI_MEDIA_EDITOR_PATH")
    if configured:
        candidates.append(Path(configured))
    repo_parent = Path(__file__).resolve().parents[3]
    candidates.append(repo_parent / "ai-media-editor")

    checked: list[str] = []
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if str(root) in checked:
            continue
        checked.append(str(root))
        manifest_path = root / "ellmos-module.v2.json"
        if not manifest_path.is_file():
            continue
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        if value.get("id") != "ai-media-editor":
            if path is not None and root == path.expanduser().resolve():
                raise ValueError(
                    f"expected ai-media-editor manifest, got {value.get('id')!r}"
                )
            continue
        capabilities = set(value.get("provides", []))
        missing = sorted(REQUIRED_MEDIA_CAPABILITIES - capabilities)
        if missing:
            raise ValueError(
                "ai-media-editor manifest misses required capabilities: "
                + ", ".join(missing)
            )
        entrypoints = value.get("entrypoints", {})
        if "cli" not in entrypoints or "workflow" not in entrypoints:
            raise ValueError(
                "ai-media-editor must expose cli and workflow entrypoints"
            )
        if not (root / "editor.py").is_file():
            raise ValueError("ai-media-editor CLI entrypoint editor.py is missing")
        if not (root / str(entrypoints["workflow"])).is_file():
            raise ValueError("ai-media-editor workflow entrypoint is missing")
        return MediaEditorInfo(
            root=root,
            version=str(value.get("version", "unknown")),
            manifest=value,
        )
    raise ValueError(
        "ai-media-editor not found; pass --media-editor or set "
        "AI_MEDIA_EDITOR_PATH"
    )


def build_explainer_package(
    graphs: dict[str, dict[str, Any]],
    output_dir: Path,
    *,
    title: str,
    media_editor: MediaEditorInfo,
    probe: bool = False,
) -> dict[str, Any]:
    if not graphs:
        raise ValueError("at least one analyzed system map is required")
    output_dir = output_dir.expanduser().resolve()
    marker_path = output_dir / ".system-explorer-explainer.json"
    if output_dir.exists() and any(output_dir.iterdir()) and not marker_path.is_file():
        legacy_handoff = output_dir / "ai-media-editor-handoff.json"
        legacy_managed = False
        if legacy_handoff.is_file():
            try:
                legacy_managed = (
                    json.loads(legacy_handoff.read_text(encoding="utf-8")).get(
                        "schema"
                    )
                    == "system-explorer.ai-media-editor-handoff.v1"
                )
            except json.JSONDecodeError:
                legacy_managed = False
        if not legacy_managed:
            raise ValueError(
                f"explainer output directory is not managed by system-explorer: "
                f"{output_dir}"
            )
    if marker_path.is_file():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("schema") != "system-explorer.explainer-package-marker.v1":
            raise ValueError(f"invalid explainer package marker: {marker_path}")
    maps_dir = output_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    normalized = {
        name: {
            "nodes": sorted(
                graph.get("nodes", []),
                key=lambda node: str(node.get("id", "")),
            ),
            "edges": sorted(
                graph.get("edges", []),
                key=lambda edge: (
                    str(edge.get("source_id", "")),
                    str(edge.get("relation", "")),
                    str(edge.get("target_id", "")),
                    str(edge.get("mode", "")),
                    str(edge.get("status", "")),
                ),
            ),
            **({"summary": graph["summary"]} if "summary" in graph else {}),
        }
        for name, graph in sorted(graphs.items())
    }
    source_hash = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    analysis = _analyze_graphs(normalized)
    scenes = _storyboard(title, analysis, list(normalized))

    map_paths: list[str] = []
    for name, graph in normalized.items():
        safe_name = _safe_filename(name)
        path = maps_dir / f"{safe_name}.mmd"
        _write_text_atomic(path, render_mermaid(graph))
        map_paths.append(path.relative_to(output_dir).as_posix())

    storyboard = {
        "schema": "system-explorer.explainer-storyboard.v1",
        "title": title,
        "language": "de",
        "source_map_hash": source_hash,
        "scenes": scenes,
    }
    handoff = {
        "schema": "system-explorer.ai-media-editor-handoff.v1",
        "producer": {
            "id": "system-explorer",
            "source_map_hash": source_hash,
            "views": list(normalized),
        },
        "consumer": {
            "id": "ai-media-editor",
            "version": media_editor.version,
            "root": str(media_editor.root),
            "workflow": str(
                media_editor.root
                / str(media_editor.manifest["entrypoints"]["workflow"])
            ),
        },
        "production": {
            "usecase": 6,
            "kind": "explainer-video",
            "aspect_ratio": "16:9",
            "rendered": False,
            "strategy_confirmation_required_before_render": True,
            "artifacts": {
                "narration": "narration.md",
                "storyboard": "storyboard.json",
                "maps": map_paths,
            },
        },
        "truth_boundary": {
            "map_names_only": True,
            "raw_evidence_copied": False,
            "render_requires_ai_media_editor_workflow": True,
        },
    }
    _write_json_atomic(output_dir / "storyboard.json", storyboard)
    _write_json_atomic(output_dir / "ai-media-editor-handoff.json", handoff)
    _write_text_atomic(output_dir / "narration.md", _narration(title, scenes))
    _write_text_atomic(output_dir / "README.md", _package_readme(title))
    _write_json_atomic(
        marker_path,
        {
            "schema": "system-explorer.explainer-package-marker.v1",
            "source_map_hash": source_hash,
        },
    )

    connector_probe = (
        probe_ai_media_editor(media_editor) if probe else {"ok": None, "ran": False}
    )
    return {
        "status": "handoff-ready",
        "output": str(output_dir),
        "source_map_hash": source_hash,
        "scenes": len(scenes),
        "maps": map_paths,
        "connector_probe": connector_probe,
        "rendered": False,
    }


def probe_ai_media_editor(
    media_editor: MediaEditorInfo, timeout_seconds: float = 15
) -> dict[str, Any]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        completed = subprocess.run(
            [sys.executable, str(media_editor.root / "editor.py"), "modes"],
            cwd=media_editor.root,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "ran": True,
            "error": type(exc).__name__,
        }
    return {
        "ok": completed.returncode == 0 and "6" in completed.stdout,
        "ran": True,
        "returncode": completed.returncode,
        "usecase_6_detected": "6" in completed.stdout,
    }


def _analyze_graphs(graphs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    summary: dict[str, int] = {}
    for graph in graphs.values():
        for node in graph["nodes"]:
            nodes.setdefault(str(node["id"]), node)
        for edge in graph["edges"]:
            key = (
                str(edge["source_id"]),
                str(edge["relation"]),
                str(edge["target_id"]),
            )
            edges.setdefault(key, edge)
        for key, value in graph.get("summary", {}).items():
            if isinstance(value, int):
                summary[key] = max(summary.get(key, 0), value)

    degree: dict[str, int] = {}
    for source, _, target in edges:
        degree[source] = degree.get(source, 0) + 1
        degree[target] = degree.get(target, 0) + 1

    def names(types: set[str]) -> list[str]:
        selected = [
            node
            for node in nodes.values()
            if str(node.get("node_type")) in types
        ]
        selected.sort(
            key=lambda node: (
                -degree.get(str(node["id"]), 0),
                str(node.get("name", "")).casefold(),
            )
        )
        return [_short_name(node.get("name", node["id"])) for node in selected]

    entries = names(
        {
            "entrypoint",
            "interface",
            "control_document",
            "system_instance",
        }
    )
    functions = names({"function"})
    carriers = names({"carrier", "software_resource", "module", "repository"})
    gaps = [
        _short_name(node.get("name", node["id"]))
        for node in nodes.values()
        if node.get("node_type") == "gap"
        or node.get("metadata", {}).get("coverage_verdict")
        in {"uncovered", "negative"}
    ]
    highlight_types = {
        "function",
        "carrier",
        "software_resource",
        "module",
        "repository",
    }
    top_ids = sorted(
        (
            node_id
            for node_id, node in nodes.items()
            if node.get("node_type") in highlight_types
            and node.get("metadata", {}).get("coverage_verdict")
            not in {"uncovered", "negative"}
        ),
        key=lambda node_id: (
            -int(
                nodes[node_id].get("metadata", {}).get("coverage_verdict")
                == "full"
            ),
            -degree.get(node_id, 0),
            str(nodes[node_id].get("name", "")).casefold(),
        ),
    )
    highlights = [
        _short_name(nodes[node_id].get("name", node_id))
        for node_id in top_ids
    ]
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "entries": _unique(entries),
        "functions": _unique(functions),
        "carriers": _unique(carriers),
        "gaps": _unique(gaps),
        "highlights": _unique(highlights),
        "summary": summary,
    }


def _storyboard(
    title: str, analysis: dict[str, Any], views: list[str]
) -> list[dict[str, Any]]:
    entries = _take(analysis["entries"], 5, "Konfiguration und CLI")
    functions = _take(analysis["functions"], 6, "Funktionen aus der Systemkarte")
    carriers = _take(analysis["carriers"], 5, "Module und Funktionsträger")
    highlights = _take(analysis["highlights"], 5, "Zentrale Systembausteine")
    additional = analysis["functions"][6:10]
    additional.extend(f"Offen: {gap}" for gap in analysis["gaps"][:3])
    additional = _take(
        _unique(additional),
        7,
        "Keine weiteren oder ungedeckten Funktionen in dieser Ansicht",
    )
    view_text = ", ".join(views)
    return [
        {
            "id": "opening",
            "title": title,
            "question": "Was wird erklärt?",
            "voiceover": (
                f"Diese Tour erklärt {title} anhand einer analysierten Systemkarte "
                f"mit {analysis['nodes']} Knoten und {analysis['edges']} Beziehungen."
            ),
            "on_screen": [f"{analysis['nodes']} Knoten", f"{analysis['edges']} Beziehungen"],
            "map_view": views[0],
        },
        {
            "id": "entry",
            "title": "Wo steigt man ein?",
            "question": "Wo steigt man ein?",
            "voiceover": (
                "Der Einstieg beginnt bei den sichtbaren Interfaces, Entrypoints "
                "und Steuerdokumenten. Von dort führt die Karte zu den ausführenden "
                "Trägern."
            ),
            "on_screen": entries,
            "map_view": _preferred_view(views, "control"),
        },
        {
            "id": "capabilities",
            "title": "Was kann das System?",
            "question": "Was kann das System?",
            "voiceover": (
                "Die Funktionsknoten beschreiben die Fähigkeiten unabhängig davon, "
                "welches Modul sie trägt. So bleiben deklarierte und belegte "
                "Fähigkeiten unterscheidbar."
            ),
            "on_screen": functions,
            "map_view": _preferred_view(views, "coverage"),
        },
        {
            "id": "mechanism",
            "title": "Wie funktioniert es?",
            "question": "Wie funktioniert es?",
            "voiceover": (
                "Entrypoints rufen Funktionsträger auf. Träger stellen Interfaces "
                "und Outputs bereit, tragen Funktionen und übergeben Ergebnisse. "
                "Die Kanten der Karte machen diesen Ablauf nachvollziehbar."
            ),
            "on_screen": carriers,
            "map_view": _preferred_view(views, "function-paths"),
        },
        {
            "id": "highlights",
            "title": "Die besten Features",
            "question": "Was sind die besten Features?",
            "voiceover": (
                "Als Highlights erscheinen stark verbundene, positiv gedeckte "
                "Bausteine. Die Auswahl folgt der analysierten Karte und ist keine "
                "unbelegte Produktwerbung."
            ),
            "on_screen": highlights,
            "map_view": _preferred_view(views, "coverage"),
        },
        {
            "id": "additional",
            "title": "Weitere Features und offene Lücken",
            "question": "Welche weiteren Features gibt es?",
            "voiceover": (
                "Neben den Highlights zeigt die Karte zusätzliche Funktionen und "
                "sichtbare Lücken. Fehlende Deckung bleibt als Befund erhalten."
            ),
            "on_screen": additional,
            "map_view": _preferred_view(views, "diff"),
        },
        {
            "id": "schematics",
            "title": "Schaltpläne und Karten",
            "question": "Wie sind die Schaltpläne und Karten aufgebaut?",
            "voiceover": (
                "Die Karten trennen Steuerung, Funktionspfade, Deckung und "
                "Ressourcen. Jede Ansicht basiert auf denselben evidenzgestützten "
                "Knoten und Beziehungen."
            ),
            "on_screen": [f"Ansichten: {view_text}", "Mermaid-Karten im Paket"],
            "map_view": views[0],
        },
    ]


def _narration(title: str, scenes: list[dict[str, Any]]) -> str:
    lines = [f"# {title}", "", "## Sprechertext", ""]
    for scene in scenes:
        lines.extend(
            [
                f"### {scene['title']}",
                "",
                scene["voiceover"],
                "",
                "**Einblendungen:** " + " · ".join(scene["on_screen"]),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _package_readme(title: str) -> str:
    return f"""# Erklärvideo-Paket: {title}

Dieses Paket wurde aus analysierten `system-explorer`-Karten erzeugt und ist
für `ai-media-editor` Usecase 6 vorbereitet.

1. `ai-media-editor-handoff.json` und `storyboard.json` prüfen.
2. Die Strategie und den Sprechertext vor dem Rendern bestätigen.
3. Den UC6-Workflow aus dem im Handoff genannten `ai-media-editor`-Workflow
   ausführen.
4. Die Mermaid-Dateien unter `maps/` als Schaltplan-Visuals verwenden.

Das Paket ist noch kein gerendertes MP4. Reale TTS-, Hyperframes-, FFmpeg-,
Cloud- oder Provider-Läufe bleiben ein separater, freizugebender Schritt.
"""


def _preferred_view(views: list[str], preferred: str) -> str:
    return preferred if preferred in views else views[0]


def _take(values: list[str], count: int, fallback: str) -> list[str]:
    return values[:count] or [fallback]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _short_name(value: Any) -> str:
    text = " ".join(str(value).split())
    return text[:120]


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
    safe = safe.strip("-_")
    if not safe:
        raise ValueError(f"invalid map view name: {value!r}")
    return safe


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_text_atomic(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def _write_text_atomic(path: Path, body: str) -> None:
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
