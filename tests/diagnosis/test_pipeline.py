import copy
import json
import math

import pytest

from knowflow.cli import main
from knowflow.diagnosis.mastery import DiagnosisConfig, estimate_mastery
from knowflow.diagnosis.pipeline import export_evidence, run_diagnosis
from knowflow.diagnosis.profiles import build_class_profile, build_student_profile
from knowflow.diagnosis.validation import (
    validate_bundle,
    validate_class,
    validate_saved_run,
    validate_student,
)
from knowflow.io.adapters import adapt_official

STAMP = "2026-11-10T12:00:00+08:00"


def profile(bundle, sid="S001", nid="N02"):
    return build_student_profile(
        bundle,
        next(s for s in bundle["students"] if s["student_id"] == sid),
        next(n for n in bundle["nodes"] if n["node_id"] == nid),
        DiagnosisConfig(),
    )


def test_revisions_and_invalid_latest_do_not_revive_old_grade(bundle):
    assert validate_bundle(bundle) == []
    q = bundle["quality_report"]
    assert q["input_records"] == 13
    assert q["duplicates_removed"] == 2
    assert q["rejected_records"] == 1
    assert q["total_records"] == 10
    assert q["records_by_state"] == {
        "observed_correct": 4,
        "observed_wrong": 4,
        "pending": 1,
        "assigned_not_attempted": 1,
        "unobserved": 0,
    }
    assert not any(r["student_id"] == "S003" for r in bundle["records"])
    assert any(p["student_id"] == "S003" and p["node_id"] == "N01" for p in bundle["participation"])
    assert (
        sum(r["student_id"] == "S001" and r["material_id"] == "M-001" for r in bundle["records"])
        == 2
    )


def test_pending_unattempted_and_not_taught_are_distinct(bundle):
    p = profile(bundle, nid="N01")
    k = p["knowledge_states"][0]
    assert k["evidence_count"] == 1
    assert math.isclose(k["mastery"], 2 / 3, abs_tol=1e-6)
    assert k["state_counts"]["pending"] == 1
    assert k["state_counts"]["assigned_not_attempted"] == 1
    assert p["coverage"]["ratio"] == pytest.approx(1 / 3, abs=1e-6)
    assert p["knowledge_states"][1]["status"] == "not_applicable"
    assert p["knowledge_states"][1]["mastery"] is None
    assert validate_student(p, bundle, DiagnosisConfig()) == []


def test_unknown_participation_is_not_zero_coverage(bundle):
    p = profile(bundle, "S004")
    assert p["coverage"]["ratio"] is None
    assert p["coverage"]["scope_known"] is False
    assert all(
        s["mastery"] is None and s["status"] == "insufficient_evidence"
        for s in p["knowledge_states"]
    )


def test_partial_credit_and_rubric_evidence(bundle):
    p = profile(bundle)
    state = p["knowledge_states"][1]
    assert state["performance"] == {
        "full_credit": 0,
        "partial_credit": 1,
        "zero_credit": 0,
        "mean_score_ratio": 0.666667,
    }
    issue = next(i for i in p["issues"] if i["knowledge_id"] == state["knowledge_id"])
    assert issue["rubric_evidence"][0]["point_id"] == "M-004P3"
    assert issue["rubric_evidence"][0]["criterion"] == "合成步骤3"
    assert (
        issue["type"] == "insufficient_evidence"
    )  # One observation cannot confirm a general cause.
    serialized = json.dumps(bundle)
    assert "synthetic-private-answer" not in serialized
    assert "synthetic-private-steps" not in serialized


@pytest.mark.parametrize(
    ("correct", "n", "status"),
    [
        (0, 0, "insufficient_evidence"),
        (0, 2, "insufficient_evidence"),
        (0, 3, "likely_weak"),
        (3, 3, "likely_mastered"),
        (0, 8, "confirmed_weak"),
        (12, 12, "confirmed_mastered"),
        (4, 8, "mixed_performance"),
    ],
)
def test_beta_statuses(correct, n, status):
    result = estimate_mastery(correct, n, DiagnosisConfig())
    assert result["status"] == status
    if n:
        assert result["mastery"] == pytest.approx((correct + 1) / (n + 2), abs=1e-6)
    else:
        assert result["mastery"] is None
    if (correct, n) == (0, 3):
        assert result["weak_probability"] == pytest.approx(1 - 0.6**4, abs=1e-6)


@pytest.mark.parametrize(
    "options",
    [
        {"prior_alpha": 0},
        {"min_evidence": 1.5},
        {"weak_threshold": 0.9},
        {"confirmation_probability": 0.5},
        {"credible_mass": float("nan")},
        {"min_evidence": True},
    ],
)
def test_invalid_configuration(options):
    with pytest.raises(ValueError):
        DiagnosisConfig(**options)


def test_class_counts_and_nulls(bundle):
    ps = [profile(bundle, s["student_id"]) for s in bundle["students"]]
    c = build_class_profile(ps, "ALL", bundle, "N02")
    first = c["knowledge_distribution"][0]
    assert first["mean_mastery"] == 0.5  # (0.2 + 0.8)/2, excluding two nulls.
    assert (first["weak_count"], first["mastered_count"], first["insufficient_count"]) == (1, 1, 2)
    assert c["coverage_summary"]["students_with_known_scope"] == 2
    assert c["coverage_summary"]["mean_ratio"] == 0.875  # (4/4 + 3/4)/2.
    partial = next(r for r in c["rubric_patterns"] if r["knowledge_id"] == "K-02")
    assert partial["affected_student_count"] == partial["observed_student_count"] == 1
    assert partial["criterion"] == "合成步骤3"
    assert validate_class(c, ps, bundle) == []
    c["knowledge_distribution"][0]["mean_mastery"] = 0.25
    assert validate_class(c, ps, bundle)


def test_empty_class(bundle):
    c = build_class_profile([], "ALL", bundle, "N02")
    assert c["student_count"] == 0
    assert c["coverage_summary"]["mean_ratio"] is None
    assert validate_class(c, [], bundle) == []


def test_duplicate_record_ids_are_quarantined(official_tables, write_official):
    official_tables["作答记录"][-1]["记录编号"] = official_tables["作答记录"][0]["记录编号"]
    b = adapt_official(write_official(official_tables), "synthetic-task2", STAMP)
    assert b["quality_report"]["rejected_records"] == 4
    assert validate_bundle(b) == []


def test_bad_point_total_keeps_official_grade_but_drops_point_claims(
    official_tables, write_official
):
    official_tables["作答记录"][7]["评分点得分"] = "Q004P1=1；Q004P2=1；Q004P3=1"
    b = adapt_official(write_official(official_tables), "synthetic-task2", STAMP)
    r = next(r for r in b["records"] if r["material_id"] == "M-004")
    assert r["score"] == 2 and r["score_points"] == []
    assert any(
        a["reason"] == "unreliable_or_missing_score_points"
        for a in b["quality_report"]["anomalies"]
    )


def test_scored_pending_invalid_and_unknown_columns(official_tables, write_official):
    official_tables["作答记录"][2]["得分"] = "1"
    root = write_official(official_tables)
    b = adapt_official(root, "synthetic-task2", STAMP)
    assert b["quality_report"]["rejected_records"] == 2
    path = root / "4_赛题数据/模拟学情数据/模拟学生.csv"
    path.write_text(
        path.read_text(encoding="utf-8-sig").replace("年级", "未知字段", 1), encoding="utf-8-sig"
    )
    with pytest.raises(ValueError, match="column mismatch"):
        adapt_official(root, "synthetic-task2", STAMP)


def test_unknown_material_rejected_without_crash(official_tables, write_official):
    row = official_tables["作答记录"][7]
    row["材料编号"] = "Q999"
    row["作答事件编号"] = "D01-N02-Q999"
    b = adapt_official(write_official(official_tables), "synthetic-task2", STAMP)
    assert b["quality_report"]["rejected_records"] == 2
    assert validate_bundle(b) == []


def test_newer_pending_replaces_old_graded_record(official_tables, write_official):
    row = official_tables["作答记录"][1]
    row.update({"评分状态": "待评分", "得分": "", "评分点得分": ""})
    b = adapt_official(write_official(official_tables), "synthetic-task2", STAMP)
    p = profile(b, nid="N01")
    assert p["knowledge_states"][0]["mastery"] is None
    assert p["knowledge_states"][0]["state_counts"]["pending"] == 2


def test_id_map_stability_with_added_earlier_indicator(official_tables, write_official, bundle):
    row = copy.deepcopy(official_tables["课程要求"][0])
    row["指标编号"] = "T00I1"
    official_tables["课程要求"].insert(0, row)
    b = adapt_official(
        write_official(official_tables, "new-raw"), "synthetic-task2", STAMP, bundle["id_map"]
    )
    assert b["id_map"]["knowledge"]["T01I1"] == "K-01"
    assert b["id_map"]["knowledge"]["T00I1"] == "K-03"


def test_validation_rejects_tampered_evidence(bundle):
    p = profile(bundle)
    p["knowledge_states"][0]["evidence_count"] = 99
    assert validate_student(p, bundle, DiagnosisConfig())


def test_end_to_end_replay_and_original_evidence(bundle, tmp_path):
    output = tmp_path / "run"
    result = run_diagnosis(bundle, output)
    assert result["gate"] == "pass"
    assert result["student_profiles"] == 8 and result["class_profiles"] == 6
    assert validate_saved_run(output)["gate"] == "pass"
    assert main(["verify-run", "--run", str(output)]) == 0
    record = bundle["records"][0]["record_id"]
    path = export_evidence(output, record)
    evidence = json.loads(path.read_text(encoding="utf-8"))
    assert evidence["record"]["学生最终作答"] == "synthetic-private-answer"
    source = next((tmp_path / "raw").rglob("作答记录.csv"))
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source file changed"):
        export_evidence(output, record)
    with pytest.raises(ValueError, match="already exists"):
        run_diagnosis(bundle, output)
    target = output / "nodes/N02/students/S001.json"
    p = json.loads(target.read_text(encoding="utf-8"))
    p["coverage"]["ratio"] = 0.123
    target.write_text(json.dumps(p), encoding="utf-8")
    assert validate_saved_run(output)["gate"] == "fail"


def test_latest_only_and_repeatability(bundle, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    run_diagnosis(bundle, a, node_id="latest")
    run_diagnosis(bundle, b, node_id="latest")
    assert not (a / "nodes/N01").exists()
    assert (a / "nodes/N02/students/S001.json").read_bytes() == (
        b / "nodes/N02/students/S001.json"
    ).read_bytes()


def test_missing_target_cannot_turn_verification_green(bundle, tmp_path):
    output = tmp_path / "run"
    run_diagnosis(bundle, output, node_id="N02")
    manifest_path = output / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["targets"] = [
        t for t in manifest["targets"] if not t["path"].endswith("students/S004.json")
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert validate_saved_run(output)["gate"] == "fail"


def test_r1_mapping_override_and_missing_material(official_tables, write_official):
    root = write_official(official_tables)
    knowledge = [{"knowledge_id": "K-11", "objective_id": "OBJ-7M-01", "name": "合成R1指标"}]
    kb = {
        "knowledge": knowledge,
        "qmatrix": [
            {"material_id": f"M-{i:03d}", "knowledge_id": "K-11", "weight": 1} for i in range(1, 5)
        ],
    }
    bundle = adapt_official(root, "synthetic-task2", STAMP, knowledge_base=kb)
    assert validate_bundle(bundle) == []
    assert all(m["knowledge_ids"] == ["K-11"] for m in bundle["materials"])
    kb["qmatrix"].pop()
    with pytest.raises(ValueError, match="does not cover"):
        adapt_official(root, "synthetic-task2", STAMP, knowledge_base=kb)
