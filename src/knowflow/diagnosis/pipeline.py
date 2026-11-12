"""Local task-2 commands. All official-derived artifacts stay outside Git."""

import csv
import hashlib
import json
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
from knowflow.io.adapters import adapt_official

SCHEMA_PREFIX = "https://knowflow.local/schemas/"


def now_iso():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def _checked(bundle):
    errors = validate_bundle(bundle)
    if errors:
        raise ValueError("diagnosis input validation failed:\n" + "\n".join(errors[:30]))
    return bundle


def prepare_dataset(dataset_id: str, knowledge_base_path: Path | None = None) -> tuple[dict, Path]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dataset_id) or ".." in dataset_id:
        raise ValueError("dataset ID must be a safe directory name")
    root = repo_root()
    raw = root / "data/raw" / dataset_id
    if not raw.is_dir():
        raise ValueError(f"official data not found: {raw}; run scripts/ingest_raw.py first")
    interim = root / "data/interim" / dataset_id
    previous = (
        json.loads((interim / "id_map.json").read_text(encoding="utf-8"))
        if (interim / "id_map.json").is_file()
        else None
    )
    kb = None
    if knowledge_base_path:
        kb = json.loads(knowledge_base_path.read_text(encoding="utf-8"))
        errors = schema_errors(kb, "output/knowledge_base.schema.json")
        if errors:
            raise ValueError("R1 knowledge base schema failed:\n" + "\n".join(errors[:10]))
    bundle = _checked(adapt_official(raw, dataset_id, now_iso(), previous, kb))
    # Only replace derived files after every input and reference has passed.
    write_json(interim / "diagnosis_input.json", bundle)
    write_json(interim / "id_map.json", bundle["id_map"])
    for name in ["students", "records"]:
        schema = json.loads(
            (root / f"schemas/input/{name}.schema.json").read_text(encoding="utf-8")
        )
        fields = list(schema["properties"])
        with (interim / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in bundle[name]:
                writer.writerow(
                    {
                        k: ""
                        if record.get(k) is None
                        else json.dumps(record[k], ensure_ascii=False)
                        if isinstance(record[k], (bool, list, dict))
                        else record[k]
                        for k in fields
                    }
                )
    return bundle, interim / "diagnosis_input.json"


def _protect_output(output: Path):
    root = repo_root().resolve()
    target = output.resolve()
    if target.is_relative_to(root) and not target.is_relative_to(root / "artifacts"):
        raise ValueError("repository outputs must be under artifacts/ (Git-ignored)")
    # Existing runs are immutable; use a new directory for each recomputation.
    if target.exists():
        raise ValueError(f"output already exists; choose a new run directory: {target}")
    return target


def run_diagnosis(
    bundle: dict, output: Path, config: DiagnosisConfig | None = None, node_id: str = "all"
) -> dict:
    config = config or DiagnosisConfig()
    _checked(bundle)
    output = _protect_output(output)
    nodes = bundle["nodes"]
    if node_id == "latest":
        nodes = [max(nodes, key=lambda n: (n["date"], n["node_id"]))]
    elif node_id != "all":
        nodes = [n for n in nodes if n["node_id"] == node_id]
    if not nodes:
        raise ValueError("requested test node does not exist")
    generated = []
    all_students, all_classes = [], []
    for node in nodes:
        profiles = [build_student_profile(bundle, s, node, config) for s in bundle["students"]]
        classes = [
            build_class_profile(profiles, group, bundle, node["node_id"])
            for group in sorted({s["group_id"] for s in bundle["students"]}) + ["ALL"]
        ]
        for p in profiles:
            errors = validate_student(p, bundle, config)
            if errors:
                raise ValueError("student checks failed:\n" + "\n".join(errors[:20]))
            generated.append(
                (
                    f"nodes/{node['node_id']}/students/{p['student_id']}.json",
                    p,
                    "output/student_profile.schema.json",
                )
            )
        for p in classes:
            errors = validate_class(p, profiles, bundle)
            if errors:
                raise ValueError("class checks failed:\n" + "\n".join(errors[:20]))
            generated.append(
                (
                    f"nodes/{node['node_id']}/classes/{p['class_id']}.json",
                    p,
                    "output/class_profile.schema.json",
                )
            )
        all_students.extend(profiles)
        all_classes.extend(classes)
    generated += [
        ("diagnosis_input.json", bundle, "input/diagnosis_input.schema.json"),
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
        for p in all_students:
            for s in p["knowledge_states"]:
                writer.writerow(
                    {
                        "node_id": p["node_id"],
                        "student_id": p["student_id"],
                        "group_id": p["group_id"],
                        **{
                            k: s[k] for k in ["knowledge_id", "evidence_count", "mastery", "status"]
                        },
                        **s["performance"],
                        **{f"state_{k}": v for k, v in s["state_counts"].items()},
                    }
                )
    q = bundle["quality_report"]
    text = [
        "# 任务2运行结果",
        "",
        f"数据集：{bundle['dataset_id']}。本次只验证任务2，未生成任务3学习计划。",
        "",
        f"输入{q['input_records']}条；保留{q['total_records']}条；被新版本替代{q['duplicates_removed']}条；隔离{q['rejected_records']}条。",
        f"生成{len(all_students)}份个人画像、{len(all_classes)}份群体画像。",
        "",
        "mastery为当前题目范围内满分成功率的Beta后验估计；部分得分另见performance。不能将其解释为整体能力百分比。",
        "未知参与范围的覆盖率为null；未覆盖的知识点区分证据不足与不适用。",
        "",
        "原始记录定位：个人画像issues/evidence中的record_id → diagnosis_input.json的record_sources → 原始CSV逻辑行号（含表头，不是物理文本行）。",
        "可使用 knowflow evidence --run <本目录> --record <记录ID> 导出本机证据详情，核对实际答案、过程和分点评分。",
        "",
        "## 案例候选",
    ]
    text += [
        f"- {c['case_type']}：{c['student_id']}（原编号{c['source_student_id']}）；{c['reason']}"
        for c in cases
    ]
    (output / "运行说明.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "0.3.0",
        "dataset_id": bundle["dataset_id"],
        "generated_at": bundle["generated_at"],
        "scope": "task2_only",
        "nodes": [n["node_id"] for n in nodes],
        "configuration": asdict(config),
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
            + (
                "通过"
                if verification["gate"] == "pass"
                else "失败：" + "; ".join(verification["errors"][:10])
            ),
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
        "schema_version": "0.3.0",
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
        raise ValueError("validation report schema failed")
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
    source_ids = {v: k for k, v in bundle["id_map"]["students"].items()}
    chosen, used = [], set()

    def add(kind, pool, key, reverse, reason):
        pool = [p for p in pool if p["student_id"] not in used]
        if pool:
            p = sorted(pool, key=lambda p: (key(p), p["student_id"]), reverse=reverse)[0]
            used.add(p["student_id"])
            chosen.append(
                {
                    "case_type": kind,
                    "student_id": p["student_id"],
                    "source_student_id": source_ids[p["student_id"]],
                    "reason": reason,
                }
            )

    def partial(p):
        return sum(s["performance"]["partial_credit"] for s in p["knowledge_states"])

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
    bundle = json.loads((run / "diagnosis_input.json").read_text(encoding="utf-8"))
    if record_id not in bundle["record_sources"]:
        raise ValueError("record not in this run's retained evidence")
    source = bundle["record_sources"][record_id]
    raw_root = Path(bundle["raw_root"]).resolve()
    path = (raw_root / source["relative_path"]).resolve()
    if not path.is_relative_to(raw_root):
        raise ValueError("invalid evidence source path")
    expected = next(
        f["sha256"]
        for f in bundle["quality_report"]["input_files"]
        if f["path"] == source["relative_path"]
    )
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(
            "source file changed since this run; rerun diagnosis before viewing evidence"
        )
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    raw = rows[source["source_row"] - 2]
    if raw["记录编号"] != source["source_record_id"]:
        raise ValueError("source record mismatch")
    target = run / "evidence" / f"{record_id}.json"
    write_json(
        target,
        {
            "record_id": record_id,
            "source": source,
            "local_only": True,
            "warning": "包含原始作答，仅供本机人工核对；禁止提交Git或发送第三方API。",
            "record": raw,
        },
    )
    return target
