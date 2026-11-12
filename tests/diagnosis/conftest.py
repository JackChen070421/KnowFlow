"""Synthetic canonical tables for diagnosis tests.

The data layer already resolves revisions and keeps verbatim evidence, so these
fixtures start *after* it: ten CSV files shaped exactly like ``data/interim/``.
No real data, no raw answer text beyond the explicit evidence layer.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

STAMP = "2026-11-10T12:00:00+08:00"
DATASET = "synthetic-task2"
ANSWER_TEXT = "synthetic-private-answer"
STEPS_TEXT = "synthetic-private-steps"

STUDENTS = [
    ("S001", "G1"),
    ("S002", "G1"),
    ("S003", "G1"),
    ("S004", "G2"),
    ("S005", "G2"),
    ("S006", "G2"),
]

KNOWLEDGE = [
    ("K-01", "OBJ-7M-01", "有理数与代数式"),
    ("K-02", "OBJ-7M-02", "一元一次方程"),
    ("K-03", "OBJ-7M-03", "一元一次不等式"),
]

MATERIALS = [
    ("M-001", "K-01", "OBJ-7M-01", 2),
    ("M-002", "K-01", "OBJ-7M-01", 2),
    ("M-003", "K-02", "OBJ-7M-02", 2),
    ("M-004", "K-02", "OBJ-7M-02", 2),
    ("M-005", "K-03", "OBJ-7M-03", 2),
    ("M-006", "K-03", "OBJ-7M-03", 2),
]

NODES = [
    ("N01", "2026-01-20", ["OBJ-7M-01", "OBJ-7M-02"]),
    ("N02", "2026-06-17", ["OBJ-7M-01", "OBJ-7M-02", "OBJ-7M-03"]),
]

# (record_id, student, material, node, attempted, score, comment)
RECORDS = [
    ("R-0001", "S001", "M-001", "N02", True, 2, "correct"),
    ("R-0002", "S001", "M-003", "N02", True, 1, "partial: P2 missing"),
    ("R-0003", "S001", "M-001", "N01", True, 2, "correct"),
    ("R-0004", "S001", "M-002", "N01", True, None, "pending"),
    ("R-0005", "S001", "M-004", "N01", False, None, "not attempted"),
    ("R-0006", "S002", "M-001", "N02", True, 0, "wrong"),
    ("R-0007", "S002", "M-002", "N02", True, 2, "correct"),
    ("R-0008", "S002", "M-003", "N02", True, 2, "correct"),
    ("R-0009", "S002", "M-004", "N02", True, 0, "wrong"),
    ("R-0010", "S003", "M-001", "N01", True, 2, "correct"),
    ("R-0011", "S004", "M-005", "N02", True, 1, "partial: P2 missing"),
    ("R-0012", "S005", "M-001", "N02", True, 2, "correct"),
    ("R-0013", "S005", "M-002", "N02", True, 2, "correct"),
    ("R-0014", "S005", "M-003", "N02", True, 2, "correct"),
    ("R-0015", "S005", "M-004", "N02", True, 2, "correct"),
    ("R-0016", "S005", "M-005", "N02", True, 2, "correct"),
    ("R-0017", "S005", "M-006", "N02", True, 2, "correct"),
]


def _rubric(material_id: str) -> list[dict]:
    return [
        {"id": f"{material_id}P1", "text": "步骤一", "points": 1},
        {"id": f"{material_id}P2", "text": "步骤二", "points": 1},
    ]


def _points(material_id: str, score: float | None) -> dict:
    if score is None:
        return {}
    return {
        f"{material_id}P1": 1 if score >= 1 else 0,
        f"{material_id}P2": 1 if score >= 2 else 0,
    }


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_canonical(base: Path) -> Path:
    _write(
        base / "students.csv",
        [
            {"student_id": s, "group_id": g, "grade": "7", "stage": "middle", "notes": ""}
            for s, g in STUDENTS
        ],
        ["student_id", "group_id", "grade", "stage", "notes"],
    )
    _write(
        base / "knowledge.csv",
        [
            {
                "knowledge_id": k,
                "objective_id": o,
                "parent_id": "",
                "name": n,
                "level": "knowledge",
                "cognitive_type": "procedure",
                "description": "",
                "sort_order": str(i),
            }
            for i, (k, o, n) in enumerate(KNOWLEDGE)
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
                "item_format": "blank",
                "difficulty": "",
                "objective_id": objective,
                "options_json": "",
                "answer_key": "合成答案",
                "explanation": "合成解析",
                "rubric_json": json.dumps(_rubric(mid), ensure_ascii=False),
                "attachments_json": "",
                "est_minutes": "2",
                "source": "synthetic",
                "license": "synthetic",
            }
            for mid, _, objective, _ in MATERIALS
        ],
        [
            "material_id",
            "title",
            "body",
            "material_type",
            "item_format",
            "difficulty",
            "objective_id",
            "options_json",
            "answer_key",
            "explanation",
            "rubric_json",
            "attachments_json",
            "est_minutes",
            "source",
            "license",
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
            for mid, kid, _, _ in MATERIALS
        ],
        ["material_id", "knowledge_id", "weight", "difficulty", "item_type", "is_primary"],
    )
    _write(
        base / "nodes.csv",
        [
            {
                "node_id": node,
                "title": f"模拟测验 {node}",
                "exam_date": date,
                "taught_objective_ids_json": json.dumps(taught),
                "available_material_ids_json": json.dumps([m[0] for m in MATERIALS]),
                "note": "",
            }
            for node, date, taught in NODES
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
    for rid, sid, mid, node, attempted, score, _ in RECORDS:
        records.append(
            {
                "record_id": rid,
                "student_id": sid,
                "material_id": mid,
                "node_id": node,
                "assigned": "true",
                "attempted": "true" if attempted else "false",
                "score": "" if score is None else str(score),
                "max_score": "2",
                "is_correct": ""
                if score is None
                else ("true" if score == 2 else "false"),
                "answer": ANSWER_TEXT,
                "rubric_scores_json": ""
                if score is None
                else json.dumps(_points(mid, score)),
                "steps_json": json.dumps([STEPS_TEXT]),
                "submitted_at": "2026-06-17T09:00:00+08:00",
                "duration_seconds": "",
                "attempt_no": "1",
                "source": DATASET,
            }
        )
    fields = [
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
    ]
    _write(base / "records.csv", records, fields)

    details = []
    row_number = 2
    for record in records:
        details.append(
            {
                "csv_record_number": str(row_number),
                "source_record_id": f"DR{row_number - 1:04d}",
                "record_id": record["record_id"],
                "student_id": record["student_id"],
                "material_id": record["material_id"],
                "node_id": record["node_id"],
                "kept": "true",
                "final_answer": ANSWER_TEXT,
                "solution_process": STEPS_TEXT,
                "scoring_point_scores": "",
            }
        )
        row_number += 1
    details.append(
        {
            "csv_record_number": str(row_number),
            "source_record_id": f"DR{row_number - 1:04d}",
            "record_id": "R-0002",
            "student_id": "S001",
            "material_id": "M-003",
            "node_id": "N02",
            "kept": "false",
            "final_answer": ANSWER_TEXT,
            "solution_process": STEPS_TEXT,
            "scoring_point_scores": "",
        }
    )
    _write(
        base / "record_details.csv",
        details,
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
    for name in ("objectives.csv", "edges.csv", "tasks.csv"):
        _write(base / name, [], ["placeholder"])

    quality = {
        "schema_version": "0.4.0",
        "dataset_id": DATASET,
        "generated_at": STAMP,
        "input_files": [
            {
                "path": "4_赛题数据/模拟学情数据/作答记录.csv",
                "sha256": "0" * 64,
                "rows": len(details),
            }
        ],
        "total_records": len(records),
        "duplicates_removed": 1,
        "records_by_state": {
            "observed_correct": sum(
                1 for _, _, _, _, a, s, _ in RECORDS if a and s == 2
            ),
            "observed_wrong": sum(1 for _, _, _, _, a, s, _ in RECORDS if a and s is not None and s < 2),
            "assigned_not_attempted": sum(1 for _, _, _, _, a, _, _ in RECORDS if not a),
            "pending": sum(1 for _, _, _, _, a, s, _ in RECORDS if a and s is None),
            "unobserved": 0,
        },
        "missing": {
            "students_without_records": 1,
            "items_without_records": 0,
            "empty_answers": 0,
        },
        "anomalies": [],
        "field_quality": [],
        "handling_rules": ["synthetic fixture: revisions already resolved upstream"],
    }
    (base / "data_quality_report.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return base


@pytest.fixture()
def canonical_root(tmp_path: Path) -> Path:
    write_canonical(tmp_path / "interim" / DATASET)
    return tmp_path / "interim"


@pytest.fixture()
def bundle(canonical_root: Path) -> dict:
    from knowflow.diagnosis.pipeline import build_bundle

    data, _ = build_bundle(DATASET, root=canonical_root)
    return data
