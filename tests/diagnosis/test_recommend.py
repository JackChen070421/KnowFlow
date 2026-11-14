"""Task-3 unit and integration checks on the synthetic canonical package."""

from __future__ import annotations

import json

from knowflow.cli import main
from knowflow.diagnosis.mastery import DiagnosisConfig
from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.diagnosis.profiles import build_student_profile
from knowflow.recommend.catalog import build_catalog
from knowflow.recommend.pipeline import recommend_run
from knowflow.recommend.rules import recommend_profile
from knowflow.recommend.validation import validate_recommendation, validate_saved_recommendations

STAMP = "2026-11-14T18:00:00+08:00"


def profile(bundle, sid="S001", nid="N02", config=None):
    return build_student_profile(
        bundle,
        next(s for s in bundle["students"] if s["student_id"] == sid),
        next(n for n in bundle["nodes"] if n["node_id"] == nid),
        config or DiagnosisConfig(),
    )


def knowledge_base(bundle):
    objectives = []
    knowledge = []
    for index, row in enumerate(bundle["knowledge"]):
        objectives.append(
            {
                "objective_id": row["objective_id"],
                "subject": "math",
                "grade": 7,
                "theme": row["objective_id"],
                "unit": "",
                "objective_text": row["objective_id"],
                "verb_level": "apply",
                "source_material_id": None,
                "source_locator": "synthetic",
            }
        )
        knowledge.append(
            {
                "knowledge_id": row["knowledge_id"],
                "objective_id": row["objective_id"],
                "parent_id": None,
                "name": row["name"],
                "level": "knowledge",
                "cognitive_type": "procedure",
                "description": None,
                "sort_order": index,
            }
        )
    # De-duplicate objective rows while keeping deterministic order.
    objectives = list({row["objective_id"]: row for row in objectives}.values())

    materials, qmatrix = [], []
    for material in bundle["materials"]:
        materials.append(
            {
                "material_id": material["material_id"],
                "title": material["material_id"],
                "body": "synthetic body",
                "material_type": "assessment",
                "item_format": "blank",
                "difficulty": None,
                "objective_id": material["objective_id"],
                "options_json": None,
                "answer_key": "synthetic",
                "explanation": "synthetic explanation",
                "rubric_json": json.dumps(
                    [
                        {
                            "id": point["point_id"],
                            "text": point["label"],
                            "points": point["max_score"],
                        }
                        for point in material["rubric"]
                    ],
                    ensure_ascii=False,
                ),
                "attachments_json": None,
                "est_minutes": None,
                "source": "synthetic",
                "license": "synthetic",
            }
        )
        for knowledge_id in material["knowledge_ids"]:
            qmatrix.append(
                {
                    "material_id": material["material_id"],
                    "knowledge_id": knowledge_id,
                    "weight": 1.0,
                    "difficulty": None,
                    "item_type": "assessment",
                    "is_primary": True,
                }
            )

    for offset, objective_id in enumerate(sorted({row["objective_id"] for row in knowledge})):
        material_id = f"M-{101 + offset}"
        materials.append(
            {
                "material_id": material_id,
                "title": f"{objective_id} 学习卡",
                "body": "synthetic explanation",
                "material_type": "explain",
                "item_format": None,
                "difficulty": None,
                "objective_id": objective_id,
                "options_json": None,
                "answer_key": None,
                "explanation": "synthetic explanation",
                "rubric_json": None,
                "attachments_json": None,
                "est_minutes": None,
                "source": "synthetic",
                "license": "synthetic",
            }
        )
        for row in knowledge:
            if row["objective_id"] == objective_id:
                qmatrix.append(
                    {
                        "material_id": material_id,
                        "knowledge_id": row["knowledge_id"],
                        "weight": 1.0,
                        "difficulty": None,
                        "item_type": "explain",
                        "is_primary": False,
                    }
                )

    edges = [
        {
            "from_id": row["objective_id"],
            "to_id": row["knowledge_id"],
            "edge_type": "contains",
            "weight": 1.0,
            "note": "synthetic",
        }
        for row in knowledge
    ]
    return {
        "schema_version": "1.0.0",
        "dataset_id": bundle["dataset_id"],
        "generated_at": STAMP,
        "subject": "math",
        "grade": 7,
        "counts": {
            "objective_count": len(objectives),
            "knowledge_count": len(knowledge),
            "material_count": len(materials),
            "qmatrix_count": len(qmatrix),
            "edge_count": len(edges),
        },
        "objectives": objectives,
        "knowledge": knowledge,
        "materials": materials,
        "qmatrix": qmatrix,
        "edges": edges,
    }


def recommendation(bundle, sid, config=None):
    catalog = build_catalog(knowledge_base(bundle))
    node = next(node for node in bundle["nodes"] if node["node_id"] == "N02")
    return (
        recommend_profile(
            profile(bundle, sid, config=config),
            catalog,
            set(node["material_ids"]),
            bundle["records"],
            STAMP,
            "a" * 64,
        ),
        catalog,
        set(node["material_ids"]),
    )


def test_score_point_gap_uses_failed_criterion_and_explain(bundle):
    rec, _, _ = recommendation(bundle, "S002", DiagnosisConfig(min_evidence=2))
    assert rec["node_id"] == "N02"
    assert rec["plan"], "S002 has a score-point gap on K-02"
    item = next(item for item in rec["plan"] if item["issue_id"] == "IS-002-02")
    assert item["activity_type"] == "consolidate"
    assert "M-102" in item["material_ids"]
    assert item["primary_material_id"] in item["material_ids"]
    assert "步骤二" in item["reason"]
    assert 1 <= item["difficulty"] <= 5
    assert 1 <= item["est_minutes"] <= 120


def test_insufficient_evidence_becomes_unattempted_probe(bundle):
    rec, _, node_available = recommendation(bundle, "S004")
    assert rec["probe_plan"]["needed"] is True
    assert rec["probe_plan"]["items"]
    assert all(material in node_available for material in rec["probe_plan"]["items"])
    assert all(item["activity_type"] == "probe" for item in rec["plan"])
    assert "未掌握" in rec["plan"][0]["reason"]


def test_scope_unknown_gets_no_fabricated_plan(bundle):
    rec, _, _ = recommendation(bundle, "S006")
    assert rec["plan"] == []
    assert rec["probe_plan"] == {
        "needed": False,
        "items": [],
        "purpose": "该生在该节点没有参与记录，先确认参与范围，不据此判断未掌握。",
    }


def test_mastered_student_has_no_forced_practice(bundle):
    catalog = build_catalog(knowledge_base(bundle))
    p = profile(bundle, "S005")
    p["issues"] = []
    node = next(node for node in bundle["nodes"] if node["node_id"] == "N02")
    rec = recommend_profile(
        p,
        catalog,
        set(node["material_ids"]),
        bundle["records"],
        STAMP,
        "a" * 64,
    )
    assert rec["plan"] == []
    assert rec["probe_plan"]["needed"] is False


def test_validator_rejects_unlocked_numbers(bundle):
    rec, catalog, node_available = recommendation(bundle, "S002")
    rec["plan"][0]["reason"] = rec["plan"][0]["reason"] + " 99 次"
    errors = validate_recommendation(rec, profile(bundle, "S002"), catalog, node_available, bundle["records"])
    assert any("unlocked numbers" in error for error in errors)


def test_validator_rejects_attempted_probe_and_unknown_material(bundle):
    rec, catalog, node_available = recommendation(bundle, "S004")
    rec["probe_plan"]["items"] = ["M-005"]
    rec["plan"][0]["material_ids"] = ["M-999"]
    rec["plan"][0]["primary_material_id"] = "M-999"
    errors = validate_recommendation(rec, profile(bundle, "S004"), catalog, node_available, bundle["records"])
    assert any("unknown material" in error for error in errors)
    assert any("was already attempted" in error or "already attempted" in error for error in errors)


def test_recommend_run_and_verify_are_self_contained(bundle, tmp_path):
    run_dir = tmp_path / "run"
    run_diagnosis(bundle, run_dir, DiagnosisConfig(), "latest")
    kb_path = tmp_path / "knowledge_base.json"
    kb_path.write_text(json.dumps(knowledge_base(bundle), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "recommend"

    result = recommend_run(run=str(run_dir), knowledge=str(kb_path), output=str(out))
    assert result["gate"] == "pass"
    assert result["students"] == len(bundle["students"])
    assert (out / "inputs" / "diagnosis_input.json").is_file()
    assert (out / "knowledge_base.json").is_file()

    report = validate_saved_recommendations(out)
    assert report["gate"] == "pass"
    assert report["summary"]["failed"] == 0

    assert main(["recommend", "--run", str(run_dir), "--knowledge", str(kb_path), "--output", str(tmp_path / "cli")]) == 0
    assert main(["verify-recommend", "--run", str(tmp_path / "cli")]) == 0
