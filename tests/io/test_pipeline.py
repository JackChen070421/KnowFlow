"""End-to-end build: counts, schema validity, report, idempotency, tampering."""

from __future__ import annotations

import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from knowflow.contracts import build_registry, load_json, repo_root, validate_instance
from knowflow.io import AdaptError, run_adapt, verify_written
from knowflow.io.pipeline import TABLES, schema_properties

EXPECTED_COUNTS = {
    "objectives": 2,
    "knowledge": 3,
    "materials": 6,
    "qmatrix": 4,
    "edges": 3,
    "students": 2,
    "nodes": 2,
    "records": 9,
    "tasks": 0,
}

FIXED_TIME = "2026-11-10T00:00:00+08:00"


def _read_table(path) -> list[dict[str, str]]:  # type: ignore[no-untyped-def]
    import csv

    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_build_end_to_end(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    summary = run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)

    assert summary["counts"] == EXPECTED_COUNTS

    report = summary["report"]
    assert report["dataset_id"] == "mini-v1"
    assert report["total_records"] == 9
    assert report["duplicates_removed"] == 1
    assert report["records_by_state"] == {
        "observed_correct": 5,
        "observed_wrong": 2,
        "assigned_not_attempted": 1,
        "pending": 1,
        "unobserved": 0,
    }
    assert report["missing"] == {
        "students_without_records": 0,
        "items_without_records": 0,
        "empty_answers": 1,
    }
    assert len(report["anomalies"]) == 5
    reasons = " | ".join(
        f"{item['reason']} {item['action']}" for item in report["anomalies"]
    )
    for keyword in ("超出满分", "评分点合计", "主题", "改判", "更高修订版本"):
        assert keyword in reasons
    assert len(report["field_quality"]) == 8
    assert len(report["handling_rules"]) >= 10

    # every canonical row matches its schema (typed rows from the rebuild)
    errors, bundle = verify_written(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    assert errors == []
    assert bundle.counts() == EXPECTED_COUNTS

    registry = build_registry()
    for name, filename in TABLES.items():
        schema = load_json(repo_root() / "schemas" / "input" / f"{name}.schema.json")
        validator = Draft202012Validator(schema, registry=registry)
        rows = bundle.tables[name]
        assert len(rows) == EXPECTED_COUNTS[name], name
        for row in rows:
            assert list(validator.iter_errors(row)) == [], (name, row)

    # the files on disk carry the schema columns and the same row counts
    for name, filename in TABLES.items():
        path = mini_dataset.out / filename
        header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
        assert header == schema_properties(name), name
        assert len(_read_table(path)) == EXPECTED_COUNTS[name], name

    # the quality report matches its output schema
    assert (
        validate_instance(
            repo_root() / "schemas" / "output" / "data_quality_report.schema.json",
            mini_dataset.out / "data_quality_report.json",
        )
        == []
    )


def test_runs_are_byte_identical_with_fixed_timestamp(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in mini_dataset.out.iterdir()
        if path.is_file()
    }
    run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in mini_dataset.out.iterdir()
        if path.is_file()
    }
    assert first == second


def test_verify_detects_hand_edits(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    records_path = mini_dataset.out / "records.csv"
    text = records_path.read_text(encoding="utf-8")
    records_path.write_text(text.replace(",true,", ",false,", 1), encoding="utf-8")
    errors, _ = verify_written(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    assert any("records.csv" in error for error in errors)


def test_missing_raw_directory_is_a_clear_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(AdaptError) as excinfo:
        run_adapt(tmp_path / "absent", tmp_path / "out", "mini-v1", FIXED_TIME)
    assert "ingest_raw" in str(excinfo.value)


def test_unknown_column_fails_loudly(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    import csv

    path = mini_dataset.raw / "4_赛题数据" / "模拟学情数据" / "课程要求.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    fields.append("新增列")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            row["新增列"] = "x"
            writer.writerow(row)
    with pytest.raises(AdaptError) as excinfo:
        run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    assert "未知列" in str(excinfo.value) or "列与数据字典不一致" in str(excinfo.value)


def test_failed_build_writes_nothing(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    import csv

    path = mini_dataset.raw / "4_赛题数据" / "模拟学情数据" / "作答记录.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    rows[0]["评分状态"] = "重考"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(AdaptError) as excinfo:
        run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    assert "未知评分状态" in str(excinfo.value)
    assert not mini_dataset.out.exists()


def test_report_is_parseable_json(mini_dataset) -> None:  # type: ignore[no-untyped-def]
    run_adapt(mini_dataset.raw, mini_dataset.out, "mini-v1", FIXED_TIME)
    payload = json.loads(
        (mini_dataset.out / "data_quality_report.json").read_text(encoding="utf-8")
    )
    assert payload["input_files"]
    assert all(len(item["sha256"]) == 64 for item in payload["input_files"])
