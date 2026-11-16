"""Checks for the review report; the report is the audit trail, so be strict."""

from __future__ import annotations

import json
from functools import lru_cache

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.contracts import build_registry, repo_root

from .rules import EXCLUDED_FLAG_CODES, FLAG_CODES

SCHEMA_NAME = "output/review_report.schema.json"
FORBIDDEN_KEYS = {
    "answer",
    "answer_text",
    "final_answer",
    "solution_process",
    "steps_json",
    "raw_answer",
}


@lru_cache(maxsize=1)
def schema_validator() -> Draft202012Validator:
    root = repo_root()
    schema = json.loads((root / "schemas" / SCHEMA_NAME).read_text(encoding="utf-8"))
    return Draft202012Validator(
        schema, registry=build_registry(root), format_checker=FormatChecker()
    )


def schema_errors(report: dict) -> list[str]:
    return [
        f"{SCHEMA_NAME}:{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in schema_validator().iter_errors(report)
    ]


def _raw_keys(node, path="$") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FORBIDDEN_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_raw_keys(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_raw_keys(value, f"{path}[{index}]"))
    return found


def validate_report(report: dict, tables: dict | None = None) -> list[str]:
    """Schema + invariants + reference integrity. ``tables`` is canonical rows."""

    errors = schema_errors(report)
    if errors:
        return errors

    def check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    raw = _raw_keys(report)
    if raw:
        errors.append(f"review report must not carry raw answer text: {raw[:3]}")

    candidates = report.get("candidates", [])
    counts = report.get("counts", {})
    check(counts.get("candidates") == len(candidates), "candidate count mismatch")
    check(
        counts.get("disputed_records") == sum(1 for item in candidates if item["disputed"]),
        "disputed count mismatch",
    )
    for status in ("flagged", "confirmed_issue", "dismissed", "needs_more_evidence"):
        check(
            counts.get(status) == sum(1 for item in candidates if item["review_status"] == status),
            f"{status} count mismatch",
        )

    excluded = set(report["policy"]["excluded_flag_codes"])
    check(excluded == set(EXCLUDED_FLAG_CODES), "policy excluded_flag_codes changed silently")

    seen: set[str] = set()
    for item in candidates:
        rid = item["record_id"]
        check(rid not in seen, f"{rid}: duplicate candidate")
        seen.add(rid)
        for flag in item["flags"]:
            check(flag["code"] in FLAG_CODES, f"{rid}: unknown flag code {flag['code']}")
        has_excluded = any(flag["excluded_by_default"] for flag in item["flags"])
        expected_disputed = item["review_status"] != "dismissed" and has_excluded
        check(item["disputed"] == expected_disputed, f"{rid}: disputed flag inconsistent")
        if item["decisions"]:
            latest = item["decisions"][-1]
            check(latest["record_id"] == rid, f"{rid}: decision points to another record")
            check(
                latest["review_status"] == item["review_status"],
                f"{rid}: review_status is not the latest decision",
            )
            check(
                set(latest["flag_codes"]) <= {flag["code"] for flag in item["flags"]},
                f"{rid}: decision cites a flag the record does not have",
            )
        else:
            check(item["review_status"] == "flagged", f"{rid}: status without a decision")
        ref = item["evidence_ref"]
        check(ref["csv_record_number"] >= 2, f"{rid}: invalid evidence row")
        check(ref["kept"] is True, f"{rid}: candidate must reference a kept evidence row")

    if tables is not None:
        students = {row["student_id"] for row in tables["students"]}
        materials = {row["material_id"]: row for row in tables["materials"]}
        nodes = {row["node_id"] for row in tables["nodes"]}
        knowledge = {row["knowledge_id"] for row in tables["knowledge"]}
        details = {
            row["record_id"]: row
            for row in tables["record_details"]
            if str(row.get("kept", "")).strip().lower() in {"true", "1"}
        }
        records = {row["record_id"]: row for row in tables["records"]}
        check(counts.get("records_scanned") == len(records), "records_scanned mismatch")
        for item in candidates:
            rid = item["record_id"]
            record = records.get(rid)
            check(record is not None, f"{rid}: candidate is not a retained record")
            if record is None:
                continue
            check(item["student_id"] == record["student_id"], f"{rid}: student mismatch")
            check(item["material_id"] == record["material_id"], f"{rid}: material mismatch")
            check(item["node_id"] == record["node_id"], f"{rid}: node mismatch")
            check(item["student_id"] in students, f"{rid}: unknown student")
            check(item["node_id"] in nodes, f"{rid}: unknown node")
            check(item["material_id"] in materials, f"{rid}: unknown material")
            check(set(item["knowledge_ids"]) <= knowledge, f"{rid}: unknown knowledge")
            detail = details.get(rid)
            check(detail is not None, f"{rid}: missing kept record_details row")
            if detail is not None:
                check(
                    detail["source_record_id"] == item["evidence_ref"]["source_record_id"],
                    f"{rid}: source record mismatch",
                )
                check(
                    int(detail["csv_record_number"]) == item["evidence_ref"]["csv_record_number"],
                    f"{rid}: evidence row number mismatch",
                )
            check(item["official"]["score"] == _float(record["score"]), f"{rid}: score changed")
            check(
                item["official"]["max_score"] == _float(record["max_score"]),
                f"{rid}: max_score changed",
            )
    return errors


def _float(value) -> float | None:
    text = str(value or "").strip()
    return float(text) if text else None
