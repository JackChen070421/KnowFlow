"""Synthetic canonical tables for the review tests.

The data layer is already resolved upstream, so these fixtures start after it:
ten CSV files shaped exactly like ``data/interim/``, with answer keys chosen to
exercise the review rules (literal match, notation variant, rubric mismatch,
pending answer that must never be graded).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

STAMP = "2026-11-16T09:00:00+08:00"
DATASET = "synthetic-review"

STUDENTS = [("S001", "G1"), ("S002", "G1"), ("S003", "G1"), ("S004", "G2")]

KNOWLEDGE = [
    ("K-01", "OBJ-7M-01", "整式化简"),
    ("K-02", "OBJ-7M-02", "整式运算"),
]

# material_id, knowledge_id, objective_id, item_format, answer_key, rubric
MATERIALS = [
    ("M-001", "K-01", "OBJ-7M-01", "blank", "SECRET-9", [("答案正确", 1)]),
    ("M-002", "K-01", "OBJ-7M-01", "blank", "-2", [("答案正确", 1)]),
    (
        "M-003",
        "K-02",
        "OBJ-7M-02",
        "solution",
        "4a-7b",
        [("正确去括号", 1), ("合并同类项", 1), ("写出正确结果", 1)],
    ),
    ("M-004", "K-02", "OBJ-7M-02", "blank", "14", [("答案正确", 1)]),
    ("M-005", "K-02", "OBJ-7M-02", "blank", "5", [("答案正确", 1)]),
    ("M-006", "K-02", "OBJ-7M-02", "blank", "7", [("答案正确", 1)]),
    ("M-007", "K-01", "OBJ-7M-01", "blank", "3", [("答案正确", 1)]),
    ("M-008", "K-01", "OBJ-7M-01", "blank", "8", [("答案正确", 1)]),
]

# record_id, student, material, status, score, answer, rubric points
RECORDS = [
    ("R-0001", "S001", "M-001", "已评分", 0, "SECRET-9", {"M-001P1": 0}),
    ("R-0002", "S001", "M-002", "已评分", 1, "x=-2", {"M-002P1": 1}),
    ("R-0003", "S002", "M-003", "已评分", 3, "4a+7b", {"M-003P1": 1, "M-003P2": 1, "M-003P3": 0}),
    ("R-0004", "S002", "M-004", "待评分", None, "14", None),
    ("R-0005", "S003", "M-005", "已评分", 0, "6", {"M-005P1": 0}),
    ("R-0006", "S003", "M-006", "已评分", 1, "7", {"M-006P1": 1}),
    ("R-0007", "S004", "M-007", "已评分", 0, "3", {"M-007P1": 0}),
    ("R-0008", "S001", "M-008", "已评分", 1, "8", {"M-008P1": 1}),
]

OBJECTIVES = [
    ("OBJ-7M-01", "整式加减", "能进行整式的加减运算"),
    ("OBJ-7M-02", "整式乘除", "能进行简单的整式乘法"),
]


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _rubric(material_id: str, points: list[tuple[str, int]]) -> str:
    return json.dumps(
        [{"id": f"{material_id}P{i}", "text": text, "points": value} for i, (text, value) in enumerate(points, 1)],
        ensure_ascii=False,
    )


def max_score(material_id: str) -> int:
    points = next(item[5] for item in MATERIALS if item[0] == material_id)
    return sum(value for _, value in points)


def write_dataset(base: Path) -> Path:
    _write(
        base / "students.csv",
        [
            {"student_id": sid, "group_id": group, "grade": "7", "stage": "middle", "notes": ""}
            for sid, group in STUDENTS
        ],
        ["student_id", "group_id", "grade", "stage", "notes"],
    )
    _write(
        base / "objectives.csv",
        [
            {
                "objective_id": oid,
                "subject": "math",
                "grade": "7",
                "theme": title,
                "unit": title,
                "objective_text": text,
                "verb_level": "apply",
                "source_material_id": "",
                "source_locator": "synthetic",
                "notes": "合成样例",
            }
            for oid, title, text in OBJECTIVES
        ],
        [
            "objective_id",
            "subject",
            "grade",
            "theme",
            "unit",
            "objective_text",
            "verb_level",
            "source_material_id",
            "source_locator",
            "notes",
        ],
    )
    _write(
        base / "knowledge.csv",
        [
            {
                "knowledge_id": kid,
                "objective_id": oid,
                "parent_id": "",
                "name": name,
                "level": "knowledge",
                "cognitive_type": "procedure",
                "description": "",
                "sort_order": str(index),
            }
            for index, (kid, oid, name) in enumerate(KNOWLEDGE)
        ],
        [
            "knowledge_id",
            "objective_id",
            "parent_id",
            "name",
            "level",
            "cognitive_type",
            "description",
            "sort_order",
        ],
    )
    _write(
        base / "materials.csv",
        [
            {
                "material_id": mid,
                "title": f"{mid} 合成题",
                "body": "合成题干",
                "material_type": "assessment",
                "difficulty": "",
                "objective_id": oid,
                "options_json": "",
                "answer_key": key,
                "attachments_json": "",
                "est_minutes": "2",
                "source": "synthetic",
                "license": "synthetic",
                "item_format": fmt,
                "explanation": "合成解析",
                "rubric_json": _rubric(mid, points),
            }
            for mid, _, oid, fmt, key, points in MATERIALS
        ],
        [
            "material_id",
            "title",
            "body",
            "material_type",
            "difficulty",
            "objective_id",
            "options_json",
            "answer_key",
            "attachments_json",
            "est_minutes",
            "source",
            "license",
            "item_format",
            "explanation",
            "rubric_json",
        ],
    )
    _write(
        base / "qmatrix.csv",
        [
            {
                "material_id": mid,
                "knowledge_id": kid,
                "weight": "1.0",
                "difficulty": "",
                "item_type": "assessment",
                "is_primary": "true",
            }
            for mid, kid, _, _, _, _ in MATERIALS
        ],
        ["material_id", "knowledge_id", "weight", "difficulty", "item_type", "is_primary"],
    )
    _write(
        base / "nodes.csv",
        [
            {
                "node_id": "N01",
                "title": "合成测验",
                "exam_date": "2026-01-20",
                "taught_objective_ids_json": json.dumps([item[0] for item in OBJECTIVES]),
                "available_material_ids_json": json.dumps([item[0] for item in MATERIALS]),
                "note": "",
            }
        ],
        [
            "node_id",
            "title",
            "exam_date",
            "taught_objective_ids_json",
            "available_material_ids_json",
            "note",
        ],
    )
    records = []
    for rid, sid, mid, status, score, answer, points in RECORDS:
        records.append(
            {
                "record_id": rid,
                "student_id": sid,
                "material_id": mid,
                "node_id": "N01",
                "assigned": "true",
                "attempted": "true" if status != "未作答" else "false",
                "score": "" if score is None else str(score),
                "max_score": str(max_score(mid)),
                "is_correct": ""
                if score is None
                else ("true" if score == max_score(mid) else "false"),
                "answer": answer,
                "rubric_scores_json": "" if points is None else json.dumps(points),
                "steps_json": "",
                "submitted_at": "2026-01-20T09:00:00+08:00",
                "duration_seconds": "",
                "attempt_no": "1",
                "source": DATASET,
            }
        )
    _write(
        base / "records.csv",
        records,
        [
            "record_id",
            "student_id",
            "material_id",
            "node_id",
            "assigned",
            "attempted",
            "score",
            "max_score",
            "is_correct",
            "answer",
            "rubric_scores_json",
            "steps_json",
            "submitted_at",
            "duration_seconds",
            "attempt_no",
            "source",
        ],
    )
    _write(
        base / "record_details.csv",
        [
            {
                "csv_record_number": str(index + 2),
                "source_record_id": f"DR{index + 1:04d}",
                "record_id": record["record_id"],
                "student_id": record["student_id"],
                "material_id": record["material_id"],
                "node_id": record["node_id"],
                "kept": "true",
                "final_answer": record["answer"],
                "solution_process": "",
                "scoring_point_scores": "",
            }
            for index, record in enumerate(records)
        ],
        [
            "csv_record_number",
            "source_record_id",
            "record_id",
            "student_id",
            "material_id",
            "node_id",
            "kept",
            "final_answer",
            "solution_process",
            "scoring_point_scores",
        ],
    )
    _write(
        base / "edges.csv",
        [
            {
                "from_id": oid,
                "to_id": kid,
                "edge_type": "contains",
                "weight": "1.0",
                "note": "课标包含知识点",
            }
            for kid, oid, _ in KNOWLEDGE
        ],
        ["from_id", "to_id", "edge_type", "weight", "note"],
    )
    _write(
        base / "tasks.csv",
        [],
        [
            "task_id",
            "title",
            "goal",
            "target_scope",
            "target_ids_json",
            "material_scope_json",
            "constraints_json",
            "expected_output",
        ],
    )
    correct = wrong = pending = 0
    for _rid, _sid, mid, _status, score, _answer, _points in RECORDS:
        if score is None:
            pending += 1
        elif score == max_score(mid):
            correct += 1
        else:
            wrong += 1
    quality = {
        "schema_version": "0.4.0",
        "dataset_id": DATASET,
        "generated_at": STAMP,
        "input_files": [
            {
                "path": "4_赛题数据/模拟学情数据/作答记录.csv",
                "sha256": "0" * 64,
                "rows": len(records),
            }
        ],
        "total_records": len(records),
        "duplicates_removed": 0,
        "records_by_state": {
            "observed_correct": correct,
            "observed_wrong": wrong,
            "assigned_not_attempted": 0,
            "pending": pending,
            "unobserved": 0,
        },
        "missing": {"students_without_records": 0, "items_without_records": 0, "empty_answers": 0},
        "anomalies": [],
        "field_quality": [],
        "handling_rules": ["synthetic fixture: revisions already resolved upstream"],
    }
    (base / "data_quality_report.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return base


@pytest.fixture()
def review_root(tmp_path: Path) -> Path:
    write_dataset(tmp_path / "interim" / DATASET)
    return tmp_path


@pytest.fixture()
def bundle(review_root: Path) -> dict:
    from knowflow.diagnosis.pipeline import build_bundle

    data, _ = build_bundle(DATASET, root=review_root / "interim")
    return data


@pytest.fixture()
def review_context(review_root: Path):
    from knowflow.review.pipeline import build_context, load_report, scan_dataset

    scan_dataset(
        DATASET,
        root=review_root / "interim",
        output=review_root / "review",
        ledger_root=review_root,
    )
    report = load_report(review_root / "review")
    return build_context(report, review_root / "review", "official")


@pytest.fixture()
def tables(review_root: Path) -> dict:
    from knowflow.diagnosis.pipeline import load_canonical

    _, data, _ = load_canonical(DATASET, review_root / "interim")
    return data


@pytest.fixture()
def knowledge_base(review_root: Path) -> dict:
    from knowflow.knowledge.pipeline import build_knowledge_base

    return build_knowledge_base(review_root / "interim" / DATASET, DATASET)

