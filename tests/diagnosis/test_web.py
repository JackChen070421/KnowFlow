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
