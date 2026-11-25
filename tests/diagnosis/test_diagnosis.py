import json
import math
import os
from pathlib import Path

import pytest

from knowflow.cli import main
from knowflow.diagnosis.beta import betainc, betappf
from knowflow.diagnosis.evidence import evidence_action
from knowflow.diagnosis.mastery import DiagnosisConfig, apply_evidence_status, estimate_mastery
from knowflow.diagnosis.pipeline import (
    build_bundle,
    export_evidence,
    latest_run_dir,
    run_diagnosis,
)
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
    # 没有参与记录 = 未覆盖（unobserved），不是"看了但看不准"。
    assert all(
        s["mastery"] is None and s["status"] == "unobserved" for s in p["knowledge_states"]
    )
    assert p["lists"]["needs_coverage"]
    assert not p["lists"]["needs_observation"]


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
        (0, 1, "insufficient_evidence"),
        (0, 2, "likely_weak"),
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


def test_two_observations_never_reach_a_confirmed_status():
    """门槛降到 2 只放开"方向"，不放开"已确认"：确认仍要概率 ≥0.9。"""

    for correct in range(3):
        result = estimate_mastery(correct, 2, DiagnosisConfig())
        assert not result["status"].startswith("confirmed_")


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
            + row["unobserved_count"]
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


def test_apply_evidence_status_separates_uncovered_from_insufficient():
    """一条评分都没有是"未覆盖"，不是"证据不足"；门槛参数本身不变。"""

    empty = estimate_mastery(0, 0, DiagnosisConfig())
    assert apply_evidence_status(empty, observed=0, pending=0)["status"] == "unobserved"
    # 交了但没评分：仍然算证据不足，因为已经有作答在等结果。
    assert apply_evidence_status(empty, observed=0, pending=1)["status"] == "insufficient_evidence"
    # 有 1~2 条评分：不足以定性，但确实看过了。
    sparse = estimate_mastery(1, 1, DiagnosisConfig())
    assert apply_evidence_status(sparse, observed=1, pending=0)["status"] == "insufficient_evidence"


def test_unobserved_knowledge_goes_to_the_coverage_list(bundle):
    p = profile(bundle, "S004")  # N02 只做了 K-03 的一道题
    uncovered = [
        s for s in p["knowledge_states"] if s["status"] == "unobserved" and s["applicable_items"]
    ]
    assert uncovered, "K-01/K-02 在该节点有题但一道没做"
    assert {item["knowledge_id"] for item in p["lists"]["needs_coverage"]} == {
        s["knowledge_id"] for s in uncovered
    }
    assert all(s["knowledge_id"] not in {i["knowledge_id"] for i in p["lists"]["needs_observation"]} for s in uncovered)
    assert all(s["evidence_action"] == "probe" for s in uncovered)


def test_evidence_action_splits_sparse_substates():
    base = {"status": "insufficient_evidence", "evidence_count": 0, "state_counts": {}}
    assert evidence_action(base) == "probe"
    assert evidence_action({**base, "state_counts": {"pending": 1}}) == "pending"
    assert evidence_action({**base, "state_counts": {"assigned_not_attempted": 1}}) == "not_attempted"
    sparse = {"status": "insufficient_evidence", "evidence_count": 1, "state_counts": {}}
    assert evidence_action({**sparse, "weak_probability": 0.8, "mastered_probability": 0.05}) == "sparse_weak"
    assert evidence_action({**sparse, "weak_probability": 0.1, "mastered_probability": 0.7}) == "sparse_mastered"
    assert evidence_action({**sparse, "weak_probability": 0.2, "mastered_probability": 0.3}) == "sparse_mixed"
    assert evidence_action({"status": "likely_mastered", "evidence_count": 5}) is None


def _tier_profile(sid, statuses, observation=(), coverage=()):
    """Minimal profile shaped only for tiering (build_class_profile reads these keys).

    Every knowledge point of the bundle must appear, so callers pass a full map.
    """

    states = [
        {
            "knowledge_id": kids,
            "objective_id": "OBJ-7M-01",
            "status": status,
            "mastery": 0.5,
            "evidence_count": 1,
            "performance": {"mean_score_ratio": 0.5},
        }
        for kids, status in statuses.items()
    ]
    return {
        "student_id": sid,
        "group_id": "G1",
        "node_id": "N02",
        "coverage": {"scope_known": True, "ratio": 0.5},
        "knowledge_states": states,
        "lists": {
            "strengths": [],
            "needs_consolidation": [],
            "needs_observation": [{"knowledge_id": k, "reason": "r"} for k in observation],
            "needs_coverage": [{"knowledge_id": k, "reason": "r"} for k in coverage],
        },
        "issues": [],
    }


def test_class_tier_prefers_actionable_gaps_over_sparse_evidence(bundle):
    """有已观测失分点的学生先做分项练习，不再被"补观测"盖过去。"""

    ps = [
        _tier_profile(
            "S901",
            {"K-01": "mixed_performance", "K-02": "insufficient_evidence", "K-03": "likely_mastered"},
            observation=["K-02"],
        ),
        _tier_profile(
            "S902",
            {"K-01": "insufficient_evidence", "K-02": "likely_mastered", "K-03": "likely_mastered"},
            observation=["K-01"],
        ),
        _tier_profile(
            "S903",
            {"K-01": "unobserved", "K-02": "likely_mastered", "K-03": "likely_mastered"},
            coverage=["K-01"],
        ),
    ]
    c = build_class_profile(ps, "ALL", bundle, "N02")
    tiers = {tier["tier_id"].split("-")[0]: set(tier["student_ids"]) for tier in c["tiers"]}
    assert "S901" in tiers["practice"]
    assert "S901" not in tiers.get("observe", set())
    assert "S902" in tiers["observe"]
    assert "S903" in tiers["cover"]
    assert {sid for members in tiers.values() for sid in members} == {"S901", "S902", "S903"}


def test_class_tier_members_partition_the_class(bundle):
    ps = [profile(bundle, s["student_id"]) for s in bundle["students"]]
    c = build_class_profile(ps, "ALL", bundle, "N02")
    assert validate_class(c, ps, bundle) == []


def test_latest_run_dir_picks_newest_completed_run(tmp_path):
    older, newer, unfinished = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for path in (older, newer, unfinished):
        path.mkdir()
    for path in (older, newer):
        (path / "run_manifest.json").write_text("{}", encoding="utf-8")
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    assert latest_run_dir(tmp_path) == newer


def test_latest_run_dir_requires_a_completed_run(tmp_path):
    with pytest.raises(ValueError, match="no runs yet"):
        latest_run_dir(tmp_path / "missing")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="no completed runs"):
        latest_run_dir(tmp_path)


def test_verify_run_rejects_missing_directory_and_placeholder(tmp_path):
    """`<目录>` is a placeholder: the CLI must explain it instead of raising OSError."""

    assert main(["verify-run", "--run", str(tmp_path / "nope")]) == 2
    assert main(["verify-run", "--run", "artifacts/run/<目录>"]) == 2


def test_verify_run_rejects_incomplete_run(tmp_path):
    (tmp_path / "half").mkdir()
    with pytest.raises(ValueError, match="not a completed run"):
        validate_saved_run(tmp_path / "half")
