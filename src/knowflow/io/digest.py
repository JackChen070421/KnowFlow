"""Content-free digest of the canonical tables — the cross-machine check.

The digest carries **no row content**: per-table row counts and the sha256 of
each serialized file, plus aggregate counters from the quality report.  It is
safe to commit, and it is how two teammates prove their locally built tables
are byte-identical without exchanging the data itself.

``generated_at`` is deliberately excluded: it is a clock value, not a fact.
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from . import mapping
from .pipeline import TABLES


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_rows(path: Path) -> int:
    """Count CSV records, not raw lines: quoted fields may contain newlines."""

    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.reader(handle)) - 1


def normalize_reason(reason: str) -> str:
    """Strip ids and values so the key stays stable across data versions."""

    normalized = re.sub(r"[A-Z]{1,2}-?\d+", "<id>", reason)
    normalized = re.sub(r"\d+", "<n>", normalized)
    return re.sub(r"\[[^\]]*\]", "[...]", normalized)


def anomaly_counts(report: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in report.get("anomalies", []):
        key = normalize_reason(item["reason"])
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def build_digest(interim: Path) -> dict:
    tables = {}
    for name in TABLES:
        path = interim / f"{name}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"MISSING {path}；先跑 build_canonical")
        tables[name] = {"rows": count_rows(path), "sha256": sha256_file(path)}

    report_path = interim / "data_quality_report.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"MISSING {report_path}；先跑 build_canonical")

    import json

    report = json.loads(report_path.read_text(encoding="utf-8"))

    return {
        "note": "纯指纹：行数 + sha256 + 聚合计数；不含任何数据内容，可入库。",
        "dataset_id": report["dataset_id"],
        "canonical_version": mapping.CANONICAL_VERSION,
        "tables": tables,
        "total_records": report["total_records"],
        "duplicates_removed": report["duplicates_removed"],
        "records_by_state": report["records_by_state"],
        "missing": report["missing"],
        "anomaly_counts": anomaly_counts(report),
    }


def compare(expected: dict, actual: dict) -> list[str]:
    problems: list[str] = []
    if expected.get("canonical_version") != actual.get("canonical_version"):
        problems.append(
            f"canonical_version: 实际 {actual.get('canonical_version')} "
            f"!= 预期 {expected.get('canonical_version')}"
        )

    exp_tables = expected.get("tables", {})
    act_tables = actual.get("tables", {})
    for name in sorted(set(exp_tables) | set(act_tables)):
        want, got = exp_tables.get(name), act_tables.get(name)
        if want is None:
            problems.append(f"{name}: 预期里没有这张表")
            continue
        if got is None:
            problems.append(f"{name}: 实际缺少这张表")
            continue
        if want["rows"] != got["rows"]:
            problems.append(f"{name}: 行数 {got['rows']} != 预期 {want['rows']}")
        if want["sha256"] != got["sha256"]:
            problems.append(f"{name}: 内容 sha256 不一致")

    for field in (
        "total_records",
        "duplicates_removed",
        "records_by_state",
        "missing",
        "anomaly_counts",
    ):
        if expected.get(field) != actual.get(field):
            problems.append(f"{field}: 与预期不一致")
    return problems
