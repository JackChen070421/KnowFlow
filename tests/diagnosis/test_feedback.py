"""Direction 5: supplemental evidence, teacher adjustments and feedback replay."""

from __future__ import annotations

import json
from pathlib import Path

from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.diagnosis.validation import validate_saved_run
from knowflow.feedback import (
    append_event,
    apply_to_recommendation,
    make_event,
    plan_snapshot,
    state_for,
    supplemental_record,
    validate_event,
)
from knowflow.recommend.pipeline import recommend_run
from knowflow.recommend.validation import validate_saved_recommendations

STAMP = "2026-11-10T12:00:00+08:00"


def _attempt(bundle: dict, material_id: str = "M-002", score: float = 2.0, event_id: str = "EV-TEST-0001"):
    material = next(m for m in bundle["materials"] if m["material_id"] == material_id)
    return make_event(
        event_type="supplemental_attempt",
        student_id="S001",
        node_id="N02",
        actor="student",
        material_id=material_id,
        score=score,
        max_score=material["max_score"],
        event_id=event_id,
        created_at=STAMP,
        submitted_at=STAMP,
        source="test",
    )


def _run(tmp_path: Path, name: str, bundle: dict, **kwargs) -> Path:
    output = tmp_path / name
    run_diagnosis(bundle, output, node_id="N02", **kwargs)
    return output


def _knowledge(tmp_path: Path, bundle: dict) -> Path:
    materials = []
    qmatrix = []
    for material in bundle["materials"]:
        materials.append(
            {
                "material_id": material["material_id"],
                "title": material["material_id"],
                "body": "synthetic",
                "material_type": "assessment",
                "item_format": "blank",
                "objective_id": material["objective_id"],
                "difficulty": None,
                "est_minutes": None,
                "rubric_json": json.dumps(
                    [
                        {"id": point["point_id"], "text": point["label"], "points": point["max_score"]}
                        for point in material["rubric"]
                    ]
                ),
                "source": "",
            }
        )
        for knowledge_id in material["knowledge_ids"]:
            qmatrix.append(
                {"material_id": material["material_id"], "knowledge_id": knowledge_id, "weight": 1.0}
            )
    data = {
        "schema_version": "1.0.0",
        "dataset_id": bundle["dataset_id"],
        "generated_at": STAMP,
        "source": {"canonical_version": "0.4.0"},
        "objectives": [],
        "knowledge": [
            {
                "knowledge_id": row["knowledge_id"],
                "objective_id": row["objective_id"],
                "name": row["name"],
                "cognitive_type": row.get("cognitive_type") or "procedure",
                "sort_order": index,
            }
            for index, row in enumerate(bundle["knowledge"])
        ],
        "materials": materials,
        "qmatrix": qmatrix,
        "edges": [],
        "counts": {
            "objective_count": 0,
            "knowledge_count": len(bundle["knowledge"]),
            "material_count": len(materials),
            "qmatrix_count": len(qmatrix),
            "edge_count": 0,
        },
    }
    path = tmp_path / "knowledge_base.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _recommend(tmp_path: Path, run: Path, knowledge: Path, name: str, **kwargs) -> dict:
    output = tmp_path / name
    empty = tmp_path / "no-feedback.jsonl"
    report = recommend_run(
        run=str(run),
        knowledge=str(knowledge),
        node="N02",
        output=str(output),
        generated_at=STAMP,
        feedback=str(kwargs.pop("feedback", empty)),
        **kwargs,
    )
    if report["gate"] != "pass":
        errors = json.loads((output / "validation_report.json").read_text(encoding="utf-8"))["errors"]
        raise AssertionError("; ".join(errors[:5]))
    return json.loads((output / "nodes/N02/students/S001.json").read_text(encoding="utf-8"))


def _adjustment(rec: dict, seq: int, action: str, reason: str, event_id: str, **payload):
    item = rec["plan"][seq - 1]
    return make_event(
        event_type="teacher_adjustment",
        student_id="S001",
        node_id="N02",
        actor="teacher",
        plan_item_id=item["plan_item_id"],
        plan_version=item["plan_version"],
        action=action,
        issue_id=item["issue_id"],
        knowledge_id=item["knowledge_ids"][0],
        activity_type=item["activity_type"],
        payload=payload or None,
        reason=reason,
        snapshot=plan_snapshot(item),
        event_id=event_id,
        created_at=STAMP,
        source="test",
    )


def test_supplemental_attempt_is_validated_and_mapped_to_evidence(bundle) -> None:
    event = _attempt(bundle)
    assert validate_event(event, bundle, {"materials": {}}) == []
    material = next(m for m in bundle["materials"] if m["material_id"] == "M-002")
    record = supplemental_record(event, material)
    assert record["record_id"] == event["event_id"]
    assert record["source"] == "supplemental"
    assert record["attempted"] is True
    assert record["score"] == record["max_score"] == 2.0

    bad = _attempt(bundle, score=9.0, event_id="EV-TEST-0002")
    assert any("score exceeds" in error for error in validate_event(bad, bundle, {"materials": {}}))


def test_supplemental_diagnosis_changes_mastery_but_not_canonical(
    tmp_path, bundle, canonical_root
) -> None:
    before = len(bundle["records"])
    base = _run(tmp_path, "base", bundle)
    new = _run(tmp_path, "new", bundle, supplemental=[_attempt(bundle)], previous=base)
    assert validate_saved_run(new)["gate"] == "pass"
    manifest = json.loads((new / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["supplemental"]["records"] == 1
    stored = json.loads((new / "diagnosis_input.json").read_text(encoding="utf-8"))
    assert len(stored["records"]) == before
    supplemental = json.loads((new / "supplemental_input.json").read_text(encoding="utf-8"))
    assert supplemental["records"][0]["record_id"] == "EV-TEST-0001"
    diff = json.loads((new / "diagnosis_diff.json").read_text(encoding="utf-8"))
    changed = [entry for entry in diff["students"] if entry["student_id"] == "S001"]
    assert changed and changed[0]["mastery_changes"]
    assert changed[0]["evidence_added"] is True


def test_teacher_lock_and_replace_persist_across_versions(
    tmp_path, bundle, canonical_root
) -> None:
    # 给 K-02 加一份节点范围内的备用材料，保证低置信度巩固项有可替换空间。
    bundle["materials"].append(
        {
            "material_id": "M-007",
            "objective_id": "OBJ-7M-02",
            "max_score": 2.0,
            "rubric": [
                {"point_id": "M-007P1", "label": "步骤一", "max_score": 1.0},
                {"point_id": "M-007P2", "label": "步骤二", "max_score": 1.0},
            ],
            "knowledge_ids": ["K-02"],
        }
    )
    for node in bundle["nodes"]:
        if node["node_id"] == "N02":
            node["material_ids"] = sorted([*node["material_ids"], "M-007"])

    knowledge = _knowledge(tmp_path, bundle)
    run = _run(tmp_path, "run", bundle)
    first = _recommend(tmp_path, run, knowledge, "rec1")
    assert len(first["plan"]) >= 2
    target = first["plan"][0]  # K-02 低置信度巩固
    replacement = "M-007"
    events = tmp_path / "events.jsonl"
    append_event(events, _adjustment(first, 2, "lock", "课堂统一讲", "EV-TEST-0101"))
    append_event(
        events,
        _adjustment(
            first,
            1,
            "replace_materials",
            "换成同评分点练习",
            "EV-TEST-0102",
            material_ids=[replacement],
        ),
    )
    second = _recommend(
        tmp_path, run, knowledge, "rec2", feedback=str(events), previous=str(tmp_path / "rec1")
    )
    locked = next(item for item in second["plan"] if item["issue_id"] == first["plan"][1]["issue_id"])
    replaced = next(item for item in second["plan"] if item["issue_id"] == target["issue_id"])
    assert locked["teacher_locked"] is True
    assert any(
        adjustment["action"] == "lock" for adjustment in locked.get("adjustments", [])
    )
    assert replaced["material_ids"] == [replacement]
    assert replaced["completion_condition"]["material_ids"] == [replacement]
    assert second["feedback"]["teacher_adjustments"] == 2
    assert second["plan_diff"]["retained"]
    assert validate_saved_recommendations(tmp_path / "rec2")["gate"] == "pass"


def test_remove_action_defers_the_item(tmp_path, bundle, canonical_root) -> None:
    knowledge = _knowledge(tmp_path, bundle)
    run = _run(tmp_path, "run", bundle)
    first = _recommend(tmp_path, run, knowledge, "rec1")
    target = first["plan"][1]
    events = tmp_path / "events.jsonl"
    append_event(
        events, _adjustment(first, 2, "remove", "本节先不安排", "EV-TEST-0201")
    )
    second = _recommend(
        tmp_path, run, knowledge, "rec2", feedback=str(events), previous=str(tmp_path / "rec1")
    )
    assert target["issue_id"] not in {item["issue_id"] for item in second["plan"]}
    deferred = next(
        entry for entry in second["deferred"] if entry["knowledge_id"] == target["knowledge_ids"][0]
    )
    assert "教师移除" in deferred["reason"]
    assert validate_saved_recommendations(tmp_path / "rec2")["gate"] == "pass"


def test_comments_and_student_feedback_are_surfaced(
    tmp_path, bundle, canonical_root
) -> None:
    knowledge = _knowledge(tmp_path, bundle)
    run = _run(tmp_path, "run", bundle)
    first = _recommend(tmp_path, run, knowledge, "rec1")
    item = first["plan"][0]
    events = tmp_path / "events.jsonl"
    append_event(
        events,
        make_event(
            event_type="teacher_comment",
            student_id="S001",
            node_id="N02",
            actor="teacher",
            plan_item_id=item["plan_item_id"],
            issue_id=item["issue_id"],
            text="先按这个顺序，明天检查。",
            event_id="EV-TEST-0301",
            created_at=STAMP,
            source="test",
        ),
    )
    append_event(
        events,
        make_event(
            event_type="student_feedback",
            student_id="S001",
            node_id="N02",
            actor="student",
            plan_item_id=item["plan_item_id"],
            issue_id=item["issue_id"],
            kind="confusion",
            text="第二步没看懂",
            event_id="EV-TEST-0302",
            created_at=STAMP,
            source="test",
        ),
    )
    second = _recommend(
        tmp_path, run, knowledge, "rec2", feedback=str(events), previous=str(tmp_path / "rec1")
    )
    updated = next(entry for entry in second["plan"] if entry["issue_id"] == item["issue_id"])
    assert updated["teacher_comments"][0]["text"].startswith("先按这个顺序")
    assert updated["student_feedback"][0]["kind"] == "confusion"
    assert second["feedback"]["comments"] == 1
    assert second["feedback"]["student_feedback"] == 1


def test_adjustment_by_issue_applies_to_a_new_version() -> None:
    rec = {
        "plan": [
            {
                "plan_item_id": "PL-001-N02-v9-02",
                "plan_version": 9,
                "seq": 1,
                "issue_id": "IS-001-02",
                "knowledge_ids": ["K-02"],
                "material_ids": ["M-003", "M-004"],
                "primary_material_id": "M-003",
                "est_minutes": 10,
                "difficulty": 2,
                "completion_condition": {"type": "full_credit", "material_ids": ["M-003", "M-004"]},
            }
        ]
    }
    event = make_event(
        event_type="teacher_adjustment",
        student_id="S001",
        node_id="N02",
        actor="teacher",
        plan_item_id="PL-001-N02-v8-02",
        plan_version=8,
        action="replace_materials",
        issue_id="IS-001-02",
        knowledge_id="K-02",
        activity_type="consolidate",
        payload={"material_ids": ["M-005"]},
        reason="旧版本事件",
        snapshot={"issue_id": "IS-001-02", "knowledge_id": "K-02"},
        event_id="EV-TEST-0401",
        created_at=STAMP,
    )
    state = state_for([event], "S001", "N02")
    catalog = {"materials": {"M-005": {"material_id": "M-005", "knowledge_ids": ["K-02"]}}}
    apply_to_recommendation(rec, state, catalog)
    item = rec["plan"][0]
    assert item["material_ids"] == ["M-005"]
    assert item["adjustments"][0]["action"] == "replace_materials"
    assert rec["feedback"]["applied_items"] == ["PL-001-N02-v9-02"]
