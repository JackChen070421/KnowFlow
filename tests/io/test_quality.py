"""Cleaning rules: five states, dedupe scope, clamp and reassign guards."""

from __future__ import annotations

import csv

import pytest

from knowflow.io import AdaptError, run_adapt
from knowflow.io import quality
from knowflow.io.adapters import parse_rubric

RECORDS_REL = "4_赛题数据/模拟学情数据/作答记录.csv"
FIXED_TIME = "2026-11-10T00:00:00+08:00"


def _rewrite_record(mini, record_id: str, column: str, value: str) -> None:
    path = mini.raw / RECORDS_REL
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for row in rows:
        if row["记录编号"] == record_id:
            row[column] = value
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _drop_records(mini, record_ids: set[str]) -> None:
    path = mini.raw / RECORDS_REL
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = [row for row in reader if row["记录编号"] not in record_ids]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _read_records(mini) -> list[dict[str, str]]:
    with (mini.out / "records.csv").open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_classify_state() -> None:
    assert quality.classify_state({"attempted": False, "score": None, "is_correct": None}) == (
        "assigned_not_attempted"
    )
    assert quality.classify_state({"attempted": True, "score": None, "is_correct": None}) == (
        "pending"
    )
    assert quality.classify_state({"attempted": True, "score": 1, "is_correct": True}) == (
        "observed_correct"
    )
    assert quality.classify_state({"attempted": True, "score": 0, "is_correct": False}) == (
        "observed_wrong"
    )


def test_cross_node_answers_are_two_observations(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    rows = [
        row
        for row in _read_records(mini_dataset)
        if row["student_id"] == "S001" and row["material_id"] == "M-001"
    ]
    assert sorted(row["node_id"] for row in rows) == ["N01", "N02"]
    assert len(_read_records(mini_dataset)) == 9


def test_clamp_requires_rubric_evidence(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    _rewrite_record(mini_dataset, "DR0005", "评分点得分", "Q001P1=0")
    with pytest.raises(AdaptError) as excinfo:
        run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    assert "无法安全截断" in str(excinfo.value)


def test_node_reassign_requires_matching_date(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    _rewrite_record(mini_dataset, "DR0009", "模拟提交时间", "2026-01-21T10:10:00+08:00")
    with pytest.raises(AdaptError) as excinfo:
        run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    assert "无法用提交日期唯一改判" in str(excinfo.value)


def test_partial_node_student_is_reported_not_fabricated(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    _drop_records(mini_dataset, {"DR0002", "DR0008"})
    summary = run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    anomalies = summary["report"]["anomalies"]
    missing = [item for item in anomalies if item["record_id"] is None]
    assert len(missing) == 1
    assert "缺少" in missing[0]["reason"]
    assert "N02" in missing[0]["reason"]


def test_error_messages_do_not_echo_cell_content() -> None:
    with pytest.raises(AdaptError) as excinfo:
        parse_rubric("Q001 缺少行号后缀的内容", "Q001")
    assert "缺少行号后缀" not in str(excinfo.value)
    assert "Q001" in str(excinfo.value)
