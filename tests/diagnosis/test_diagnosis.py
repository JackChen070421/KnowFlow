import json
import math
from pathlib import Path

import pytest

from knowflow.cli import main
from knowflow.diagnosis.beta import betainc, betappf
from knowflow.diagnosis.mastery import DiagnosisConfig, estimate_mastery
from knowflow.diagnosis.pipeline import build_bundle, export_evidence, run_diagnosis
from knowflow.diagnosis.profiles import build_class_profile, build_student_profile
from knowflow.diagnosis.validation import (
    validate_bundle,
    validate_class,
    validate_saved_run,
    validate_student,
)


def profile(bundle, sid="S001", nid="N02", config=None):
    return build_student_profile(
        bundle,
        next(s for s in bundle["students"] if s["student_id"] == sid),
        next(n for n in bundle["nodes"] if n["node_id"] == nid),
        config or DiagnosisConfig(),
    )


def test_bundle_is_derived_from_canonical_and_keeps_answers_out(bundle):
    assert validate_bundle(bundle) == []
    q = bundle["quality_report"]
    assert q["input_records"] == 18
    assert q["total_records"] == 17
    assert q["duplicates_removed"] == 1
    assert q["rejected_records"] == 0
    assert len(q["decisions"]) == q["input_records"]
    superseded = [d for d in q["decisions"] if d["decision"] == "superseded"]
    assert len(superseded) == 1 and superseded[0]["record_id"] == "R-0002"
    serialized = json.dumps(bundle)
    assert "synthetic-private-answer" not in serialized
    assert "synthetic-private-steps" not in serialized
    assert all("answer" not in r and "steps_json" not in r for r in bundle["records"])


def test_pending_is_counted_but_not_graded(bundle):
    p = profile(bundle, nid="N01")
    k = p["knowledge_states"][0]
    assert k["knowledge_id"] == "K-01"
    assert k["state_counts"] == {
        "observed_correct": 1,
        "observed_wrong": 0,
        "assigned_not_attempted": 0,
        "pending": 1,
        "unobserved": 0,
    }
    assert k["evidence_count"] == 1
    assert math.isclose(k["mastery"], 2 / 3, abs_tol=1e-6)
    assert k["status"] == "insufficient_evidence"


def test_assigned_not_attempted_is_not_wrong(bundle):
    p = profile(bundle, nid="N01")
    state = next(s for s in p["knowledge_states"] if s["knowledge_id"] == "K-02")
    assert state["state_counts"]["assigned_not_attempted"] == 1
    assert state["state_counts"]["unobserved"] == 1
    assert state["evidence_count"] == 0
    assert state["mastery"] is None


def test_node_without_item_is_not_applicable(bundle):
    p = profile(bundle, nid="N01")
    state = next(s for s in p["knowledge_states"] if s["knowledge_id"] == "K-03")
    assert state["status"] == "not_applicable"
    assert state["applicable_items"] == 0
    assert state["mastery"] is None
    assert state["state_counts"] == {
        "observed_correct": 0,
        "observed_wrong": 0,
        "assigned_not_attempted": 0,
        "pending": 0,
        "unobserved": 0,
    }


def test_unknown_participation_is_null_coverage(bundle):
    p = profile(bundle, "S006")
    assert p["coverage"]["ratio"] is None
    assert p["coverage"]["scope_known"] is False
    assert all(
        s["mastery"] is None and s["status"] == "insufficient_evidence"
        for s in p["knowledge_states"]
    )


def test_partial_credit_becomes_score_point_evidence(bundle):
    p = profile(bundle, "S002", config=DiagnosisConfig(min_evidence=2))
    state = next(s for s in p["knowledge_states"] if s["knowledge_id"] == "K-02")
    assert state["performance"]["partial_credit"] == 0
    assert state["performance"]["zero_credit"] == 1
    assert state["status"] == "mixed_performance"
    issue = next(i for i in p["issues"] if i["knowledge_id"] == "K-02")
    assert issue["type"] == "score_point_gap"
    assert {p["point_id"] for p in issue["rubric_evidence"]} == {"M-004P1", "M-004P2"}
    assert all(p["record_id"] == "R-0009" for p in issue["rubric_evidence"])


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
        low, high = result["credible_interval"]
        assert 0 <= low < result["mastery"] < high <= 1
    else:
        assert result["mastery"] is None
        assert result["credible_interval"] is None


def test_beta_primitive_matches_known_values():
    assert betainc(1, 4, 0.4) == pytest.approx(1 - 0.6**4, abs=1e-12)
    assert betainc(2, 1, 0.4) == pytest.approx(0.16, abs=1e-12)
    assert betappf(0.5, 1, 1) == pytest.approx(0.5, abs=1e-9)
    for a, b in [(1, 4), (2, 1), (11, 2)]:
        for q in (0.05, 0.5, 0.95):
            assert betainc(a, b, betappf(q, a, b)) == pytest.approx(q, abs=1e-9)


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


def test_class_distribution_counts_sum_to_population(bundle):
    ps = [profile(bundle, s["student_id"]) for s in bundle["students"]]
    c = build_class_profile(ps, "ALL", bundle, "N02")
    assert c["student_count"] == 6
    for row in c["knowledge_distribution"]:
        total = (
            row["mastered_count"]
            + row["weak_count"]
            + row["insufficient_count"]
            + row["mixed_count"]
            + row["not_applicable_count"]
        )
        assert total == c["student_count"]
    assert c["coverage_summary"]["students_with_known_scope"] == 4
    assert validate_class(c, ps, bundle) == []
    c["knowledge_distribution"][0]["mean_mastery"] = 0.123
    assert validate_class(c, ps, bundle)


def test_empty_class(bundle):
    c = build_class_profile([], "ALL", bundle, "N02")
    assert c["student_count"] == 0
    assert c["coverage_summary"]["mean_ratio"] is None
    assert c["rubric_patterns"] == []
    assert validate_class(c, [], bundle) == []


def test_end_to_end_run_verify_and_evidence(bundle, tmp_path):
    output = tmp_path / "run"
    result = run_diagnosis(bundle, output)
    assert result["gate"] == "pass"
    assert result["student_profiles"] == 12 and result["class_profiles"] == 6
    assert validate_saved_run(output)["gate"] == "pass"
    assert main(["verify-run", "--run", str(output)]) == 0

    record = bundle["records"][0]["record_id"]
    path = export_evidence(output, record)
    evidence = json.loads(path.read_text(encoding="utf-8"))
    assert evidence["detail"]["final_answer"] == "synthetic-private-answer"

    with pytest.raises(ValueError, match="already exists"):
        run_diagnosis(bundle, output)

    target = output / "nodes/N02/students/S001.json"
    profile_data = json.loads(target.read_text(encoding="utf-8"))
    profile_data["coverage"]["ratio"] = 0.123
    target.write_text(json.dumps(profile_data), encoding="utf-8")
    assert validate_saved_run(output)["gate"] == "fail"


def test_evidence_rejects_changed_canonical_source(bundle, tmp_path):
    output = tmp_path / "run"
    run_diagnosis(bundle, output)
    record = bundle["records"][0]["record_id"]
    source = Path(bundle["canonical_root"]) / "record_details.csv"
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="canonical source changed"):
        export_evidence(output, record)


def test_latest_only_and_repeatability(bundle, tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    run_diagnosis(bundle, first, node_id="latest")
    run_diagnosis(bundle, second, node_id="latest")
    assert not (first / "nodes/N01").exists()
    assert (first / "nodes/N02/students/S001.json").read_bytes() == (
        second / "nodes/N02/students/S001.json"
    ).read_bytes()


def test_missing_target_cannot_turn_verification_green(bundle, tmp_path):
    output = tmp_path / "run"
    run_diagnosis(bundle, output, node_id="N02")
    manifest_path = output / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["targets"] = [
        t for t in manifest["targets"] if not t["path"].endswith("students/S006.json")
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert validate_saved_run(output)["gate"] == "fail"


def test_issue_id_is_stable_across_nodes(bundle):
    at_n01 = profile(bundle, "S002", "N01")
    at_n02 = profile(bundle, "S002", "N02")
    ids_n01 = {i["issue_id"] for i in at_n01["issues"]}
    ids_n02 = {i["issue_id"] for i in at_n02["issues"]}
    for issue_id in ids_n01 & ids_n02:
        suffix = issue_id.split("-")[-1]
        assert any(i["issue_id"] == issue_id and i["knowledge_id"] == f"K-{suffix}" for i in at_n02["issues"])
    assert all(i["issue_id"].startswith("IS-002-") for i in at_n02["issues"])


def test_bundle_rejects_unknown_dataset(tmp_path):
    with pytest.raises(ValueError, match="canonical tables not found"):
        build_bundle("missing-dataset", root=tmp_path)


def test_student_profile_recomputes_from_bundle(bundle):
    p = profile(bundle)
    assert validate_student(p, bundle, DiagnosisConfig()) == []
    p["knowledge_states"][0]["evidence_count"] = 99
    assert validate_student(p, bundle, DiagnosisConfig())
