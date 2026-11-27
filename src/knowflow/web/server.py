"""Loopback-only HTTP adapter; never expose the repository as a static directory.

Every page and API route except the login surface requires a local session. The
snapshot is trimmed per account, so a student browser never receives another
student's profiles, records or recommendations.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from knowflow.contracts import repo_root
from knowflow.diagnosis.pipeline import export_evidence
from knowflow.llm.chat import answer_question
from knowflow.llm.settings_store import read_llm_settings, save_llm_settings, test_llm_connection
from knowflow.web.auth import COOKIE_NAME, Account, AuthStore
from knowflow.web.data import read_json
from knowflow.web.learning import LearningStore
from knowflow.web.training import TrainingStore

STATIC = Path(__file__).with_name("static")
ASSETS = {
    "/app.js": "text/javascript",
    "/login.js": "text/javascript",
    "/charts.js": "text/javascript",
    "/knowledge-map.js": "text/javascript",
    "/course-stories.mjs": "text/javascript",
    "/analytics.mjs": "text/javascript",
    "/explore-labs.mjs": "text/javascript",
    "/explore-more.mjs": "text/javascript",
    "/theme-boot.js": "text/javascript",
    "/map-layout.mjs": "text/javascript",
    "/panel-resize.mjs": "text/javascript",
    "/styles.css": "text/css",
    "/workspace.css": "text/css",
    "/theme.css": "text/css",
    "/motion.css": "text/css",
    "/login.css": "text/css",
    "/knowledge-map.css": "text/css",
    "/panel-resize.css": "text/css",
    "/training.js": "text/javascript",
    "/learning.js": "text/javascript",
    "/learning.css": "text/css",
    "/advice-summary.mjs": "text/javascript",
    "/advice-summary.css": "text/css",
    "/pdf-viewer.js": "text/javascript",
    "/pdf-print.js": "text/javascript",
    "/pdf-print.css": "text/css",
    "/favicon.svg": "image/svg+xml",
}
PUBLIC_PAGES = {"/login"}
SESSION_PAGES = {"/", "/teacher", "/student", "/training-print"}
MAX_SETTINGS_BODY = 8192
MAX_CHAT_BODY = 16384
MAX_LOGIN_BODY = 4096
LOGIN_FAILURE_DELAY = 0.4
OPEN_ACCOUNT = Account("local", "teacher", None, "本机")


def scope_snapshot(snapshot: dict, account: Account) -> dict:
    """Return the part of the validated snapshot this account may see.

    Students get their own profiles, recommendations, records and statistics
    plus class-level aggregates (which carry no per-student rows). The raw
    quality report and the disputed-score review are teacher-only.
    """

    scoped = dict(snapshot)
    meta = dict(snapshot["meta"])
    meta["viewer"] = {
        "username": account.username,
        "role": account.role,
        "student_id": account.student_id,
        "display_name": account.display_name,
    }
    scoped["meta"] = meta
    if account.role != "student":
        return scoped
    sid = account.student_id
    scoped["students"] = [s for s in snapshot["students"] if s["student_id"] == sid]
    for key in ("profiles", "recommendations", "stats"):
        scoped[key] = {
            node_id: {student: value for student, value in people.items() if student == sid}
            for node_id, people in snapshot[key].items()
        }
    scoped["records"] = [r for r in snapshot["records"] if r["student_id"] == sid]
    scoped["quality"] = None
    scoped["reviews"] = None
    scoped["review_meta"] = None
    return scoped


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
    auth: AuthStore | None = None,
    thresholds_provider=None,
) -> ThreadingHTTPServer:
    training = TrainingStore(repo_root() / 'data/training' / snapshot['meta']['dataset_id'], snapshot)
    knowledge_base = read_json(run / "knowledge_base.json")
    materials = {m["material_id"]: m for m in knowledge_base["materials"]}
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
    for item in snapshot["knowledge_base"]["materials"]:
        mid = item["material_id"]
        if mid in documents:
            item["document_url"] = "/api/document/" + mid
    record_ids = {r["record_id"] for r in snapshot["records"]}
    record_owner = {r["record_id"]: r["student_id"] for r in snapshot["records"]}
    learning = LearningStore(repo_root() / 'data/learning' / snapshot['meta']['dataset_id'], snapshot, knowledge_base)
    scoped_cache: dict[str, bytes] = {}

    def snapshot_bytes(account: Account) -> bytes:
        key = account.student_id if account.role == "student" else "teacher"
        if key not in scoped_cache:
            scoped_cache[key] = json.dumps(
                scope_snapshot(snapshot, account), ensure_ascii=False
            ).encode("utf-8")
        return scoped_cache[key]

    def reload_snapshot() -> str:
        from knowflow.web.data import load_dashboard, prepare

        scoped_cache.clear()
        thresholds = thresholds_provider() if thresholds_provider is not None else None
        print(f"[rebuild] preparing {thresholds}", flush=True)
        run = prepare(refresh=True, thresholds=thresholds)
        print(f"[rebuild] validating {run.name}", flush=True)
        fresh = load_dashboard(run)
        snapshot.clear()
        snapshot.update(fresh)
        # The chat reads 课标原文与材料正文 from here; a rebuilt run has new ones.
        knowledge_base.clear()
        knowledge_base.update(read_json(run / "knowledge_base.json"))
        print(f"[rebuild] snapshot updated {run.name}", flush=True)
        return run.name

    def handle_feedback(payload: dict) -> dict:
        from knowflow.diagnosis.pipeline import build_bundle
        from knowflow.feedback import (
            append_event,
            feedback_path,
            load_events,
            make_event,
            plan_snapshot,
            validate_event,
        )
        from knowflow.recommend.catalog import build_catalog, load_knowledge_base
        from knowflow.recommend.pipeline import default_knowledge_path

        event_type = payload.get("event_type")
        sid = payload.get("student_id")
        nid = payload.get("node_id")
        if event_type not in {
            "teacher_adjustment",
            "teacher_comment",
            "student_feedback",
            "supplemental_attempt",
        }:
            raise ValueError("unsupported feedback event type")
        dataset = snapshot["meta"]["dataset_id"]
        bundle, _ = build_bundle(dataset)
        catalog = build_catalog(load_knowledge_base(default_knowledge_path()))
        path = feedback_path(dataset)
        existing = load_events(path)
        rec = (snapshot.get("recommendations") or {}).get(nid, {}).get(sid, {})
        items = rec.get("plan") or []
        plan_item_id = payload.get("plan_item_id")
        item = next((entry for entry in items if entry.get("plan_item_id") == plan_item_id), None)
        if event_type == "teacher_adjustment":
            if item is None:
                raise ValueError("plan item is not in the current recommendation")
            action = payload.get("action")
            fields = {}
            if payload.get("materials"):
                fields["material_ids"] = [
                    value.strip() for value in str(payload["materials"]).split(",") if value.strip()
                ]
            if payload.get("est_minutes"):
                fields["est_minutes"] = int(payload["est_minutes"])
            if payload.get("difficulty"):
                fields["difficulty"] = int(payload["difficulty"])
            event = make_event(
                event_type="teacher_adjustment",
                student_id=sid,
                node_id=nid,
                actor="teacher",
                plan_item_id=item["plan_item_id"],
                plan_version=item.get("plan_version", rec.get("plan_version", 1)),
                action=action,
                issue_id=item["issue_id"],
                knowledge_id=item["knowledge_ids"][0],
                activity_type=item.get("activity_type", "consolidate"),
                payload=fields or None,
                reason=payload.get("reason"),
                snapshot=plan_snapshot(item),
                existing=existing,
            )
        elif event_type == "teacher_comment":
            event = make_event(
                event_type="teacher_comment",
                student_id=sid,
                node_id=nid,
                actor="teacher",
                plan_item_id=plan_item_id,
                issue_id=item["issue_id"] if item else payload.get("issue_id"),
                text=payload.get("text"),
                existing=existing,
            )
        elif event_type == "student_feedback":
            event = make_event(
                event_type="student_feedback",
                student_id=sid,
                node_id=nid,
                actor="student",
                plan_item_id=plan_item_id,
                issue_id=item["issue_id"] if item else payload.get("issue_id"),
                kind=payload.get("kind"),
                rating=payload.get("rating"),
                text=payload.get("text"),
                existing=existing,
            )
        else:
            material_id = payload.get("material_id")
            material = next(
                (m for m in bundle["materials"] if m["material_id"] == material_id), None
            )
            if material is None:
                raise ValueError("material is not an assessment item")
            event = make_event(
                event_type="supplemental_attempt",
                student_id=sid,
                node_id=nid,
                actor="student",
                material_id=material_id,
                score=float(payload.get("score", 0)),
                max_score=material["max_score"],
                submitted_at=payload.get("submitted_at"),
                note=payload.get("note"),
                existing=existing,
            )
        errors = validate_event(event, bundle, catalog)
        if errors:
            raise ValueError("; ".join(errors))
        append_event(path, event)
        run_name = reload_snapshot()
        return {"event": event, "snapshot": run_name}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Do not log student IDs or raw evidence query strings.
            return

        def respond(
            self,
            data: bytes,
            content_type: str,
            status: int = 200,
            cookies: tuple[str, ...] = (),
            extra_headers: dict[str, str] | None = None,
        ) -> None:
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
            for cookie in cookies:
                self.send_header("Set-Cookie", cookie)
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def json(self, data: dict, status: int = 200, **kwargs) -> None:
            self.respond(
                json.dumps(data, ensure_ascii=False).encode("utf-8"),
                "application/json",
                status,
                **kwargs,
            )

        def redirect(self, location: str) -> None:
            self.respond(b"", "text/html", 302, extra_headers={"Location": location})

        def do_HEAD(self):
            self.do_GET()

        def allowed_host(self) -> bool:
            return self.headers.get("Host") in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }

        def session_token(self) -> str | None:
            raw = self.headers.get("Cookie")
            if not raw:
                return None
            jar = SimpleCookie()
            try:
                jar.load(raw)
            except Exception:  # noqa: BLE001 - a malformed cookie is simply anonymous
                return None
            morsel = jar.get(COOKIE_NAME)
            return morsel.value if morsel else None

        def account(self) -> Account | None:
            if auth is None:
                return OPEN_ACCOUNT
            return auth.resolve(self.session_token())

        def require_teacher(self, account: Account) -> bool:
            if account.role == "teacher":
                return True
            self.json({"error": "该操作仅限教师账号。"}, 403)
            return False

        def read_body(self, limit: int) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > limit:
                self.close_connection = True
                self.json({"error": "请求体过大。"}, 413)
                return None
            body = self.rfile.read(length) if length > 0 else b""
            return body

        def do_GET(self):
            if not self.allowed_host():
                self.json({"error": "仅允许本机访问。"}, 403)
                return
            path = unquote(urlsplit(self.path).path)
            if path in PUBLIC_PAGES:
                self.respond((STATIC / "login.html").read_bytes(), "text/html")
                return
            if path in ASSETS:
                self.respond((STATIC / path[1:]).read_bytes(), ASSETS[path])
                return
            if path == "/api/session":
                account = self.account()
                self.json({**account.as_dict(), "auth_enabled": auth is not None} if account else {"authenticated": False, "auth_enabled": auth is not None})
                return
            if path in SESSION_PAGES:
                account = self.account()
                if account is None:
                    # 把 ?motion=1 这类显式动效开关带到登录页：否则未登录访问
                    # /?motion=1 会被 302 抹掉查询串，开关在登录前就失效了。
                    motion = ((parse_qs(urlsplit(self.path).query).get("motion") or [""])[0] or "").lower()
                    allowed = {"1", "on", "true", "yes", "force", "0", "off", "false", "no", "auto", "system"}
                    self.redirect(f"/login?motion={motion}" if motion in allowed else "/login")
                    return
                home = "/teacher" if account.role == "teacher" else "/student"
                if path == "/":
                    self.redirect(home)
                    return
                if path == "/teacher" and account.role != "teacher":
                    self.redirect(home)
                    return
                self.respond((STATIC / ("pdf-print.html" if path == '/training-print' else "index.html")).read_bytes(), "text/html")
                return

            account = self.account()
            if account is None:
                self.json({"error": "请先登录。"}, 401)
                return
            if path == "/api/snapshot":
                self.respond(snapshot_bytes(account), "application/json")
            elif path == "/api/profile":
                if auth is None:
                    self.json({"error": "本机未启用账号，无法保存个人设置。"}, 400)
                    return
                try:
                    self.json(auth.settings_payload(account.username))
                except ValueError as exc:
                    self.json({"error": str(exc)}, 400)
            elif path == '/api/training':
                self.json(training.list_for(account))
            elif path == '/api/learning':
                query = parse_qs(urlsplit(self.path).query)
                sid = query.get('student_id', [account.student_id])[0]
                nid = query.get('node_id', [''])[0]
                if account.role == 'student' and sid != account.student_id:
                    self.json({'error': '只能查看本人的学习空间。'}, 403)
                    return
                try:
                    self.json(learning.list_for(sid, nid))
                except ValueError as exc:
                    self.json({'error': str(exc)}, 400)
            elif any(path.startswith('/api/training/' + route + '/') for route in ('pdf', 'pdf-preview', 'pdf-page')):
                try:
                    identifier = path.rsplit('/', 1)[-1]
                    paper = training.get('papers', identifier)
                    query = parse_qs(urlsplit(self.path).query)
                    answers = query.get('answers', ['0'])[0] == '1'
                    if account.role == 'student' and (answers or paper['status'] != 'approved' or paper['student_id'] not in (None, account.student_id)):
                        self.json({'error': '无权访问该试卷。'}, 403)
                        return
                    pdf = training.pdf(identifier, answers)
                    if path.startswith('/api/training/pdf/'):
                        self.respond(pdf, 'application/pdf', extra_headers={'Content-Disposition': f'attachment; filename="training-{identifier}{"-answers" if answers else ""}.pdf"'})
                    else:
                        import fitz
                        with fitz.open(stream=pdf, filetype='pdf') as doc:
                            if path.startswith('/api/training/pdf-preview/'):
                                self.json({'pages': len(doc), 'title': paper.get('title', '变式训练') + (' · 答案' if answers else ' · 题卷')})
                            else:
                                page = int(query.get('page', ['0'])[0])
                                if not 0 <= page < len(doc):
                                    raise ValueError('PDF 页码超出范围。')
                                self.respond(doc[page].get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png'), 'image/png')
                except ValueError as exc:
                    self.json({'error': str(exc)}, 400)
                except Exception:
                    self.json({'error': 'PDF 生成失败，请确认已安装 training 依赖。'}, 500)
            elif path.startswith('/api/training/scan/'):
                try:
                    scan = training.get('scans', path.rsplit('/', 1)[-1])
                    if account.role == 'student' and scan['student_id'] != account.student_id:
                        self.json({'error': '无权访问该扫描。'}, 403)
                        return
                    page = int(parse_qs(urlsplit(self.path).query).get('page', ['0'])[0])
                    if not 0 <= page < scan['pages']:
                        raise ValueError('扫描页码超出范围。')
                    self.respond((training.root / 'uploads' / (scan['id'] + f'-{page}.png')).read_bytes(), 'image/png')
                except ValueError as exc:
                    self.json({'error': str(exc)}, 400)
            elif path == "/api/settings/llm":
                if not self.require_teacher(account):
                    return
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
                record_id = path.removeprefix("/api/evidence/")
                if account.role == "student" and record_owner.get(record_id) != account.student_id:
                    self.json({"error": "只能查看本人的原始作答。"}, 403)
                    return
                try:
                    target = export_evidence(run / "diagnosis", record_id)
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
            if not self.allowed_host():
                self.json({"error": "仅允许本机访问。"}, 403)
                return
            path = unquote(urlsplit(self.path).path)
            limit = 17 * 1024 * 1024 if path == '/api/training/scan' else MAX_LOGIN_BODY if path == "/api/login" else MAX_CHAT_BODY
            body = self.read_body(limit)
            if body is None:
                return
            if path not in (
                "/api/login",
                "/api/logout",
                "/api/settings/llm",
                "/api/settings/llm/test",
                "/api/chat",
                "/api/feedback",
                "/api/profile",
                "/api/preferences",
                "/api/password",
                "/api/rebuild",
                "/api/training/delete",
                "/api/training/generate",
                "/api/training/approve",
                "/api/training/scan",
                "/api/training/review",
                "/api/learning/start",
                "/api/learning/read",
                "/api/learning/answer",
                "/api/learning/generate",
                "/api/learning/favorite",
                "/api/learning/question",
            ):
                self.json({"error": "没有找到该接口。"}, 404)
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

            if path == "/api/login":
                if self.headers.get("X-KnowFlow-Login") != "1":
                    self.json({"error": "缺少本机请求头，已拒绝。"}, 403)
                    return
                if auth is None:
                    self.json({"error": "本机未启用登录。"}, 400)
                    return
                username = str(payload.get("username") or "")
                password = str(payload.get("password") or "")
                account = auth.authenticate(username, password)
                if account is None:
                    time.sleep(LOGIN_FAILURE_DELAY)
                    self.json({"error": "用户名或密码不正确。"}, 401)
                    return
                token = auth.new_session(account)
                cookie = (
                    f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; "
                    f"Max-Age={auth.ttl}"
                )
                home = "/teacher" if account.role == "teacher" else "/student"
                self.json(
                    {**account.as_dict(), "redirect": home},
                    cookies=(cookie,),
                )
                return

            account = self.account()
            if account is None:
                self.json({"error": "请先登录。"}, 401)
                return

            if path == "/api/logout":
                if self.headers.get("X-KnowFlow-Logout") != "1":
                    self.json({"error": "缺少本机请求头，已拒绝。"}, 403)
                    return
                if auth is not None:
                    auth.drop(self.session_token())
                cleared = f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
                self.json({"ok": True}, cookies=(cleared,))
                return

            if path.startswith('/api/learning/'):
                if self.headers.get('X-KnowFlow-Learning') != '1':
                    self.json({'error': '缺少本机请求头。'}, 403)
                    return
                sid, nid = payload.get('student_id'), payload.get('node_id')
                if account.role == 'student' and sid != account.student_id:
                    self.json({'error': '只能操作本人的学习空间。'}, 403)
                    return
                action = path.rsplit('/', 1)[-1]
                try:
                    if action == 'start':
                        result = learning.start(sid, nid, payload.get('knowledge_id'))
                    elif action == 'read':
                        result = learning.mark_read(sid, nid, payload.get('knowledge_id'))
                    elif action == 'answer':
                        result = learning.answer(sid, nid, payload)
                    elif action == 'generate':
                        result = learning.generate(sid, nid, payload.get('knowledge_id'))
                    elif action == 'favorite':
                        result = learning.favorite(sid, nid, payload.get('question_id'), payload.get('favorite'))
                    else:
                        result = learning.question(sid, nid, payload.get('question_id'))
                    self.json(result)
                except ValueError as exc:
                    self.json({'error': str(exc)}, 400)
                except Exception:
                    traceback.print_exc()
                    self.json({'error': '学习记录操作失败，请重试。'}, 500)
                return

            if path.startswith('/api/training/'):
                if self.headers.get('X-KnowFlow-Training') != '1':
                    self.json({'error': '缺少本机请求头。'}, 403)
                    return
                action = path.rsplit('/', 1)[-1]
                if action != 'scan' and not self.require_teacher(account):
                    return
                if account.role == 'student' and payload.get('student_id') != account.student_id:
                    self.json({'error': '只能上传本人作答。'}, 403)
                    return
                try:
                    if action == 'generate':
                        result = training.generate(payload)
                    elif action == 'delete':
                        result = training.delete(payload.get('paper_id'))
                    elif action == 'approve':
                        result = training.approve(payload.get('paper_id'))
                    elif action == 'scan':
                        result = training.scan(payload)
                    else:
                        result = training.review(payload, account.username)
                    self.json(result)
                except ValueError as exc:
                    self.json({'error': str(exc)}, 400)
                except Exception:
                    self.json({'error': '训练操作失败，请检查 API 配置和 training 依赖后重试。'}, 500)
                return

            required_header = {
                "/api/settings/llm": "X-KnowFlow-Settings",
                "/api/settings/llm/test": "X-KnowFlow-Settings",
                "/api/chat": "X-KnowFlow-Chat",
                "/api/feedback": "X-KnowFlow-Feedback",
                "/api/profile": "X-KnowFlow-Profile",
                "/api/preferences": "X-KnowFlow-Prefs",
                "/api/password": "X-KnowFlow-Password",
                "/api/rebuild": "X-KnowFlow-Rebuild",
            }[path]
            if self.headers.get(required_header) != "1":
                self.json({"error": "缺少本机请求头，已拒绝。"}, 403)
                return

            if path == "/api/feedback":
                event_type = payload.get("event_type")
                if account.role == "student" and (
                    event_type not in {"student_feedback", "supplemental_attempt"}
                    or payload.get("student_id") != account.student_id
                ):
                    self.json({"error": "学生账号只能提交本人的学习反馈。"}, 403)
                    return
                try:
                    self.json(handle_feedback(payload))
                except ValueError as exc:
                    self.json({"error": str(exc)}, 400)
                except Exception as exc:  # local write/recompute errors
                    traceback.print_exc()
                    self.json({"error": f"反馈保存失败（{type(exc).__name__}）。"}, 500)
                return

            if path == "/api/settings/llm/test":
                if not self.require_teacher(account):
                    return
                try:
                    self.json(test_llm_connection(payload))
                except Exception as exc:  # a probe must never drop the connection
                    traceback.print_exc()
                    self.json(
                        {"ok": False, "kind": "unknown", "error": f"测试失败（{type(exc).__name__}）。"},
                        500,
                    )
                return

            if path == "/api/settings/llm":
                if not self.require_teacher(account):
                    return
                if int(self.headers.get("Content-Length") or 0) > MAX_SETTINGS_BODY:
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

            if path == "/api/profile":
                if auth is None:
                    self.json({"error": "本机未启用账号，无法保存个人设置。"}, 400)
                    return
                try:
                    values = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
                    self.json(auth.update_profile(account.username, values))
                except ValueError as exc:
                    self.json({"error": str(exc)}, 400)
                return

            if path == "/api/preferences":
                if auth is None:
                    self.json({"error": "本机未启用账号，无法保存偏好。"}, 400)
                    return
                preferences = payload.get("preferences")
                thresholds = payload.get("thresholds")
                if preferences is not None and not isinstance(preferences, dict):
                    self.json({"error": "偏好格式不正确。"}, 400)
                    return
                if thresholds is not None and not isinstance(thresholds, dict):
                    self.json({"error": "阈值格式不正确。"}, 400)
                    return
                try:
                    self.json(
                        auth.update_preferences(
                            account.username, preferences=preferences, thresholds=thresholds
                        )
                    )
                except ValueError as exc:
                    self.json({"error": str(exc)}, 400)
                return

            if path == "/api/password":
                if auth is None:
                    self.json({"error": "本机未启用账号，无法修改密码。"}, 400)
                    return
                try:
                    auth.change_password(
                        account.username,
                        str(payload.get("current_password") or ""),
                        str(payload.get("new_password") or ""),
                        str(payload.get("username") or ""),
                    )
                except ValueError as exc:
                    self.json({"error": str(exc)}, 400)
                    return
                self.json({"ok": True, "message": "密码已更新，下次登录请使用新密码。"})
                return

            if path == "/api/rebuild":
                if not self.require_teacher(account):
                    return
                try:
                    name = reload_snapshot()
                except ValueError as exc:
                    self.json({"error": str(exc)}, 400)
                    return
                except Exception as exc:  # rebuild errors stay in the connection
                    traceback.print_exc()
                    self.json({"error": f"重建失败（{type(exc).__name__}）。"}, 500)
                    return
                self.json({"ok": True, "snapshot": name})
                return

            question = payload.get("message")
            context = payload.get("context") or {}
            history = payload.get("history")
            mode = payload.get("mode") or "concise"
            if mode not in ("concise", "evidence"):
                self.json({"error": "mode 必须是 concise 或 evidence。"}, 400)
                return
            if not isinstance(question, str) or not isinstance(context, dict):
                self.json({"error": "message 必须是字符串，context 必须是对象。"}, 400)
                return
            if history is not None and not isinstance(history, list):
                self.json({"error": "history 必须是数组。"}, 400)
                return
            if account.role == "student" and account.student_id:
                context = {**context, "student_id": account.student_id}
            preferences = None
            if auth is not None:
                try:
                    preferences = auth.settings_payload(account.username)["preferences"]
                except ValueError:
                    preferences = None
            try:
                result = answer_question(
                    snapshot=scope_snapshot(snapshot, account),
                    message=question,
                    context=context,
                    mode=mode,
                    preferences=preferences,
                    history=history,
                    knowledge=knowledge_base,
                )
            except ValueError as exc:
                self.json({"error": str(exc)}, 400)
                return
            except Exception:  # never drop the connection on a chat failure
                traceback.print_exc()
                self.json({"error": "回答生成失败，请查看启动窗口日志后重试。"}, 500)
                return
            self.json(result)

    return LocalHTTPServer(("127.0.0.1", port), Handler)
