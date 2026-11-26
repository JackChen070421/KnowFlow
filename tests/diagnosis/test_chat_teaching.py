"""Chat analysis layer: intent, signal separation, audit, guard and fallback.

Everything here runs on the synthetic bundle.  The real 40-student snapshot is
exercised by ``scripts/chat_acceptance.py``, which cannot be part of CI because
the official data never enters the repository.

The point of these tests is that the *program* guarantees the facts while the
*answer* stops being a template:

* a count question is answered with a count;
* a knowledge point with gaps is not described as a weak one;
* a teaching duration is not treated as a fabricated statistic;
* a fabricated statistic still is.
"""

from __future__ import annotations

import json

import pytest
from test_llm import SequenceClient
from test_recommend import knowledge_base

from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.knowledge.pipeline import write_knowledge_base
from knowflow.llm import audit
from knowflow.llm.chat import answer_question, build_facts, rules_answer, validate_answer
from knowflow.llm.intent import classify_intent, guide_block
from knowflow.recommend.pipeline import recommend_run
from knowflow.web.data import load_dashboard


@pytest.fixture()
def chat_run(tmp_path, bundle):
    run = tmp_path / "chat-run"
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


@pytest.fixture()
def snapshot(chat_run):
    return load_dashboard(chat_run)


@pytest.fixture()
def knowledge(chat_run):
    return json.loads((chat_run / "knowledge_base.json").read_text(encoding="utf-8"))


# --- 意图识别 ---------------------------------------------------------------

INTENT_CASES = [
    ("这个班学情如何？", False, False, "overview"),
    ("班上学生整体学得怎么样？", False, False, "overview"),
    ("最近班级的学习情况有什么变化？", False, False, "progress"),
    ("哪些知识点掌握得最差？", False, False, "knowledge"),
    ("哪些知识点需要重点讲解？", False, False, "knowledge"),
    ("学生在哪些知识点上存在困难？", False, False, "knowledge"),
    ("班上有哪些学生需要重点关注？", False, False, "group"),
    ("学生之间的差异大吗？", False, False, "group"),
    ("有没有明显的分层？", False, False, "group"),
    ("这个班需要分层教学吗？", False, False, "group"),
    ("他目前最需要补什么？", False, False, "student"),
    ("下一节课应该讲什么？", False, False, "strategy"),
    ("应该如何安排复习？", False, False, "strategy"),
    ("下一节课应该怎么安排？", False, False, "strategy"),
    ("最近学习情况有没有改善？", False, False, "progress"),
    ("哪些知识点正在逐步掌握？", False, False, "progress"),
    ("学生的学习进度是否正常？", False, False, "progress"),
    ("班级有多少人？", False, False, "lookup"),
    ("全班有多少人？", False, False, "lookup"),
    ("K-06 是不是全班都没掌握？", False, True, "knowledge"),
    ("K-06 有多少人掌握？", False, True, "lookup"),
    ("S002 目前学得怎么样？", True, False, "student"),
    ("S002 最近进步了吗？", True, False, "student"),
    ("S002 完成了多少道题？", True, False, "lookup"),
]


@pytest.mark.parametrize("question,student_named,knowledge_named,primary", INTENT_CASES)
def test_question_intent(question, student_named, knowledge_named, primary):
    result = classify_intent(
        question, student_named=student_named, knowledge_named=knowledge_named
    )
    assert result["primary"] == primary


def test_compound_question_keeps_both_intents():
    result = classify_intent("最近班级的学习情况有什么变化？")
    assert result["primary"] == "progress"
    assert "overview" in result["all"]


def test_a_changed_count_is_not_mistaken_for_analysis():
    result = classify_intent("这个班有多少人，学情如何？")
    assert result["primary"] != "lookup"


def test_a_count_question_uses_the_count_form():
    assert classify_intent("全班有多少人？")["form"] == "how_many"
    assert classify_intent("大家最近有没有进步？")["form"] == "yes_no"
    assert classify_intent("下一节课应该怎么安排？")["form"] == "how_to"


def test_greeting_is_itself_the_intent():
    assert classify_intent("你好")["greeting"] is True
    assert classify_intent("这个班学情如何？")["greeting"] is False


def test_subject_question_is_marked_as_teaching():
    """"K-07 怎么算" 要讲方法；“K-05 为什么薄弱”仍需学情分析。"""

    assert classify_intent("K-07 怎么算？", knowledge_named=True)["teach"] is True
    assert classify_intent("K-05 为什么薄弱？", knowledge_named=True)["teach"] is False


def test_lookup_guide_demands_a_single_fact():
    guide = guide_block(classify_intent("全班有多少人？"))
    assert "只回答数据本身" in guide
    assert "不展开学情分析" in guide


def test_guide_block_does_not_stack_secondary_guides():
    """次要意图只出现在标题行，否则学生会收到一份“班级分层”指南。"""

    guide = guide_block(classify_intent("S002 最近进步了吗？", student_named=True))
    assert guide.count("怎么想】") == 1
    assert "同时涉及" in guide


# --- 事实卡：把两种信号分开 -------------------------------------------------


def test_fact_card_separates_weak_evidence_from_missing_evidence(snapshot, knowledge):
    facts = build_facts(snapshot, "这个班哪些知识点最薄弱？", {"node_id": "N02"}, knowledge)
    class_facts = facts["class"]
    # 需要支持的一侧是「薄弱 + 较差」（PR #33 的 SUPPORT 口径）；两者仍是分开报的数字，
    # 所以这里断言的是和支持相关的桶，而不是单看 weak。
    assert all(
        (row["weak"] + row["sparse_poor"]) > 0 for row in class_facts["weak_signal"]
    )
    assert all(
        row["insufficient"] + row["unobserved"] > 0 for row in class_facts["evidence_gap"]
    )
    # 只有缺口、既无薄弱又无较差的知识点不能混进 weak_signal。
    weak_ids = {row["id"] for row in class_facts["weak_signal"]}
    gap_only = {
        row["id"]
        for row in class_facts["evidence_gap"]
        if row["weak"] == 0 and row["sparse_poor"] == 0
    }
    assert not (weak_ids & gap_only)


def test_fact_card_carries_short_names_for_sentences(snapshot, knowledge):
    facts = build_facts(snapshot, "这个班学情如何？", {"node_id": "N02"}, knowledge)
    for row in facts["class"]["knowledge"]:
        assert row["short"]
        assert "，" not in row["short"]


def test_fact_card_carries_a_node_timeline_with_a_caveat(snapshot, knowledge):
    facts = build_facts(snapshot, "最近学习情况有没有改善？", {"node_id": "N02"}, knowledge)
    assert [row["node"] for row in facts["timeline"]] == ["N01", "N02"]
    assert "不能当作学生进步" in facts["timeline_note"]


def test_fact_card_resolves_a_lookup(snapshot, knowledge):
    facts = build_facts(snapshot, "全班有多少人？", {"node_id": "N02"}, knowledge)
    assert facts["lookup"]["kind"] == "class_students"
    assert facts["lookup"]["value"] == facts["class"]["students"]


def test_fact_card_shows_tiers_as_descriptive_groups(snapshot, knowledge):
    facts = build_facts(snapshot, "这个班需要分层教学吗？", {"node_id": "N02"}, knowledge)
    tiers = facts["class"]["tiers"]
    assert "不是能力分层" in tiers["note"]
    assert facts["class"]["groups"]["note"].startswith("同一节点内的描述性差异")


# --- 规则兜底：按意图作答，不再一段模板走天下 -------------------------------


@pytest.mark.parametrize(
    "question",
    ["这个班学情如何？", "这个班哪些知识点最薄弱？", "下一节课应该怎么安排？", "这个班需要分层教学吗？"],
)
def test_rules_answer_differs_by_intent(question, snapshot, knowledge):
    facts = build_facts(snapshot, question, {"node_id": "N02"}, knowledge)
    assert rules_answer(facts)


def test_two_intents_do_not_share_one_template(snapshot, knowledge):
    answers = []
    for question in (
        "这个班学情如何？",
        "这个班哪些知识点最薄弱？",
        "下一节课应该怎么安排？",
        "这个班需要分层教学吗？",
    ):
        facts = build_facts(snapshot, question, {"node_id": "N02"}, knowledge)
        answers.append(rules_answer(facts))
    assert len(set(answers)) == len(answers)


def test_rules_lookup_answers_only_the_question(snapshot, knowledge):
    facts = build_facts(snapshot, "全班有多少人？", {"node_id": "N02"}, knowledge)
    answer = rules_answer(facts)
    assert answer == f"全班共 {facts['class']['students']} 人。"
    assert "证据不足" not in answer


def test_a_count_question_never_gets_an_evidence_section(snapshot, knowledge):
    """数据查询没有第二段可写，硬套“依据”只会写出与问题无关的解释。"""

    facts = build_facts(snapshot, "全班有多少人？", {"node_id": "N02"}, knowledge)
    evidence = rules_answer(facts, "evidence")
    assert "依据" not in evidence
    assert evidence == rules_answer(facts)

    def grounded(user: str) -> str:
        payload = user.split("FACTS（唯一可用信息）：\n", 1)[1].split("\n\n用户问题：", 1)[0]
        return f"全班共 {json.loads(payload)['class']['students']} 人。"

    result = answer_question(
        snapshot=snapshot,
        message="全班有多少人？",
        context={"node_id": "N02"},
        client=SequenceClient([grounded]),
        knowledge=knowledge,
        mode="evidence",
    )
    # No structure nudge, no second call: the one-fact answer is accepted as-is.
    assert result["source"] == "llm"
    assert result["trace"]["guard"]["attempts"] == 1


def test_a_mastery_count_without_a_target_is_not_answered_with_class_size(snapshot, knowledge):
    facts = build_facts(snapshot, "有多少人掌握？", {"node_id": "N02"}, knowledge)
    assert facts["lookup"] is None
    answer = rules_answer(facts)
    assert "请指明" in answer
    assert f"共 {facts['class']['students']} 人" not in answer


def test_a_named_knowledge_count_is_answered_from_that_row(snapshot, knowledge):
    facts = build_facts(snapshot, "K-02 有多少人掌握？", {"node_id": "N02"}, knowledge)
    assert facts["lookup"]["kind"] == "knowledge_counts"
    assert facts["lookup"]["asked"] == "mastered"
    row = next(item for item in facts["class"]["knowledge"] if item["id"] == "K-02")
    assert facts["lookup"]["value"] == row["mastered"]


def test_a_subject_question_gets_its_own_guide():
    guide = guide_block(classify_intent("K-07 怎么算？", knowledge_named=True))
    assert "学科问题怎么想" in guide
    assert "知识点分析怎么想" not in guide


def test_a_student_without_applicable_scope_has_no_zero_over_zero():
    facts = {
        "node": {"id": "N02", "date": "2026-06-17", "objectives": 3},
        "intent": {"primary": "student", "label": "个体学生", "form": "open"},
        "student": {
            "id": "S017",
            "coverage": {"observed": 0, "applicable": 0, "ratio": None, "scope_known": False},
            "status_counts": {"unobserved": 9},
            "needs_consolidation": [],
            "needs_observation": [],
            "needs_coverage": [],
            "states": [],
            "issues": [],
            "plan": [],
        },
        "knowledge": [],
        "materials": [],
        "sources": [],
    }
    answer = rules_answer(facts)
    assert "0/0" not in answer
    assert "还没有可判断的记录" in answer


def test_rules_never_print_internal_ids(snapshot, knowledge):
    for question in ("这个班学情如何？", "下一节课应该怎么安排？", "这个班需要分层教学吗？"):
        facts = build_facts(snapshot, question, {"node_id": "N02"}, knowledge)
        answer = rules_answer(facts)
        assert "M-" not in answer
        assert "ALL" not in answer


def test_rules_yes_no_keeps_gaps_out_of_the_weak_bucket(snapshot, knowledge):
    facts = build_facts(snapshot, "K-02 是不是全班都没掌握？", {"node_id": "N02"}, knowledge)
    answer = rules_answer(facts)
    assert answer.startswith("不是")
    assert "不等于没有掌握" in answer


def test_rules_put_confirmed_weakness_before_evidence_gaps():
    """一个“缺记录”的知识点，不能排在“已确认薄弱”的前面。"""

    facts = {
        "node": {"id": "N02", "date": "2026-06-17", "objectives": 3},
        "intent": {"primary": "knowledge", "label": "知识点分析", "form": "which"},
        "class": {
            "id": "ALL",
            "students": 40,
            "coverage": {
                "mean_ratio": 0.23,
                "students_below_0_5": 39,
                "students_with_insufficient_evidence": 36,
            },
            "knowledge": [],
            "weak_signal": [
                {"id": "K-05", "name": "用消元法解二元一次方程组", "short": "消元法", "weak": 8}
            ],
            "evidence_gap": [
                {
                    "id": "K-06",
                    "name": "列方程解实际问题",
                    "short": "列方程",
                    "weak": 0,
                    "insufficient": 18,
                    "unobserved": 12,
                }
            ],
        },
        "knowledge": [],
        "materials": [],
        "sources": [],
    }
    answer = rules_answer(facts)
    assert "消元法" in answer and "列方程" in answer
    assert answer.index("消元法") < answer.index("列方程")


def test_rules_evidence_mode_keeps_the_two_headings(snapshot, knowledge):
    facts = build_facts(
        snapshot, "S002 现在最需要补什么？", {"node_id": "N02", "student_id": "S002"}, knowledge
    )
    answer = rules_answer(facts, "evidence")
    assert answer.startswith("结论：")
    assert "\n依据：" in answer


def test_rules_teach_a_subject_question_without_a_report(snapshot, knowledge):
    facts = build_facts(snapshot, "K-02 怎么算？", {"node_id": "N02"}, knowledge)
    answer = rules_answer(facts)
    assert "证据不足" not in answer


# --- 数字审计：教学数字与学情数字 ------------------------------------------

NUMBER_CASES = [
    # (text, allowed facts, should a data claim be rejected?)
    ("先看学习卡第 3 步，再做 14 道同类题。", {1.0, 2.0}, False),
    ("建议每次练 15 分钟，做完 4 道同类题。", {1.0, 2.0}, False),
    ("建议每组 4 人，先做 K-05 的消元练习。", {1.0, 2.0, 3.0}, False),
    ("2026 年 11 月 3 日这个节点，平均覆盖约 23%。", {0.233}, False),
    ("只有 8 人掌握了这一项。", {1.0, 2.0, 3.0}, True),
    ("班上有 8 人需要补课。", {1.0, 2.0, 3.0}, True),
    ("这个班有 40 人，39 人覆盖率不到一半。", {40.0, 39.0}, False),
    ("这个班有 41 人，39 人覆盖率不到一半。", {40.0, 39.0}, True),
    ("K-05 有 8 人薄弱，K-07 有 9 人。", {8.0, 7.0}, True),
    ("有 12 个学生没交。", {1.0, 2.0}, True),
    # The real model sentence the old sentence-wide rule rejected:
    (
        "开场用10分钟做一次统一小测，把36名证据不足的学生先落下来。",
        {36.0},
        False,
    ),
    ("平均分 45 分，低于班级均分。", {45.0}, False),
    ("平均分 47 分，低于班级均分。", {45.0}, True),
]


@pytest.mark.parametrize("text,allowed,rejected", NUMBER_CASES)
def test_number_audit_separates_teaching_from_claims(text, allowed, rejected):
    problems = validate_answer(text, allowed, set())
    assert any(problem.startswith("numbers") for problem in problems) is rejected


def test_an_approximation_does_not_cover_the_whole_sentence():
    """"39 人覆盖率不到一半" 里的“不到”不能给同一句的另一个数字放水。"""

    problems = validate_answer("这个班有 41 人，39 人覆盖率不到一半。", {40.0, 39.0}, set())
    assert any("numbers outside facts" in problem for problem in problems)


def test_a_count_cannot_be_licensed_as_a_percentage_of_another_count():
    """事实卡里有一个 10，不代表“999 人”可以按“999% of 10”过关。"""

    problems = validate_answer("班上共有 999 人需要补课。", {10.0, 40.0}, set())
    assert any("numbers outside facts" in problem for problem in problems)
    # A real ratio may still be restated as a percentage.
    assert validate_answer("平均覆盖约 23%。", {0.233}, set()) == []
    assert validate_answer("覆盖率达到 100%。", {1.0}, set()) == []


def test_number_audit_reports_the_split():
    result = audit.number_audit("这个班有 40 人；建议先做 3 道题热身。", {40.0})
    assert result["data_claims"] == 1
    assert result["teaching_numbers"] >= 1
    assert result["unverified"] == []


def test_unknown_ids_are_still_rejected():
    problems = validate_answer("先看 M-999 这张学习卡。", {1.0}, {"M-001"})
    assert any(problem.startswith("ids") for problem in problems)


def test_absolute_claims_need_a_hedge():
    facts = {
        "class": {
            "knowledge": [{"id": "K-06", "insufficient": 18, "unobserved": 12}],
        }
    }
    assert audit.claim_problems("K-06 全班都没掌握。", facts)
    assert audit.claim_problems("不能说 K-06 全班都没掌握，证据还不够。", facts) == []
    assert audit.claim_problems("K-06 全班都没掌握。", {"class": {"knowledge": []}}) == []


# --- 端到端：失败分类与 trace ----------------------------------------------


def ask(snapshot, message, client, **kwargs):
    return answer_question(
        snapshot=snapshot,
        message=message,
        context={"node_id": "N02"},
        client=client,
        knowledge=kwargs.pop("knowledge", None),
        **kwargs,
    )


def test_a_fabricated_number_is_reported_as_a_number_problem(snapshot, knowledge):
    client = SequenceClient(["S002 的班级共有 999 人需要补课。"])
    result = ask(snapshot, "S002 现在最需要补什么？", client, knowledge=knowledge)
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "number"
    assert "无法核对" in result["note"]
    assert "999" not in result["answer"]


def test_an_unknown_id_is_reported_as_an_id_problem(snapshot, knowledge):
    client = SequenceClient(["S002 先看 M-999 这张学习卡。具体材料见学习建议。"])
    result = ask(snapshot, "S002 现在最需要补什么？", client, knowledge=knowledge)
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "id"
    assert "编号" in result["note"]


def test_an_absolute_claim_is_reported_as_a_claim_problem(snapshot, knowledge):
    client = SequenceClient(["全班都没掌握 K-02，需要从头讲。"])
    result = ask(snapshot, "K-02 是不是全班都没掌握？", client, knowledge=knowledge)
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "claim"
    assert "证据不足" in result["note"]


def test_a_rejected_answer_is_carried_into_the_trace(snapshot, knowledge):
    client = SequenceClient(["S002 的班级共有 999 人需要补课。"])
    result = ask(snapshot, "S002 现在最需要补什么？", client, knowledge=knowledge)
    guard = result["trace"]["guard"]
    assert guard["problems"]
    assert guard["attempts"] >= 1
    assert any("999" in problem for problem in guard["problems"])


def test_an_accepted_answer_records_its_intent(snapshot, knowledge):
    def grounded(user: str) -> str:
        payload = user.split("FACTS（唯一可用信息）：\n", 1)[1].split("\n\n用户问题：", 1)[0]
        facts = json.loads(payload)
        return f"全班共 {facts['class']['students']} 人。"

    result = ask(
        snapshot, "全班有多少人？", SequenceClient([grounded]), knowledge=knowledge
    )
    assert result["source"] == "llm"
    assert result["trace"]["guard"]["intent"] == "lookup"
    assert result["trace"]["guard"]["attempts"] == 1
    # The answer stays a fact, not a report.
    assert len(result["answer"]) <= 20


def test_trace_explains_how_the_question_was_read(snapshot, knowledge):
    facts = build_facts(snapshot, "这个班学情如何？", {"node_id": "N02"}, knowledge)
    result = ask(snapshot, "这个班学情如何？", SequenceClient(["这个班现在最缺的是证据。"]),
                 knowledge=knowledge)
    labels = [step["label"] for step in result["trace"]["steps"]]
    assert labels[0] == "理解问题"
    assert "区分证据" in labels
    assert "有薄弱证据" in "".join(step["detail"] for step in result["trace"]["steps"])
    assert facts["intent"]["primary"] == "overview"


def test_history_still_works_with_the_new_guard(snapshot, knowledge):
    result = answer_question(
        snapshot=snapshot,
        message="那第二个呢？",
        context={"node_id": "N02", "student_id": "S002"},
        client=SequenceClient(["S002 目前优先关注 K-02。"]),
        knowledge=knowledge,
        history=[
            {"role": "user", "text": "S002 最需要补什么？"},
            {"role": "assistant", "text": "先补 K-02。"},
        ],
    )
    assert result["source"] == "llm"
    assert result["trace"]["guard"]["history_turns"] == 2
