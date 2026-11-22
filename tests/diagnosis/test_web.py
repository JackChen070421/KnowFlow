"""Dashboard integration checks on the existing synthetic diagnosis fixture only."""

import json
import threading
from http.client import HTTPConnection

import pytest
from test_llm import SequenceClient
from test_recommend import knowledge_base

from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.knowledge.pipeline import write_knowledge_base
from knowflow.llm.chat import answer_question
from knowflow.llm.settings_store import MANAGED_KEYS
from knowflow.recommend.pipeline import recommend_run
from knowflow.web.data import load_dashboard, read_json, record_summary, write_json
from knowflow.web.server import create_server


@pytest.fixture()
def dashboard_run(tmp_path, bundle):
    run = tmp_path / "web-demo"
    knowledge = knowledge_base(bundle)
    for objective in knowledge["objectives"]:
        objective["unit"] = "synthetic unit"
    write_knowledge_base(knowledge, run / "knowledge_base.json")
    run_diagnosis(bundle, run / "diagnosis", node_id="all")
    report = recommend_run(
        run=str(run / "diagnosis"),
        knowledge=str(run / "knowledge_base.json"),
        node="all",
        output=str(run / "recommendations"),
    )
    assert report["gate"] == "pass"
    return run


def test_completion_score_and_coverage_have_different_denominators():
    rows = [
        {"assigned": True, "attempted": True, "score": 1, "max_score": 2},
        {"assigned": True, "attempted": True, "score": 0, "max_score": 2},
        {"assigned": True, "attempted": True, "score": None, "max_score": 2},
        {"assigned": True, "attempted": False, "score": None, "max_score": 2},
        {"assigned": False, "attempted": False, "score": None, "max_score": 2},
    ]
    summary = record_summary(rows)
    assert summary["completion"] == 3 / 4
    assert summary["score_ratio"] == 1 / 4  # Partial credit is retained.
    assert summary["pending"] == 1
    assert summary["not_attempted"] == 1
    assert summary["graded"] == 2


def test_absence_is_not_zero_or_unfinished():
    summary = record_summary([])
    assert summary["completion"] is None
    assert summary["score_ratio"] is None
    assert summary["assigned"] == 0


def test_dashboard_excludes_answers_and_preserves_node_scope(dashboard_run, bundle):
    data = load_dashboard(dashboard_run)
    serialized = json.dumps(data)
    assert "synthetic-private-answer" not in serialized
    assert "synthetic-private-steps" not in serialized
    assert "answer_key" not in serialized
    assert "record_sources" not in serialized
    assert len(data["students"]) == len(bundle["students"])
    assert set(data["profiles"]) == {n["node_id"] for n in bundle["nodes"]}
    for nid, profiles in data["profiles"].items():
        for sid, profile in profiles.items():
            assert profile["node_id"] == nid
            assert data["recommendations"][nid][sid]["node_id"] == nid
            expected = record_summary(
                [r for r in bundle["records"] if r["node_id"] == nid and r["student_id"] == sid]
            )
            assert data["stats"][nid][sid] == expected
    assert set(data["meta"]["validation"].values()) == {"pass"}


def test_changed_profile_cannot_be_presented_as_verified(dashboard_run):
    path = next((dashboard_run / "diagnosis/nodes/N02/students").glob("*.json"))
    data = read_json(path)
    data["coverage"]["ratio"] = 0.1234567
    write_json(path, data)
    with pytest.raises(ValueError, match="复算校验"):
        load_dashboard(dashboard_run)


def test_different_valid_knowledge_versions_are_rejected(dashboard_run):
    path = dashboard_run / "knowledge_base.json"
    data = read_json(path)
    data["materials"][0]["title"] = "different synthetic revision"
    write_json(path, data)
    with pytest.raises(ValueError, match="同一个版本"):
        load_dashboard(dashboard_run)


def test_local_server_routes_and_explicit_evidence(dashboard_run):
    data = load_dashboard(dashboard_run)
    server = create_server(dashboard_run, data, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:

        def request(path, host=None):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("GET", path, headers={"Host": host} if host else {})
            response = connection.getresponse()
            body = response.read()
            status, headers = response.status, dict(response.getheaders())
            connection.close()
            return status, headers, body

        for path in ("/teacher", "/student", "/styles.css", "/app.js", "/charts.js", "/analytics.mjs"):
            status, _, body = request(path)
            assert status == 200 and body
        status, headers, body = request("/api/snapshot")
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert b"synthetic-private-answer" not in body
        assert "Access-Control-Allow-Origin" not in headers
        assert request("/api/snapshot", "untrusted.example")[0] == 403
        for path in (
            "/.git/config",
            "/../README.md",
            "/%2e%2e/README.md",
            "/api/material/../../README.md",
            "/api/evidence/unknown",
        ):
            assert request(path)[0] == 404
        rid = data["records"][0]["record_id"]
        status, _, body = request("/api/evidence/" + rid)
        assert status == 200
        assert json.loads(body)["local_only"] is True
        assert b"synthetic-private-answer" in body
        assert (
            request("/api/material/" + data["knowledge_base"]["materials"][0]["material_id"])[0]
            == 200
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_settings_endpoint_is_local_and_csrf_protected(dashboard_run, tmp_path, monkeypatch):
    for key in MANAGED_KEYS:
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("KNOWFLOW_LLM_ENABLED", "false")
    data = load_dashboard(dashboard_run)
    env_file = tmp_path / ".env"
    server = create_server(dashboard_run, data, port=0, settings_path=env_file)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:

        def call(method, path, body=None, headers=None, host=None):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            all_headers = dict(headers or {})
            if host:
                all_headers["Host"] = host
            connection.request(method, path, body=body, headers=all_headers)
            response = connection.getresponse()
            payload = response.read()
            status = response.status
            connection.close()
            return status, payload

        status, payload = call("GET", "/api/settings/llm")
        assert status == 200
        assert json.loads(payload)["enabled"] is False

        body = json.dumps(
            {"enabled": True, "provider": "deepseek", "api_key": "sk-test-only"}
        ).encode()
        assert call("POST", "/api/settings/llm", body, {"Content-Type": "application/json"})[0] == 403
        assert (
            call(
                "POST",
                "/api/settings/llm",
                body,
                {"Content-Type": "application/json", "X-KnowFlow-Settings": "1"},
                host="untrusted.example",
            )[0]
            == 403
        )
        status, payload = call(
            "POST",
            "/api/settings/llm",
            body,
            {"Content-Type": "application/json", "X-KnowFlow-Settings": "1"},
        )
        assert status == 200
        assert json.loads(payload)["enabled"] is True
        assert b"sk-test-only" not in payload
        assert "KNOWFLOW_LLM_API_KEY=sk-test-only" in env_file.read_text(encoding="utf-8")

        status, payload = call("GET", "/api/settings/llm")
        assert status == 200
        assert json.loads(payload)["api_key_set"] is True
        assert b"sk-test-only" not in payload
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_settings_errors_return_json_instead_of_dropping_the_connection(
    dashboard_run, tmp_path, monkeypatch
):
    data = load_dashboard(dashboard_run)
    server = create_server(dashboard_run, data, port=0, settings_path=tmp_path / ".env")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:

        def call(method, path, body=None, headers=None):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            payload = response.read()
            status = response.status
            connection.close()
            return status, payload

        def write_failure(payload, path=None):
            raise RuntimeError("disk full")

        monkeypatch.setattr("knowflow.web.server.save_llm_settings", write_failure)
        body = json.dumps(
            {"enabled": True, "provider": "deepseek", "api_key": "sk-x"}
        ).encode()
        status, payload = call(
            "POST",
            "/api/settings/llm",
            body,
            {"Content-Type": "application/json", "X-KnowFlow-Settings": "1"},
        )
        assert status == 500
        assert "保存失败" in json.loads(payload)["error"]
        assert call("GET", "/teacher")[0] == 200  # the socket is still usable

        def read_failure():
            raise RuntimeError("bad env")

        monkeypatch.setattr("knowflow.web.server.read_llm_settings", read_failure)
        status, payload = call("GET", "/api/settings/llm")
        assert status == 500
        assert "读取设置失败" in json.loads(payload)["error"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_chat_falls_back_to_rules_without_a_client(dashboard_run, monkeypatch):
    monkeypatch.setattr("knowflow.llm.chat.build_client", lambda settings: None)
    data = load_dashboard(dashboard_run)
    result = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
    )
    assert result["source"] == "rules"
    assert "S002" in result["answer"]
    assert "synthetic-private-answer" not in json.dumps(result, ensure_ascii=False)


def test_chat_rejects_fabricated_numbers_and_falls_back(dashboard_run, monkeypatch):
    data = load_dashboard(dashboard_run)
    client = SequenceClient(["S002 的班级共有 999 人需要补课。"])
    result = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
        client=client,
    )
    assert result["source"] == "rules"
    assert "999" not in result["answer"]
    assert "无法核对" in (result.get("note") or "")
    assert client.calls == 2


def test_chat_accepts_rounded_numbers_and_small_ordinals(dashboard_run):
    data = load_dashboard(dashboard_run)

    def rounded(user: str) -> str:
        payload = user.split("FACTS（唯一可用信息）：\n", 1)[1].split("\n\n用户问题：", 1)[0]
        facts = json.loads(payload)
        student = facts["student"]
        percent = round(student["coverage"]["ratio"] * 100)
        return f"{student['id']} 的观测覆盖约 {percent}%，建议先补 3 个知识点。"

    result = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
        client=SequenceClient([rounded]),
    )
    assert result["source"] == "llm"


def test_chat_retries_with_feedback_before_falling_back(dashboard_run):
    data = load_dashboard(dashboard_run)

    def grounded(user: str) -> str:
        payload = user.split("FACTS（唯一可用信息）：\n", 1)[1].split("\n\n用户问题：", 1)[0]
        facts = json.loads(payload)
        student = facts.get("student", {}).get("id") or facts["class"]["id"]
        knowledge = facts["knowledge"][0]["id"] if facts.get("knowledge") else "课程要求"
        return f"{student} 目前优先关注 {knowledge}；具体材料见学习建议。"

    client = SequenceClient(["S002 共有 999 人。", grounded])
    result = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
        client=client,
    )
    assert result["source"] == "llm"
    assert client.calls == 2


def test_chat_accepts_grounded_answer_from_client(dashboard_run):
    data = load_dashboard(dashboard_run)

    def grounded(user: str) -> str:
        payload = user.split("FACTS（唯一可用信息）：\n", 1)[1].split("\n\n用户问题：", 1)[0]
        facts = json.loads(payload)
        student = facts.get("student", {}).get("id") or facts["class"]["id"]
        knowledge = facts["knowledge"][0]["id"] if facts.get("knowledge") else "课程要求"
        return f"{student} 目前优先关注 {knowledge}；具体材料与验证标准见学习建议。"

    result = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
        client=SequenceClient([grounded]),
    )
    assert result["source"] == "llm"
    assert result["citations"]


def test_chat_modes_are_explainable_and_differ(dashboard_run, monkeypatch):
    monkeypatch.setattr("knowflow.llm.chat.build_client", lambda settings: None)
    data = load_dashboard(dashboard_run)
    concise = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
        mode="concise",
    )
    evidence = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
        mode="evidence",
    )
    assert concise["source"] == evidence["source"] == "rules"
    assert "S002" in concise["answer"]
    assert "M-" not in concise["answer"]
    assert "结论：" in evidence["answer"] and "依据：" in evidence["answer"]
    for result, mode in ((concise, "concise"), (evidence, "evidence")):
        trace = result["trace"]
        assert trace["mode"] == mode
        assert trace["steps"] and trace["evidence"]
        assert "reasoning" not in trace
        assert trace["guard"]["numbers_checked"] is True
        assert trace["note"].startswith("展示事实卡")


def test_chat_evidence_mode_requires_structure(dashboard_run):
    data = load_dashboard(dashboard_run)

    def unstructured(user: str) -> str:
        payload = user.split("FACTS（唯一可用信息）：\n", 1)[1].split("\n\n用户问题：", 1)[0]
        facts = json.loads(payload)
        student = facts.get("student", {}).get("id") or facts["class"]["id"]
        return f"{student} 先补观测。"

    def structured(user: str) -> str:
        payload = user.split("FACTS（唯一可用信息）：\n", 1)[1].split("\n\n用户问题：", 1)[0]
        facts = json.loads(payload)
        student = facts.get("student", {}).get("id") or facts["class"]["id"]
        knowledge = facts["knowledge"][0]["id"] if facts.get("knowledge") else "课程要求"
        return f"结论：{student} 先补 {knowledge}。\n依据：当前数据只有该知识点的基础信息。"

    client = SequenceClient([unstructured, structured])
    result = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
        client=client,
        mode="evidence",
    )
    assert result["source"] == "llm"
    assert client.calls == 2
    assert "结论" in result["answer"] and "依据" in result["answer"]


def test_chat_rejects_unknown_mode(dashboard_run):
    data = load_dashboard(dashboard_run)
    with pytest.raises(ValueError, match="concise 或 evidence"):
        answer_question(
            snapshot=data,
            message="S002 现在最需要补什么？",
            context={"node_id": "N02"},
            mode="verbose",
        )


def test_chat_reports_model_call_failure(dashboard_run):
    data = load_dashboard(dashboard_run)

    class BrokenClient:
        provider = "fake"
        model = "fake-model"

        def complete(self, system: str, user: str) -> str:
            raise RuntimeError("timeout")

    result = answer_question(
        snapshot=data,
        message="S002 现在最需要补什么？",
        context={"node_id": "N02", "group_id": "G1", "student_id": "S002"},
        client=BrokenClient(),
    )
    assert result["source"] == "rules"
    assert "调用不通" in (result.get("note") or "")


def test_chat_endpoint_is_local_and_validates_input(dashboard_run, monkeypatch):
    monkeypatch.setattr("knowflow.llm.chat.build_client", lambda settings: None)
    data = load_dashboard(dashboard_run)
    server = create_server(dashboard_run, data, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:

        def call(body, headers=None):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request(
                "POST", "/api/chat", body=body, headers=headers or {}
            )
            response = connection.getresponse()
            payload = response.read()
            status = response.status
            connection.close()
            return status, payload

        body = json.dumps(
            {
                "message": "S002 现在最需要补什么？",
                "context": {"node_id": "N02", "group_id": "G1", "student_id": "S002"},
            }
        ).encode()
        assert call(body, {"Content-Type": "application/json"})[0] == 403
        status, payload = call(
            body,
            {"Content-Type": "application/json", "X-KnowFlow-Chat": "1"},
        )
        assert status == 200
        answer = json.loads(payload)
        assert answer["source"] == "rules"
        assert b"synthetic-private-answer" not in payload

        empty = json.dumps({"message": ""}).encode()
        status, _ = call(
            empty, {"Content-Type": "application/json", "X-KnowFlow-Chat": "1"}
        )
        assert status == 400

        evidence = json.dumps(
            {
                "message": "S002 现在最需要补什么？",
                "mode": "evidence",
                "context": {"node_id": "N02", "group_id": "G1", "student_id": "S002"},
            }
        ).encode()
        status, payload = call(
            evidence,
            {"Content-Type": "application/json", "X-KnowFlow-Chat": "1"},
        )
        assert status == 200
        assert json.loads(payload)["trace"]["mode"] == "evidence"

        bad_mode = json.dumps({"message": "S002", "mode": "verbose"}).encode()
        status, _ = call(
            bad_mode,
            {"Content-Type": "application/json", "X-KnowFlow-Chat": "1"},
        )
        assert status == 400
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_password_hash_is_salted_and_verifiable():
    from knowflow.web.auth import hash_password, verify_password

    first = hash_password("123456")
    second = hash_password("123456")
    assert first["salt"] != second["salt"]
    assert first["password_hash"] != second["password_hash"]
    assert verify_password("123456", first["salt"], first["password_hash"])
    assert not verify_password("123457", first["salt"], first["password_hash"])
    assert not verify_password("", "", "")


def test_login_is_required_and_students_only_receive_their_own_data(dashboard_run, tmp_path):
    from knowflow.web.auth import AuthStore

    data = load_dashboard(dashboard_run)
    student_id = data["students"][0]["student_id"]
    auth = AuthStore(tmp_path / "users.json", student_id)
    assert auth.created is True
    server = create_server(dashboard_run, data, port=0, auth=auth)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def call(method, path, payload=None, headers=None, cookie=None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        all_headers = dict(headers or {})
        if cookie:
            all_headers["Cookie"] = cookie
        body = None
        if payload is not None:
            body = json.dumps(payload)
            all_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=body, headers=all_headers)
        response = connection.getresponse()
        raw = response.read()
        result = (response.status, dict(response.getheaders()), raw)
        connection.close()
        return result

    def login(username, password, header=True):
        headers = {"X-KnowFlow-Login": "1"} if header else {}
        return call(
            "POST",
            "/api/login",
            {"username": username, "password": password},
            headers,
        )

    try:
        # Anonymous requests never reach the workspace or its data.
        assert call("GET", "/api/snapshot")[0] == 401
        status, headers, _ = call("GET", "/teacher")
        assert status == 302 and headers["Location"] == "/login"
        assert call("GET", "/login")[0] == 200

        # Login must come from the local page, with a real password.
        assert call("POST", "/api/login", {"username": "teacher", "password": "123456"})[0] == 403
        assert login("teacher", "wrong-password")[0] == 401

        status, headers, raw = login(student_id, "123456")
        assert status == 200
        set_cookie = headers["Set-Cookie"]
        assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie
        cookie = set_cookie.split(";")[0]
        assert json.loads(raw)["redirect"] == "/student"

        status, _, raw = call("GET", "/api/snapshot", cookie=cookie)
        assert status == 200
        scoped = json.loads(raw)
        assert scoped["meta"]["viewer"]["role"] == "student"
        assert [s["student_id"] for s in scoped["students"]] == [student_id]
        for people in scoped["profiles"].values():
            assert list(people) == [student_id]
        assert {r["student_id"] for r in scoped["records"]} <= {student_id}
        assert scoped["quality"] is None
        assert scoped["reviews"] is None
        assert scoped["classes"], "class aggregates stay available to students"

        # A student may read only their own raw answer evidence.
        other = next(r for r in data["records"] if r["student_id"] != student_id)
        assert call("GET", "/api/evidence/" + other["record_id"], cookie=cookie)[0] == 403
        own = next(r for r in data["records"] if r["student_id"] == student_id)
        assert call("GET", "/api/evidence/" + own["record_id"], cookie=cookie)[0] == 200

        # Teacher-only surfaces stay closed.
        assert call("GET", "/api/settings/llm", cookie=cookie)[0] == 403
        adjustment = {
            "event_type": "teacher_adjustment",
            "student_id": student_id,
            "node_id": data["nodes"][0]["node_id"],
            "plan_item_id": "PL-unknown",
            "action": "lock",
            "reason": "synthetic",
        }
        assert (
            call(
                "POST",
                "/api/feedback",
                adjustment,
                {"X-KnowFlow-Feedback": "1"},
                cookie=cookie,
            )[0]
            == 403
        )

        # The teacher account still sees the whole dataset.
        status, headers, raw = login("teacher", "123456")
        teacher_cookie = headers["Set-Cookie"].split(";")[0]
        status, _, raw = call("GET", "/api/snapshot", cookie=teacher_cookie)
        assert status == 200
        full = json.loads(raw)
        assert len(full["students"]) == len(data["students"])
        assert full["meta"]["viewer"]["role"] == "teacher"
        assert call("GET", "/teacher", cookie=teacher_cookie)[0] == 200

        # Logout revokes the session for later requests.
        assert (
            call(
                "POST",
                "/api/logout",
                {},
                {"X-KnowFlow-Logout": "1"},
                cookie=teacher_cookie,
            )[0]
            == 200
        )
        assert call("GET", "/api/snapshot", cookie=teacher_cookie)[0] == 401
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_profile_preferences_and_password_flow(dashboard_run, tmp_path):
    from knowflow.web.auth import AuthStore

    data = load_dashboard(dashboard_run)
    student_id = data["students"][0]["student_id"]
    auth = AuthStore(tmp_path / "users.json", student_id)
    server = create_server(dashboard_run, data, port=0, auth=auth)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def call(method, path, payload=None, headers=None, cookie=None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        all_headers = dict(headers or {})
        if cookie:
            all_headers["Cookie"] = cookie
        body = None
        if payload is not None:
            body = json.dumps(payload)
            all_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=body, headers=all_headers)
        response = connection.getresponse()
        raw = response.read()
        result = (response.status, dict(response.getheaders()), raw)
        connection.close()
        return result

    def login(username, password):
        return call(
            "POST",
            "/api/login",
            {"username": username, "password": password},
            {"X-KnowFlow-Login": "1"},
        )

    try:
        assert call("GET", "/api/profile")[0] == 401
        status, headers, _ = login("teacher", "123456")
        assert status == 200
        cookie = headers["Set-Cookie"].split(";")[0]

        status, _, raw = call("GET", "/api/profile", cookie=cookie)
        assert status == 200
        payload = json.loads(raw)
        assert payload["account"]["role"] == "teacher"
        assert payload["preferences"]["home_view"] == "overview"
        assert payload["thresholds"] == {
            "coverage_sufficient": 10,
            "coverage_missing": 3,
            "mastery_mastered": 85,
            "mastery_weak": 60,
        }

        status, _, raw = call(
            "POST",
            "/api/profile",
            {
                "profile": {
                    "display_name": "王老师",
                    "term": "2026-2027春",
                    "classes": "七年级 1 班",
                    "subject": "数学",
                }
            },
            {"X-KnowFlow-Profile": "1"},
            cookie,
        )
        assert status == 200
        updated = json.loads(raw)
        assert updated["account"]["display_name"] == "王老师"
        assert updated["profile"]["term"] == "2026-2027春"
        assert updated["profile"]["classes"] == "七年级 1 班"

        # invalid profile values are rejected
        assert (
            call(
                "POST",
                "/api/profile",
                {"profile": {"display_name": "   "}},
                {"X-KnowFlow-Profile": "1"},
                cookie,
            )[0]
            == 400
        )
        assert (
            call(
                "POST",
                "/api/profile",
                {"profile": {"term": "2026-2027夏"}},
                {"X-KnowFlow-Profile": "1"},
                cookie,
            )[0]
            == 400
        )

        # preferences + thresholds validation
        assert (
            call(
                "POST",
                "/api/preferences",
                {"preferences": {"tone": "loud"}},
                {"X-KnowFlow-Prefs": "1"},
                cookie,
            )[0]
            == 400
        )
        assert (
            call(
                "POST",
                "/api/preferences",
                {"thresholds": {"coverage_sufficient": 2, "coverage_missing": 5}},
                {"X-KnowFlow-Prefs": "1"},
                cookie,
            )[0]
            == 400
        )
        status, _, raw = call(
            "POST",
            "/api/preferences",
            {
                "preferences": {
                    "tone": "direct",
                    "report_length": "brief",
                    "insufficient": "probe",
                    "home_view": "students",
                },
                "thresholds": {
                    "coverage_sufficient": 12,
                    "coverage_missing": 4,
                    "mastery_mastered": 90,
                    "mastery_weak": 55,
                },
            },
            {"X-KnowFlow-Prefs": "1"},
            cookie,
        )
        assert status == 200
        saved = json.loads(raw)
        assert saved["preferences"]["insufficient"] == "probe"
        assert saved["thresholds"]["mastery_mastered"] == 90

        # password change requires the current password and a long enough new one
        assert (
            call(
                "POST",
                "/api/password",
                {"username": "teacher", "current_password": "wrong", "new_password": "new-pass-123"},
                {"X-KnowFlow-Password": "1"},
                cookie,
            )[0]
            == 400
        )
        assert (
            call(
                "POST",
                "/api/password",
                {"username": "teacher", "current_password": "123456", "new_password": "short"},
                {"X-KnowFlow-Password": "1"},
                cookie,
            )[0]
            == 400
        )
        assert (
            call(
                "POST",
                "/api/password",
                {"username": "teacher", "current_password": "123456", "new_password": "new-pass-123"},
                {"X-KnowFlow-Password": "1"},
                cookie,
            )[0]
            == 200
        )
        assert login("teacher", "123456")[0] == 401
        assert login("teacher", "new-pass-123")[0] == 200

        stored = (tmp_path / "users.json").read_text(encoding="utf-8")
        assert "new-pass-123" not in stored
        assert "123456" not in stored
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_thresholds_drive_the_diagnosis_configuration():
    from knowflow.web.data import diagnosis_config, threshold_config

    config = diagnosis_config(
        {
            "coverage_sufficient": 12,
            "coverage_missing": 5,
            "mastery_mastered": 90,
            "mastery_weak": 55,
        }
    )
    assert config.min_evidence == 5
    assert config.weak_threshold == 0.55
    assert config.mastered_threshold == 0.9
    assert threshold_config(None)["mastery_mastered"] == 85


def test_thresholds_change_mastery_status():
    from knowflow.diagnosis.mastery import DiagnosisConfig, estimate_mastery

    default = estimate_mastery(8, 10, DiagnosisConfig())
    strict = estimate_mastery(8, 10, DiagnosisConfig(weak_threshold=0.6, mastered_threshold=0.85))
    assert default["status"] != strict["status"]
    assert default["status"] in {"likely_mastered", "confirmed_mastered"}
    assert strict["status"] == "mixed_performance"


def test_policy_thresholds_are_read_from_the_teacher_account(tmp_path):
    from knowflow.web.auth import DEFAULT_THRESHOLDS, AuthStore, read_policy_thresholds

    users = tmp_path / "users.json"
    auth = AuthStore(users, "S001")
    assert auth.policy_thresholds() == DEFAULT_THRESHOLDS
    auth.update_preferences(
        "teacher",
        thresholds={
            "coverage_sufficient": 14,
            "coverage_missing": 4,
            "mastery_mastered": 88,
            "mastery_weak": 52,
        },
    )
    stored = read_policy_thresholds(users)
    assert stored["coverage_sufficient"] == 14
    assert stored["mastery_mastered"] == 88
    assert read_policy_thresholds(tmp_path / "missing.json") is None


def test_username_rename_and_password_requires_matching_username(dashboard_run, tmp_path):
    from knowflow.web.auth import AuthStore

    data = load_dashboard(dashboard_run)
    student_id = data["students"][0]["student_id"]
    auth = AuthStore(tmp_path / "users.json", student_id)
    server = create_server(dashboard_run, data, port=0, auth=auth)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def call(method, path, payload=None, headers=None, cookie=None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        all_headers = dict(headers or {})
        if cookie:
            all_headers["Cookie"] = cookie
        body = None
        if payload is not None:
            body = json.dumps(payload)
            all_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=body, headers=all_headers)
        response = connection.getresponse()
        raw = response.read()
        result = (response.status, dict(response.getheaders()), raw)
        connection.close()
        return result

    def login(username, password):
        return call(
            "POST",
            "/api/login",
            {"username": username, "password": password},
            {"X-KnowFlow-Login": "1"},
        )

    try:
        status, headers, _ = login("teacher", "123456")
        assert status == 200
        cookie = headers["Set-Cookie"].split(";")[0]

        # the password form must type the current username
        assert (
            call(
                "POST",
                "/api/password",
                {"current_password": "123456", "new_password": "new-pass-123"},
                {"X-KnowFlow-Password": "1"},
                cookie,
            )[0]
            == 400
        )
        assert (
            call(
                "POST",
                "/api/password",
                {
                    "username": "someone-else",
                    "current_password": "123456",
                    "new_password": "new-pass-123",
                },
                {"X-KnowFlow-Password": "1"},
                cookie,
            )[0]
            == 400
        )

        # rename the account; the existing session follows the new name
        status, _, raw = call(
            "POST",
            "/api/profile",
            {"profile": {"username": "wang", "display_name": "王老师"}},
            {"X-KnowFlow-Profile": "1"},
            cookie,
        )
        assert status == 200
        assert json.loads(raw)["account"]["username"] == "wang"
        status, _, raw = call("GET", "/api/profile", cookie=cookie)
        assert status == 200 and json.loads(raw)["account"]["username"] == "wang"

        # the old name no longer logs in, the new one does
        assert login("teacher", "123456")[0] == 401
        status, headers, _ = login("wang", "123456")
        assert status == 200
        new_cookie = headers["Set-Cookie"].split(";")[0]

        # a taken name is rejected
        assert (
            call(
                "POST",
                "/api/profile",
                {"profile": {"username": "S001"}},
                {"X-KnowFlow-Profile": "1"},
                new_cookie,
            )[0]
            == 400
        )

        # password change with the renamed account
        assert (
            call(
                "POST",
                "/api/password",
                {
                    "username": "wang",
                    "current_password": "123456",
                    "new_password": "new-pass-123",
                },
                {"X-KnowFlow-Password": "1"},
                new_cookie,
            )[0]
            == 200
        )
        assert login("wang", "new-pass-123")[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
