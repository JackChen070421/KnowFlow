"""Loopback-only HTTP adapter; never expose the repository as a static directory."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from knowflow.contracts import repo_root
from knowflow.diagnosis.pipeline import export_evidence
from knowflow.web.data import read_json

STATIC = Path(__file__).with_name("static")
ASSETS = {
    "/app.js": "text/javascript",
    "/charts.js": "text/javascript",
    "/styles.css": "text/css",
    "/favicon.svg": "image/svg+xml",
}


def create_server(run: Path, snapshot: dict, port: int = 8765) -> ThreadingHTTPServer:
    materials = {m["material_id"]: m for m in read_json(run / "knowledge_base.json")["materials"]}
    raw = (repo_root() / "data/raw" / snapshot["meta"]["dataset_id"]).resolve()
    documents = {}
    for mid, material in materials.items():
        source = material.get("source") or ""
        if not source.lower().endswith(".pdf"):
            continue
        candidate = (raw / source).resolve()
        if candidate.is_relative_to(raw) and candidate.is_file():
            documents[mid] = candidate
            material["document_url"] = "/api/document/" + mid
    record_ids = {r["record_id"] for r in snapshot["records"]}
    snapshot_bytes = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Do not log student IDs or raw evidence query strings.
            return

        def respond(self, data: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header(
                "Content-Type",
                content_type + ("; charset=utf-8" if content_type != "application/pdf" else ""),
            )
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def json(self, data: dict, status: int = 200) -> None:
            self.respond(
                json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json", status
            )

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            allowed = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            if self.headers.get("Host") not in allowed:
                self.json({"error": "仅允许本机访问。"}, 403)
                return
            path = unquote(urlsplit(self.path).path)
            if path in ("/", "/teacher", "/student"):
                self.respond((STATIC / "index.html").read_bytes(), "text/html")
            elif path in ASSETS:
                self.respond((STATIC / path[1:]).read_bytes(), ASSETS[path])
            elif path == "/api/snapshot":
                self.respond(snapshot_bytes, "application/json")
            elif (
                path.startswith("/api/document/")
                and path.removeprefix("/api/document/") in documents
            ):
                self.respond(
                    documents[path.removeprefix("/api/document/")].read_bytes(), "application/pdf"
                )
            elif (
                path.startswith("/api/material/")
                and path.removeprefix("/api/material/") in materials
            ):
                self.json(materials[path.removeprefix("/api/material/")])
            elif (
                path.startswith("/api/evidence/")
                and path.removeprefix("/api/evidence/") in record_ids
            ):
                try:
                    target = export_evidence(run / "diagnosis", path.removeprefix("/api/evidence/"))
                    self.json(read_json(target))
                except (ValueError, OSError):
                    self.json({"error": "原始证据文件不可用或已变化，请重新生成展示数据。"}, 409)
            else:
                self.json({"error": "没有找到该页面或资料。"}, 404)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
