"""结构化验收（任务 F）。

Two layers, kept apart so a failure can be attributed:

* ``test_data_*`` — the fact card is compared with the validated snapshot and with
  the per-student states recomputed here.  A failure means extraction is wrong.
* ``test_metric_*`` — the statistics' 口径 (partition, disjoint sums, which
  aggregate is *not* a bucket).  A failure means the definition is wrong.
* ``test_expression_*`` — a mocked model says something the data does not support;
  the answer must be rejected or corrected.  A failure means the expression
  layer let it through.
* ``test_audit_*`` — the number audit itself (Arabic + Chinese).
* ``test_entity_*`` — IDs that do not exist.

Every test name carries its category, so ``scripts/check_acceptance.py`` can run
one category at a time and print counts per category.
"""

from __future__ import annotations

import json

import pytest
from acceptance_support import misattributed_counts
from chat_fixtures import build_chat_run
from test_llm import SequenceClient

from knowflow.llm import audit
from knowflow.llm.chat import (
    _knowledge_rows,
    allowed_sets,
    answer_question,
    build_facts,
    rules_answer,
)
from knowflow.web.data import load_dashboard, read_json

# The official 40-student snapshot shape, used where a synthetic fixture cannot
# reproduce a 口径 edge (K-05 mostly weak vs K-06 mostly unmeasured).
ROWS = [
    {
        "id": "K-05",
        "short": "消元法",
        "weak": 8,
        "mixed": 19,
        "insufficient": 4,
        "unobserved": 4,
        "mastered": 5,
        "not_applicable": 0,
        "observed": 36,
        "student_count": 40,
    },
    {
        "id": "K-06",
        "short": "列方程",
        "weak": 6,
        "mixed": 2,
        "insufficient": 18,
        "unobserved": 12,
        "mastered": 2,
        "not_applicable": 0,
        "observed": 28,
        "student_count": 40,
    },
]


@pytest.fixture()
def chat_run(tmp_path, bundle):
    return build_chat_run(tmp_path, bundle, name="acceptance-run")


@pytest.fixture()
def snapshot(chat_run):
    return load_dashboard(chat_run)


@pytest.fixture()
def knowledge(chat_run):
    return read_json(chat_run / "knowledge_base.json")


def facts_for(snapshot, knowledge, question="这个班学情如何？", context=None):
    return build_facts(snapshot, question, context or {"node_id": "N02"}, knowledge)


def ask(snapshot, knowledge, message, reply, context=None, history=None):
    return answer_question(
        snapshot=snapshot,
        message=message,
        context=context or {"node_id": "N02"},
        client=SequenceClient([reply]),
        history=history,
        knowledge=knowledge,
    )


# --- 第一层：结构化事实正确性 ---------------------------------------------


def _status_bucket(status: str) -> str:
    return {
        "confirmed_weak": "weak",
        "likely_weak": "weak",
        "mixed_performance": "mixed",
        "insufficient_evidence": "insufficient",
        "unobserved": "unobserved",
        "confirmed_mastered": "mastered",
        "likely_mastered": "mastered",
        "not_applicable": "not_applicable",
    }[status]


def _recompute(profiles: dict, knowledge_id: str) -> dict:
    counts = {
        "weak": 0,
        "mixed": 0,
        "insufficient": 0,
        "unobserved": 0,
        "mastered": 0,
        "not_applicable": 0,
        "student_count": len(profiles),
    }
    for profile in profiles.values():
        state = next(
            item for item in profile["knowledge_states"]
            if item["knowledge_id"] == knowledge_id
        )
        counts[_status_bucket(state["status"])] += 1
    return counts


def test_data_class_size_matches_the_snapshot(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "全班有多少人？")
    expected = snapshot["classes"]["N02"]["ALL"]["student_count"]
    assert facts["class"]["students"] == expected
    assert facts["lookup"]["value"] == expected


def test_data_knowledge_counts_match_the_student_states(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "这个班哪些知识点最薄弱？")
    profiles = snapshot["profiles"]["N02"]
    for row in facts["class"]["knowledge"]:
        expected = _recompute(profiles, row["id"])
        for key in (
            "weak",
            "mixed",
            "insufficient",
            "unobserved",
            "mastered",
            "not_applicable",
            "student_count",
        ):
            assert row[key] == expected[key], f"{row['id']}.{key}"


def test_data_knowledge_names_and_objectives_come_from_the_base(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "这个班学情如何？")
    base = {item["knowledge_id"]: item for item in knowledge["knowledge"]}
    for row in facts["class"]["knowledge"]:
        assert row["name"] == base[row["id"]]["name"]
    for item in facts["knowledge"]:
        assert item["objective_id"] == base[item["id"]]["objective_id"]


def test_data_coverage_matches_the_class_profile(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "这个班学情如何？")
    profile = snapshot["classes"]["N02"]["ALL"]
    assert facts["class"]["students"] == profile["student_count"]
    for key, value in profile["coverage_summary"].items():
        assert facts["class"]["coverage"][key] == value


def test_data_a_student_state_matches_the_profile(snapshot, knowledge):
    facts = facts_for(
        snapshot, knowledge, "S002 现在最需要补什么？", {"node_id": "N02", "student_id": "S002"}
    )
    assert facts["student"]["id"] == "S002"
    states = {
        item["knowledge_id"]: item
        for item in snapshot["profiles"]["N02"]["S002"]["knowledge_states"]
    }
    for state in facts["student"]["states"]:
        expected = states[state["id"]]
        assert state["status"] == expected["status"]
        assert state["evidence"] == expected["evidence_count"]


def test_data_materials_follow_the_qmatrix(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "K-02 怎么算？")
    mapping = {(row["material_id"], row["knowledge_id"]) for row in knowledge["qmatrix"]}
    examples = [item for item in facts["sources"] if item["kind"] == "example"]
    assert examples
    for item in examples:
        assert (item["id"], "K-02") in mapping, item["id"]


def test_data_lookup_for_a_knowledge_point_uses_that_row(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "K-02 有多少人掌握？")
    row = next(item for item in facts["class"]["knowledge"] if item["id"] == "K-02")
    assert facts["lookup"]["kind"] == "knowledge_counts"
    assert facts["lookup"]["value"] == row["mastered"]


# --- 统计口径 -------------------------------------------------------------


def test_metric_status_buckets_partition_each_knowledge_point(snapshot, knowledge):
    """每个学生在一个知识点上只有一个状态；六个桶必须正好加总到班级人数。"""

    facts = facts_for(snapshot, knowledge, "这个班学情如何？")
    for row in facts["class"]["knowledge"]:
        total = (
            row["weak"]
            + row["mixed"]
            + row["insufficient"]
            + row["unobserved"]
            + row["mastered"]
            + row["not_applicable"]
        )
        assert total == row["student_count"], row["id"]


def test_metric_unknown_is_the_disjoint_sum(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "这个班学情如何？")
    for row in facts["class"]["knowledge"]:
        assert row["unknown"] == row["insufficient"] + row["unobserved"]


def test_metric_untestable_students_are_not_a_gap():
    """not_applicable 是"本节点没有可测题"，不能算进"还判断不了"。"""

    distribution = [
        {
            "knowledge_id": "K-04",
            "weak_count": 0,
            "mixed_count": 0,
            "insufficient_count": 0,
            "unobserved_count": 1,
            "mastered_count": 0,
            "not_applicable_count": 39,
            "observed_student_count": 0,
            "mean_mastery": None,
        }
    ]
    row = _knowledge_rows({"K-04": "方程"}, distribution)[0]
    assert row["unknown"] == 1
    assert row["not_applicable"] == 39


def test_metric_observed_is_not_a_partition_bucket():
    """observed_student_count 是 evidence_count>0，不是状态桶，不能拿来做加总。

    官方快照里 K-09 的状态和是 21，observed 却是 20；把 observed 当桶会让
    "21 人" 和 "20 人" 同时合法。
    """

    row = dict(ROWS[0], weak=3, mixed=3, insufficient=14, unobserved=19, mastered=1, observed=20)
    legal = audit.knowledge_legal_counts(row)
    assert 33 in legal  # insufficient + unobserved
    assert 20 in legal  # observed itself is a real metric
    assert 21 not in legal  # 状态和不是可引用的口径


def test_metric_zero_record_reaches_the_fallback(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "这个班学情如何？")
    top = max(facts["class"]["knowledge"], key=lambda item: item["unobserved"])
    assert top["unobserved"] > 0
    answer = rules_answer(facts)
    assert "完全没有作答记录" in answer
    assert top["short"] in answer
    assert answer.count("完全没有作答记录") == 1


def test_metric_zero_record_does_not_displace_the_weak_signal():
    """有薄弱证据的知识点仍然排在"缺记录"之前（任务 G 不改变主判断）。"""

    facts = {
        "node": {"id": "N02", "date": "2026-06-17", "objectives": 3},
        "intent": {"primary": "overview", "label": "整体学情", "form": "open"},
        "class": {
            "id": "ALL",
            "students": 40,
            "coverage": {
                "mean_ratio": 0.23,
                "students_below_0_5": 39,
                "students_with_insufficient_evidence": 36,
            },
            "knowledge": ROWS,
            "weak_signal": [ROWS[0]],
            "evidence_gap": [ROWS[1]],
            "no_record": [
                {
                    "id": "K-03",
                    "short": "整式解释",
                    "unobserved": 29,
                    "insufficient": 11,
                }
            ],
        },
        "knowledge": [],
        "materials": [],
        "sources": [],
    }
    answer = rules_answer(facts)
    assert answer.index("消元法") < answer.index("整式解释")


# --- 第二层：表达正确性 ---------------------------------------------------


def test_expression_evidence_gap_is_not_reported_as_not_mastered(snapshot, knowledge):
    result = ask(snapshot, knowledge, "K-02 是不是全班都没掌握？", "全班都没掌握 K-02。")
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "claim"
    assert "不等于" in result["answer"]


def test_expression_one_group_is_not_reported_as_class_wide(snapshot, knowledge):
    result = ask(snapshot, knowledge, "这个班哪些知识点最薄弱？", "全班学生都薄弱。")
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "claim"


def test_expression_a_hedged_answer_is_kept(snapshot, knowledge):
    result = ask(
        snapshot,
        knowledge,
        "K-02 是不是全班都没掌握？",
        "不是。现在只能说证据还不够，不能说全班都没掌握。",
    )
    assert result["source"] == "llm"


def test_expression_misattribution_is_detected_by_the_checker():
    """B 的原型：K-06 没有 19 人薄弱，19 是 K-05 的混合人数。"""

    wrong = misattributed_counts("K-06 有 19 人薄弱。", ROWS)
    assert wrong and wrong[0]["value"] == 19 and wrong[0]["knowledge"] == ["K-06"]
    assert not misattributed_counts("K-05 有 19 人混合。", ROWS)
    assert not misattributed_counts("K-06 有 8 人薄弱。", ROWS)  # 6+2 是合法合计


@pytest.mark.xfail(strict=True, reason="任务 B 尚未实现：审计只校验数字存在性")
def test_expression_misattributed_count_is_not_yet_rejected():
    """记录当前缺口：运行时审计放行"K-06 有 19 人薄弱"。

    这是有意保留的 xfail：B 落地后它会通过，strict 会让它变成 XPASS 失败，
    提醒把这条标记改掉。
    """

    result = audit.verdict(
        "K-06 有 19 人薄弱。", {19.0, 6.0}, {"K-06"}, {"class": {"knowledge": ROWS}}
    )
    assert result["ok"] is False


# --- 数字审计 -------------------------------------------------------------


def test_audit_fabricated_arabic_number_is_rejected(snapshot, knowledge):
    result = ask(snapshot, knowledge, "S002 现在最需要补什么？", "S002 的班级共有 999 人。")
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "number"


def test_audit_fabricated_chinese_number_is_rejected(snapshot, knowledge):
    result = ask(snapshot, knowledge, "这个班哪些知识点最薄弱？", "班上有四十三人薄弱。")
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "number"


def test_audit_a_teaching_quantity_is_not_a_data_claim(snapshot, knowledge):
    result = ask(
        snapshot,
        knowledge,
        "下一节课应该怎么安排？",
        "先用 10 分钟做一次小测，再留 15 分钟讲评，让学生做 3 道同类题。",
    )
    assert result["source"] == "llm"


def test_audit_the_fact_card_is_the_only_number_source(snapshot, knowledge):
    facts = facts_for(snapshot, knowledge, "这个班学情如何？")
    numbers, _ = allowed_sets(facts)
    assert 999.0 not in numbers
    assert facts["class"]["students"] in numbers


# --- 实体引用 -------------------------------------------------------------


def test_entity_unknown_student_id_is_rejected(snapshot, knowledge):
    result = ask(snapshot, knowledge, "S999 现在怎么样？", "S999 目前记录不足。")
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "id"


def test_entity_unknown_material_id_is_rejected(snapshot, knowledge):
    result = ask(snapshot, knowledge, "S002 现在最需要补什么？", "先看 M-999 这张学习卡。")
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "id"


def test_entity_a_real_id_is_accepted(snapshot, knowledge):
    result = ask(snapshot, knowledge, "S002 现在最需要补什么？", "S002 目前优先关注 K-02。")
    assert result["source"] == "llm"


def test_acceptance_output_is_json_serialisable(snapshot, knowledge):
    """失败报告要能直接贴进 Issue，因此结构化结果必须可序列化。"""

    facts = facts_for(snapshot, knowledge, "这个班学情如何？")
    report = {
        "class_size": facts["class"]["students"],
        "rows": misattributed_counts("K-05 有 8 人薄弱。", ROWS),
    }
    assert json.dumps(report, ensure_ascii=False)
