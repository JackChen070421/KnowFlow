"""Direction-1 checks: rules, ledger, diagnosis isolation, recommendation isolation.

Everything runs on a synthetic canonical package. The official data is only
exercised by the local manual verification, never by CI (it is not in Git).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from knowflow.diagnosis.mastery import DiagnosisConfig
from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.diagnosis.profiles import build_class_profile, build_student_profile
from knowflow.diagnosis.validation import validate_saved_run, validate_student
from knowflow.knowledge.pipeline import write_knowledge_base
from knowflow.recommend.catalog import build_catalog
from knowflow.recommend.pipeline import recommend_run
from knowflow.recommend.rules import recommend_profile
from knowflow.recommend.validation import validate_recommendation
from knowflow.review.pipeline import (
    build_context,
    context_from_run_manifest,
    decide,
    load_report,
    scan_dataset,
)
from knowflow.review.rules import DISABLED_RULES, RULES, scan_record
from knowflow.review.validation import validate_report

STAMP = "2026-11-16T09:00:00+08:00"
DATASET = "synthetic-review"


def _record(tables: dict, record_id: str) -> dict:
    return next(row for row in tables["records"] if row["record_id"] == record_id)


def _material(tables: dict, material_id: str) -> dict:
    return next(row for row in tables["materials"] if row["material_id"] == material_id)


def _profile(bundle: dict, student_id: str, review: dict | None = None) -> dict:
    return build_student_profile(
        bundle,
        next(s for s in bundle["students"] if s["student_id"] == student_id),
        next(n for n in bundle["nodes"] if n["node_id"] == "N01"),
        DiagnosisConfig(),
        review,
    )


def _state(profile: dict, knowledge_id: str) -> dict:
    return next(s for s in profile["knowledge_states"] if s["knowledge_id"] == knowledge_id)


def _recommend(bundle: dict, knowledge_base: dict, student_id: str, review: dict | None) -> dict:
    profile = _profile(bundle, student_id, review)
    return recommend_profile(
        profile,
        build_catalog(knowledge_base),
        set(bundle["nodes"][0]["material_ids"]),
        bundle["records"],
        STAMP,
        "0" * 64,
        review,
    )


# --------------------------------------------------------------------------- #
# rules
# --------------------------------------------------------------------------- #


def test_literal_match_under_credit_is_flagged(tables: dict) -> None:
    flags = scan_record(_record(tables, "R-0001"), _material(tables, "M-001"))
    assert [flag.code for flag in flags] == ["answer_matches_key_under_credit"]
    assert flags[0].excluded_by_default is True


def test_notation_variant_is_not_flagged(tables: dict) -> None:
    """"x=-2" vs "-2" is a notation difference, not evidence of a wrong score."""

    assert scan_record(_record(tables, "R-0002"), _material(tables, "M-002")) == []


def test_rubric_total_mismatch_is_flagged(tables: dict) -> None:
    flags = scan_record(_record(tables, "R-0003"), _material(tables, "M-003"))
    assert [flag.code for flag in flags] == ["rubric_total_mismatch"]
    assert "写出正确结果" in flags[0].reason


def test_pending_answer_is_never_graded_or_flagged(tables: dict) -> None:
    """The answer text matches the key, but an ungraded row must stay ungraded."""

    assert scan_record(_record(tables, "R-0004"), _material(tables, "M-004")) == []


def test_disabled_over_credit_rule_stays_off(tables: dict) -> None:
    flag = DISABLED_RULES["answer_key_mismatch_full_credit"](
        _record(tables, "R-0002"), _material(tables, "M-002")
    )
    assert flag is not None and flag.code == "answer_key_mismatch_full_credit"
    assert "answer_key_mismatch_full_credit" not in RULES


# --------------------------------------------------------------------------- #
# scan, report, ledger
# --------------------------------------------------------------------------- #


def test_scan_report_is_valid_and_leaks_no_raw_text(review_context: dict) -> None:
    report = review_context["report"]
    assert validate_report(report) == []
    text = json.dumps(report, ensure_ascii=False)
    assert "SECRET-9" not in text
    assert "4a+7b" not in text


def test_scan_marks_the_expected_candidates(review_context: dict) -> None:
    report = review_context["report"]
    by_id = {item["record_id"]: item for item in report["candidates"]}
    assert set(by_id) == {"R-0001", "R-0003", "R-0007"}
    assert all(item["disputed"] for item in by_id.values())
    assert report["counts"]["disputed_records"] == 3
    assert by_id["R-0001"]["evidence_ref"]["csv_record_number"] == 2
    assert by_id["R-0003"]["official"]["rubric_sum"] == 2


def test_scan_does_not_touch_canonical(review_root: Path) -> None:
    base = review_root / "interim" / DATASET
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in base.glob("*.csv")}
    scan_dataset(
        DATASET,
        root=review_root / "interim",
        output=review_root / "r1",
        ledger_root=review_root,
        generated_at=STAMP,
    )
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in base.glob("*.csv")}
    assert before == after


def test_scan_is_deterministic(review_root: Path) -> None:
    for name in ("a", "b"):
        scan_dataset(
            DATASET,
            root=review_root / "interim",
            output=review_root / name,
            ledger_root=review_root,
            generated_at=STAMP,
        )
    assert load_report(review_root / "a") == load_report(review_root / "b")


def test_decide_appends_and_latest_wins(review_root: Path) -> None:
    for status, note in (
        ("dismissed", "核对原始作答：评分无误"),
        ("confirmed_issue", "复核：评分点与得分不一致"),
    ):
        decide(
            DATASET,
            "R-0001",
            status,
            note,
            root=review_root / "interim",
            ledger_root=review_root,
        )
    scan_dataset(
        DATASET,
        root=review_root / "interim",
        output=review_root / "review",
        ledger_root=review_root,
    )
    report = load_report(review_root / "review")
    candidate = next(item for item in report["candidates"] if item["record_id"] == "R-0001")
    assert candidate["review_status"] == "confirmed_issue"
    assert [item["review_status"] for item in candidate["decisions"]] == [
        "dismissed",
        "confirmed_issue",
    ]
    assert candidate["disputed"] is True


def test_dismissed_record_returns_to_evidence(review_root: Path) -> None:
    scan_dataset(
        DATASET,
        root=review_root / "interim",
        output=review_root / "first",
        ledger_root=review_root,
    )
    decide(
        DATASET,
        "R-0001",
        "dismissed",
        "核对原始作答与参考答案：评分无误",
        root=review_root / "interim",
        ledger_root=review_root,
    )
    scan_dataset(
        DATASET,
        root=review_root / "interim",
        output=review_root / "second",
        ledger_root=review_root,
    )
    from knowflow.diagnosis.pipeline import build_bundle

    bundle, _ = build_bundle(DATASET, root=review_root / "interim")
    context = build_context(load_report(review_root / "second"), review_root / "second", "official")
    profile = _profile(bundle, "S001", context)
    assert "review" not in _state(profile, "K-01")


def test_unknown_record_is_rejected(review_root: Path) -> None:
    with pytest.raises(ValueError, match="not a retained record"):
        decide(
            DATASET,
            "R-9999",
            "dismissed",
            "x",
            root=review_root / "interim",
            ledger_root=review_root,
        )


def test_record_without_a_clue_cannot_be_decided(review_root: Path) -> None:
    with pytest.raises(ValueError, match="no review clue"):
        decide(
            DATASET,
            "R-0002",
            "dismissed",
            "x",
            root=review_root / "interim",
            ledger_root=review_root,
        )


def test_decision_rejects_a_flag_the_record_does_not_have(review_root: Path) -> None:
    with pytest.raises(ValueError, match="unknown flag codes"):
        decide(
            DATASET,
            "R-0001",
            "dismissed",
            "x",
            flag_codes=["rubric_total_mismatch"],
            root=review_root / "interim",
            ledger_root=review_root,
        )


def test_blank_note_is_rejected(review_root: Path) -> None:
    with pytest.raises(ValueError, match="review note"):
        decide(
            DATASET,
            "R-0001",
            "dismissed",
            "   ",
            root=review_root / "interim",
            ledger_root=review_root,
        )


def test_ledger_refuses_changed_source(review_root: Path) -> None:
    scan_dataset(
        DATASET,
        root=review_root / "interim",
        output=review_root / "first",
        ledger_root=review_root,
    )
    records = review_root / "interim" / DATASET / "records.csv"
    records.write_bytes(records.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="canonical tables changed"):
        scan_dataset(
            DATASET,
            root=review_root / "interim",
            output=review_root / "second",
            ledger_root=review_root,
        )


def test_context_rejects_a_changed_report(review_context: dict) -> None:
    manifest = {
        "review": {
            "report_path": review_context["report_path"],
            "report_sha256": review_context["report_sha256"],
            "policy": "official",
        }
    }
    assert context_from_run_manifest(manifest) is not None
    Path(review_context["report_path"]).write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed since the run"):
        context_from_run_manifest(manifest)


# --------------------------------------------------------------------------- #
# diagnosis
# --------------------------------------------------------------------------- #


def test_review_block_records_both_views(bundle: dict, review_context: dict) -> None:
    profile = _profile(bundle, "S001", review_context)
    state = _state(profile, "K-01")
    assert state["review"]["disputed_record_ids"] == ["R-0001"]
    assert state["mastery"] == 0.6  # official: 2 full credit of 3
    assert state["review"]["official_mastery"] == 0.6
    assert state["review"]["usable_mastery"] == 0.75
    assert state["review"]["usable_status"] == "insufficient_evidence"
    assert state["review"]["status_changed"] is True
    assert state["evidence_count"] == 3  # official ledger untouched


def test_exclude_flagged_policy_moves_top_level_numbers(bundle: dict, review_context: dict) -> None:
    context = {**review_context, "policy": "exclude_flagged"}
    profile = _profile(bundle, "S001", context)
    state = _state(profile, "K-01")
    assert state["mastery"] == 0.75
    assert state["review"]["official_mastery"] == 0.6
    assert state["evidence_count"] == 3
    assert state["state_counts"]["observed_wrong"] == 1
    assert validate_student(profile, bundle, DiagnosisConfig(), context) == []


def test_profile_without_review_is_unchanged_and_valid(bundle: dict) -> None:
    profile = _profile(bundle, "S001")
    assert "review" not in _state(profile, "K-01")
    assert validate_student(profile, bundle, DiagnosisConfig(), None) == []


def test_disputed_loss_never_enters_rubric_evidence(bundle: dict, review_context: dict) -> None:
    profile = _profile(bundle, "S001", review_context)
    issue = next(item for item in profile["issues"] if item["knowledge_id"] == "K-01")
    assert issue["rubric_evidence"] == []
    assert [point["record_id"] for point in issue["disputed_rubric_evidence"]] == ["R-0001"]
    assert issue["disputed_rubric_evidence"][0]["review_status"] == "flagged"


def test_validate_student_recomputes_the_review_block(bundle: dict, review_context: dict) -> None:
    profile = _profile(bundle, "S001", review_context)
    assert validate_student(profile, bundle, DiagnosisConfig(), review_context) == []
    _state(profile, "K-01")["review"]["usable_mastery"] = 0.9
    errors = validate_student(profile, bundle, DiagnosisConfig(), review_context)
    assert any("usable mastery" in error for error in errors)


def test_class_patterns_ignore_disputed_losses(bundle: dict, review_context: dict) -> None:
    node = bundle["nodes"][0]
    config = DiagnosisConfig()
    with_review = [
        build_student_profile(bundle, student, node, config, review_context)
        for student in bundle["students"]
    ]
    without = [
        build_student_profile(bundle, student, node, config) for student in bundle["students"]
    ]
    disputed_ids = {
        record_id
        for profile in with_review
        for pattern in build_class_profile(
            [profile], "ALL", bundle, node["node_id"], review_context
        )["rubric_patterns"]
        for record_id in pattern["example_record_ids"]
    }
    plain_patterns = build_class_profile(without, "ALL", bundle, node["node_id"])[
        "rubric_patterns"
    ]
    plain_ids = {record_id for pattern in plain_patterns for record_id in pattern["example_record_ids"]}
    assert "R-0001" not in disputed_ids and "R-0007" not in disputed_ids
    assert "R-0001" in plain_ids


# --------------------------------------------------------------------------- #
# recommendations
# --------------------------------------------------------------------------- #


def test_plan_never_uses_a_disputed_record_as_basis(
    bundle: dict, review_context: dict, knowledge_base: dict
) -> None:
    rec = _recommend(bundle, knowledge_base, "S001", review_context)
    for item in rec["plan"]:
        assert "R-0001" not in item.get("basis_records", [])
        assert "R-0001" not in item["reason"]
    flags = [flag for item in rec["plan"] for flag in item.get("review_flags", [])]
    assert {"record_id": "R-0001", "review_status": "flagged"} in flags
    assert rec["review_context"]["excluded_record_ids"] == ["R-0001"]


def test_only_disputed_evidence_becomes_review_required(
    bundle: dict, review_context: dict, knowledge_base: dict
) -> None:
    rec = _recommend(bundle, knowledge_base, "S004", review_context)
    assert [entry["issue_id"] for entry in rec["review_required"]] == ["IS-004-01"]
    assert rec["review_required"][0]["record_ids"] == ["R-0007"]
    item = next(entry for entry in rec["plan"] if entry["issue_id"] == "IS-004-01")
    assert item["activity_type"] == "probe"


def test_plan_without_review_keeps_old_shape(
    bundle: dict, knowledge_base: dict
) -> None:
    rec = _recommend(bundle, knowledge_base, "S001", None)
    assert "review_context" not in rec and "review_required" not in rec
    assert all("basis_records" not in item for item in rec["plan"])


def test_validator_rejects_a_disputed_basis(
    bundle: dict, review_context: dict, knowledge_base: dict
) -> None:
    catalog = build_catalog(knowledge_base)
    profile = _profile(bundle, "S001", review_context)
    rec = _recommend(bundle, knowledge_base, "S001", review_context)
    node_available = set(bundle["nodes"][0]["material_ids"])
    assert (
        validate_recommendation(
            rec, profile, catalog, node_available, bundle["records"], "0" * 64, review_context
        )
        == []
    )
    rec["plan"][0]["basis_records"] = ["R-0001"]
    errors = validate_recommendation(
        rec, profile, catalog, node_available, bundle["records"], "0" * 64, review_context
    )
    assert any("disputed record" in error for error in errors)


def test_saved_run_with_review_verifies(review_root: Path, bundle: dict, review_context: dict,
                                        knowledge_base: dict) -> None:
    run = review_root / "run"
    run_diagnosis(bundle, run, node_id="N01", review=review_context)
    assert validate_saved_run(run)["gate"] == "pass"
    knowledge_path = review_root / "knowledge_base.json"
    write_knowledge_base(knowledge_base, knowledge_path)
    result = recommend_run(
        run=str(run),
        knowledge=str(knowledge_path),
        node="N01",
        output=str(review_root / "rec"),
    )
    assert result["gate"] == "pass"
    recommendation = json.loads(
        (review_root / "rec" / "nodes/N01/students/S001.json").read_text(encoding="utf-8")
    )
    assert (
        recommendation["review_context"]["report_sha256"] == review_context["report_sha256"]
    )
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["review"]["policy"] == "official"
    assert manifest["review"]["report_sha256"] == review_context["report_sha256"]


def test_run_without_review_keeps_old_shape(review_root: Path, bundle: dict) -> None:
    run = review_root / "plain"
    run_diagnosis(bundle, run, node_id="N01")
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["review"] is None
    assert validate_saved_run(run)["gate"] == "pass"


def test_cli_registers_review_commands() -> None:
    from knowflow.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["review-scan"]).func.__name__ == "_cmd_review_scan"
    args = parser.parse_args(
        ["review-decide", "--record", "R-0001", "--status", "dismissed", "--note", "ok"]
    )
    assert args.func.__name__ == "_cmd_review_decide"
    assert args.reviewer == "local_demo_user"
