"""Build and load the disputed-score review context.

The scan is read-only with respect to the canonical tables: it reads three CSVs,
writes a report under ``artifacts/review/`` and appends nothing. Human decisions
live in the append-only ledger under ``data/reviews/`` and are joined on read.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from knowflow.contracts import repo_root
from knowflow.diagnosis.pipeline import load_canonical

from .rules import POLICY_NAME, RULE_VERSION, official_snapshot, scan_record
from .store import (
    LEDGER_FILE,
    append_decision,
    ensure_meta,
    latest_by_record,
    ledger_digest,
    ledger_dir,
    load_decisions,
    source_hashes,
)
from .validation import validate_report

REPORT_FILE = "review_report.json"
REPORT_SCHEMA_VERSION = "1.0.0"
REPORT_SCHEMA_ID = "https://knowflow.local/schemas/output/review_report.schema.json"
POLICY_VALUES = ("official", "exclude_flagged")


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def _kept(value) -> bool:
    return str(value or "").strip().lower() in {"true", "1"}


def _anomalies_by_record(quality: dict) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for anomaly in quality.get("anomalies", []):
        record_id = anomaly.get("record_id")
        reason = str(anomaly.get("reason") or "").strip()
        if record_id and "超出满分" in reason:
            grouped[str(record_id)].append(reason)
    return grouped


def _knowledge_by_material(tables: dict) -> dict[str, list[str]]:
    knowledge_ids = {row["knowledge_id"] for row in tables["knowledge"]}
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in tables["qmatrix"]:
        if float(row.get("weight") or 0) <= 0:
            continue
        if row["knowledge_id"] in knowledge_ids:
            mapping[row["material_id"]].add(row["knowledge_id"])
    return {material_id: sorted(ids) for material_id, ids in mapping.items()}


def _protect_output(output: Path) -> Path:
    root = repo_root().resolve()
    target = output.resolve()
    if target.is_relative_to(root) and not target.is_relative_to(root / "artifacts"):
        raise ValueError("repository outputs must be under artifacts/ (Git-ignored)")
    if target.exists():
        raise ValueError(f"output already exists; choose a new directory: {target}")
    return target


def scan_dataset(
    dataset_id: str = "official-v1",
    root: Path | None = None,
    output: Path | None = None,
    generated_at: str | None = None,
    ledger_root: Path | None = None,
) -> dict:
    """Scan canonical records, join the local ledger, write one review report.

    ``root`` is the interim parent directory (same meaning as ``load_canonical``);
    the ledger lives under the repository's ``data/reviews`` unless
    ``ledger_root`` says otherwise, so rebuilding canonical keeps the same
    human decisions while still refusing a changed fingerprint.
    """

    base, tables, quality = load_canonical(dataset_id, root)
    hashes = source_hashes(base)
    directory = ledger_dir(dataset_id, ledger_root)
    stamp = generated_at or now_iso()
    ensure_meta(directory, dataset_id, hashes, stamp)
    decisions = load_decisions(directory / LEDGER_FILE)
    latest = latest_by_record(decisions)
    history: dict[str, list[dict]] = defaultdict(list)
    for decision in decisions:
        history[decision["record_id"]].append(decision)

    materials = {row["material_id"]: row for row in tables["materials"]}
    knowledge_of = _knowledge_by_material(tables)
    details = {row["record_id"]: row for row in tables["record_details"] if _kept(row["kept"])}
    anomalies = _anomalies_by_record(quality)

    candidates = []
    for record in sorted(tables["records"], key=lambda row: row["record_id"]):
        flags = scan_record(
            record,
            materials[record["material_id"]],
            anomalies.get(record["record_id"], ()),
        )
        if not flags:
            continue
        record_id = record["record_id"]
        decision = latest.get(record_id)
        status = decision["review_status"] if decision else "flagged"
        disputed = status != "dismissed" and any(flag.excluded_by_default for flag in flags)
        detail = details.get(record_id)
        if detail is None:
            raise ValueError(f"{record_id}: missing kept record_details row")
        candidates.append(
            {
                "record_id": record_id,
                "student_id": record["student_id"],
                "material_id": record["material_id"],
                "node_id": record["node_id"],
                "knowledge_ids": knowledge_of.get(record["material_id"], []),
                "review_status": status,
                "disputed": disputed,
                "flags": [flag.as_dict() for flag in flags],
                "official": official_snapshot(record, materials[record["material_id"]]),
                "evidence_ref": {
                    "csv_record_number": int(detail["csv_record_number"]),
                    "source_record_id": detail["source_record_id"],
                    "kept": True,
                },
                "decisions": history.get(record_id, []),
            }
        )

    by_status = {status: 0 for status in ("flagged", "confirmed_issue", "dismissed", "needs_more_evidence")}
    for candidate in candidates:
        by_status[candidate["review_status"]] += 1
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "generated_at": stamp,
        "rule_version": RULE_VERSION,
        "source_sha256": hashes,
        "policy": {
            "name": POLICY_NAME,
            "excluded_flag_codes": ["answer_matches_key_under_credit", "rubric_total_mismatch"],
            "default_for_unreviewed": "flagged",
            "note": "未获人工排除的存疑证据不进入问题识别与建议；官方分数原样保留。",
        },
        "counts": {
            "records_scanned": len(tables["records"]),
            "candidates": len(candidates),
            "disputed_records": sum(1 for candidate in candidates if candidate["disputed"]),
            **by_status,
        },
        "decisions_applied": len(decisions),
        "candidates": candidates,
    }
    errors = validate_report(report, tables)
    if errors:
        raise ValueError("review report validation failed:\n" + "\n".join(errors[:20]))

    target = (
        Path(output)
        if output
        else repo_root() / "artifacts" / "review" / f"{dataset_id}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    )
    target = _protect_output(target)
    target.mkdir(parents=True)
    write_json(target / REPORT_FILE, report)
    report_sha = hashlib.sha256((target / REPORT_FILE).read_bytes()).hexdigest()
    digest = ledger_digest(directory)
    manifest = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "generated_at": stamp,
        "rule_version": RULE_VERSION,
        "source_sha256": hashes,
        "ledger": {
            "path": str(directory.resolve()),
            "file": LEDGER_FILE,
            "sha256": digest,
            "decisions": len(decisions),
            "records_decided": len(latest),
        },
        "counts": report["counts"],
        "targets": [
            {
                "path": REPORT_FILE,
                "sha256": report_sha,
                "schema_id": REPORT_SCHEMA_ID,
            }
        ],
    }
    write_json(target / "run_manifest.json", manifest)
    (target / "运行说明.md").write_text(_summary_text(report), encoding="utf-8")
    return {
        "output": str(target),
        "report": str(target / REPORT_FILE),
        "counts": report["counts"],
        "rule_version": RULE_VERSION,
    }


def _summary_text(report: dict) -> str:
    counts = report["counts"]
    lines = [
        "# 存疑评分审查",
        "",
        f"数据集：{report['dataset_id']}；规则版本：{report['rule_version']}。",
        "",
        f"扫描 {counts['records_scanned']} 条保留记录，发现 {counts['candidates']} 条复核线索，"
        f"其中 {counts['disputed_records']} 条当前不进入结论。",
        f"状态：待复核 {counts['flagged']}；已确认问题 {counts['confirmed_issue']}；"
        f"已排除 {counts['dismissed']}；需补证据 {counts['needs_more_evidence']}。",
        "",
        "## 边界",
        "",
        "- 规则只读 canonical，未修改任何官方分数；线索不等于学生答对或答错。",
        "- 报告不含原始作答与过程文本；原文用 `knowflow evidence --record <ID>` 在本机导出。",
        "- 人工结论追加在 `data/reviews/<dataset>/decisions.jsonl`，最新生效、历史保留。",
        "- 账本绑定 canonical 三张表的 SHA-256；数据重建后旧结论会被拒绝套用。",
        "",
        "## 候选",
        "",
    ]
    for candidate in report["candidates"]:
        codes = "、".join(flag["code"] for flag in candidate["flags"])
        lines.append(
            f"- {candidate['record_id']} / {candidate['student_id']} / "
            f"{candidate['material_id']} / {candidate['node_id']}：{candidate['review_status']}"
            f"（{codes}）"
        )
    return "\n".join(lines) + "\n"


def decide(
    dataset_id: str,
    record_id: str,
    status: str,
    note: str,
    reviewer: str = "local_demo_user",
    source: str = "local manual review",
    flag_codes: list[str] | None = None,
    reviewed_at: str | None = None,
    root: Path | None = None,
    ledger_root: Path | None = None,
) -> dict:
    """Validate and append one human decision; never touches canonical data."""

    if status not in ("confirmed_issue", "dismissed", "needs_more_evidence"):
        raise ValueError("review status must be confirmed_issue, dismissed or needs_more_evidence")
    if not note.strip():
        raise ValueError("a review note is required; decisions must be explainable")
    if not reviewer.strip():
        raise ValueError("reviewer_role is required (default local_demo_user)")
    if not source.strip():
        raise ValueError("source_reference is required")
    base, tables, quality = load_canonical(dataset_id, root)
    records = {row["record_id"]: row for row in tables["records"]}
    record = records.get(record_id)
    if record is None:
        raise ValueError(f"{record_id}: not a retained record in {dataset_id}")
    materials = {row["material_id"]: row for row in tables["materials"]}
    flag_codes_found = {
        flag.code
        for flag in scan_record(
            record,
            materials[record["material_id"]],
            _anomalies_by_record(quality).get(record_id, ()),
        )
    }
    if not flag_codes_found:
        raise ValueError(f"{record_id}: no review clue on this record; nothing to decide")
    selected = sorted(flag_codes or flag_codes_found)
    unknown = set(selected) - flag_codes_found
    if unknown:
        raise ValueError(
            f"{record_id}: unknown flag codes {sorted(unknown)}; "
            f"this record carries {sorted(flag_codes_found)}"
        )
    hashes = source_hashes(base)
    directory = ledger_dir(dataset_id, ledger_root)
    ensure_meta(directory, dataset_id, hashes, now_iso())
    decision = {
        "schema_version": "1.0.0",
        "record_id": record_id,
        "review_status": status,
        "reviewer_role": reviewer,
        "review_note": note.strip(),
        "reviewed_at": reviewed_at or now_iso(),
        "policy_version": RULE_VERSION,
        "source_reference": source.strip(),
        "flag_codes": selected,
    }
    append_decision(directory / LEDGER_FILE, decision)
    return {
        "record_id": record_id,
        "review_status": status,
        "flag_codes": selected,
        "ledger": str((directory / LEDGER_FILE).resolve()),
        "warning": "本机演示角色，不是经过认证的教师身份；未修改官方分数。",
    }


def load_report(path: Path) -> dict:
    path = Path(path)
    if path.is_dir():
        path = path / REPORT_FILE
    if not path.is_file():
        raise ValueError(f"review report not found: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_report(report)
    if errors:
        raise ValueError("review report validation failed:\n" + "\n".join(errors[:20]))
    return report


def build_context(report: dict, report_path: Path, policy: str) -> dict:
    if policy not in POLICY_VALUES:
        raise ValueError(f"review policy must be one of {POLICY_VALUES}")
    report_path = Path(report_path)
    if report_path.is_dir():
        report_path = report_path / REPORT_FILE
    index = {
        candidate["record_id"]: {
            "review_status": candidate["review_status"],
            "flag_codes": [flag["code"] for flag in candidate["flags"]],
            "disputed": bool(candidate["disputed"]),
        }
        for candidate in report["candidates"]
    }
    return {
        "policy": policy,
        "report_path": str(report_path.resolve()),
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "report": report,
        "index": index,
        "disputed_record_ids": sorted(
            record_id for record_id, entry in index.items() if entry["disputed"]
        ),
    }


def context_from_run_manifest(manifest: dict) -> dict | None:
    """Reload the review context a saved diagnosis run was built with."""

    review = manifest.get("review")
    if not review:
        return None
    path = Path(review["report_path"])
    if not path.is_file():
        raise ValueError(f"review report recorded by the run is missing: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != review["report_sha256"]:
        raise ValueError("review report changed since the run; rerun diagnosis")
    report = load_report(path)
    return build_context(report, path, review["policy"])


def latest_report(dataset_id: str, root: Path | None = None) -> Path | None:
    base = (Path(root) if root is not None else repo_root()) / "artifacts" / "review"
    if not base.is_dir():
        return None
    candidates = [
        path
        for path in base.iterdir()
        if path.is_dir() and (path / REPORT_FILE).is_file()
    ]
    for path in sorted(candidates, key=lambda item: (item.stat().st_mtime, item.name), reverse=True):
        try:
            report = json.loads((path / REPORT_FILE).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if report.get("dataset_id") == dataset_id:
            return path
    return None
