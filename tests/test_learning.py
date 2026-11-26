import copy
import json
import threading
from http.client import HTTPConnection
from types import SimpleNamespace

import pytest

from knowflow.web.learning import LearningStore
from knowflow.web.learning_math import grade_answer
from knowflow.web.server import create_server


@pytest.fixture
def learning(tmp_path):
    state = {"knowledge_id": "K-02", "status": "insufficient_evidence", "evidence_count": 1}
    snapshot = {
        "meta": {"dataset_id": "synthetic-learning"},
        "students": [{"student_id": "S001"}, {"student_id": "S002"}],
        "profiles": {
            "N01": {
                "S001": {"knowledge_states": [state]},
                "S002": {"knowledge_states": [copy.deepcopy(state)]},
            }
        },
        "records": [
            {
                "record_id": "R-1",
                "student_id": "S001",
                "node_id": "N01",
                "material_id": "M-001",
                "attempted": True,
                "score": 0,
                "max_score": 1,
            }
        ],
        "knowledge_base": {"materials": []},
    }
    knowledge = {
        "knowledge": [{"knowledge_id": "K-02", "name": "去括号"}],
        "materials": [
            {
                "material_id": "M-001",
                "material_type": "assessment",
                "body": "化简 2x+x",
                "answer_key": "3x",
                "explanation": "合并同类项。",
                "options_json": None,
            },
            {
                "material_id": "M-002",
                "material_type": "assessment",
                "body": "计算 2+3",
                "answer_key": "5",
                "explanation": "加法。",
                "options_json": None,
            },
        ],
        "qmatrix": [
            {"material_id": "M-001", "knowledge_id": "K-02", "weight": 1},
            {"material_id": "M-002", "knowledge_id": "K-02", "weight": 1},
        ],
    }
    return LearningStore(tmp_path / "learning", snapshot, knowledge)


def submit(store, qid, answer, sid="S001", rid="request-123"):
    return store.answer(sid, "N01", {"question_id": qid, "answer": answer, "request_id": rid})


@pytest.mark.parametrize("score", [0, 1, 2])
def test_probe_first_attempt_controls_transition(learning, score):
    lesson = learning.start("S001", "N01", "K-02")
    assert len(lesson["probe_questions"]) == 2
    assert all("answer" not in q and "explanation" not in q for q in lesson["probe_questions"])
    answers = ["B", "B"]
    for i, q in enumerate(lesson["probe_questions"]):
        r = submit(learning, q["question_id"], answers[i] if i < score else "A", rid=f"request-{i}")
    assert r["probe_result"]["correct"] == score
    card = learning.list_for("S001", "N01")["cards"][0]
    assert card["mode"] == "learn"
    assert card["status"] == ("ready" if score == 2 else "needs_practice")
    submit(learning, lesson["probe_questions"][0]["question_id"], "B", rid="retry-001")
    assert learning.start("S001", "N01", "K-02")["probe_result"]["correct"] == score
    assert (
        learning.snapshot["profiles"]["N01"]["S001"]["knowledge_states"][0]["status"]
        == "insufficient_evidence"
    )


def test_probe_no_zero_for_blank_and_idempotency(learning):
    lesson = learning.start("S001", "N01", "K-02")
    q = lesson["probe_questions"][0]
    with pytest.raises(ValueError):
        submit(learning, q["question_id"], "")
    assert learning.start("S001", "N01", "K-02")["probe_result"] is None
    first = submit(learning, q["question_id"], "A")
    assert submit(learning, q["question_id"], "A") == first
    assert len(learning._load("S001")["attempts"]) == 1
    with pytest.raises(ValueError):
        submit(learning, q["question_id"], "B")


def test_favorites_persist_and_are_isolated(learning):
    learning.favorite("S001", "N01", "M-001", True)
    reopened = LearningStore(learning.root, learning.snapshot, learning.knowledge)
    assert len(reopened.list_for("S001", "N01")["favorites"]) == 1
    assert not reopened.list_for("S002", "N01")["favorites"]
    assert not reopened.list_for("S002", "N01")["mistakes"]
    reopened.favorite("S001", "N01", "M-001", False)
    assert not reopened.list_for("S001", "N01")["favorites"]


def test_wrong_notebook_correction_keeps_history(learning):
    assert learning.list_for("S001", "N01")["mistakes"][0]["origin"] == "history"
    learning.question("S001", "N01", "M-001")
    r = submit(learning, "M-001", "x+x+x")
    assert r["correct"] is True and r["independent"] is False
    assert learning.list_for("S001", "N01")["mistakes"][0]["resolved"] is True
    submit(learning, "M-001", "2x", rid="second-123")
    assert learning.list_for("S001", "N01")["mistakes"][0]["resolved"] is False


def test_persisted_learning_contract(learning):
    from pathlib import Path

    from jsonschema import Draft202012Validator

    lesson = learning.start("S001", "N01", "K-02")
    submit(learning, lesson["probe_questions"][0]["question_id"], "A")
    learning.favorite("S001", "N01", "M-001", True)
    schema = json.loads(
        (Path(__file__).parents[1] / "schemas/output/learning_state.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(learning._load("S001"))


@pytest.mark.parametrize(
    "answer,key,expected",
    [
        ("x+x+x", "3x", True),
        ("2x", "3x", False),
        ("x=3", "3", True),
        ("1/2", "0.5", True),
        ("-2x+6", "2(3-x)", True),
        ("3x²y", "x*x*3*y", True),
        ("5>x", "x<5", True),
        ("5≥x>1", "1<x≤5", True),
        ("x<5", "x≤5", False),
        ("3y+2x=17", "2x+3y=17", True),
        ("我觉得是3", "3", None),
        ('__import__("os").system("id")', "3", None),
        ("2**1000000", "3", None),
        ("鸡3只", "鸡7只，兔3只", None),
    ],
)
def test_exact_bounded_math(answer, key, expected):
    assert grade_answer({"answer": key}, answer) is expected


class Model:
    model = "test-model"

    def __init__(self, mismatch=False):
        self.calls = []
        self.mismatch = mismatch

    def complete(self, system, user):
        self.calls.append((system, user))
        if len(self.calls) % 2 == 0:
            return json.dumps({"answers": ["D", "D"] if self.mismatch else ["A", "B"]})
        return json.dumps(
            {
                "questions": [
                    {
                        "prompt": "化简 3(x+2)",
                        "options": ["3x+6", "3x+2", "x+6", "3x-6"],
                        "answer": "A",
                        "explanation": "分配律。",
                    },
                    {
                        "prompt": "化简 2(y-3)",
                        "options": ["2y-3", "2y-6", "y-6", "2y+6"],
                        "answer": "B",
                        "explanation": "分配律。",
                    },
                ]
            }
        )


def ready(learning):
    learning.snapshot["profiles"]["N01"]["S001"]["knowledge_states"][0]["status"] = "likely_weak"
    lesson = learning.start("S001", "N01", "K-02")
    learning.mark_read("S001", "N01", "K-02")
    for i, q in enumerate(lesson["bank_questions"]):
        submit(
            learning,
            q["question_id"],
            "5" if q["question_id"] == "M-002" else "3x",
            rid=f"bank-{i}-123",
        )


def test_ai_uses_real_client_contract_and_independent_verification(learning):
    ready(learning)
    model = Model()
    lesson = learning.generate("S001", "N01", "K-02", client=model)
    assert len(model.calls) == 2 and len(lesson["ai_questions"]) == 2
    assert "S001" not in str(model.calls) and "化简 2x+x" not in str(model.calls)
    assert '"answer"' not in model.calls[1][1]
    assert all(q["source"] == "ai" and "answer" not in q for q in lesson["ai_questions"])
    with pytest.raises(ValueError):
        learning.generate("S001", "N01", "K-02", client=model)


def test_ai_mismatch_is_not_published_or_replaced_by_fake_questions(learning):
    ready(learning)
    with pytest.raises(ValueError, match="复核"):
        learning.generate("S001", "N01", "K-02", client=Model(True))
    assert not learning.start("S001", "N01", "K-02")["ai_questions"]
    assert not learning.generating


def test_student_http_access_and_csrf(learning, tmp_path, monkeypatch):
    monkeypatch.setattr("knowflow.web.server.repo_root", lambda: tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    (run / "knowledge_base.json").write_text(json.dumps(learning.knowledge), encoding="utf-8")
    account = SimpleNamespace(role="student", student_id="S001", username="S001")
    auth = SimpleNamespace(resolve=lambda token: account)
    # The server uses the authentication store's session resolver.
    auth.account_for_session = lambda token: account
    server = create_server(run, learning.snapshot, port=0, auth=auth)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def call(method, path, body=None, header=True):
        c = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if header:
            headers["X-KnowFlow-Learning"] = "1"
        c.request(method, path, json.dumps(body) if body else None, headers)
        r = c.getresponse()
        result = (r.status, r.read())
        c.close()
        return result

    try:
        assert call("GET", "/api/learning?student_id=S002&node_id=N01")[0] == 403
        body = {"student_id": "S002", "node_id": "N01", "knowledge_id": "K-02"}
        assert call("POST", "/api/learning/start", body)[0] == 403
        body["student_id"] = "S001"
        assert call("POST", "/api/learning/start", body, False)[0] == 403
        code, payload = call("POST", "/api/learning/start", body)
        assert code == 200
        assert all("answer" not in q for q in json.loads(payload)["probe_questions"])
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
