"""End-to-end adapter: raw official package → canonical tables + quality report."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..contracts import load_json, repo_root
from . import adapters, mapping, quality
from .errors import AdaptError

CANONICAL_VERSION = mapping.CANONICAL_VERSION

#: Canonical table → output file name (also the schema stem).
TABLES: dict[str, str] = {
    "objectives": "objectives.csv",
    "knowledge": "knowledge.csv",
    "materials": "materials.csv",
    "qmatrix": "qmatrix.csv",
    "edges": "edges.csv",
    "students": "students.csv",
    "nodes": "nodes.csv",
    "records": "records.csv",
    "record_details": "record_details.csv",
    "tasks": "tasks.csv",
}

PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "objectives": ("objective_id",),
    "knowledge": ("knowledge_id",),
    "materials": ("material_id",),
    "qmatrix": ("material_id", "knowledge_id"),
    "edges": ("from_id", "to_id", "edge_type"),
    "students": ("student_id",),
    "nodes": ("node_id",),
    "records": ("record_id",),
    "record_details": ("csv_record_number",),
    "tasks": ("task_id",),
}


@dataclass
class OfficialTables:
    course: list[dict[str, str]]
    materials: list[dict[str, str]]
    students: list[dict[str, str]]
    nodes: list[dict[str, str]]
    records: list[dict[str, str]]
    input_files: list[dict[str, object]]


@dataclass
class Bundle:
    dataset_id: str
    generated_at: str
    tables: dict[str, list[dict[str, object]]]
    report: dict[str, object]
    raw_record_rows: int
    counters: quality.ReportCounters = field(default_factory=quality.ReportCounters)

    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}


def now_iso() -> str:
    """Beijing time, seconds precision — the same clock the official data uses."""

    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_table(
    path: Path, expected_columns: tuple[str, ...], label: str
) -> list[dict[str, str]]:
    if not path.is_file():
        raise AdaptError(
            f"缺少官方文件: {path}\n"
            "  data/raw 不会随 git pull 带下来，先运行 "
            "python scripts/ingest_raw.py --source \"<赛题数据目录>\""
        )
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        missing = [column for column in expected_columns if column not in header]
        extra = [column for column in header if column not in expected_columns]
        if missing or extra:
            raise AdaptError(
                f"{label}: 列与数据字典不一致 missing={missing} extra={extra}；"
                "未知列不猜，确认后再扩适配层"
            )
        rows: list[dict[str, str]] = []
        for line_no, row in enumerate(reader, start=2):
            if None in row:
                raise AdaptError(f"{label}:{line_no}: 列数多于表头")
            if any(value is None for value in row.values()):
                raise AdaptError(f"{label}:{line_no}: 列数少于表头")
            rows.append({key: value for key, value in row.items() if key is not None})
    return rows


def load_official(raw_dir: Path | str, dataset_id: str = mapping.DATASET_ID) -> OfficialTables:
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        raise AdaptError(
            f"原始数据目录不存在: {raw_dir}\n"
            "  先运行 python scripts/ingest_raw.py --source \"<赛题数据目录>\""
        )

    manifest_path = raw_dir / "manifest.json"
    manifest: dict[str, object] | None = None
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
    recorded: dict[str, dict[str, object]] = {}
    if manifest is not None:
        recorded = {
            str(item["path"]): item for item in manifest.get("files", [])  # type: ignore[index]
        }

    tables: dict[str, list[dict[str, str]]] = {}
    input_files: list[dict[str, object]] = []
    for name, relative in mapping.OFFICIAL_FILES.items():
        path = raw_dir / relative
        rows = _read_table(path, mapping.OFFICIAL_COLUMNS[name], relative)
        digest = sha256_file(path)
        entry = {"path": relative, "sha256": digest, "rows": len(rows)}
        earlier = recorded.get(relative)
        if earlier is not None:
            if earlier.get("sha256") != digest:
                raise AdaptError(
                    f"{relative}: sha256 与 manifest.json 不一致；数据可能被改动或换版"
                )
            if earlier.get("rows") is not None and int(earlier["rows"]) != len(rows):
                raise AdaptError(
                    f"{relative}: 行数 {len(rows)} 与 manifest.json {earlier['rows']} 不一致"
                )
        input_files.append(entry)
        tables[name] = rows

    return OfficialTables(
        course=tables["course"],
        materials=tables["materials"],
        students=tables["students"],
        nodes=tables["nodes"],
        records=tables["records"],
        input_files=input_files,
    )


def build_bundle(
    tables: OfficialTables,
    dataset_id: str,
    generated_at: str,
) -> Bundle:
    anomalies: list[quality.Anomaly] = []
    counters = quality.ReportCounters()

    grade = int(tables.students[0]["年级"])
    students = adapters.adapt_students(tables.students)
    materials = adapters.adapt_materials(tables.materials)
    objectives = adapters.adapt_objectives(tables.course, tables.materials, grade)
    knowledge = adapters.adapt_knowledge(tables.course)
    qmatrix = adapters.adapt_qmatrix(tables.materials)
    edges = adapters.adapt_edges(tables.course)
    nodes = adapters.adapt_nodes(tables.nodes)

    official_materials = {row["材料编号"].strip(): row for row in tables.materials}
    records, record_details = quality.build_records(
        tables.records, nodes, official_materials, anomalies, counters
    )
    quality.find_partial_node_students(records, nodes, anomalies)

    report = quality.build_report(
        dataset_id=dataset_id,
        generated_at=generated_at,
        input_files=tables.input_files,
        students=students,
        materials=materials,
        records=records,
        anomalies=anomalies,
        counters=counters,
    )

    canonical = {
        "objectives": objectives,
        "knowledge": knowledge,
        "materials": materials,
        "qmatrix": qmatrix,
        "edges": edges,
        "students": students,
        "nodes": nodes,
        "records": records,
        "record_details": record_details,
        "tasks": [],
    }
    return Bundle(
        dataset_id=dataset_id,
        generated_at=generated_at,
        tables=canonical,
        report=report,
        raw_record_rows=len(tables.records),
        counters=counters,
    )


def validate_bundle(bundle: Bundle) -> list[str]:
    """G2 (references) + G3 (consistency) checks; an empty list means OK."""

    tables = bundle.tables
    errors: list[str] = []

    keys: dict[str, list[tuple[object, ...]]] = {}
    for name, fields in PRIMARY_KEYS.items():
        seen: set[tuple[object, ...]] = set()
        keys[name] = []
        for row in tables[name]:
            key = tuple(row[field] for field in fields)
            if key in seen:
                errors.append(f"{name}: duplicate primary key {key}")
            seen.add(key)
            keys[name].append(key)

    objective_ids = {row["objective_id"] for row in tables["objectives"]}
    knowledge_ids = {row["knowledge_id"] for row in tables["knowledge"]}
    material_ids = {row["material_id"] for row in tables["materials"]}
    student_ids = {row["student_id"] for row in tables["students"]}
    node_ids = {row["node_id"] for row in tables["nodes"]}
    all_ids = objective_ids | knowledge_ids | material_ids

    for row in tables["knowledge"]:
        if row["objective_id"] not in objective_ids:
            errors.append(f"knowledge {row['knowledge_id']}: 悬空 objective_id")
    for row in tables["materials"]:
        if row["objective_id"] is not None and row["objective_id"] not in objective_ids:
            errors.append(f"materials {row['material_id']}: 悬空 objective_id")
        if row["material_type"] != "reference" and row["objective_id"] is None:
            errors.append(f"materials {row['material_id']}: 非参考材料必须有 objective_id")
    for row in tables["qmatrix"]:
        if row["material_id"] not in material_ids:
            errors.append(f"qmatrix {row['material_id']}: 悬空 material_id")
        if row["knowledge_id"] not in knowledge_ids:
            errors.append(f"qmatrix {row['knowledge_id']}: 悬空 knowledge_id")
    for row in tables["students"]:
        if not str(row["group_id"]).startswith("G"):
            errors.append(f"students {row['student_id']}: group_id 必须以 G 开头")
    for row in tables["edges"]:
        if row["from_id"] == row["to_id"]:
            errors.append(f"edges: 自环 {row['from_id']}")
        for field_name in ("from_id", "to_id"):
            if row[field_name] not in all_ids:
                errors.append(f"edges: 悬空 {field_name} {row[field_name]}")

    node_meta = quality.node_index(tables["nodes"])
    for node_id, meta in node_meta.items():
        for objective_id in meta["taught"]:
            if objective_id not in objective_ids:
                errors.append(f"nodes {node_id}: 悬空 taught_objective {objective_id}")
        for material_id in meta["available"]:
            if material_id not in material_ids:
                errors.append(f"nodes {node_id}: 悬空 available_material {material_id}")

    for row in tables["records"]:
        if row["student_id"] not in student_ids:
            errors.append(f"records {row['record_id']}: 悬空 student_id")
        if row["material_id"] not in material_ids:
            errors.append(f"records {row['record_id']}: 悬空 material_id")
        if row["node_id"] not in node_ids:
            errors.append(f"records {row['record_id']}: 悬空 node_id")
        elif row["material_id"] not in node_meta[str(row["node_id"])]["available"]:
            errors.append(
                f"records {row['record_id']}: 材料 {row['material_id']} 不在节点 "
                f"{row['node_id']} 的可用题目中"
            )
        if not row["assigned"]:
            errors.append(f"records {row['record_id']}: official 数据不应出现 assigned=false")
        score = row["score"]
        if score is not None:
            if float(score) < 0 or float(score) > float(row["max_score"]):
                errors.append(f"records {row['record_id']}: score 超出 [0, max_score]")
            if row["is_correct"] != (float(score) == float(row["max_score"])):
                errors.append(f"records {row['record_id']}: is_correct 与 score 不一致")
        else:
            if row["is_correct"] is not None:
                errors.append(f"records {row['record_id']}: 无得分却有 is_correct")
            if row["attempted"] and row["node_id"] is None:
                errors.append(f"records {row['record_id']}: 缺少 node_id")

    records_by_id = {str(row["record_id"]): row for row in tables["records"]}
    kept_details: dict[str, int] = {}
    for row in tables["record_details"]:
        record_id = str(row["record_id"])
        record = records_by_id.get(record_id)
        if record is None:
            errors.append(
                f"record_details {row['csv_record_number']}: 悬空 record_id {record_id}"
            )
            continue
        for field_name in ("student_id", "material_id", "node_id"):
            if row[field_name] != record[field_name]:
                errors.append(
                    f"record_details {row['csv_record_number']}: {field_name} "
                    f"与记录 {record_id} 不一致"
                )
        if row["kept"]:
            if record_id in kept_details:
                errors.append(
                    f"record_details {row['csv_record_number']}: 记录 {record_id} 有多条 kept 明细"
                )
            kept_details[record_id] = int(row["csv_record_number"])  # type: ignore[arg-type]
    for record_id in sorted(set(records_by_id) - set(kept_details)):
        errors.append(f"records {record_id}: 缺少 kept 明细，证据不可回查")
    if len(tables["record_details"]) != bundle.raw_record_rows:
        errors.append(
            f"record_details: 行数 {len(tables['record_details'])} "
            f"!= 原始记录行数 {bundle.raw_record_rows}"
        )

    assessment_materials = {
        row["material_id"]
        for row in tables["materials"]
        if row["material_type"] in {"assessment", "practice", "probe"}
    }
    measured = {row["material_id"] for row in tables["qmatrix"]}
    for material_id in sorted(assessment_materials - measured):
        errors.append(f"qmatrix: 测评材料 {material_id} 没有挂任何知识点")
    assessment_rows = [
        row for row in tables["qmatrix"] if row["item_type"] == "assessment"
    ]
    covered = {row["knowledge_id"] for row in assessment_rows}
    for knowledge_id in sorted(knowledge_ids - covered):
        errors.append(f"qmatrix: 知识点 {knowledge_id} 没有 assessment 题目")

    states = quality.state_counts(tables["records"])
    report = bundle.report
    if report["records_by_state"] != states:
        errors.append("report: records_by_state 与 records 实际统计不一致")
    if sum(states.values()) != len(tables["records"]) or report["total_records"] != len(
        tables["records"]
    ):
        errors.append("report: total_records 与 records 行数不一致")
    if states["unobserved"] != 0:
        errors.append("report: unobserved 必须为 0")
    if bundle.raw_record_rows - len(tables["records"]) != report["duplicates_removed"]:
        errors.append("report: duplicates_removed 与原始行数不一致")

    return errors


def schema_properties(name: str) -> list[str]:
    root = repo_root()
    schema_path = root / "schemas" / "input" / f"{name}.schema.json"
    return list(load_json(schema_path)["properties"])


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def serialize_table(name: str, rows: list[dict[str, object]]) -> str:
    fields = schema_properties(name)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=fields, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _cell(row[field]) for field in fields})
    return buffer.getvalue()


def _write_atomic(path: Path, text: str) -> None:
    """Write via a temp name and atomically replace: no half-written table survives."""

    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def write_bundle(bundle: Bundle, out_dir: Path | str) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, filename in TABLES.items():
        _write_atomic(out_dir / filename, serialize_table(name, bundle.tables[name]))
    report_path = out_dir / "data_quality_report.json"
    _write_atomic(
        report_path,
        json.dumps(bundle.report, ensure_ascii=False, indent=2) + "\n",
    )
    return report_path


def run_adapt(
    raw_dir: Path | str,
    out_dir: Path | str,
    dataset_id: str = mapping.DATASET_ID,
    generated_at: str | None = None,
) -> dict[str, object]:
    tables = load_official(raw_dir, dataset_id)
    bundle = build_bundle(tables, dataset_id, generated_at or now_iso())
    errors = validate_bundle(bundle)
    if errors:
        raise AdaptError("canonical 校验失败:\n  - " + "\n  - ".join(errors))
    report_path = write_bundle(bundle, out_dir)
    return {
        "dataset_id": dataset_id,
        "generated_at": bundle.generated_at,
        "counts": bundle.counts(),
        "report": bundle.report,
        "report_path": str(report_path),
        "out_dir": str(out_dir),
    }


def verify_written(
    raw_dir: Path | str,
    out_dir: Path | str,
    dataset_id: str = mapping.DATASET_ID,
    generated_at: str | None = None,
) -> tuple[list[str], Bundle]:
    """Recompute in memory and compare with the files on disk."""

    tables = load_official(raw_dir, dataset_id)
    bundle = build_bundle(tables, dataset_id, generated_at or now_iso())
    errors = validate_bundle(bundle)
    out_dir = Path(out_dir)
    for name, filename in TABLES.items():
        path = out_dir / filename
        if not path.is_file():
            errors.append(f"{filename}: 文件不存在")
            continue
        if path.read_text(encoding="utf-8") != serialize_table(name, bundle.tables[name]):
            errors.append(f"{filename}: 与重算结果不一致（请重跑 build_canonical）")
    report_path = out_dir / "data_quality_report.json"
    if not report_path.is_file():
        errors.append("data_quality_report.json: 文件不存在")
    else:
        written = load_json(report_path)
        expected = dict(bundle.report)
        written = dict(written) if isinstance(written, dict) else {}
        written.pop("generated_at", None)
        expected.pop("generated_at", None)
        if written != expected:
            errors.append("data_quality_report.json: 与重算结果不一致")
    return errors, bundle


__all__ = [
    "CANONICAL_VERSION",
    "Bundle",
    "OfficialTables",
    "TABLES",
    "build_bundle",
    "load_official",
    "now_iso",
    "run_adapt",
    "serialize_table",
    "validate_bundle",
    "verify_written",
    "write_bundle",
]
