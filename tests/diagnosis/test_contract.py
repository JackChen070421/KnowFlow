"""契约层：行为红线与决策/语言边界的可机检断言。"""

from __future__ import annotations

from test_llm import issue_summary
from test_recommend import profile

from knowflow.diagnosis.mastery import DiagnosisConfig
from knowflow.llm import chat, prompt
from knowflow.llm.contract import (
    MUST_NOT_INFER,
    answer_key_visible,
    forbidden_text,
    material_drift,
)
from knowflow.llm.summary import build_issue_summary
from knowflow.recommend.validation import allowed_numbers


def test_forbidden_line_is_shared_by_both_prompts():
    text = forbidden_text()
    assert text in prompt.SYSTEM_PROMPT
    assert text in chat.SYSTEM_PROMPT
    assert all(rule in text for rule in MUST_NOT_INFER)


def test_summary_uses_the_shared_rules(bundle):
    summary, _, _ = issue_summary(bundle)
    assert summary["constraints"]["must_not_infer"] == list(MUST_NOT_INFER)


def test_material_drift_flags_only_out_of_plan_citations():
    item = {"material_ids": ["M-057", "M-037"]}
    assert material_drift("先看 M-057，再做 M-037。", item) == []
    assert material_drift("先看 M-043，再做 M-037。", item) == ["M-043"]


def test_answer_key_visibility():
    assert answer_key_visible("teacher") is True
    assert answer_key_visible("student") is False
    assert answer_key_visible(None) is False


def test_audience_is_carried_into_the_summary(bundle):
    summary, _, _ = issue_summary(bundle)
    assert summary["audience"] == "teacher"

    student_profile = profile(bundle, "S002", config=DiagnosisConfig(min_evidence=2))
    issue = next(item for item in student_profile["issues"] if item["knowledge_id"] == "K-02")
    state = next(
        item for item in student_profile["knowledge_states"] if item["knowledge_id"] == "K-02"
    )
    ids = {"S002", "N02", issue["issue_id"], "K-02", issue["objective_id"]}
    student_summary = build_issue_summary(
        profile=student_profile,
        issue=issue,
        dataset_id=bundle["dataset_id"],
        allowed_numbers=allowed_numbers(issue, state),
        allowed_ids=ids,
        audience="student",
    )
    assert student_summary["audience"] == "student"
