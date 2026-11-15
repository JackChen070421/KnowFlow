"""Loopback-only HTTP adapter; never expose the repository as a static directory."""

from __future__ import annotations

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from knowflow.contracts import repo_root
from knowflow.diagnosis.pipeline import export_evidence
from knowflow.llm.chat import answer_question
from knowflow.llm.settings_store import read_llm_settings, save_llm_settings
from knowflow.web.data import read_json

STATIC = Path(__file__).with_name("static")
ASSETS = {
    "/app.js": "text/javascript",
    "/charts.js": "text/javascript",
    "/styles.css": "text/css",
    "/favicon.svg": "image/svg+xml",
}
MAX_SETTINGS_BODY = 8192
MAX_CHAT_BODY = 16384


class LocalHTTPServer(ThreadingHTTPServer):
    """Refuse a second bind on Windows.

    ``allow_reuse_address`` is inherited as True from ``HTTPServer``; on Windows
    that lets a second dashboard share the port, so requests randomly land on
    an older process and hit missing routes. POSIX keeps the reuse flag so a
    restart after TIME_WAIT still works.
    """

    allow_reuse_address = sys.platform != "win32"


def create_server(
    run: Path,
    snapshot: dict,
    port: int = 8765,
    settings_path: Path | None = None,
) -> ThreadingHTTPServer:
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

        def allowed_host(self) -> bool:
            return self.headers.get("Host") in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }

        def do_GET(self):
            if not self.allowed_host():
                self.json({"error": "仅允许本机访问。"}, 403)
                return
            path = unquote(urlsplit(self.path).path)
            if path in ("/", "/teacher", "/student"):
                self.respond((STATIC / "index.html").read_bytes(), "text/html")
            elif path in ASSETS:
                self.respond((STATIC / path[1:]).read_bytes(), ASSETS[path])
            elif path == "/api/snapshot":
                self.respond(snapshot_bytes, "application/json")
            elif path == "/api/settings/llm":
                try:
                    self.json(read_llm_settings())
                except Exception:  # a broken .env must not kill the connection
                    traceback.print_exc()
                    self.json({"error": "读取设置失败：请检查本机 .env 的 LLM 段。"}, 500)
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

        def do_POST(self):
            # Loopback-only, same-origin-only writes. The custom headers force a
            # CORS preflight, which this server never answers, so a random web
            # page cannot silently write settings or ask questions.
            # Drain the body first: answering before reading it makes Windows
            # reset the connection instead of delivering the 4xx.
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_CHAT_BODY:
                self.close_connection = True
                self.json({"error": "请求体过大。"}, 413)
                return
            body = self.rfile.read(length) if length > 0 else b""
            if not self.allowed_host():
                self.json({"error": "仅允许本机访问。"}, 403)
                return
            path = unquote(urlsplit(self.path).path)
            if path not in ("/api/settings/llm", "/api/chat"):
                self.json({"error": "没有找到该接口。"}, 404)
                return
            required_header = (
                "X-KnowFlow-Settings" if path == "/api/settings/llm" else "X-KnowFlow-Chat"
            )
            if self.headers.get(required_header) != "1":
                self.json({"error": "缺少本机请求头，已拒绝。"}, 403)
                return
            content_type = (
                (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            )
            if content_type != "application/json":
                self.json({"error": "请求必须是 application/json。"}, 415)
                return
            if not body:
                self.json({"error": "请求体为空。"}, 400)
                return
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.json({"error": "请求体不是合法 JSON。"}, 400)
                return
            if not isinstance(payload, dict):
                self.json({"error": "请求体必须是 JSON 对象。"}, 400)
                return

            if path == "/api/settings/llm":
                if length > MAX_SETTINGS_BODY:
                    self.json({"error": "请求体过大。"}, 413)
                    return
                try:
                    settings = save_llm_settings(payload, path=settings_path)
                except ValueError as exc:
                    self.json({"error": str(exc)}, 400)
                    return
                except Exception as exc:  # write/permission/parse errors stay HTTP
                    traceback.print_exc()
                    self.json(
                        {"error": f"保存失败（{type(exc).__name__}）：请查看启动窗口日志，"
                         "或手工检查本机 .env 是否可写。"},
                        500,
                    )
                    return
                self.json(settings)
                return

            question = payload.get("message")
            context = payload.get("context") or {}
            if not isinstance(question, str) or not isinstance(context, dict):
                self.json({"error": "message 必须是字符串，context 必须是对象。"}, 400)
                return
            try:
                result = answer_question(snapshot=snapshot, message=question, context=context)
            except ValueError as exc:
                self.json({"error": str(exc)}, 400)
                return
            except Exception:  # never drop the connection on a chat failure
                traceback.print_exc()
                self.json({"error": "回答生成失败，请查看启动窗口日志后重试。"}, 500)
                return
            self.json(result)

    return LocalHTTPServer(("127.0.0.1", port), Handler)
