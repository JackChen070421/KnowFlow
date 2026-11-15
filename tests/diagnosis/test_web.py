"""Dashboard integration checks on the existing synthetic diagnosis fixture only."""

import json
import threading
from http.client import HTTPConnection

import pytest
from test_recommend import knowledge_base

from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.knowledge.pipeline import write_knowledge_base
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

        for path in ("/teacher", "/student", "/styles.css", "/app.js", "/charts.js"):
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
