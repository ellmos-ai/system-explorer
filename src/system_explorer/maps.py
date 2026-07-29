from __future__ import annotations

import html
import json
from typing import Any

from .coverage import coverage_report
from .deployment import deployment_report, purpose_report
from .federation import federation_graph
from .resources import resource_graph
from .store import Store


def graph_view(
    store: Store, view: str, system_id: str | None = None
) -> dict[str, Any]:
    if view in {"actual", "desired"}:
        return _filter_system(store.graph(view), system_id)
    if view == "coverage":
        return _filter_system(coverage_graph(store), system_id)
    if view in {"control", "tree"}:
        return _filter_system(document_graph(store, view), system_id)
    if view == "data":
        return _filter_system(data_graph(store), system_id)
    if view == "deployment":
        return _filter_system(deployment_graph(store), system_id)
    if view == "purpose":
        return _filter_system(purpose_graph(store), system_id)
    if view == "federation":
        return _filter_system(federation_graph(store), system_id)
    if view == "llm-traces":
        return _filter_system(llm_trace_graph(store), system_id)
    if view == "llm-actions":
        return _filter_system(llm_action_graph(store), system_id)
    if view == "function-paths":
        return _filter_system(function_path_graph(store), system_id)
    if view == "resources":
        return _filter_system(resource_graph(store), system_id)
    if view != "diff":
        raise ValueError(f"Unknown view: {view}")
    actual = store.graph("actual")
    desired = store.graph("desired")
    actual_keys = {_edge_key(edge): edge for edge in actual["edges"]}
    desired_keys = {_edge_key(edge): edge for edge in desired["edges"]}
    edges = []
    for key in sorted(actual_keys.keys() | desired_keys.keys()):
        if key in actual_keys and key in desired_keys:
            edge = dict(actual_keys[key])
            edge["diff_status"] = (
                "matched"
                if actual_keys[key]["status"] == desired_keys[key]["status"]
                else "changed"
            )
            edge["desired_status"] = desired_keys[key]["status"]
        elif key in desired_keys:
            edge = dict(desired_keys[key])
            edge["diff_status"] = "missing"
        else:
            edge = dict(actual_keys[key])
            edge["diff_status"] = "extra"
        edges.append(edge)
    node_ids = {value for edge in edges for value in (edge["source_id"], edge["target_id"])}
    node_map = {node["id"]: node for node in store.nodes()}
    return _filter_system(
        {"nodes": [node_map[item] for item in node_ids if item in node_map], "edges": edges},
        system_id,
    )


def coverage_graph(store: Store) -> dict[str, Any]:
    report = coverage_report(store)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for row in report["functions"]:
        function = dict(row["function"])
        function["metadata"] = {
            **function.get("metadata", {}),
            "coverage_verdict": row["verdict"],
            "overlap": row["overlap"],
        }
        nodes[function["id"]] = function
        if not row["carriers"]:
            stub_id = f"uncovered:{function['id']}"
            nodes[stub_id] = {
                "id": stub_id,
                "node_type": "gap",
                "name": "UNGedeckt",
                "scope": function.get("scope"),
                "metadata": {"coverage_verdict": "uncovered"},
            }
            edges.append(
                {
                    "source_id": stub_id,
                    "relation": "does_not_cover",
                    "target_id": function["id"],
                    "status": "uncovered",
                    "mode": "diff",
                    "confidence": 1.0,
                    "metadata": {},
                }
            )
        for carrier in row["carriers"]:
            nodes[carrier["id"]] = carrier
        for edge in row["actual"] + row["desired"]:
            edges.append(edge)
    return {"nodes": list(nodes.values()), "edges": edges, "summary": report["summary"]}


def document_graph(store: Store, view: str = "control") -> dict[str, Any]:
    all_nodes = {node["id"]: node for node in store.nodes()}
    all_edges = store.resolved_edges()
    if view == "tree":
        types = {
            "system",
            "directory",
            "control_document",
            "policy_document",
            "decision_document",
            "documentation",
        }
        relations = {"contains", "enters_at", "points_to"}
    else:
        core_types = {
            "entrypoint",
            "control_document",
            "policy_document",
            "decision_document",
        }
        core = {
            node_id
            for node_id, node in all_nodes.items()
            if node["node_type"] in core_types
        }
        pointer_edges = [
            edge
            for edge in all_edges
            if edge["source_id"] in core
            and edge["relation"] in {"points_to", "references"}
        ]
        selected_ids = core | {
            edge["target_id"] for edge in pointer_edges
        }
        entry_directories = {
            node_id
            for node_id, node in all_nodes.items()
            if node["node_type"] == "directory"
            and node.get("metadata", {}).get("entry_directory")
        }
        selected_ids |= entry_directories
        structural_edges = [
            edge
            for edge in all_edges
            if edge["relation"] in {"contains", "enters_at"}
            and edge["target_id"] in selected_ids
        ]
        selected_ids |= {
            edge["source_id"] for edge in structural_edges
        }
        edges = [
            edge
            for edge in pointer_edges + structural_edges
            if edge["source_id"] in selected_ids
            and edge["target_id"] in selected_ids
        ]
        return {
            "nodes": [
                node
                for node_id, node in all_nodes.items()
                if node_id in selected_ids
            ],
            "edges": edges,
            "view": view,
        }
    selected = {
        node_id: node
        for node_id, node in all_nodes.items()
        if node["node_type"] in types
    }
    edges = [
        edge
        for edge in all_edges
        if edge["relation"] in relations
        and edge["source_id"] in selected
        and edge["target_id"] in selected
    ]
    connected = {
        node_id
        for edge in edges
        for node_id in (edge["source_id"], edge["target_id"])
    }
    nodes = [
        node
        for node_id, node in selected.items()
        if node_id in connected
        or node["node_type"]
        in {
            "control_document",
            "policy_document",
            "decision_document",
            "entrypoint",
        }
    ]
    return {"nodes": nodes, "edges": edges, "view": view}


def data_graph(store: Store) -> dict[str, Any]:
    all_nodes = {node["id"]: node for node in store.nodes()}
    types = {
        "registry",
        "registry_collection",
        "database",
        "database_table",
        "data_actor",
        "entrypoint",
        "cloud_provider",
        "credential_reference",
        "mapping_point",
    }
    selected = {
        node_id
        for node_id, node in all_nodes.items()
        if node["node_type"] in types
        or (
            node["node_type"] == "directory"
            and node.get("metadata", {}).get("cloud_mode")
        )
    }
    relations = {
        "contains_collection",
        "contains_table",
        "fills",
        "reads",
        "accesses",
        "connects_to",
        "mirrors_to",
        "uses_credential",
    }
    edges = [
        edge
        for edge in store.resolved_edges()
        if edge["relation"] in relations
        and edge["source_id"] in selected
        and edge["target_id"] in selected
    ]
    connected = {
        node_id
        for edge in edges
        for node_id in (edge["source_id"], edge["target_id"])
    }
    return {
        "nodes": [
            all_nodes[node_id]
            for node_id in selected
            if node_id in connected
            or all_nodes[node_id]["node_type"]
            in {"registry", "database", "directory"}
        ],
        "edges": edges,
        "view": "data",
    }


def deployment_graph(store: Store) -> dict[str, Any]:
    report = deployment_report(store)
    nodes: dict[str, dict[str, Any]] = {}
    edges = []
    relevant = {
        "exposes",
        "protected_by",
        "probed_by",
        "hosted_by",
        "priced_by",
        "offered_by",
        "documents",
    }
    all_nodes = {node["id"]: node for node in store.nodes()}
    verdict_by_server = {
        row["server"]["id"]: row["verdict"] for row in report["servers"]
    }
    for edge in store.resolved_edges():
        if edge["relation"] not in relevant:
            continue
        edges.append(edge)
        for node_id in (edge["source_id"], edge["target_id"]):
            if node_id in all_nodes:
                nodes[node_id] = dict(all_nodes[node_id])
    for server_id, verdict in verdict_by_server.items():
        if server_id in all_nodes:
            nodes[server_id] = dict(all_nodes[server_id])
            nodes[server_id]["metadata"] = {
                **nodes[server_id].get("metadata", {}),
                "purpose_verdict": verdict,
            }
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "view": "deployment",
        "summary": report["summary"],
    }


def purpose_graph(store: Store) -> dict[str, Any]:
    report = purpose_report(store)
    node_map = {node["id"]: node for node in store.nodes()}
    relations = {"has_purpose", "requires_function", "carries"}
    selected_ids = {
        item["id"]
        for row in report["purposes"]
        for item in (row["target"], row["purpose"])
        if item
    }
    selected_ids |= {
        criterion["function"]["id"]
        for row in report["purposes"]
        for criterion in row["criteria"]
        if criterion.get("function")
    }
    edges = [
        edge
        for edge in store.resolved_edges()
        if edge["relation"] in relations
        and edge["source_id"] in selected_ids
        and edge["target_id"] in selected_ids
    ]
    return {
        "nodes": [node_map[node_id] for node_id in selected_ids if node_id in node_map],
        "edges": edges,
        "view": "purpose",
        "report": report,
    }


def llm_trace_graph(store: Store) -> dict[str, Any]:
    types = {"actor", "session", "entrypoint", "artifact_reference", "carrier"}
    relations = {
        "participates_in",
        "enters_at",
        "invoked",
        "returned_from",
        "references",
        "used",
    }
    return _subgraph(store, types, relations, "llm-traces")


def llm_action_graph(store: Store) -> dict[str, Any]:
    types = {
        "actor",
        "entrypoint",
        "carrier",
        "server_surface",
        "system_connection",
        "handoff",
        "system_instance",
    }
    relations = {
        "enters_at",
        "invoked",
        "returned_from",
        "used",
        "probed_by",
        "connects_via",
        "reaches",
        "hands_off",
        "assigned_to",
    }
    return _subgraph(store, types, relations, "llm-actions")


def function_path_graph(store: Store) -> dict[str, Any]:
    types = {
        "actor",
        "entrypoint",
        "carrier",
        "function",
        "handoff",
        "system_instance",
        "artifact",
        "artifact_reference",
        "output",
        "interface",
    }
    relations = {
        "enters_at",
        "carries",
        "invoked",
        "used",
        "produces",
        "delivers_to",
        "hands_off",
        "assigned_to",
        "points_to",
        "exposes_interface",
        "alternative_to",
    }
    return _subgraph(store, types, relations, "function-paths")


def _subgraph(
    store: Store, types: set[str], relations: set[str], view: str
) -> dict[str, Any]:
    all_nodes = {node["id"]: node for node in store.nodes()}
    edges = [
        edge
        for edge in store.resolved_edges()
        if edge["relation"] in relations
        and all_nodes.get(edge["source_id"], {}).get("node_type") in types
        and all_nodes.get(edge["target_id"], {}).get("node_type") in types
    ]
    connected = {
        node_id
        for edge in edges
        for node_id in (edge["source_id"], edge["target_id"])
    }
    nodes = [
        node
        for node_id, node in all_nodes.items()
        if node_id in connected
        or (node["node_type"] == "actor" and node["node_type"] in types)
    ]
    return {"nodes": nodes, "edges": edges, "view": view}


def _filter_system(
    graph: dict[str, Any], system_id: str | None
) -> dict[str, Any]:
    if not system_id or system_id in {"all", "*"}:
        return graph
    selected = {
        node["id"]
        for node in graph.get("nodes", [])
        if node.get("metadata", {}).get("origin_system") == system_id
        or (
            node.get("node_type") == "system_instance"
            and node.get("id") == f"system-instance:{system_id}"
        )
    }
    node_map = {node["id"]: node for node in graph.get("nodes", [])}
    boundary_ids = {
        node_id
        for node_id in selected
        if node_map.get(node_id, {}).get("metadata", {}).get(
            "crosses_system_boundary"
        )
    }
    for edge in graph.get("edges", []):
        if edge["source_id"] in boundary_ids or edge["target_id"] in boundary_ids:
            for node_id in (edge["source_id"], edge["target_id"]):
                if node_map.get(node_id, {}).get("node_type") == "system_instance":
                    selected.add(node_id)
    filtered = dict(graph)
    filtered["nodes"] = [
        node for node in graph.get("nodes", []) if node["id"] in selected
    ]
    filtered["edges"] = [
        edge
        for edge in graph.get("edges", [])
        if edge["source_id"] in selected and edge["target_id"] in selected
    ]
    if "summary" in graph:
        summary: dict[str, int] = {}
        for node in filtered["nodes"]:
            metadata = node.get("metadata", {})
            verdict = metadata.get("coverage_verdict") or metadata.get(
                "purpose_verdict"
            )
            if verdict:
                summary[verdict] = summary.get(verdict, 0) + 1
            if metadata.get("overlap"):
                summary["overlap"] = summary.get("overlap", 0) + 1
        filtered["summary"] = summary
    if "report" in graph:
        report = graph["report"]
        if "resources" in report:
            rows = [
                row
                for row in report.get("resources", [])
                if row.get("resource", {}).get("id") in selected
            ]
            resource_summary: dict[str, int] = {}
            for row in rows:
                readiness = row.get("resource", {}).get("metadata", {}).get(
                    "llm_readiness", "unproven"
                )
                resource_summary[readiness] = (
                    resource_summary.get(readiness, 0) + 1
                )
            filtered["report"] = {
                **report,
                "resources": rows,
                "summary": resource_summary,
            }
        else:
            filtered["report"] = {
                "purposes": [
                    row
                    for row in report.get("purposes", [])
                    if row.get("target", {}).get("id") in selected
                ]
            }
    if "levels" in graph:
        filtered["levels"] = [
            level for level in graph.get("levels", []) if level.get("id") == system_id
        ]
    filtered["system_filter"] = system_id
    return filtered


def render_ascii(graph: dict[str, Any]) -> str:
    names = {node["id"]: node["name"] for node in graph["nodes"]}
    lines = ["SYSTEM MAP", "=========="]
    for edge in sorted(
        graph["edges"], key=lambda item: (item["source_id"], item["relation"], item["target_id"])
    ):
        status = edge.get("diff_status") or (
            f"{edge.get('mode', 'actual')}/{edge.get('status', '')}"
        )
        lines.append(
            f"[{names.get(edge['source_id'], edge['source_id'])}]"
            f" --{edge['relation']}:{status}--> "
            f"[{names.get(edge['target_id'], edge['target_id'])}]"
        )
    if not graph["edges"]:
        lines.append("(no edges)")
    return "\n".join(lines) + "\n"


def render_mermaid(graph: dict[str, Any]) -> str:
    lines = ["flowchart LR"]
    node_alias: dict[str, str] = {}
    for index, node in enumerate(graph["nodes"], start=1):
        alias = f"N{index}"
        node_alias[node["id"]] = alias
        label = str(node["name"]).replace('"', "'")
        lines.append(f'  {alias}["{label}"]')
        verdict = node.get("metadata", {}).get("coverage_verdict")
        if verdict:
            lines.append(f"  class {alias} {verdict}")
    for edge in graph["edges"]:
        source = node_alias.get(edge["source_id"])
        target = node_alias.get(edge["target_id"])
        if source and target:
            status = edge.get("diff_status") or (
                f"{edge.get('mode', 'actual')}/{edge.get('status', '')}"
            )
            label = f"{edge['relation']}:{status}"
            lines.append(f"  {source} -->|{label}| {target}")
    lines.extend(
        [
            "  classDef full fill:#d8f3dc,stroke:#2d6a4f",
            "  classDef partial fill:#fff3bf,stroke:#a66f00,stroke-dasharray: 5 5",
            "  classDef uncovered fill:#ffe3e3,stroke:#c92a2a",
            "  classDef negative fill:#ff8787,stroke:#7f0000,stroke-width:3px",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(graph: dict[str, Any], title: str = "system-explorer") -> str:
    payload = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(title)}</title>
<style>
body{{font:14px system-ui;margin:0;background:#111827;color:#e5e7eb}}
header{{padding:14px 20px;background:#0f172a}} #map{{width:100%;height:78vh}}
.node{{stroke:#e5e7eb;stroke-width:1.2}} .carrier{{fill:#2563eb}} .function{{fill:#15803d}}
.gap{{fill:#dc2626}} .edge{{stroke:#94a3b8;stroke-width:1.4}} text{{fill:#f8fafc;font-size:12px}}
aside{{padding:10px 20px;background:#1f2937;white-space:pre-wrap}}
</style></head><body><header><b>{html.escape(title)}</b> — drag nodes; click for evidence metadata</header>
<svg id="map"></svg><aside id="details">Select a node or edge.</aside>
<script id="graph-data" type="application/json">{payload}</script>
<script>
const g=JSON.parse(document.getElementById('graph-data').textContent), svg=document.getElementById('map');
const W=svg.clientWidth||1200,H=svg.clientHeight||700,NS='http://www.w3.org/2000/svg';
const nodes=g.nodes.map((n,i)=>Object.assign(n,{{x:90+(i%6)*(W-180)/5,y:80+Math.floor(i/6)*110}}));
const byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
for(const e of g.edges){{let a=byId[e.source_id],b=byId[e.target_id];if(!a||!b)continue;
 let l=document.createElementNS(NS,'line');l.setAttribute('x1',a.x);l.setAttribute('y1',a.y);
 l.setAttribute('x2',b.x);l.setAttribute('y2',b.y);l.setAttribute('class','edge');
 if(['negative','uncovered'].includes(e.status))l.style.stroke='#ef4444';l.onclick=()=>details(e);svg.appendChild(l);}}
for(const n of nodes){{let grp=document.createElementNS(NS,'g'),c=document.createElementNS(NS,'circle'),
 t=document.createElementNS(NS,'text');c.setAttribute('cx',n.x);c.setAttribute('cy',n.y);c.setAttribute('r',24);
 c.setAttribute('class','node '+n.node_type);t.setAttribute('x',n.x+30);t.setAttribute('y',n.y+4);
 t.textContent=n.name;c.onclick=()=>details(n);grp.append(c,t);svg.appendChild(grp);
 let drag=false;c.onpointerdown=()=>drag=true;c.onpointerup=()=>drag=false;c.onpointermove=e=>{{if(drag){{c.setAttribute('cx',e.offsetX);c.setAttribute('cy',e.offsetY);t.setAttribute('x',e.offsetX+30);t.setAttribute('y',e.offsetY+4)}}}};}}
function details(v){{document.getElementById('details').textContent=JSON.stringify(v,null,2)}}
</script></body></html>"""


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return edge["source_id"], edge["relation"], edge["target_id"]
