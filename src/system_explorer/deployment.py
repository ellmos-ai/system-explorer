from __future__ import annotations

import json
import hashlib
import ipaddress
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .store import Store
from .util import sha256_file, stable_id


PUBLIC_CONTROL_KEYS = (
    "tls",
    "authentication",
    "firewall_default_deny",
    "rate_limit",
    "logging",
    "secret_storage",
)


def register_deployment(config: dict[str, Any], store: Store) -> dict[str, int]:
    """Register declared servers, public surfaces, controls, costs, and purposes."""
    stats = {
        "servers": 0,
        "surfaces": 0,
        "controls": 0,
        "purposes": 0,
        "provider_documents": 0,
        "cost_offers": 0,
    }
    evidence_id = _config_evidence(config, store)
    adapter_id: str | None = None
    for item in config.get("provider_sources", []):
        provider_key = str(item["provider"])
        provider_id = f"cloud:{provider_key}"
        store.add_node(
            "cloud_provider",
            item.get("provider_name", provider_key),
            node_id=provider_id,
            metadata={"cloud_symbol": "☁"},
        )
        document_id = f"provider-document:{stable_id(provider_key, str(item['url']))}"
        store.add_node(
            "provider_document",
            item.get("name", item.get("document_type", "Provider document")),
            node_id=document_id,
            scope=provider_key,
            metadata={
                **item,
                "refresh_required": True,
                "content_copied": False,
            },
        )
        store.add_edge(
            provider_id,
            "documents",
            document_id,
            status="referenced",
            evidence_id=evidence_id,
        )
        stats["provider_documents"] += 1

    for item in config.get("servers", []):
        server_key = str(item["id"])
        server_id = f"server:{server_key}"
        metadata = {
            key: value
            for key, value in item.items()
            if key not in {"surfaces", "controls", "credentials"}
        }
        metadata["purpose_kind"] = item.get("purpose", "unspecified")
        metadata["location"] = item.get("location", "unknown")
        store.add_node(
            "server",
            item.get("name", server_key),
            node_id=server_id,
            scope=item.get("scope"),
            metadata=metadata,
        )
        stats["servers"] += 1
        provider_key = item.get("provider")
        if provider_key:
            provider_id = f"cloud:{provider_key}"
            store.add_node(
                "cloud_provider",
                str(provider_key),
                node_id=provider_id,
                metadata={"cloud_symbol": "☁"},
            )
            store.add_edge(
                server_id,
                "hosted_by",
                provider_id,
                status="declared",
                evidence_id=evidence_id,
            )
        monthly_cost = item.get("monthly_cost")
        if isinstance(monthly_cost, dict):
            offer_id = (
                "cost-offer:"
                f"{stable_id(server_key, json.dumps(monthly_cost, sort_keys=True))}"
            )
            store.add_node(
                "cost_offer",
                monthly_cost.get(
                    "name", f"{item.get('name', server_key)} monthly cost"
                ),
                node_id=offer_id,
                scope=server_key,
                metadata={
                    **monthly_cost,
                    "time_bound_evidence": True,
                    "refresh_required": True,
                },
            )
            store.add_edge(
                server_id,
                "priced_by",
                offer_id,
                status="observed",
                evidence_id=evidence_id,
            )
            if provider_key:
                store.add_edge(
                    offer_id,
                    "offered_by",
                    f"cloud:{provider_key}",
                    status="observed",
                    evidence_id=evidence_id,
                )
            stats["cost_offers"] += 1

        controls = item.get("controls", {})
        for control_name in PUBLIC_CONTROL_KEYS:
            state = controls.get(control_name)
            control_id = f"security-control:{server_key}:{control_name}"
            store.add_node(
                "security_control",
                control_name.replace("_", " "),
                node_id=control_id,
                scope=server_key,
                metadata={"enabled": state, "control": control_name},
            )
            store.add_edge(
                server_id,
                "protected_by",
                control_id,
                status=_boolean_status(state),
                evidence_id=evidence_id,
                metadata={"control": control_name},
            )
            stats["controls"] += 1

        for index, surface in enumerate(item.get("surfaces", []), start=1):
            surface_key = str(surface.get("id") or f"surface-{index}")
            surface_id = f"server-surface:{server_key}:{surface_key}"
            store.add_node(
                "server_surface",
                surface.get("name", surface.get("url", surface_key)),
                node_id=surface_id,
                scope=server_key,
                metadata=dict(surface),
            )
            store.add_edge(
                server_id,
                "exposes",
                surface_id,
                status=(
                    "reachable"
                    if surface.get("reachable") is True
                    else "blocked"
                    if surface.get("reachable") is False
                    else "unproven"
                ),
                evidence_id=evidence_id,
                metadata={
                    "desired_public": bool(surface.get("desired_public", False)),
                    "vantage": surface.get("vantage", "declared"),
                },
            )
            stats["surfaces"] += 1
            if surface.get("probe_adapter") == "api-prober":
                if adapter_id is None:
                    adapter_id = _register_api_prober(store)
                store.add_edge(
                    surface_id,
                    "probed_by",
                    adapter_id,
                    status="planned",
                    evidence_id=evidence_id,
                    metadata={"authorization_required": True, "passive_only": True},
                )

    for item in config.get("purposes", []):
        purpose_key = str(item["id"])
        target_id = _ensure_target(item, store)
        purpose_id = f"purpose:{purpose_key}"
        store.add_node(
            "purpose",
            item.get("name", purpose_key),
            node_id=purpose_id,
            scope=target_id,
            metadata={"description": item.get("description", "")},
        )
        store.add_edge(
            target_id,
            "has_purpose",
            purpose_id,
            mode="desired",
            status="required",
            evidence_id=evidence_id,
        )
        for criterion in item.get("criteria", []):
            function_key = str(criterion["function"])
            function_id = f"function:{function_key}"
            store.add_node(
                "function",
                criterion.get("name", function_key),
                node_id=function_id,
                metadata={"criterion_for": purpose_key},
            )
            store.add_edge(
                purpose_id,
                "requires_function",
                function_id,
                mode="desired",
                status=criterion.get("required", "full"),
                evidence_id=evidence_id,
            )
        stats["purposes"] += 1
    store.commit()
    return stats


def deployment_report(store: Store) -> dict[str, Any]:
    edges = store.resolved_edges()
    nodes = {node["id"]: node for node in store.nodes()}
    by_source: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        by_source.setdefault(edge["source_id"], []).append(edge)
    rows = []
    for server in store.nodes("server"):
        server_edges = by_source.get(server["id"], [])
        surfaces = [
            nodes[edge["target_id"]]
            for edge in server_edges
            if edge["relation"] == "exposes" and edge["target_id"] in nodes
        ]
        control_nodes = [
            nodes[edge["target_id"]]
            for edge in server_edges
            if edge["relation"] == "protected_by" and edge["target_id"] in nodes
        ]
        verdict, reasons = _server_verdict(server, surfaces, control_nodes)
        rows.append(
            {
                "server": server,
                "verdict": verdict,
                "reasons": reasons,
                "surfaces": surfaces,
                "controls": control_nodes,
                "cost_comparison": compare_costs(server.get("metadata", {})),
                "api_prober_plan": api_prober_plan(server, surfaces),
            }
        )
    summary = {key: 0 for key in ("full", "partial", "negative", "unproven")}
    for row in rows:
        summary[row["verdict"]] += 1
    return {"servers": rows, "summary": summary}


def refresh_provider_sources(
    config: dict[str, Any],
    store: Store,
    *,
    timeout_seconds: float = 15,
    max_bytes: int = 2_000_000,
) -> dict[str, Any]:
    """Fetch public provider documents without retaining their contents."""
    results = []
    fetcher_id = store.add_node(
        "carrier",
        "Provider document fetcher",
        node_id="carrier:provider-document-fetcher",
        metadata={
            "carrier_kind": "module",
            "read_only": True,
            "content_retained": False,
        },
    )
    opener = build_opener(_SafeRedirectHandler())
    for item in config.get("provider_sources", []):
        url = str(item["url"])
        _validate_public_url(url)
        request = Request(
            url,
            headers={"User-Agent": "system-explorer/0.1 provider-document-refresh"},
            method="GET",
        )
        with opener.open(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            _validate_public_url(final_url)
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError(f"Provider document exceeds max_bytes: {url}")
            digest = hashlib.sha256(body).hexdigest()
            evidence_id = store.add_evidence(
                uri=final_url,
                source_kind="provider-document-fetch",
                sha256=digest,
                confidence=1.0,
                sensitivity="public",
                metadata={
                    "requested_url": url,
                    "http_status": response.status,
                    "content_type": response.headers.get("Content-Type"),
                    "content_length": len(body),
                    "content_retained": False,
                },
            )
            provider_key = str(item["provider"])
            document_id = f"provider-document:{stable_id(provider_key, url)}"
            store.add_node(
                "provider_document",
                item.get("name", item.get("document_type", "Provider document")),
                node_id=document_id,
                scope=provider_key,
                metadata={
                    **item,
                    "last_refresh_sha256": digest,
                    "last_refresh_status": response.status,
                    "content_retained": False,
                },
            )
            store.add_edge(
                document_id,
                "observed_by",
                fetcher_id,
                status="refreshed",
                evidence_id=evidence_id,
            )
            results.append(
                {
                    "provider": provider_key,
                    "url": url,
                    "final_url": final_url,
                    "status": response.status,
                    "sha256": digest,
                    "bytes": len(body),
                }
            )
    store.commit()
    return {"documents": results, "content_retained": False}


def purpose_report(store: Store, target: str | None = None) -> dict[str, Any]:
    nodes = {node["id"]: node for node in store.nodes()}
    edges = store.resolved_edges()
    actual_by_target: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        if edge["relation"] == "carries" and edge["mode"] == "actual":
            actual_by_target.setdefault(edge["source_id"], []).append(edge)
    rows = []
    for purpose_edge in edges:
        if purpose_edge["relation"] != "has_purpose":
            continue
        target_id = purpose_edge["source_id"]
        if target and target not in {target_id, nodes.get(target_id, {}).get("name")}:
            continue
        purpose_id = purpose_edge["target_id"]
        criteria = [
            edge
            for edge in edges
            if edge["source_id"] == purpose_id
            and edge["relation"] == "requires_function"
        ]
        actual = {
            edge["target_id"]: edge for edge in actual_by_target.get(target_id, [])
        }
        criterion_rows = []
        for criterion in criteria:
            observation = actual.get(criterion["target_id"])
            status = observation["status"] if observation else "uncovered"
            criterion_rows.append(
                {
                    "function": nodes.get(criterion["target_id"]),
                    "required": criterion["status"],
                    "actual": status,
                    "verdict": _criterion_verdict(status),
                }
            )
        verdict = _aggregate_purpose([row["verdict"] for row in criterion_rows])
        rows.append(
            {
                "target": nodes.get(target_id, {"id": target_id, "name": target_id}),
                "purpose": nodes.get(purpose_id, {"id": purpose_id, "name": purpose_id}),
                "verdict": verdict,
                "criteria": criterion_rows,
            }
        )
    return {"purposes": rows}


def import_apiprober_export(
    path: Path, store: Store, *, server_id: str
) -> dict[str, int]:
    """Import ApiProber JSON as referenced observations, never raw response bodies."""
    value = json.loads(path.read_text(encoding="utf-8"))
    evidence_id = store.add_evidence(
        uri=path.resolve().as_uri(),
        source_kind="apiprober-export",
        sha256=sha256_file(path),
        sensitivity="sensitive",
        metadata={"raw_response_retained": False},
    )
    server_node_id = server_id if server_id.startswith("server:") else f"server:{server_id}"
    if server_node_id not in {node["id"] for node in store.nodes()}:
        store.add_node("server", server_id, node_id=server_node_id)
    endpoints = _extract_endpoints(value)
    for index, endpoint in enumerate(endpoints, start=1):
        path_value = str(endpoint.get("path") or endpoint.get("url") or f"endpoint-{index}")
        endpoint_id = f"server-surface:{stable_id(server_node_id, path_value)}"
        status_code = endpoint.get("status_code", endpoint.get("status"))
        reachable = isinstance(status_code, int) and status_code < 500
        store.add_node(
            "server_surface",
            path_value,
            node_id=endpoint_id,
            scope=server_node_id,
            metadata={
                "path": path_value,
                "method": endpoint.get("method", "GET"),
                "status_code": status_code,
                "reachable": reachable,
                "source": "api-prober",
                "raw_response_retained": False,
            },
        )
        store.add_edge(
            server_node_id,
            "exposes",
            endpoint_id,
            status="reachable" if reachable else "unproven",
            evidence_id=evidence_id,
            metadata={"vantage": "api-prober"},
        )
    adapter_id = _register_api_prober(store)
    store.add_edge(adapter_id, "observed", server_node_id, status="completed", evidence_id=evidence_id)
    store.commit()
    return {"endpoints": len(endpoints), "evidence": 1}


def api_prober_plan(
    server: dict[str, Any], surfaces: list[dict[str, Any]]
) -> dict[str, Any]:
    targets = [
        surface["metadata"].get("url")
        for surface in surfaces
        if surface.get("metadata", {}).get("url")
        and surface.get("metadata", {}).get("probe_adapter") == "api-prober"
    ]
    return {
        "adapter": "api-prober",
        "authorized_targets_only": True,
        "passive_only": True,
        "respect_robots_txt": True,
        "default_delay_ms": 500,
        "commands": [
            f"python api_prober.py probe {target} --delay-ms 500"
            for target in targets
        ],
        "import_command": (
            f"system-explorer import-apiprober <export.json> --server {server['id']}"
        ),
    }


def compare_costs(metadata: dict[str, Any]) -> dict[str, Any] | None:
    cloud = metadata.get("monthly_cost")
    local = metadata.get("local_alternative")
    if not isinstance(cloud, dict) or not isinstance(local, dict):
        return None
    cloud_amount = float(cloud.get("amount", 0))
    amortization_months = max(int(local.get("amortization_months", 36)), 1)
    local_monthly = (
        float(local.get("monthly_cost", 0))
        + float(local.get("one_time_cost", 0)) / amortization_months
        + float(local.get("energy_kwh_month", 0))
        * float(local.get("energy_price_per_kwh", 0))
        + float(local.get("admin_hours_month", 0))
        * float(local.get("admin_hour_rate", 0))
    )
    delta = round(cloud_amount - local_monthly, 2)
    verified = cloud.get("verified") is True
    return {
        "currency": cloud.get("currency", local.get("currency", "EUR")),
        "cloud_monthly": round(cloud_amount, 2),
        "local_effective_monthly": round(local_monthly, 2),
        "delta_cloud_minus_local": delta,
        "lower_cost": (
            "unproven"
            if not verified
            else "local"
            if delta > 0
            else "cloud"
            if delta < 0
            else "equal"
        ),
        "evidence_status": "verified" if verified else "unproven",
        "decision_note": "Cost is only one criterion; availability, latency, maintenance, and exposure remain separate.",
        "source": cloud.get("source"),
        "source_effective_at": cloud.get("effective_at"),
    }


def _server_verdict(
    server: dict[str, Any],
    surfaces: list[dict[str, Any]],
    control_nodes: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    purpose = server.get("metadata", {}).get("purpose_kind")
    controls = {
        node["metadata"].get("control"): node["metadata"].get("enabled")
        for node in control_nodes
    }
    reasons: list[str] = []
    if purpose == "private-server":
        reachable = [
            item
            for item in surfaces
            if item.get("metadata", {}).get("reachable") is True
            and not item.get("metadata", {}).get("desired_public", False)
        ]
        if reachable:
            return "negative", ["A private server has an observed public surface."]
        externally_blocked = [
            item
            for item in surfaces
            if item.get("metadata", {}).get("reachable") is False
            and item.get("metadata", {}).get("vantage") == "external"
        ]
        if surfaces and len(externally_blocked) == len(surfaces):
            return "full", ["All declared public surfaces are blocked from an external vantage."]
        if controls.get("firewall_default_deny") is True:
            reasons.append("Default-deny is declared, but external blocking is not fully evidenced.")
            return "partial", reasons
        return "unproven", ["No complete external-vantage evidence proves public access is blocked."]

    public_surfaces = [
        item
        for item in surfaces
        if item.get("metadata", {}).get("desired_public", False)
    ]
    if purpose in {"part-open-service", "public-service"} or public_surfaces:
        missing = [key for key in PUBLIC_CONTROL_KEYS if controls.get(key) is not True]
        if controls.get("tls") is False or controls.get("authentication") is False:
            return "negative", ["A public surface lacks TLS or authentication."]
        if missing:
            return "partial", [f"Missing or unproven controls: {', '.join(missing)}."]
        return "full", ["All baseline controls for declared public surfaces are evidenced."]
    return "unproven", ["No supported server purpose was declared."]


def _ensure_target(item: dict[str, Any], store: Store) -> str:
    target = str(item["target"])
    existing = {node["id"]: node for node in store.nodes()}
    if target in existing:
        return target
    target_id = target if ":" in target else f"carrier:{target}"
    store.add_node(
        item.get("target_type", "carrier"),
        item.get("target_name", target),
        node_id=target_id,
        metadata={"carrier_kind": item.get("target_kind", "module")},
    )
    return target_id


def _register_api_prober(store: Store) -> str:
    adapter_id = "carrier:api-prober"
    store.add_node(
        "carrier",
        "ApiProber",
        node_id=adapter_id,
        metadata={
            "carrier_kind": "module",
            "purpose": "authorized passive REST surface discovery",
            "rate_limited": True,
            "respects_robots_txt": True,
            "credential_values_retained": False,
        },
    )
    return adapter_id


def _config_evidence(config: dict[str, Any], store: Store) -> str | None:
    path_value = config.get("_config_path")
    if not path_value:
        return None
    path = Path(path_value)
    return store.add_evidence(
        uri=path.resolve().as_uri(),
        source_kind="deployment-config",
        sha256=sha256_file(path),
        sensitivity=config.get("privacy", {}).get("sensitivity", "user-local"),
    )


def _extract_endpoints(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("endpoints", "routes", "observations", "results"):
        candidate = value.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    paths = value.get("paths")
    if isinstance(paths, dict):
        return [
            {"path": path, "method": method.upper()}
            for path, methods in paths.items()
            for method in (methods.keys() if isinstance(methods, dict) else ["GET"])
        ]
    return []


def _boolean_status(value: Any) -> str:
    return "enabled" if value is True else "disabled" if value is False else "unproven"


def _criterion_verdict(status: str) -> str:
    if status in {"full", "fulfilled", "observed"}:
        return "full"
    if status in {"negative", "contradicted"}:
        return "negative"
    if status in {"partial", "under"}:
        return "partial"
    return "uncovered"


def _aggregate_purpose(values: list[str]) -> str:
    if not values:
        return "unproven"
    if "negative" in values:
        return "negative"
    if "uncovered" in values:
        return "uncovered"
    if "partial" in values:
        return "partial"
    return "full"


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Only public HTTP(S) provider URLs are allowed: {url}")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in provider URLs are not allowed")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
        }
    except socket.gaierror as exc:
        raise ValueError(f"Provider hostname cannot be resolved: {parsed.hostname}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"Private or special provider address is blocked: {address}")


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
