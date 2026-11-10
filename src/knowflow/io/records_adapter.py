"""Convert official CSV rows to KnowFlow canonical records, without network or LLM."""

from __future__ import annotations

import csv
import json
import re
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


COLUMNS = (
    "记录编号", "学生编号", "材料编号", "主题编号", "节点编号", "作答事件编号",
    "修订版本", "模拟提交时间", "评分状态", "得分", "满分", "学生最终作答",
    "解答过程", "评分点得分",
)
ID_FORMATS = {
    "records": ("R-", 4), "students": ("S", 3), "materials": ("M-", 3),
}
DETAIL_COLUMNS = {"学生最终作答", "解答过程", "评分点得分"}


class ConversionError(ValueError):
    """A safe error message containing field/row location, not raw answers."""


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise ConversionError("CSV存在重复列名")
        missing = (set(COLUMNS) - DETAIL_COLUMNS) - set(headers)
        extra = set(headers) - set(COLUMNS)
        if missing or extra:
            raise ConversionError(
                f"CSV字段不匹配：缺少{sorted(missing)}；未知{sorted(extra)}"
            )
        rows = list(reader)
    if not rows:
        raise ConversionError("CSV没有数据行")
    for line, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            raise ConversionError(f"第{line}行：列数量与表头不一致")
        for column in DETAIL_COLUMNS:
            row.setdefault(column, "")
    return rows


def extract_details(row: dict[str, str], record: dict, csv_record_number: int) -> dict:
    """Preserve source text verbatim; absent/blank detail values use literal NULL."""
    def text(column: str) -> str:
        value = row.get(column)
        return value if value is not None and value.strip() else "NULL"

    return {
        "record_id": record["record_id"],
        "student_id": record["student_id"],
        "material_id": record["material_id"],
        "source_record_id": row["记录编号"],
        "csv_record_number": csv_record_number,
        "final_answer": text("学生最终作答"),
        "solution_process": text("解答过程"),
        "scoring_point_scores": text("评分点得分"),
    }


def load_id_map(path: Path) -> dict:
    if not path.exists():
        raise ConversionError("编号映射不存在，请先使用 --init-id-map 生成并核对")
    mapping = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or mapping.get("version") != 1:
        raise ConversionError("编号映射版本不支持")
    for kind, (prefix, width) in ID_FORMATS.items():
        values = mapping.get(kind)
        if not isinstance(values, dict):
            raise ConversionError(f"编号映射缺少{kind}")
        if any(not isinstance(k, str) or not k.strip() for k in values):
            raise ConversionError(f"{kind}存在空白或无效原编号")
        pattern = rf"{re.escape(prefix)}[0-9]{{{width}}}"
        if any(not isinstance(v, str) or not re.fullmatch(pattern, v) for v in values.values()):
            raise ConversionError(f"{kind}的目标编号不符合契约")
        if len(set(values.values())) != len(values):
            raise ConversionError(f"{kind}存在重复目标编号")
    return mapping


def initialize_id_map(rows: list[dict[str, str]], materials_path: Path,
                      students_path: Path, path: Path) -> dict:
    """Allocate once from complete registries; never renumber a later subset."""
    if path.exists():
        raise ConversionError("编号映射已存在，禁止重新生成覆盖")

    def registry(file: Path, column: str) -> list[str]:
        with file.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if column not in (reader.fieldnames or []):
                raise ConversionError(f"登记表缺少{column}")
            ids = [(r.get(column) or "").strip() for r in reader]
        if any(not x for x in ids) or len(ids) != len(set(ids)):
            raise ConversionError(f"登记表{column}存在空值或重复")
        return ids

    material_ids = registry(materials_path, "材料编号")
    student_ids = registry(students_path, "学生编号")
    # Official ordering: Q001..Q054, L01..L03, B01..B08, as CONTRACT §7.
    if any(not re.fullmatch(r"(?:Q[0-9]{3}|[LB][0-9]{2})", x) for x in material_ids):
        raise ConversionError("材料编号不符合官方Q/L/B格式，需先明确映射规则")
    material_ids.sort(key=lambda x: ({"Q": 0, "L": 1, "B": 2}[x[0]], int(x[1:])))
    record_ids = sorted({r["记录编号"].strip() for r in rows})
    groups = {"records": record_ids, "students": sorted(student_ids), "materials": material_ids}
    mapping = {"version": 1}
    for kind, ids in groups.items():
        prefix, width = ID_FORMATS[kind]
        if not all(ids) or len(ids) > 10 ** width - 1:
            raise ConversionError(f"{kind}原编号为空或超出编号容量")
        mapping[kind] = {old: f"{prefix}{index:0{width}d}" for index, old in enumerate(ids, 1)}
    # Registry allocation does not modify or clean scores.
    for line, row in enumerate(rows, 2):
        for kind, column in [("students", "学生编号"), ("materials", "材料编号")]:
            if row[column].strip() not in mapping[kind]:
                raise ConversionError(f"第{line}行：{column}未在完整登记表中")
    write_new_json(path, mapping)
    return mapping


def number(value: str, field: str, line: int) -> Decimal:
    try:
        result = Decimal(value.strip())
    except InvalidOperation:
        raise ConversionError(f"第{line}行：{field}不是有效数值") from None
    if not result.is_finite() or not math.isfinite(float(result)):
        raise ConversionError(f"第{line}行：{field}必须是有限数值")
    return result


def convert_rows(rows: list[dict[str, str]], mapping: dict,
                 include_answer: bool = False) -> list[dict]:
    output, seen = [], set()
    for line, row in enumerate(rows, 2):
        ids = {}
        for kind, source, target in [
            ("records", "记录编号", "record_id"),
            ("students", "学生编号", "student_id"),
            ("materials", "材料编号", "material_id"),
        ]:
            old = row[source].strip()
            if old not in mapping[kind]:
                raise ConversionError(f"第{line}行：{source}未登记到编号映射")
            ids[target] = mapping[kind][old]
        if ids["record_id"] in seen:
            raise ConversionError(f"第{line}行：记录主键重复，请先核查原始数据")
        seen.add(ids["record_id"])
        status = row["评分状态"].strip()
        if status not in {"已评分", "待评分", "未作答"}:
            raise ConversionError(f"第{line}行：未知评分状态")
        max_score = number(row["满分"], "满分", line)
        if max_score <= 0:
            raise ConversionError(f"第{line}行：满分必须大于0")
        score = None
        if status == "已评分":
            score = number(row["得分"], "得分", line)
            if not 0 <= score <= max_score:
                raise ConversionError(f"第{line}行：得分超出有效范围")
        elif row["得分"].strip():
            raise ConversionError(f"第{line}行：未评分记录却含得分，需人工核查")
        revision = row["修订版本"].strip()
        if not re.fullmatch(r"[1-9][0-9]*", revision):
            raise ConversionError(f"第{line}行：修订版本必须是正整数")
        submitted = row["模拟提交时间"].strip()
        if submitted:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", submitted):
                    raise ValueError
                parsed = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    raise ValueError
            except ValueError:
                raise ConversionError(f"第{line}行：提交时间必须是带时区的ISO 8601时间") from None
        output.append({
            **ids, "assigned": True, "attempted": status != "未作答",
            "score": float(score) if score is not None else None,
            "max_score": float(max_score),
            "is_correct": score == max_score if score is not None else None,
            "answer": row["学生最终作答"] or None if include_answer else None,
            "submitted_at": submitted or None, "duration_seconds": None,
            "attempt_no": int(revision), "source": "official-v1",
        })
    return output


def validate_rows(records: list[dict], schema_path: Path) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for line, record in enumerate(records, 2):
        errors = list(validator.iter_errors(record))
        if errors:
            fields = sorted({".".join(map(str, e.path)) or "root" for e in errors})
            raise ConversionError(f"第{line}行：schema校验失败，字段{fields}")


def write_new_json(path: Path, value: object) -> None:
    """Exclusive creation protects previous exports; strict JSON forbids NaN/Infinity."""
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
