"""Optional language-layer checks: summary boundary, guard, retry, wiring."""

from __future__ import annotations

import json

import pytest
from test_recommend import knowledge_base, profile

from knowflow.diagnosis.mastery import DiagnosisConfig
from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.llm.explain import explain_student
from knowflow.llm.guard import parse_json, response_errors
from knowflow.llm.service import ReasonWriter
from knowflow.llm.summary import build_issue_summary, summary_errors
from knowflow.recommend.pipeline import recommend_run
from knowflow.recommend.validation import allowed_numbers

ANSWER_TEXT = "synthetic-private-answer"


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
    check = f"完成 {material} 后至少 2 题全对；未达标回到讲解材料。"
    used = sorted({float(count), 2.0})
    return json.dumps(
        {
            "kind": "recommendation_reason",
            "ref_id": issue,
            "reason": reason,
            "check": check,
            "cited_ids": [issue, material],
            "numbers_used": used,
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
        "mixed_performance",
        "likely_mastered",
        "confirmed_mastered",
    }
    serialized = json.dumps(summary, ensure_ascii=False)
    assert ANSWER_TEXT not in serialized
    assert "synthetic-private-steps" not in serialized


def test_guard_accepts_locked_text_and_rejects_new_numbers_or_ids(bundle):
    summary, _, _ = issue_summary(bundle)
    good = parse_json(smart_reply(json.dumps(summary, ensure_ascii=False)))
    assert response_errors(good, summary) == []

    extra_number = dict(good)
    extra_number["reason"] = good["reason"] + " 99 次"
    extra_number["numbers_used"] = [*good["numbers_used"], 99]
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
