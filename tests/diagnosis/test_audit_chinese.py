"""中文数字审计（任务 A）。

The rule stays the same as for Arabic numbers: parse the value, classify what the
number is *doing* in the sentence, then check only the learner-data ones.  These
tests pin both directions — a fabricated Chinese headcount must be caught, and
"第一步/一方面/建议十人一组/一半" must not be.
"""

from __future__ import annotations

import pytest

from knowflow.llm import audit
from knowflow.llm.chat import validate_answer


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("四十三", 43),
        ("二十", 20),
        ("一百零五", 105),
        ("两千零二十六", 2026),
        ("十", 10),
        ("两", 2),
        ("一百", 100),
        ("二十三", 23),
    ],
)
def test_parse_chinese_number(text, value):
    assert audit.parse_chinese_number(text) == value


@pytest.mark.parametrize("text", ["一两", "二三", "十几", "几十", "百余", "多数", ""])
def test_approximations_are_not_exact_numbers(text):
    """模糊数量不能被解析成精确值，否则"十几人"就会变成事实。"""

    assert audit.parse_chinese_number(text) is None


VALIDATION_CASES = [
    # 精确中文数字：可核对
    ("班级有四十人。", {40.0}, False),
    ("有八名学生薄弱。", {8.0}, False),
    # 编造的中文人数：必须拦
    ("班上有四十三人薄弱。", {40.0, 8.0}, True),
    ("有十三名学生完成测评。", {40.0, 8.0}, True),
    # 模糊数量：不能当精确事实放行
    ("有十几名学生薄弱。", {40.0, 8.0}, True),
    ("有几十人尚未完成测评。", {40.0}, True),
    ("课上有二三十人走神。", {40.0}, True),
    # 序数与普通语言：不能误报
    ("第一步先进行测评。", {1.0}, False),
    ("一方面需要补充证据，另一方面需要针对性练习。", {1.0}, False),
    ("第三轮再集中讲解。", {1.0}, False),
    # 教学建议中的数量
    ("建议十人一组开展讨论。", {40.0}, False),
    # 百分数与分数
    ("覆盖率为百分之二十三。", {0.233}, False),
    ("覆盖率为百分之四十三。", {0.233}, True),
    ("约有三分之二的学生完成任务。", {0.667}, False),
    ("约有三分之二的学生完成任务。", {0.5}, True),
    # 阿拉伯数字回归 + 中文"一半"不能当成 1 人
    ("39 人覆盖率不到一半。", {39.0}, False),
    ("先做 14 道题。", {1.0}, False),
]


@pytest.mark.parametrize(("text", "allowed", "rejected"), VALIDATION_CASES)
def test_chinese_numbers_go_through_the_same_context_rules(text, allowed, rejected):
    problems = validate_answer(text, allowed, set())
    hit = any(problem.startswith("numbers") for problem in problems)
    assert hit is rejected


def test_the_error_names_the_chinese_number_for_debugging():
    problems = validate_answer("班上有四十三人薄弱。", {40.0}, set())
    assert any("四十三" in problem for problem in problems)


def test_unparsed_numerals_are_recorded():
    """"一两"这类解析不了的表达要留痕，而不是静默当成合法数字。"""

    result = audit.number_audit("有一两个人没交。", {40.0})
    assert audit.parse_chinese_number("一两") is None
    assert "一两" in result["unparsed"]
    assert result["unverified"]


def test_a_percentage_is_compared_with_a_ratio_fact():
    assert validate_answer("覆盖率约百分之二十三。", {0.233}, set()) == []
    assert validate_answer("覆盖率约百分之十七。", {0.233}, set())
