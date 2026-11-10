"""End-to-end tests of the raw-to-contract boundary, using generated synthetic data."""

import csv
import json
import subprocess
import sys
from pathlib import Path

from knowflow.contracts import validate_instance
from knowflow.io.records_adapter import COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def prepare(tmp_path, *, bad_score=False, missing_details=False):
    fields = list(COLUMNS)
    if missing_details:
        fields = fields[:-3]
    rows = []
    for index, status in enumerate(["已评分", "待评分", "未作答"], 1):
        row = dict.fromkeys(COLUMNS, "")
        row.update({
            "记录编号": f"DEMO{index:03}", "学生编号": "DEMO-STUDENT",
            "材料编号": "Q001", "修订版本": "1", "评分状态": status,
            "得分": ("4" if bad_score else "2") if index == 1 else "",
            "满分": "3", "学生最终作答": "2" if index != 3 else "",
            "解答过程": "first step\nsecond step" if index == 1 else "",
            "评分点得分": "P1=1;P2=1;P3=0" if index == 1 else "",
        })
        rows.append({key: row[key] for key in fields})
    source = tmp_path / "raw.csv"
    with source.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (tmp_path / "students.csv").write_text("学生编号\nDEMO-STUDENT\n", encoding="utf-8")
    (tmp_path / "materials.csv").write_text("材料编号\nQ001\n", encoding="utf-8")
    return [
        sys.executable, str(ROOT / "scripts/export_records_json.py"),
        "--source", str(source), "--output", str(tmp_path / "records.json"),
        "--id-map", str(tmp_path / "map.json"), "--init-id-map",
        "--students", str(tmp_path / "students.csv"),
        "--materials", str(tmp_path / "materials.csv"),
    ]


def run(command):
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_cli_exports_valid_linked_arrays_and_preserves_original(tmp_path):
    command = prepare(tmp_path)
    original = (tmp_path / "raw.csv").read_bytes()
    result = run(command)
    assert result.returncode == 0, result.stderr
    records = json.loads((tmp_path / "records.json").read_text(encoding="utf-8"))
    details = json.loads((tmp_path / "records_details.json").read_text(encoding="utf-8"))
    assert len(records) == len(details) == 3
    assert records[1]["attempted"] is True and records[1]["score"] is None
    assert records[2]["attempted"] is False and records[2]["score"] is None
    assert [x["record_id"] for x in records] == [x["record_id"] for x in details]
    assert details[0]["solution_process"] == "first step\nsecond step"
    assert details[2]["scoring_point_scores"] == "NULL"
    assert (tmp_path / "raw.csv").read_bytes() == original
    for name, file in [("records_export", "records.json"), ("record_details_export", "records_details.json")]:
        assert validate_instance(ROOT / f"schemas/output/{name}.schema.json", tmp_path / file, root=ROOT) == []


def test_cli_missing_detail_columns_become_null_strings(tmp_path):
    assert run(prepare(tmp_path, missing_details=True)).returncode == 0
    rows = json.loads((tmp_path / "records_details.json").read_text(encoding="utf-8"))
    assert all(row[key] == "NULL" for row in rows for key in ["final_answer", "solution_process", "scoring_point_scores"])


def test_cli_strict_failure_and_explicit_rejection_report(tmp_path):
    command = prepare(tmp_path, bad_score=True)
    assert run(command).returncode == 1
    assert not (tmp_path / "records.json").exists()
    assert not (tmp_path / "records_details.json").exists()
    command.remove("--init-id-map")
    command += ["--skip-invalid", "--issues-output", str(tmp_path / "issues.json")]
    result = run(command)
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "issues.json").read_text(encoding="utf-8"))
    assert (report["input_records"], report["exported_records"], report["rejected_records"]) == (3, 2, 1)
    assert report["issues"][0]["csv_record_number"] == 2
    records = json.loads((tmp_path / "records.json").read_text(encoding="utf-8"))
    details = json.loads((tmp_path / "records_details.json").read_text(encoding="utf-8"))
    assert [x["record_id"] for x in records] == [x["record_id"] for x in details]
    assert [x["csv_record_number"] for x in details] == [3, 4]


def test_cli_refuses_path_collisions_and_overwrite(tmp_path):
    command = prepare(tmp_path)
    collision = run(command + ["--details-output", str(tmp_path / "records.json")])
    assert collision.returncode == 1
    assert not (tmp_path / "map.json").exists()
    assert run(command).returncode == 0
    before = (tmp_path / "records.json").read_bytes()
    assert run(command).returncode == 1
    assert (tmp_path / "records.json").read_bytes() == before
