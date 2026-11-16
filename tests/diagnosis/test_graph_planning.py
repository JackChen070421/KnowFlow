"""Direction-2 planning checks: reviewed prerequisites, draft relations, confusables."""

from __future__ import annotations

import json

from knowflow.diagnosis.mastery import DiagnosisConfig
from knowflow.diagnosis.profiles import build_student_profile
from knowflow.recommend.catalog import build_catalog
from knowflow.recommend.rules import recommend_profile
from knowflow.recommend.validation import validate_recommendation

STAMP = "2026-11-16T10:00:00+08:00"
OBJECTIVE = "OBJ-7M-01"
KNOWLEDGE = [("K-01", "整式化简"), ("K-02", "整式运算"), ("K-03", "方程"), ("K-04", "不等式")]
MATERIALS = [
    ("M-001", ["K-01"], "assessment"),
    ("M-002", ["K-01"], "assessment"),
    ("M-003", ["K-01"], "assessment"),
    ("M-004", ["K-02"], "assessment"),
    ("M-005", ["K-02"], "assessment"),
    ("M-006", ["K-02"], "assessment"),
    ("M-007", ["K-03"], "assessment"),
    ("M-008", ["K-03"], "assessment"),
    ("M-009", ["K-03"], "assessment"),
    ("M-010", ["K-04"], "assessment"),
    ("M-011", ["K-04"], "assessment"),
    ("M-012", ["K-02", "K-03"], "practice"),
    ("M-013", ["K-04"], "assessment"),
]


def _record(record_id: str, student_id: str, material_id: str, score: float) -> dict:
    return {
        "record_id": record_id,
        "student_id": student_id,
        "material_id": material_id,
        "node_id": "N01",
        "assigned": True,
        "attempted": True,
        "score": score,
        "max_score": 1.0,
        "is_correct": score == 1.0,
        "submitted_at": "2026-01-20T09:00:00+08:00",
        "duration_seconds": None,
        "attempt_no": 1,
        "source": "synthetic",
        "score_points": [
            {
                "point_id": f"{material_id}P1",
                "label": "答案正确",
                "score": score,
                "max_score": 1.0,
            }
        ],
    }


def _records() -> list[dict]:
    rows = []
    number = 1

    def add(student_id: str, material_id: str, score: float) -> None:
        nonlocal number
        rows.append(_record(f"R-{number:04d}", student_id, material_id, score))
        number += 1

    for material_id in ("M-001", "M-002", "M-003"):
        add("S001", material_id, 0.0)
    add("S001", "M-004", 0.0)
    add("S001", "M-005", 1.0)
    add("S001", "M-006", 0.0)
    for material_id in ("M-007", "M-008", "M-009"):
        add("S001", material_id, 1.0)
    add("S001", "M-010", 1.0)

    for material_id in (
        "M-001",
        "M-002",
        "M-003",
        "M-004",
        "M-005",
        "M-006",
        "M-007",
        "M-008",
        "M-009",
        "M-010",
        "M-011",
        "M-013",
    ):
        add("S002", material_id, 0.0)
    return rows


def _bundle() -> dict:
    materials = [
        {
            "material_id": material_id,
            "objective_id": OBJECTIVE,
            "max_score": 1.0,
            "rubric": [{"point_id": f"{material_id}P1", "label": "答案正确", "max_score": 1.0}],
            "knowledge_ids": knowledge_ids,
        }
        for material_id, knowledge_ids, _ in MATERIALS
    ]
    node = {
        "node_id": "N01",
        "date": "2026-01-20",
        "taught_objective_ids": [OBJECTIVE],
        "material_ids": [material_id for material_id, _, _ in MATERIALS],
    }
    return {
        "dataset_id": "synthetic-graph",
        "generated_at": STAMP,
        "students": [
            {"student_id": "S001", "group_id": "G1"},
            {"student_id": "S002", "group_id": "G1"},
        ],
        "knowledge": [
            {"knowledge_id": kid, "objective_id": OBJECTIVE, "name": name}
            for kid, name in KNOWLEDGE
        ],
        "materials": materials,
        "nodes": [node],
        "participation": [
            {"student_id": "S001", "node_id": "N01"},
            {"student_id": "S002", "node_id": "N01"},
        ],
        "records": _records(),
    }


def _edge(
    edge_id: str,
    source: str,
    target: str,
    relation: str,
    status: str,
    evidence: str,
) -> dict:
    return {
        "edge_id": edge_id,
        "source_node_id": source,
        "target_node_id": target,
        "relation_type": relation,
        "source_reference": "synthetic",
        "rationale": "synthetic",
        "review_status": status,
        "evidence_level": evidence,
    }


def _graph() -> dict:
    nodes = []
    for index, (knowledge_id, name) in enumerate(KNOWLEDGE):
        nodes.append(
            {
                "node_id": f"C-10{index + 1}",
                "title": name,
                "theme_index": index % 3,
                "summary": "synthetic",
                "source_locator": "synthetic p.1",
                "textbook": "B05",
                "pdf_page": index + 1,
                "knowledge_ids": [knowledge_id],
                "material_id": ["M-001", "M-004", "M-007", "M-010"][index],
            }
        )
    edges = [
        _edge("GE-0001", "K-01", "K-02", "prerequisite", "reviewed", "textbook_locator"),
        _edge("GE-0002", "K-03", "K-02", "prerequisite", "reviewed", "textbook_locator"),
        _edge("GE-0003", "K-04", "K-02", "prerequisite", "reviewed", "textbook_locator"),
        _edge("GE-0004", "K-04", "K-01", "prerequisite", "draft", "manual_unsourced"),
        _edge("GE-0005", "K-02", "K-03", "confusable_with", "reviewed", "textbook_locator"),
        _edge("GE-0006", "K-03", "K-04", "related_to", "draft", "manual_unsourced"),
    ]
    return {
        "schema_version": "1.0.0",
        "graph_id": "synthetic-graph",
        "version": "1.0.0",
        "subject": "math",
        "grade": 7,
        "source": "synthetic",
        "nodes": nodes,
        "edges": edges,
        "counts": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "prerequisite_count": 4,
            "confusable_count": 1,
            "related_count": 1,
            "draft_count": 2,
            "reviewed_count": 4,
        },
    }


def _knowledge_base(graph: dict | None = None) -> dict:
    materials = []
    qmatrix = []
    for material_id, knowledge_ids, material_type in MATERIALS:
        materials.append(
            {
                "material_id": material_id,
                "title": material_id,
                "body": "synthetic",
                "material_type": material_type,
                "item_format": "blank" if material_type == "assessment" else None,
                "objective_id": OBJECTIVE,
                "difficulty": None,
                "est_minutes": 2,
                "rubric_json": json.dumps(
                    [{"id": f"{material_id}P1", "text": "答案正确", "points": 1}],
                    ensure_ascii=False,
                ),
                "answer_key": "1",
            }
        )
        for knowledge_id in knowledge_ids:
            qmatrix.append(
                {
                    "material_id": material_id,
                    "knowledge_id": knowledge_id,
                    "weight": 1.0,
                    "difficulty": None,
                    "item_type": "assessment",
                    "is_primary": True,
                }
            )
    knowledge_base = {
        "schema_version": "1.0.0",
        "dataset_id": "synthetic-graph",
        "generated_at": STAMP,
        "subject": "math",
        "grade": 7,
        "counts": {
            "objective_count": 1,
            "knowledge_count": len(KNOWLEDGE),
            "material_count": len(materials),
            "qmatrix_count": len(qmatrix),
            "edge_count": 0,
        },
        "objectives": [
            {
                "objective_id": OBJECTIVE,
                "subject": "math",
                "grade": 7,
                "theme": "synthetic",
                "unit": "synthetic",
                "objective_text": "synthetic",
                "verb_level": "apply",
                "source_material_id": None,
                "source_locator": "synthetic",
            }
        ],
        "knowledge": [
            {
                "knowledge_id": kid,
                "objective_id": OBJECTIVE,
                "parent_id": None,
                "name": name,
                "level": "knowledge",
                "cognitive_type": "procedure",
                "description": None,
                "sort_order": index,
            }
            for index, (kid, name) in enumerate(KNOWLEDGE)
        ],
        "materials": materials,
        "qmatrix": qmatrix,
        "edges": [],
    }
    if graph is not None:
        knowledge_base["curriculum_graph"] = graph
    return knowledge_base


def _profile(bundle: dict, student_id: str = "S001") -> dict:
    return build_student_profile(
        bundle,
        next(student for student in bundle["students"] if student["student_id"] == student_id),
        bundle["nodes"][0],
        DiagnosisConfig(),
        None,
    )


def _recommend(bundle: dict, graph: dict | None = None, student_id: str = "S001") -> tuple[dict, dict]:
    knowledge_base = _knowledge_base(graph)
    catalog = build_catalog(knowledge_base)
    profile = _profile(bundle, student_id)
    rec = recommend_profile(
        profile,
        catalog,
        set(bundle["nodes"][0]["material_ids"]),
        bundle["records"],
        STAMP,
        "0" * 64,
        None,
    )
    return rec, profile


def _item(rec: dict, knowledge_id: str) -> dict:
    return next(item for item in rec["plan"] if item["knowledge_ids"] == [knowledge_id])


def test_reviewed_prerequisite_is_planned_before_target() -> None:
    rec, _ = _recommend(_bundle(), _graph())
    order = [item["knowledge_ids"][0] for item in rec["plan"]]
    assert order.index("K-01") < order.index("K-02")
    assert order.index("K-04") < order.index("K-02")
    assert "K-03" not in order, "mastered prerequisite must not be repeated"


def test_prerequisite_check_reports_reviewed_edges() -> None:
    rec, _ = _recommend(_bundle(), _graph())
    check = _item(rec, "K-02")["prerequisite_check"]
    assert check["satisfied"] is False
    assert check["missing_knowledge_ids"] == ["K-01"]
    assert check["pending_knowledge_ids"] == ["K-04"]
    assert set(check["reviewed_edges"]) == {"GE-0001", "GE-0002", "GE-0003"}


def test_draft_prerequisite_does_not_reorder() -> None:
    rec, _ = _recommend(_bundle(), _graph())
    # GE-0004 (K-04 -> K-01) is draft: obeying it would put K-04 first.
    assert rec["plan"][0]["knowledge_ids"] == ["K-01"]
    assert "GE-0004" in rec["plan"][0]["prerequisite_check"]["draft_edges"]


def test_insufficient_prerequisite_is_probed_not_called_weak() -> None:
    rec, _ = _recommend(_bundle(), _graph())
    check = _item(rec, "K-02")["prerequisite_check"]
    assert "K-04" in check["pending_knowledge_ids"]
    assert "K-04" not in check["missing_knowledge_ids"]
    assert _item(rec, "K-04")["activity_type"] == "probe"


def test_confusable_uses_shared_practice_and_never_diagnoses_confusion() -> None:
    rec, profile = _recommend(_bundle(), _graph())
    item = _item(rec, "K-02")
    assert "M-012" in item["material_ids"]
    note = next(note for note in item["relation_notes"] if note["edge_id"] == "GE-0005")
    assert "对比" in note["note"]
    assert "混淆" not in note["note"]
    assert all(issue["knowledge_id"] != "K-03" for issue in profile["issues"])
    assert next(issue for issue in profile["issues"] if issue["knowledge_id"] == "K-02")[
        "type"
    ] == "score_point_gap"


def test_budget_is_respected_and_exclusions_explained() -> None:
    rec, _ = _recommend(_bundle(), _graph(), student_id="S002")
    assert len(rec["plan"]) == 3
    deferred_ids = {entry["issue_id"] for entry in rec["deferred"]}
    assert deferred_ids == {"IS-002-02"}
    assert all("预算" in entry["reason"] for entry in rec["deferred"])


def test_validation_accepts_graph_fields_and_rejects_status_mismatch() -> None:
    bundle = _bundle()
    catalog = build_catalog(_knowledge_base(_graph()))
    pipeline, profile = _recommend(bundle)
    node_available = set(bundle["nodes"][0]["material_ids"])
    assert (
        validate_recommendation(
            pipeline, profile, catalog, node_available, bundle["records"], "0" * 64, None
        )
        == []
    )
    item = _item(pipeline, "K-02")
    item["prerequisite_check"]["reviewed_edges"] = ["GE-0004"]
    errors = validate_recommendation(
        pipeline, profile, catalog, node_available, bundle["records"], "0" * 64, None
    )
    assert any("status mismatch" in error for error in errors)


def test_missing_graph_keeps_the_old_neutral_behaviour() -> None:
    rec, _ = _recommend(_bundle(), None)
    assert "GE-0001" not in json.dumps(rec)
    for item in rec["plan"]:
        assert item["prerequisite_check"]["satisfied"] is True
        assert item["prerequisite_check"]["missing_knowledge_ids"] == []
        assert "relation_notes" not in item


# --------------------------------------------------------------------------- #
# direction 3: learning path identities, completion conditions, probe scoring
# --------------------------------------------------------------------------- #

from knowflow.knowledge.pipeline import write_knowledge_base  # noqa: E402
from knowflow.recommend import path as path_module  # noqa: E402
from knowflow.recommend import probe as probe_module  # noqa: E402
from knowflow.recommend.pipeline import recommend_run  # noqa: E402
from knowflow.recommend.validation import validate_saved_recommendations  # noqa: E402


def _path_context(version: int, completed: list[dict], started: list[dict], history: list[dict]):
    return {
        "version": version,
        "completed": completed,
        "started": started,
        "history": history,
        "events": completed + started,
        "probe_weights": probe_module.ProbeWeights(),
        "source": "test",
    }


def test_plan_items_carry_ids_versions_and_completion_conditions() -> None:
    rec, _ = _recommend(_bundle(), _graph())
    assert rec["plan_version"] == 1
    assert rec["plan_id"] == "PLAN-001-N01-v1"
    ids = [item["plan_item_id"] for item in rec["plan"]]
    assert len(ids) == len(set(ids))
    for index, item in enumerate(rec["plan"], 1):
        assert item["seq"] == index
        assert item["plan_version"] == 1
        assert item["status"] == "planned"
        assert item["plan_item_id"].startswith("PL-001-N01-v1-")
        condition = item["completion_condition"]
        assert condition["material_ids"] == item["material_ids"] or set(
            condition["material_ids"]
        ) <= set(item["material_ids"])
        if item["activity_type"] == "probe":
            assert condition["type"] == "probe_evidence"
            assert condition["min_graded"] == 3
        else:
            assert condition["type"] == "full_credit"


def test_prerequisite_links_only_point_to_earlier_items() -> None:
    rec, _ = _recommend(_bundle(), _graph())
    target = _item(rec, "K-02")
    assert set(target["prerequisite_item_ids"]) == {
        "PL-001-N01-v1-01",
        "PL-001-N01-v1-04",
    }
    assert "K-01" in target["prerequisite_knowledge_ids"]
    assert "K-04" in target["prerequisite_knowledge_ids"]
    assert rec["plan"][0]["knowledge_ids"] == ["K-01"]


def test_probe_scoring_is_recomputable_and_has_no_fake_difficulty() -> None:
    rec, _ = _recommend(_bundle(), _graph())
    probe = rec["probe_plan"]
    assert probe["scoring"]["policy_version"] == probe_module.PROBE_POLICY_VERSION
    weights = probe["scoring"]["weights"]
    assert set(weights) == set(probe_module.COMPONENTS)
    for candidate in probe["scoring"]["candidates"]:
        total = sum(
            weights.get(name, 0.0) * value
            for name, value in candidate["components"].items()
        )
        assert abs(total - candidate["total"]) < 1e-6
        assert "difficulty" not in candidate["components"]
        assert "discrimination" not in candidate["components"]
    selected = set(probe["items"])
    assert selected <= {candidate["material_id"] for candidate in probe["scoring"]["candidates"]}


def test_probe_selection_is_deterministic() -> None:
    first, _ = _recommend(_bundle(), _graph())
    second, _ = _recommend(_bundle(), _graph())
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_probe_never_uses_attempted_pending_or_scored_items() -> None:
    bundle = _bundle()
    rec, _ = _recommend(bundle, _graph())
    attempted = {
        record["material_id"]
        for record in bundle["records"]
        if record["student_id"] == "S001" and record["attempted"]
    }
    for item in rec["plan"]:
        if item["activity_type"] != "probe":
            continue
        for material_id in item["material_ids"]:
            assert material_id not in attempted


def test_pending_answers_are_excluded_from_probe_candidates() -> None:
    bundle = _bundle()
    node = bundle["nodes"][0]
    # Mark M-011 as answered but ungraded: it must not become a probe.
    pending = {
        "record_id": "R-9001",
        "student_id": "S001",
        "material_id": "M-011",
        "node_id": "N01",
        "assigned": True,
        "attempted": True,
        "score": None,
        "max_score": 1.0,
        "is_correct": None,
        "submitted_at": STAMP,
        "duration_seconds": None,
        "attempt_no": 1,
        "source": "synthetic",
        "score_points": [],
    }
    bundle["records"].append(pending)
    profile = _profile(bundle, "S001")
    rec = recommend_profile(
        profile,
        build_catalog(_knowledge_base(_graph())),
        set(node["material_ids"]),
        bundle["records"],
        STAMP,
        "0" * 64,
        None,
    )
    for item in rec["plan"]:
        if item["activity_type"] == "probe":
            assert "M-011" not in item["material_ids"]


def test_completed_event_moves_item_to_history_and_frees_budget() -> None:
    bundle = _bundle()
    first, _ = _recommend(bundle, _graph())
    item = first["plan"][0]
    event = path_module.make_event(
        student_id="S001",
        node_id="N01",
        plan_version=first["plan_version"],
        event_type="completed",
        issue_id=item["issue_id"],
        knowledge_id=item["knowledge_ids"][0],
        material_ids=item["material_ids"],
        activity_type=item["activity_type"],
        seq=item["seq"],
        event_id="PE-TEST-0001",
        created_at=STAMP,
        source="test",
    )
    state = path_module.path_state([event], "S001", "N01")
    history = path_module.merge_history(first, state["completed"])
    second = recommend_profile(
        _profile(bundle, "S001"),
        build_catalog(_knowledge_base(_graph())),
        set(bundle["nodes"][0]["material_ids"]),
        bundle["records"],
        STAMP,
        "0" * 64,
        None,
        _path_context(2, state["completed"], state["started"], history),
    )
    assert second["plan_version"] == 2
    assert len(second["history"]) == 1
    assert second["history"][0]["plan_item_id"] == item["plan_item_id"]
    assert item["knowledge_ids"][0] not in [
        entry["knowledge_ids"][0] for entry in second["plan"]
    ]
    assert len(second["plan"]) <= 3


def test_started_item_is_kept_in_progress_with_the_same_id() -> None:
    bundle = _bundle()
    first, _ = _recommend(bundle, _graph())
    item = first["plan"][0]
    event = path_module.make_event(
        student_id="S001",
        node_id="N01",
        plan_version=first["plan_version"],
        event_type="started",
        issue_id=item["issue_id"],
        knowledge_id=item["knowledge_ids"][0],
        material_ids=item["material_ids"],
        activity_type=item["activity_type"],
        seq=item["seq"],
        event_id="PE-TEST-0002",
        created_at=STAMP,
        source="test",
    )
    state = path_module.path_state([event], "S001", "N01")
    second = recommend_profile(
        _profile(bundle, "S001"),
        build_catalog(_knowledge_base(_graph())),
        set(bundle["nodes"][0]["material_ids"]),
        bundle["records"],
        STAMP,
        "0" * 64,
        None,
        _path_context(2, state["completed"], state["started"], []),
    )
    kept = next(
        entry
        for entry in second["plan"]
        if entry["issue_id"] == item["issue_id"]
    )
    assert kept["status"] == "in_progress"
    assert kept["plan_item_id"] == item["plan_item_id"]


def test_progress_event_validation_rejects_unknown_student() -> None:
    event = path_module.make_event(
        student_id="S999",
        node_id="N01",
        plan_version=1,
        event_type="completed",
        issue_id="IS-999-01",
        knowledge_id="K-01",
        material_ids=["M-001"],
        activity_type="probe",
        seq=1,
        event_id="PE-TEST-0003",
        created_at=STAMP,
    )
    tables = {
        "students": [{"student_id": "S001"}],
        "nodes": [{"node_id": "N01"}],
        "knowledge": [{"knowledge_id": "K-01"}],
        "materials": [{"material_id": "M-001"}],
    }
    assert path_module.validate_event_refs(event, tables)


def _fake_run(tmp_path, bundle: dict, profile: dict):
    run = tmp_path / "run"
    (run / "nodes" / "N01" / "students").mkdir(parents=True)
    (run / "diagnosis_input.json").write_text(json.dumps(bundle), encoding="utf-8")
    (run / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "0.5.0",
                "dataset_id": bundle["dataset_id"],
                "generated_at": STAMP,
                "scope": "task2_only",
                "nodes": ["N01"],
                "configuration": {},
                "source_files": {},
                "review": None,
                "targets": [],
            }
        ),
        encoding="utf-8",
    )
    (run / "nodes" / "N01" / "students" / "S001.json").write_text(
        json.dumps(profile), encoding="utf-8"
    )
    return run


def test_recommend_run_replans_with_progress_and_records_the_diff(tmp_path) -> None:
    bundle = _bundle()
    profile = _profile(bundle, "S001")
    run = _fake_run(tmp_path, bundle, profile)
    knowledge_path = tmp_path / "knowledge_base.json"
    write_knowledge_base(_knowledge_base(_graph()), knowledge_path)

    first = recommend_run(
        run=str(run),
        knowledge=str(knowledge_path),
        node="N01",
        output=str(tmp_path / "rec1"),
        generated_at=STAMP,
    )
    assert first["gate"] == "pass"
    rec1 = json.loads((tmp_path / "rec1/nodes/N01/students/S001.json").read_text(encoding="utf-8"))
    item = rec1["plan"][0]
    event = path_module.make_event(
        student_id="S001",
        node_id="N01",
        plan_version=rec1["plan_version"],
        event_type="completed",
        issue_id=item["issue_id"],
        knowledge_id=item["knowledge_ids"][0],
        material_ids=item["material_ids"],
        activity_type=item["activity_type"],
        seq=item["seq"],
        event_id="PE-TEST-0010",
        created_at=STAMP,
        source="test",
    )
    events = tmp_path / "events.jsonl"
    path_module.append_event(events, event)

    second = recommend_run(
        run=str(run),
        knowledge=str(knowledge_path),
        node="N01",
        output=str(tmp_path / "rec2"),
        generated_at=STAMP,
        progress=str(events),
        previous=str(tmp_path / "rec1"),
    )
    assert second["gate"] == "pass"
    rec2 = json.loads((tmp_path / "rec2/nodes/N01/students/S001.json").read_text(encoding="utf-8"))
    assert rec2["plan_version"] == rec1["plan_version"] + 1
    assert rec2["history"][0]["plan_item_id"] == item["plan_item_id"]
    assert rec2["plan_diff"]["previous_plan_id"] == rec1["plan_id"]
    assert any(
        entry["plan_item_id"] == item["plan_item_id"]
        for entry in rec2["plan_diff"]["completed"]
    )
    assert item["knowledge_ids"][0] not in [
        entry["knowledge_ids"][0] for entry in rec2["plan"]
    ]
    assert validate_saved_recommendations(tmp_path / "rec2")["gate"] == "pass"


def test_plan_version_stays_when_nothing_changed(tmp_path) -> None:
    bundle = _bundle()
    run = _fake_run(tmp_path, bundle, _profile(bundle, "S001"))
    knowledge_path = tmp_path / "knowledge_base.json"
    write_knowledge_base(_knowledge_base(_graph()), knowledge_path)
    recommend_run(
        run=str(run), knowledge=str(knowledge_path), node="N01",
        output=str(tmp_path / "rec1"), generated_at=STAMP,
    )
    second = recommend_run(
        run=str(run), knowledge=str(knowledge_path), node="N01",
        output=str(tmp_path / "rec2"), generated_at=STAMP,
        previous=str(tmp_path / "rec1"),
    )
    assert second["gate"] == "pass"
    rec1 = json.loads((tmp_path / "rec1/nodes/N01/students/S001.json").read_text(encoding="utf-8"))
    rec2 = json.loads((tmp_path / "rec2/nodes/N01/students/S001.json").read_text(encoding="utf-8"))
    assert rec2["plan_version"] == rec1["plan_version"]
    assert rec2["plan_diff"]["added"] == []


def test_probe_weights_are_configurable_and_recorded(tmp_path) -> None:
    bundle = _bundle()
    run = _fake_run(tmp_path, bundle, _profile(bundle, "S001"))
    knowledge_path = tmp_path / "knowledge_base.json"
    write_knowledge_base(_knowledge_base(_graph()), knowledge_path)
    result = recommend_run(
        run=str(run),
        knowledge=str(knowledge_path),
        node="N01",
        output=str(tmp_path / "rec"),
        generated_at=STAMP,
        probe_weights={"material_quality": 0.0, "coverage_gain": 3.0},
    )
    assert result["gate"] == "pass"
    manifest = json.loads((tmp_path / "rec/run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["policy"]["probe_weights"]["material_quality"] == 0.0
    assert manifest["policy"]["probe_weights"]["coverage_gain"] == 3.0
    rec = json.loads((tmp_path / "rec/nodes/N01/students/S001.json").read_text(encoding="utf-8"))
    scoring = rec["probe_plan"].get("scoring")
    if scoring:
        assert scoring["weights"]["coverage_gain"] == 3.0
        for candidate in scoring["candidates"]:
            total = sum(
                scoring["weights"].get(name, 0.0) * value
                for name, value in candidate["components"].items()
            )
            assert abs(total - candidate["total"]) < 1e-6
