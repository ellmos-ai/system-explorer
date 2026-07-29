from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .assessment import assess
from .config import database_path
from .coverage import coverage_report
from .maps import graph_view
from .proposals import propose
from .registry import find_documents, register_path
from .store import Store


def serve(config: dict[str, Any], host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = _handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"system-explorer UI: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _handler(config: dict[str, Any]) -> type[BaseHTTPRequestHandler]:
    db_path = database_path(config)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = files("system_explorer").joinpath("web/index.html").read_bytes()
                self._send(HTTPStatus.OK, body, "text/html; charset=utf-8")
                return
            if parsed.path == "/favicon.ico":
                self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
                return
            if parsed.path == "/api/map":
                view = parse_qs(parsed.query).get("view", ["coverage"])[0]
                try:
                    with Store(db_path) as store:
                        self._json(HTTPStatus.OK, graph_view(store, view))
                except ValueError as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if parsed.path == "/api/coverage":
                with Store(db_path) as store:
                    self._json(HTTPStatus.OK, coverage_report(store))
                return
            if parsed.path == "/api/assessment":
                with Store(db_path) as store:
                    self._json(HTTPStatus.OK, assess(store))
                return
            if parsed.path == "/api/evidence":
                with Store(db_path) as store:
                    self._json(HTTPStatus.OK, {"evidence": store.evidence()})
                return
            if parsed.path == "/api/documents":
                query = parse_qs(parsed.query)
                with Store(db_path) as store:
                    self._json(
                        HTTPStatus.OK,
                        {
                            "documents": find_documents(
                                store,
                                role=query.get("role", [None])[0],
                                name=query.get("name", [None])[0],
                            )
                        },
                    )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/api/proposals", "/api/register"}:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 100_000)
                value = json.loads(self.rfile.read(length))
                with Store(db_path) as store:
                    if self.path == "/api/proposals":
                        prompt = value.get("prompt", "")
                        if not isinstance(prompt, str) or not prompt.strip():
                            raise ValueError("prompt is required")
                        result = propose(prompt, store)
                    else:
                        path_value = value.get("path")
                        if not isinstance(path_value, str) or not path_value.strip():
                            raise ValueError("path is required")
                        result = register_path(
                            Path(path_value),
                            value.get("role", "documentation"),
                            store,
                            config=config,
                            name=value.get("name"),
                            entry=bool(value.get("entry", False)),
                        )
                    self._json(HTTPStatus.OK, result)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _json(self, status: HTTPStatus, value: Any) -> None:
            self._send(
                status,
                json.dumps(value, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler
