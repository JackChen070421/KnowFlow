"""Task-2 commands on top of the canonical tables produced by ``src/knowflow/io/``.

The data layer has already resolved revisions, rejected malformed rows and kept
verbatim evidence in ``record_details.csv``; this module only reads it.  No file
here writes outside ``artifacts/`` or ``data/interim/`` (both git-ignored), and no
raw answer text ever enters the diagnosis bundle.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from knowflow.contracts import repo_root
from knowflow.diagnosis.mastery import DiagnosisConfig
from knowflow.diagnosis.profiles import build_class_profile, build_student_profile, optional_mean
from knowflow.diagnosis.validation import (
    schema_errors,
    validate_bundle,
    validate_class,
    validate_saved_run,
    validate_student,
)

SCHEMA_PREFIX = "https://knowflow.local/schemas/"
RUN_SCHEMA_VERSION = "0.5.0"
RAW_RECORD_FILE = "4_赛题数据/模拟学情数据/作答记录.csv"


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# canonical tables → diagnosis bundle
# --------------------------------------------------------------------------- #


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _bool(value: str) -> bool | None:
    text = (value or "").strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    return None


def _number(value: str) -> float | None:
    text = (value or "").strip()
    return float(text) if text else None


def _integer(value: str) -> int | None:
    text = (value or "").strip()
    return int(text) if text else None


def _json_or(default, value: str):
    text = (value or "").strip()
    return json.loads(text) if text else default


def _material_rubric(row: dict[str, str]) -> list[dict]:
    items = _json_or([], row.get("rubric_json", ""))
    return [
        {
            "point_id": item["id"],
            "label": item["text"],
            "max_score": float(item["points"]),
        }
        for item in items
    ]


def _score_points(raw: str, rubric: list[dict], score: float | None) -> list[dict]:
    """Attach rubric definitions to a record's official point scores.

    A point set is only exposed when it covers the whole rubric and reconciles
    with the official total; otherwise the total stands alone and the points are
    reported as unusable rather than inferred.
    """

    if score is None or not rubric:
        return []
    scores = _json_or({}, raw)
    by_id = {item["point_id"]: item for item in rubric}
    if set(scores) != set(by_id):
        return []
    points = [
        {**by_id[pid], "score": float(value)} for pid, value in sorted(scores.items())
    ]
    if abs(sum(p["score"] for p in points) - score) > 1e-9:
        return []
    if any(p["score"] < 0 or p["score"] > p["max_score"] for p in points):
        return []
    return points


def load_canonical(
    dataset_id: str, root: Path | None = None
) -> tuple[Path, dict[str, list[dict[str, str]]], dict]:
    base = (Path(root) if root is not None else repo_root() / "data" / "interim") / dataset_id
    if not base.is_dir():
        raise ValueError(
            f"canonical tables not found: {base}; run scripts/build_canonical.py first"
        )
    tables = {
        name: _read_csv(base / f"{name}.csv")
        for name in [
            "students",
            "knowledge",
            "materials",
            "qmatrix",
            "nodes",
            "records",
            "record_details",
        ]
    }
    quality_path = base / "data_quality_report.json"
    if not quality_path.is_file():
        raise ValueError(f"data quality report missing: {quality_path}")
    return base, tables, json.loads(quality_path.read_text(encoding="utf-8"))


def build_bundle(dataset_id: str = "official-v1", root: Path | None = None) -> tuple[dict, Path]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dataset_id):
        raise ValueError("dataset ID must be a safe directory name")
    base, tables, quality = load_canonical(dataset_id, root)

    students = [
        {
            "student_id": row["student_id"],
            "group_id": row["group_id"],
            "grade": _integer(row["grade"]),
            "stage": row["stage"],
            "notes": (row["notes"] or None),
        }
        for row in tables["students"]
    ]
    knowledge = [
        {
            "knowledge_id": row["knowledge_id"],
            "objective_id": row["objective_id"],
            "name": row["name"],
        }
        for row in tables["knowledge"]
    ]
    knowledge_ids = {k["knowledge_id"] for k in knowledge}
    qmatrix: dict[str, set[str]] = {}
    for row in tables["qmatrix"]:
        if float(row["weight"] or 0) <= 0:
            continue
        if row["knowledge_id"] not in knowledge_ids:
            raise ValueError(f"qmatrix refers to unknown knowledge {row['knowledge_id']}")
        qmatrix.setdefault(row["material_id"], set()).add(row["knowledge_id"])

    material_rows = {row["material_id"]: row for row in tables["materials"]}
    record_max = {}
    for row in tables["records"]:
        record_max[row["material_id"]] = max(
            record_max.get(row["material_id"], 0.0), float(row["max_score"])
        )
    materials = []
    for material_id, mapped in sorted(qmatrix.items()):
        row = material_rows.get(material_id)
        if row is None:
            raise ValueError(f"qmatrix refers to unknown material {material_id}")
        # Only scored items belong in a denominator: learning cards and textbook
        # slices may be mapped for recommendation, but they carry no evidence.
        if row["material_type"] != "assessment":
            continue
        rubric = _material_rubric(row)
        max_score = sum(p["max_score"] for p in rubric) if rubric else record_max.get(material_id, 0)
        if max_score <= 0:
            continue
        materials.append(
            {
                "material_id": material_id,
                "objective_id": row["objective_id"] or None,
                "max_score": max_score,
                "rubric": rubric,
                "knowledge_ids": sorted(mapped),
            }
        )
    by_material = {m["material_id"]: m for m in materials}

    nodes = []
    for row in tables["nodes"]:
        taught = set(_json_or([], row["taught_objective_ids_json"]))
        available = _json_or([], row["available_material_ids_json"])
        nodes.append(
            {
                "node_id": row["node_id"],
                "date": row["exam_date"],
                "taught_objective_ids": sorted(taught),
                "material_ids": sorted(
                    m
                    for m in available
                    if m in by_material
                    and by_material[m]["objective_id"] is not None
                    and by_material[m]["objective_id"] in taught
                ),
            }
        )
    if not nodes:
        raise ValueError("no test nodes in canonical data; cannot scope profiles")

    node_ids = {n["node_id"] for n in nodes}
    records, participation, dropped_points = [], set(), 0
    for row in tables["records"]:
        material = by_material.get(row["material_id"])
        if material is None:
            raise ValueError(f"{row['record_id']}: material not diagnosable")
        if row["node_id"] not in node_ids:
            raise ValueError(f"{row['record_id']}: unknown node {row['node_id']}")
        score = _number(row["score"])
        points = _score_points(row["rubric_scores_json"], material["rubric"], score)
        if score is not None and material["rubric"] and not points:
            dropped_points += 1
        records.append(
            {
                "record_id": row["record_id"],
                "student_id": row["student_id"],
                "material_id": row["material_id"],
                "node_id": row["node_id"],
                "assigned": _bool(row["assigned"]),
                "attempted": _bool(row["attempted"]),
                "score": score,
                "max_score": float(row["max_score"]),
                "is_correct": _bool(row["is_correct"]),
                "submitted_at": row["submitted_at"] or None,
                "duration_seconds": _integer(row["duration_seconds"]),
                "attempt_no": _integer(row["attempt_no"]),
                "source": row["source"] or None,
                "score_points": points,
            }
        )
        participation.add((row["student_id"], row["node_id"]))
    records.sort(key=lambda r: r["record_id"])

    record_sources = {
        row["record_id"]: {
            "csv_record_number": int(row["csv_record_number"]),
            "source_record_id": row["source_record_id"],
            "raw_file": RAW_RECORD_FILE,
        }
        for row in tables["record_details"]
        if _bool(row["kept"])
    }
    missing_sources = {r["record_id"] for r in records} - set(record_sources)
    if missing_sources:
        raise ValueError(f"record_details lacks kept rows for {sorted(missing_sources)[:3]}")

    quality = dict(quality)
    details = tables["record_details"]
    input_records = len(details)
    duplicates_removed = int(quality.get("duplicates_removed", 0))
    total_records = int(quality.get("total_records", len(records)))
    rejected = max(0, input_records - total_records - duplicates_removed)
    quality.update(
        {
            "input_records": input_records,
            "rejected_records": rejected,
            "partial_credit_records": sum(
                r["score"] is not None and 0 < r["score"] < r["max_score"] for r in records
            ),
            "decisions": _decisions(details, {r["record_id"] for r in records}),
        }
    )
    if dropped_points:
        quality.setdefault("field_quality", []).append(
            {"field": "records", "issue": "score_points_dropped", "count": dropped_points}
        )

    bundle = {
        "dataset_id": dataset_id,
        "generated_at": quality["generated_at"],
        "canonical_root": str(base.resolve()),
        "students": sorted(students, key=lambda r: r["student_id"]),
        "knowledge": sorted(knowledge, key=lambda r: r["knowledge_id"]),
        "materials": materials,
        "nodes": sorted(nodes, key=lambda n: (n["date"], n["node_id"])),
        "participation": [{"student_id": s, "node_id": n} for s, n in sorted(participation)],
        "records": records,
        "record_sources": record_sources,
        "quality_report": quality,
    }
    return bundle, base


def _decisions(details: list[dict[str, str]], retained: set[str]) -> list[dict]:
    decisions = []
    for row in sorted(details, key=lambda r: int(r["csv_record_number"])):
        record_id = row["record_id"] or None
        if _bool(row["kept"]):
            decision, reasons = "retained", []
        elif record_id in retained:
            decision, reasons = "superseded", ["newer_revision"]
        else:
            decision, reasons = "rejected", ["not_retained_by_data_layer"]
        decisions.append(
            {
                "source_row": int(row["csv_record_number"]),
                "record_id": record_id,
                "decision": decision,
                "reasons": reasons,
            }
        )
    return decisions


# --------------------------------------------------------------------------- #
# run / verify / evidence
# --------------------------------------------------------------------------- #


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def _checked(bundle: dict) -> dict:
    errors = validate_bundle(bundle)
    if errors:
        raise ValueError("diagnosis input validation failed:\n" + "\n".join(errors[:30]))
    return bundle


def _protect_output(output: Path) -> Path:
    root = repo_root().resolve()
    target = output.resolve()
    if target.is_relative_to(root) and not target.is_relative_to(root / "artifacts"):
        raise ValueError("repository outputs must be under artifacts/ (Git-ignored)")
    if target.exists():
        raise ValueError(f"output already exists; choose a new run directory: {target}")
    return target


def _source_hashes(base: Path) -> list[dict]:
    return [
        {
            "path": name,
            "sha256": hashlib.sha256((base / name).read_bytes()).hexdigest(),
        }
        for name in ("records.csv", "record_details.csv")
    ]


def run_diagnosis(
    bundle: dict,
    output: Path,
    config: DiagnosisConfig | None = None,
    node_id: str = "all",
) -> dict:
    config = config or DiagnosisConfig()
    _checked(bundle)
    output = _protect_output(Path(output))
    nodes = bundle["nodes"]
    if node_id == "latest":
        nodes = [max(nodes, key=lambda n: (n["date"], n["node_id"]))]
    elif node_id != "all":
        nodes = [n for n in nodes if n["node_id"] == node_id]
    if not nodes:
        raise ValueError("requested test node does not exist")

    generated, all_students, all_classes = [], [], []
    for node in nodes:
        profiles = [build_student_profile(bundle, s, node, config) for s in bundle["students"]]
        classes = [
            build_class_profile(profiles, group, bundle, node["node_id"])
            for group in sorted({s["group_id"] for s in bundle["students"]}) + ["ALL"]
        ]
        for profile in profiles:
            errors = validate_student(profile, bundle, config)
            if errors:
                raise ValueError("student checks failed:\n" + "\n".join(errors[:20]))
            generated.append(
                (
                    f"nodes/{node['node_id']}/students/{profile['student_id']}.json",
                    profile,
                    "output/student_profile.schema.json",
                )
            )
        for profile in classes:
            errors = validate_class(profile, profiles, bundle)
            if errors:
                raise ValueError("class checks failed:\n" + "\n".join(errors[:20]))
            generated.append(
                (
                    f"nodes/{node['node_id']}/classes/{profile['class_id']}.json",
                    profile,
                    "output/class_profile.schema.json",
                )
            )
        all_students.extend(profiles)
        all_classes.extend(classes)

    generated += [
        ("diagnosis_input.json", bundle, None),
        (
            "data_quality_report.json",
            bundle["quality_report"],
            "output/data_quality_report.schema.json",
        ),
    ]
    output.mkdir(parents=True)
    targets = []
    for relative, data, schema in generated:
        path = output / relative
        write_json(path, data)
        if schema is None:
            continue
        targets.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "schema_id": SCHEMA_PREFIX + schema,
            }
        )

    latest = max(nodes, key=lambda n: (n["date"], n["node_id"]))["node_id"]
    cases = choose_cases([p for p in all_students if p["node_id"] == latest], bundle)
    write_json(
        output / "case_candidates.json",
        {
            "node_id": latest,
            "note": "规则选出的展示候选；须由团队核对原始作答后确定正式案例。",
            "candidates": cases,
        },
    )
    with (output / "coverage_matrix.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "node_id",
            "student_id",
            "group_id",
            "knowledge_id",
            "evidence_count",
            "mastery",
            "status",
            "full_credit",
            "partial_credit",
            "zero_credit",
            "mean_score_ratio",
            *[
                f"state_{s}"
                for s in [
                    "observed_correct",
                    "observed_wrong",
                    "pending",
                    "assigned_not_attempted",
                    "unobserved",
                ]
            ],
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for profile in all_students:
            for state in profile["knowledge_states"]:
                writer.writerow(
                    {
                        "node_id": profile["node_id"],
                        "student_id": profile["student_id"],
                        "group_id": profile["group_id"],
                        **{
                            k: state[k]
                            for k in ["knowledge_id", "evidence_count", "mastery", "status"]
                        },
                        **state["performance"],
                        **{f"state_{k}": v for k, v in state["state_counts"].items()},
                    }
                )
    q = bundle["quality_report"]
    text = [
        "# 任务2运行结果",
        "",
        f"数据集：{bundle['dataset_id']}。本次只验证任务2，未生成任务3学习计划。",
        "",
        f"输入{q['input_records']}条；保留{q['total_records']}条；"
        f"被新版本替代{q['duplicates_removed']}条；隔离{q['rejected_records']}条。",
        f"生成{len(all_students)}份个人画像、{len(all_classes)}份群体画像。",
        "",
        "mastery为当前题目范围内满分成功率的Beta后验估计；部分得分另见performance。"
        "不能将其解释为整体能力百分比。",
        "未知参与范围的覆盖率为null；未覆盖的知识点区分证据不足与不适用。",
        "",
        "原始记录定位：个人画像issues/evidence中的record_id → record_sources 的 csv_record_number "
        "→ 原始CSV逻辑行号（含表头，不是物理文本行）。",
        "可使用 knowflow evidence --run <本目录> --record <记录ID> 导出本机证据详情，"
        "核对实际答案、过程和分点评分。",
        "",
        "## 案例候选",
    ]
    text += [
        f"- {c['case_type']}：{c['student_id']}；{c['reason']}" for c in cases
    ]
    (output / "运行说明.md").write_text("\n".join(text) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": RUN_SCHEMA_VERSION,
        "dataset_id": bundle["dataset_id"],
        "generated_at": bundle["generated_at"],
        "scope": "task2_only",
        "nodes": [n["node_id"] for n in nodes],
        "configuration": asdict(config),
        "source_files": _source_hashes(Path(bundle["canonical_root"])),
        "targets": targets,
        "auxiliary_files": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in ["case_candidates.json", "coverage_matrix.csv", "运行说明.md"]
        },
    }
    write_json(output / "run_manifest.json", manifest)

    verification = validate_saved_run(output)
    checks = [
        {
            "id": "task2.schema_references_recomputation",
            "level": "error",
            "passed": verification["gate"] == "pass",
            "message": "任务2格式、引用、五态、覆盖、掌握度及班级汇总复算"
            + ("通过" if verification["gate"] == "pass" else "失败：" + "; ".join(verification["errors"][:10])),
            "refs": [],
        },
        {
            "id": "scope.task2_only",
            "level": "info",
            "passed": True,
            "message": "不包含任务1课标核对、任务3建议约束、正式案例人工评审或赛事提交审批。",
            "refs": [],
        },
    ]
    if q["rejected_records"]:
        checks.append(
            {
                "id": "data.quarantined",
                "level": "warning",
                "passed": False,
                "message": f"已隔离{q['rejected_records']}条记录；详见数据质量报告，未自动修正官方得分。",
                "refs": ["data_quality_report.json"],
            }
        )
    report = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": output.name,
        "generated_at": bundle["generated_at"],
        "targets": targets,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": sum(c["passed"] for c in checks),
            "failed": sum(not c["passed"] and c["level"] == "error" for c in checks),
            "warnings": sum(c["level"] == "warning" for c in checks),
        },
        "gate": verification["gate"],
    }
    report_errors = schema_errors(report, "output/validation_report.schema.json")
    if report_errors:
        raise ValueError("validation report schema failed:\n" + "\n".join(report_errors[:10]))
    write_json(output / "validation_report.json", report)
    if verification["gate"] != "pass":
        raise ValueError(
            "saved run verification failed:\n" + "\n".join(verification["errors"][:20])
        )
    return {
        "output": str(output),
        "student_profiles": len(all_students),
        "class_profiles": len(all_classes),
        "input_records": q["input_records"],
        "retained_records": q["total_records"],
        "superseded_records": q["duplicates_removed"],
        "rejected_records": q["rejected_records"],
        "gate": verification["gate"],
    }


def choose_cases(profiles, bundle):
    chosen, used = [], set()

    def add(kind, pool, key, reverse, reason):
        pool = [p for p in pool if p["student_id"] not in used]
        if pool:
            profile = sorted(pool, key=lambda p: (key(p), p["student_id"]), reverse=reverse)[0]
            used.add(profile["student_id"])
            chosen.append(
                {
                    "case_type": kind,
                    "student_id": profile["student_id"],
                    "reason": reason,
                }
            )

    def partial(profile):
        return sum(s["performance"]["partial_credit"] for s in profile["knowledge_states"])

    add(
        "部分得分",
        [p for p in profiles if partial(p)],
        partial,
        True,
        "具有部分得分及可核对评分点，适合展示步骤分析。",
    )
    add(
        "表现较好候选",
        [p for p in profiles if p["coverage"]["observed_items"] >= 3],
        lambda p: (
            optional_mean(s["performance"]["mean_score_ratio"] for s in p["knowledge_states"]) or 0
        ),
        True,
        "在有至少3项评分的学生中按知识点平均得分率选取；不是整体能力排名。",
    )
    add(
        "记录不足",
        [p for p in profiles if p["lists"]["needs_observation"]],
        lambda p: p["coverage"]["observed_items"],
        False,
        "现有记录不足，须先确认参与范围或补充观测。",
    )
    return chosen


def export_evidence(run: Path, record_id: str) -> Path:
    run = Path(run)
    bundle = json.loads((run / "diagnosis_input.json").read_text(encoding="utf-8"))
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    if record_id not in bundle["record_sources"]:
        raise ValueError("record not in this run's retained evidence")
    source = bundle["record_sources"][record_id]
    base = Path(bundle["canonical_root"])
    for entry in manifest["source_files"]:
        path = base / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(
                "canonical source changed since this run; rerun diagnosis before viewing evidence"
            )
    rows = _read_csv(base / "record_details.csv")
    row = next(
        (r for r in rows if int(r["csv_record_number"]) == source["csv_record_number"]), None
    )
    if row is None or row["source_record_id"] != source["source_record_id"]:
        raise ValueError("evidence row not found in record_details.csv")
    target = run / "evidence" / f"{record_id}.json"
    write_json(
        target,
        {
            "record_id": record_id,
            "source": source,
            "local_only": True,
            "warning": "包含原始作答，仅供本机人工核对；禁止提交 Git 或发送第三方 API。",
            "detail": {
                "csv_record_number": int(row["csv_record_number"]),
                "source_record_id": row["source_record_id"],
                "final_answer": row["final_answer"],
                "solution_process": row["solution_process"],
                "scoring_point_scores": row["scoring_point_scores"],
            },
        },
    )
    return target
