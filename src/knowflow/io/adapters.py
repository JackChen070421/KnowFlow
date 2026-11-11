"""Official row → canonical row adapters (pure functions).

Each ``adapt_*`` takes rows as ``dict[str, str]`` (official column names) and
returns canonical rows matching ``schemas/input/*.schema.json``.  Nothing here
reads files or mutates global state, so the whole mapping is unit-testable.
"""

from __future__ import annotations

import json
import re

from . import mapping
from .errors import AdaptError

RUBRIC_LINE = re.compile(
    r"^(?P<mid>[A-Z][0-9]{3})P(?P<seq>[0-9]+)\s+(?P<text>.+?)\s+(?P<points>[0-9]+)\s*分\s*$"
)
RUBRIC_SCORE = re.compile(r"^(?P<mid>[A-Z][0-9]{3})P(?P<seq>[0-9]+)$")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def parse_options(value: str | None) -> str | None:
    """Multi-line ``选项`` → JSON array, keeping the ``A.`` labels verbatim."""

    lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
    return _json(lines) if lines else None


def parse_rubric(value: str | None, official_mid: str) -> str | None:
    """``评分点`` → JSON array of ``{id, text, points}`` with canonical IDs."""

    items: list[dict[str, object]] = []
    for index, line in enumerate((value or "").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        match = RUBRIC_LINE.match(line)
        if match is None:
            raise AdaptError(
                f"{official_mid}: 评分点第 {index} 行格式无法解析"
                "（不回显原文，避免题目/作答内容进入日志）"
            )
        if match.group("mid") != official_mid:
            raise AdaptError(
                f"{official_mid}: 评分点第 {index} 行的材料编号与所在材料不一致"
            )
        items.append(
            {
                "id": f"{mapping.material_id_for(official_mid)}P{match.group('seq')}",
                "text": match.group("text").strip(),
                "points": int(match.group("points")),
            }
        )
    return _json(items) if items else None


def parse_rubric_scores(value: str | None) -> str | None:
    """``Q043P1=1；Q043P2=0`` → ``{"M-043P1":1,"M-043P2":0}``."""

    scores: dict[str, int] = {}
    for index, part in enumerate(re.split(r"[；;]", value or ""), start=1):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise AdaptError(
                f"评分点得分第 {index} 段缺少 '='（不回显原文）"
            )
        key, raw = part.split("=", 1)
        match = RUBRIC_SCORE.match(key.strip())
        if match is None:
            raise AdaptError(f"评分点得分第 {index} 段的编号格式无法解析（不回显原文）")
        scores[f"{mapping.material_id_for(match.group('mid'))}P{match.group('seq')}"] = int(
            raw.strip()
        )
    return _json(scores) if scores else None


def rubric_sum(value: str | None) -> int | None:
    """Sum of rubric points, or ``None`` when the cell is empty."""

    total = 0
    found = False
    for part in re.split(r"[；;]", value or ""):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            return None
        try:
            total += int(part.split("=", 1)[1].strip())
        except ValueError:
            return None
        found = True
    return total if found else None


def split_steps(value: str | None) -> str | None:
    lines = [line.rstrip() for line in (value or "").splitlines() if line.strip()]
    return _json(lines) if lines else None


def adapt_objectives(
    course_rows: list[dict[str, str]],
    material_rows: list[dict[str, str]],
    grade: int,
) -> list[dict[str, object]]:
    """Three objectives, one per theme. ``unit`` comes from the textbook slice."""

    units: dict[str, str] = {}
    for row in material_rows:
        official_id = row["材料编号"].strip()
        if not official_id.startswith("B"):
            continue
        objective_id = mapping.B_SLICE_OBJECTIVE.get(official_id)
        if objective_id:
            units[objective_id] = row["题干或内容"].strip()

    themes: dict[str, dict[str, str]] = {}
    for row in course_rows:
        themes.setdefault(row["主题编号"].strip(), row)

    objectives: list[dict[str, object]] = []
    for theme_id, row in sorted(themes.items()):
        objective_id = mapping.objective_for_theme(theme_id)
        locator = row["课标文件页／正文页"].strip()
        pdf_page, _, print_page = locator.partition("／")
        source_locator = (
            f"课标 PDF 页 {pdf_page}／印刷页 {print_page}" if print_page else locator
        )
        objectives.append(
            {
                "objective_id": objective_id,
                "subject": "math",
                "grade": int(grade),
                "theme": row["主题"].strip(),
                "unit": units.get(objective_id) or row["教材正文页"].strip(),
                "objective_text": row["主题目标"].strip(),
                "verb_level": "apply",
                "source_material_id": None,
                "source_locator": source_locator,
                "notes": (
                    "主题目标原文取自 4_赛题数据/模拟学情数据/课程要求.csv；"
                    "课标 PDF 为扫描件，逐字校对待 OCR/人工。"
                ),
            }
        )
    return objectives


def adapt_knowledge(course_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    knowledge: list[dict[str, object]] = []
    order: dict[str, int] = {}
    for row in course_rows:
        indicator = row["指标编号"].strip()
        knowledge_id = mapping.knowledge_for_indicator(indicator)
        objective_id = mapping.objective_for_theme(row["主题编号"].strip())
        sort_order = order.get(objective_id, 0)
        order[objective_id] = sort_order + 1
        knowledge.append(
            {
                "knowledge_id": knowledge_id,
                "objective_id": objective_id,
                "parent_id": None,
                "name": row["观察指标"].strip(),
                "level": "knowledge",
                "cognitive_type": mapping.COGNITIVE_TYPE[indicator],
                "description": None,
                "sort_order": sort_order,
            }
        )
    return knowledge


def adapt_materials(material_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    materials: list[dict[str, object]] = []
    for row in material_rows:
        official_id = row["材料编号"].strip()
        material_id = mapping.material_id_for(official_id)
        category = row["材料类型"].strip()
        material_type = mapping.MATERIAL_TYPE.get(category)
        if material_type is None:
            raise AdaptError(f"{official_id}: 未知材料类型 {category!r}")

        theme = _text(row["主题编号"])
        if theme is not None:
            objective_id: str | None = mapping.objective_for_theme(theme)
        else:
            objective_id = mapping.B_SLICE_OBJECTIVE.get(official_id)
            if official_id.startswith("B") and official_id not in mapping.B_SLICE_OBJECTIVE:
                raise AdaptError(f"{official_id}: 教材切片不在映射表中")

        item_format = mapping.ITEM_FORMAT.get(_text(row["题型"]) or "")
        if material_type == "assessment":
            if item_format is None:
                raise AdaptError(f"{official_id}: 题目缺少题型")
            if theme is None:
                raise AdaptError(f"{official_id}: 题目缺少主题")
            if not (row["指标编号"] or "").strip():
                raise AdaptError(f"{official_id}: 题目缺少指标编号")

        if material_type == "assessment":
            label = _text(row["题型"]) or "题目"
        elif material_type == "explain":
            label = "学习卡"
        else:
            label = "教材切片"

        source = _text(row["来源或资料文件"])
        attachments = [source] if material_type == "reference" and source else None

        materials.append(
            {
                "material_id": material_id,
                "title": f"{official_id} {label}",
                "body": row["题干或内容"].strip(),
                "material_type": material_type,
                "item_format": item_format,
                "difficulty": None,
                "objective_id": objective_id,
                "options_json": parse_options(row["选项"]),
                "answer_key": _text(row["参考答案"]),
                "explanation": _text(row["参考解析"]),
                "rubric_json": parse_rubric(row["评分点"], official_id),
                "attachments_json": _json(attachments) if attachments else None,
                "est_minutes": None,
                "source": source,
                "license": (
                    "仅供个人学习使用（资料包声明）"
                    if material_type == "reference"
                    else "仅限本次比赛使用"
                ),
            }
        )
    return materials


def adapt_qmatrix(material_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in material_rows:
        official_id = row["材料编号"].strip()
        material_id = mapping.material_id_for(official_id)
        material_type = mapping.MATERIAL_TYPE.get(row["材料类型"].strip())
        if material_type == "reference":
            continue
        indicators = mapping.split_ids(row["指标编号"])
        if not indicators:
            raise AdaptError(f"{official_id}: 缺少指标编号，无法建立 Q-matrix")
        item_type = "assessment" if material_type == "assessment" else "explain"
        is_primary = material_type == "assessment"
        for indicator in indicators:
            rows.append(
                {
                    "material_id": material_id,
                    "knowledge_id": mapping.knowledge_for_indicator(indicator),
                    "weight": 1.0,
                    "difficulty": None,
                    "item_type": item_type,
                    "is_primary": is_primary,
                }
            )
    return rows


def adapt_edges(course_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for row in course_rows:
        objective_id = mapping.objective_for_theme(row["主题编号"].strip())
        knowledge_id = mapping.knowledge_for_indicator(row["指标编号"].strip())
        key = (objective_id, knowledge_id)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "from_id": objective_id,
                "to_id": knowledge_id,
                "edge_type": "contains",
                "weight": 1.0,
                "note": "课程要求：指标隶属主题",
            }
        )
    return edges


def adapt_students(student_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    students: list[dict[str, object]] = []
    for row in student_rows:
        students.append(
            {
                "student_id": mapping.student_id_for(row["学生编号"]),
                "group_id": mapping.group_id_for(row["模拟班级编号"]),
                "grade": int(row["年级"]),
                "stage": "middle",
                "notes": None,
            }
        )
    return students


def adapt_nodes(node_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    nodes: list[dict[str, object]] = []
    for row in node_rows:
        note = row["说明"].strip()
        title = note.split("：", 1)[0] if "：" in note else row["节点编号"].strip()
        taught = [
            mapping.objective_for_theme(theme)
            for theme in mapping.split_ids(row["已教及测量主题"])
        ]
        available = [
            mapping.material_id_for(material)
            for material in mapping.split_ids(row["可用题目编号"])
        ]
        nodes.append(
            {
                "node_id": row["节点编号"].strip(),
                "title": title,
                "exam_date": row["模拟测验日期"].strip(),
                "taught_objective_ids_json": _json(taught),
                "available_material_ids_json": _json(available),
                "note": note,
            }
        )
    return nodes
