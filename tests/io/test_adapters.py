"""Row-level adapter rules: parsing, nulls, and the B-slice mapping."""

from __future__ import annotations

import json

import pytest

from knowflow.io import adapters
from knowflow.io.errors import AdaptError


def test_parse_rubric_uses_canonical_ids() -> None:
    raw = "Q043P1 答案正确 1分\nQ043P2 除以负数时反向 1分"
    payload = adapters.parse_rubric(raw, "Q043")
    assert payload is not None
    assert json.loads(payload) == [
        {"id": "M-043P1", "text": "答案正确", "points": 1},
        {"id": "M-043P2", "text": "除以负数时反向", "points": 1},
    ]


def test_parse_rubric_rejects_mismatched_material() -> None:
    with pytest.raises(AdaptError):
        adapters.parse_rubric("Q001P1 答案正确 1分", "Q002")


def test_parse_rubric_scores_and_sum() -> None:
    payload = adapters.parse_rubric_scores("Q043P1=1；Q043P2=0；Q043P3=0")
    assert payload is not None
    assert json.loads(payload) == {"M-043P1": 1, "M-043P2": 0, "M-043P3": 0}
    assert adapters.rubric_sum("Q043P1=1；Q043P2=0；Q043P3=0") == 1
    assert adapters.rubric_sum("") is None


def test_parse_options_keeps_labels() -> None:
    payload = adapters.parse_options("A. 3x与3x²\nB. 3x与-2x")
    assert payload is not None
    assert json.loads(payload) == ["A. 3x与3x²", "B. 3x与-2x"]
    assert adapters.parse_options("") is None


def test_split_steps() -> None:
    payload = adapters.split_steps("1. 原式=…\n2. =…")
    assert payload is not None
    assert json.loads(payload) == ["1. 原式=…", "2. =…"]
    assert adapters.split_steps("") is None


def _material_rows() -> list[dict[str, str]]:
    return [
        {
            "材料编号": "Q001", "主题编号": "T01", "材料类型": "题目", "题型": "填空题",
            "题干或内容": "题干", "选项": "", "参考答案": "答案", "参考解析": "解析",
            "满分": "1", "评分点": "Q001P1 答案正确 1分", "指标编号": "T01I1",
            "来源或资料文件": "赛事新编",
        },
        {
            "材料编号": "L01", "主题编号": "T01", "材料类型": "学习卡", "题型": "",
            "题干或内容": "卡片", "选项": "", "参考答案": "", "参考解析": "",
            "满分": "", "评分点": "", "指标编号": "T01I1、T02I1",
            "来源或资料文件": "赛事新编",
        },
        {
            "材料编号": "B01", "主题编号": "", "材料类型": "教材", "题型": "",
            "题干或内容": "七年级上册 第一章 有理数", "选项": "", "参考答案": "",
            "参考解析": "", "满分": "", "评分点": "", "指标编号": "",
            "来源或资料文件": "5_课程标准及相关教学资源/B01_相关资料切片.pdf",
        },
        {
            "材料编号": "B05", "主题编号": "", "材料类型": "教材", "题型": "",
            "题干或内容": "七年级上册 第三章 代数式", "选项": "", "参考答案": "",
            "参考解析": "", "满分": "", "评分点": "", "指标编号": "",
            "来源或资料文件": "5_课程标准及相关教学资源/B05_相关资料切片.pdf",
        },
    ]


def test_materials_null_and_b_slice_rules() -> None:
    materials = adapters.adapt_materials(_material_rows())
    by_id = {row["material_id"]: row for row in materials}
    assert by_id["M-001"]["material_type"] == "assessment"
    assert by_id["M-001"]["item_format"] == "blank"
    assert by_id["M-001"]["difficulty"] is None
    assert by_id["M-055"]["material_type"] == "explain"
    assert by_id["M-055"]["options_json"] is None
    assert by_id["M-058"]["material_type"] == "reference"
    assert by_id["M-058"]["objective_id"] is None
    assert by_id["M-062"]["objective_id"] == "OBJ-7M-01"
    assert json.loads(by_id["M-062"]["attachments_json"]) == [
        "5_课程标准及相关教学资源/B05_相关资料切片.pdf"
    ]


def test_qmatrix_rows_for_questions_and_cards() -> None:
    rows = adapters.adapt_qmatrix(_material_rows())
    assert len(rows) == 3  # Q001 + L01×2; B slices are not measured
    question = [row for row in rows if row["material_id"] == "M-001"]
    assert question[0]["item_type"] == "assessment"
    assert question[0]["is_primary"] is True
    card = [row for row in rows if row["material_id"] == "M-055"]
    assert len(card) == 2
    assert {row["knowledge_id"] for row in card} == {"K-01", "K-04"}
    assert all(row["item_type"] == "explain" and row["is_primary"] is False for row in card)


def test_objectives_unit_comes_from_textbook_slice() -> None:
    course = [
        {
            "主题编号": "T01", "主题": "代数式", "主题目标": "能表示数量关系",
            "指标编号": "T01I1", "观察指标": "表示数量关系", "课标整理编号": "CR01",
            "课标文件页／正文页": "62／55", "教材正文页": "上册68—109",
        }
    ]
    objectives = adapters.adapt_objectives(course, _material_rows(), grade=7)
    assert len(objectives) == 1
    assert objectives[0]["unit"] == "七年级上册 第三章 代数式"
    assert objectives[0]["source_locator"] == "课标 PDF 页 62／印刷页 55"
    assert objectives[0]["verb_level"] == "apply"


def test_nodes_json_cells() -> None:
    nodes = adapters.adapt_nodes(
        [
            {
                "节点编号": "N01", "模拟测验日期": "2026-01-20",
                "已教及测量主题": "T01、T02",
                "说明": "模拟上学期期末：说明文字",
                "可用题目编号": "Q001、Q002",
            }
        ]
    )
    assert nodes[0]["title"] == "模拟上学期期末"
    assert json.loads(nodes[0]["taught_objective_ids_json"]) == ["OBJ-7M-01", "OBJ-7M-02"]
    assert json.loads(nodes[0]["available_material_ids_json"]) == ["M-001", "M-002"]
