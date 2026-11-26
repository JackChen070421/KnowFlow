"""Optional language-layer checks: summary boundary, guard, retry, wiring."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from test_recommend import knowledge_base, profile

from knowflow.diagnosis.mastery import DiagnosisConfig
from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.llm.client import LLMError, OpenAICompatClient
from knowflow.llm.explain import explain_student
from knowflow.llm.guard import parse_json, response_errors
from knowflow.llm.service import ReasonWriter
from knowflow.llm.summary import build_issue_summary, summary_errors
from knowflow.recommend.pipeline import recommend_run
from knowflow.recommend.validation import allowed_numbers

ANSWER_TEXT = "synthetic-private-answer"


class FakeResponse:
    """Minimal context manager with the one method ``complete`` calls."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self.body


class FakeOpener:
    def __init__(self, *, body: bytes = b"", error: Exception | None = None) -> None:
        self.body = body
        self.error = error
        self.request = None

    def open(self, request, timeout: float = 0):  # noqa: ANN001 - mirrors urllib
        self.request = request
        if self.error is not None:
            raise self.error
        return FakeResponse(self.body)


def client_with(monkeypatch, opener: FakeOpener, *, api_key: str = "sk-test-123456") -> OpenAICompatClient:
    monkeypatch.setattr("knowflow.llm.client._opener", lambda: opener)
    return OpenAICompatClient(
        provider="fake",
        model="fake-model",
        base_url="https://api.example.invalid",
        api_key=api_key,
        temperature=0.0,
        timeout=2.0,
        max_tokens=64,
    )


class SequenceClient:
    """Deterministic fake: replies are strings, or callables taking the user prompt."""

    provider = "fake"
    model = "fake-model"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply(user) if callable(reply) else reply


def smart_reply(user: str) -> str:
    """A response that respects the whitelist, built from the sent summary."""

    summary = json.loads(user)
    facts = summary["facts"]
    ids = summary["constraints"]["allowed_ids"]
    material = next(value for value in ids if value.startswith("M-"))
    issue = summary["ref_id"]
    count = facts["evidence_count"]
    reason = f"{issue} 显示 {count} 次有效评分；先看 {material} 重建方法，再完成同类练习。"
    return json.dumps(
        {
            "kind": "recommendation_reason",
            "ref_id": issue,
            "reason": reason,
            "cited_ids": [issue, material],
        },
        ensure_ascii=False,
    )


def issue_summary(bundle, sid="S002", kid="K-02"):
    student_profile = profile(bundle, sid, config=DiagnosisConfig(min_evidence=2))
    issue = next(item for item in student_profile["issues"] if item["knowledge_id"] == kid)
    state = next(
        item for item in student_profile["knowledge_states"] if item["knowledge_id"] == kid
    )
    ids = {sid, "N02", issue["issue_id"], kid, issue["objective_id"]}
    ids |= set((issue.get("evidence") or {}).get("material_ids") or [])
    summary = build_issue_summary(
        profile=student_profile,
        issue=issue,
        dataset_id=bundle["dataset_id"],
        allowed_numbers=allowed_numbers(issue, state),
        allowed_ids=ids,
    )
    return summary, student_profile, issue


def test_summary_is_schema_valid_and_carries_no_raw_text(bundle):
    summary, _, _ = issue_summary(bundle)
    assert summary_errors(summary) == []
    assert summary["scope"] == "issue"
    assert summary["constraints"]["must_not_infer"]
    assert summary["facts"]["evidence_count"] >= 0
    assert summary["facts"]["status"] in {
        "confirmed_weak",
        "likely_weak",
        "insufficient_evidence",
        "unobserved",
        "mixed_performance",
        "sparse_good",
        "sparse_poor",
        "likely_mastered",
        "confirmed_mastered",
    }
    assert "evidence_action" in summary["facts"]
    serialized = json.dumps(summary, ensure_ascii=False)
    assert ANSWER_TEXT not in serialized
    assert "synthetic-private-steps" not in serialized


def test_guard_accepts_locked_text_and_rejects_new_numbers_or_ids(bundle):
    summary, _, _ = issue_summary(bundle)
    good = parse_json(smart_reply(json.dumps(summary, ensure_ascii=False)))
    assert response_errors(good, summary) == []

    extra_number = dict(good)
    extra_number["reason"] = good["reason"] + " 99 次"
    assert any("unlocked numbers" in error for error in response_errors(extra_number, summary))

    unknown_id = dict(good)
    unknown_id["cited_ids"] = [*good["cited_ids"], "M-999"]
    assert any("unknown ids" in error for error in response_errors(unknown_id, summary))

    no_issue = dict(good)
    no_issue["reason"] = f"先看 {good['cited_ids'][-1]} 再练习。"
    assert any("cite the issue id" in error for error in response_errors(no_issue, summary))


def test_writer_retries_then_falls_back_to_the_rule_template(bundle):
    summary, _, _ = issue_summary(bundle)
    writer = ReasonWriter(SequenceClient(["not json at all"]))
    reason, check, meta = writer.write(summary, "模板理由", "模板检查")
    assert (reason, check) == ("模板理由", "模板检查")
    assert meta.source == "template"
    assert meta.attempts == 3
    assert meta.errors


def test_writer_uses_second_attempt_when_first_reply_is_bad(bundle):
    summary, _, _ = issue_summary(bundle)
    writer = ReasonWriter(SequenceClient(["not json", smart_reply]))
    reason, check, meta = writer.write(summary, "模板理由", "模板检查")
    assert meta.source == "llm"
    assert meta.attempts == 2
    assert "M-" in reason
    assert check


def _recommend_run(bundle, tmp_path):
    run_dir = tmp_path / "run"
    run_diagnosis(bundle, run_dir, DiagnosisConfig(), "latest")
    kb_path = tmp_path / "knowledge_base.json"
    kb_path.write_text(json.dumps(knowledge_base(bundle), ensure_ascii=False), encoding="utf-8")
    return run_dir, kb_path


def test_recommend_with_llm_stays_verifiable(bundle, tmp_path):
    run_dir, kb_path = _recommend_run(bundle, tmp_path)
    client = SequenceClient([smart_reply])
    out = tmp_path / "recommend"
    result = recommend_run(
        run=str(run_dir),
        knowledge=str(kb_path),
        output=str(out),
        llm=True,
        client=client,
    )
    assert result["gate"] == "pass"

    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["policy"]["llm_enabled"] is True
    assert manifest["llm"]["requested"] is True
    assert manifest["llm"]["items_used"] >= 1
    assert manifest["llm"]["items_fallback"] == 0
    assert manifest["llm"]["errors"] == []

    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((out / "nodes/N02/students").glob("*.json"))
    ]
    rewritten = [
        rec for rec in records if rec["plan"] and rec["generated_by"]["provider"] == "fake"
    ]
    assert rewritten
    assert client.calls == manifest["llm"]["items_used"]


def test_recommend_without_llm_keeps_templates(bundle, tmp_path):
    run_dir, kb_path = _recommend_run(bundle, tmp_path)
    out = tmp_path / "recommend"
    result = recommend_run(run=str(run_dir), knowledge=str(kb_path), output=str(out))
    assert result["gate"] == "pass"
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm"]["requested"] is False
    assert manifest["llm"]["items_used"] == 0


def test_explain_writes_summary_and_guarded_text(bundle, tmp_path):
    run_dir, kb_path = _recommend_run(bundle, tmp_path)
    out = tmp_path / "explain"
    result = explain_student(
        run=str(run_dir),
        node="N02",
        student="S002",
        knowledge_id="K-02",
        knowledge=str(kb_path),
        output=str(out),
        client=SequenceClient([smart_reply]),
    )
    assert result["source"] == "llm"
    summary = json.loads((out / "llm_summary.json").read_text(encoding="utf-8"))
    assert summary_errors(summary) == []
    assert ANSWER_TEXT not in json.dumps(summary, ensure_ascii=False)
    explain = json.loads((out / "explain.json").read_text(encoding="utf-8"))
    assert explain["issue_id"] == "IS-002-02"
    assert "M-" in explain["reason"]


def test_writer_redacts_key_shaped_secrets_in_errors(bundle):
    summary, _, _ = issue_summary(bundle)

    class LeakyClient:
        provider = "fake"
        model = "fake-model"

        def complete(self, system: str, user: str) -> str:
            raise RuntimeError("401 Incorrect API key provided: sk-live-abcdef123456")

    reason, check, meta = ReasonWriter(LeakyClient(), max_attempts=1).write(
        summary, "模板理由", "模板检查"
    )
    assert (reason, check) == ("模板理由", "模板检查")
    assert meta.source == "template"
    assert meta.errors
    assert all("sk-live-abcdef123456" not in error for error in meta.errors)
    assert any("sk-***" in error for error in meta.errors)


def test_explain_requires_a_configured_client(bundle, tmp_path, monkeypatch):
    run_dir, kb_path = _recommend_run(bundle, tmp_path)
    monkeypatch.setenv("KNOWFLOW_LLM_ENABLED", "false")
    monkeypatch.delenv("KNOWFLOW_LLM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="LLM 未启用"):
        explain_student(
            run=str(run_dir),
            node="N02",
            student="S002",
            knowledge_id="K-02",
            knowledge=str(kb_path),
            output=str(tmp_path / "explain"),
        )


# --- transport: standard library client, classified failures -----------------


def test_client_sends_the_key_and_parses_a_completion(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": " 你好 "}}]}).encode("utf-8")
    opener = FakeOpener(body=body)
    client = client_with(monkeypatch, opener)

    assert client.complete("系统", "问题") == "你好"
    assert opener.request.get_header("Authorization") == "Bearer sk-test-123456"
    payload = json.loads(opener.request.data.decode("utf-8"))
    assert payload["model"] == "fake-model"
    assert payload["max_tokens"] == 64


def test_client_posts_multi_turn_messages(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": "好"}}]}).encode("utf-8")
    opener = FakeOpener(body=body)
    client = client_with(monkeypatch, opener)

    assert (
        client.complete_messages(
            "系统",
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好呀"},
                {"role": "system", "content": "越权的一轮会被丢掉"},
                {"role": "user", "content": "继续"},
            ],
        )
        == "好"
    )
    payload = json.loads(opener.request.data.decode("utf-8"))
    assert [item["role"] for item in payload["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert payload["messages"][1]["content"] == "你好"


def test_client_classifies_an_auth_failure_without_touching_the_network(monkeypatch):
    error = urllib.error.HTTPError(
        "https://api.example.invalid/chat/completions",
        401,
        "Unauthorized",
        {},
        io.BytesIO(b'{"error":{"message":"Authentication Fails"}}'),
    )
    client = client_with(monkeypatch, FakeOpener(error=error))

    with pytest.raises(LLMError) as caught:
        client.complete("系统", "问题")

    assert caught.value.kind == "auth"
    assert caught.value.status == 401
    assert caught.value.retryable is False
    assert "sk-test-123456" not in str(caught.value)


def test_client_classifies_a_timeout_as_retryable(monkeypatch):
    client = client_with(
        monkeypatch, FakeOpener(error=urllib.error.URLError(TimeoutError("timed out")))
    )

    with pytest.raises(LLMError) as caught:
        client.complete("系统", "问题")

    assert caught.value.kind == "timeout"
    assert caught.value.retryable is True


def test_client_classifies_a_server_error_as_retryable(monkeypatch):
    error = urllib.error.HTTPError("https://x/y", 503, "busy", {}, io.BytesIO(b""))
    client = client_with(monkeypatch, FakeOpener(error=error))

    with pytest.raises(LLMError) as caught:
        client.complete("系统", "问题")

    assert caught.value.kind == "server"
    assert caught.value.status == 503
    assert caught.value.retryable is True


def test_client_rejects_an_empty_completion(monkeypatch):
    body = json.dumps({"choices": [{"message": {"content": "   "}}]}).encode("utf-8")
    client = client_with(monkeypatch, FakeOpener(body=body))

    with pytest.raises(LLMError) as caught:
        client.complete("系统", "问题")

    assert caught.value.kind == "empty"


def test_client_rejects_a_non_json_body(monkeypatch):
    client = client_with(monkeypatch, FakeOpener(body=b"<html>gateway</html>"))

    with pytest.raises(LLMError) as caught:
        client.complete("系统", "问题")

    assert caught.value.kind == "bad_response"


def test_prompt_lets_the_action_override_the_status():
    """状态只决定"能不能下结论"，动作由 evidence_action 决定——不能退回一句话。"""

    from knowflow.llm.prompt import SYSTEM_PROMPT

    assert "evidence_action" in SYSTEM_PROMPT
    assert "只能建议补充观测" not in SYSTEM_PROMPT
    for action in ("probe", "pending", "sparse_weak", "sparse_mastered", "sparse_mixed"):
        assert action in SYSTEM_PROMPT


def test_summary_carries_the_sparse_action(bundle):
    summary, _, _ = issue_summary(bundle, sid="S004", kid="K-03")
    assert summary["facts"]["evidence_action"] in {
        "probe",
        "not_attempted",
        "pending",
        "sparse_weak",
        "sparse_mastered",
        "sparse_mixed",
        None,
    }
    assert summary_errors(summary) == []


def test_rewrite_guard_rejects_flattened_advice():
    from knowflow.llm.integrate import _advice_conflict

    consolidate_item = {"activity_type": "consolidate"}
    assert _advice_conflict(consolidate_item, "建议补充观测，再测一次") is not None
    assert _advice_conflict(consolidate_item, "先用 M-001 重做同评分点练习，再复核") is None
    assert _advice_conflict({"activity_type": "probe"}, "建议补充观测") is None

