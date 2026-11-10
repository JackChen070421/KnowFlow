#!/usr/bin/env python3
"""Validate the synthetic CSV tables against the row schemas.
读 8 张合成 CSV，检查表头、类型、必填、主键唯一，并逐行过 schema
This is a lightweight M0/M1 bridge: it checks headers, required columns,
primary-key uniqueness and typed row validation. Full foreign-key/coverage
checks (G2) arrive with the validator in M3.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator  # noqa: E402

from knowflow.contracts import build_registry, load_json  # noqa: E402

INPUT_DIR = ROOT / "examples" / "synthetic" / "input"
SCHEMA_DIR = ROOT / "schemas" / "input"


def coerce(value: str | None, schema: dict[str, Any]) -> Any:
    raw = (value or "").strip()
    types = schema.get("type")
    if types is None:
        return value
    if isinstance(types, str):
        types = [types]

    if raw == "":
        return None if "null" in types else ""

    for type_name in types:
        try:
            if type_name == "null":
                return None
            if type_name == "string":
                return value
            if type_name == "integer":
                return int(raw)
            if type_name == "number":
                return float(raw)
            if type_name == "boolean":
                lowered = raw.lower()
                if lowered in {"true", "1", "yes"}:
                    return True
                if lowered in {"false", "0", "no"}:
                    return False
                raise ValueError(raw)
        except ValueError:
            continue
    return value


def validate_table(csv_path: Path, schema_path: Path) -> list[str]:
    errors: list[str] = []
    schema = load_json(schema_path)
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    primary_key = schema.get("x-primary-key", [])

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if not fieldnames:
        return [f"{csv_path.name}: empty file or missing header"]
    if set(fieldnames) != set(properties):
        missing = sorted(set(properties) - set(fieldnames))
        extra = sorted(set(fieldnames) - set(properties))
        if missing:
            errors.append(f"{csv_path.name}: missing columns {missing}")
        if extra:
            errors.append(f"{csv_path.name}: unknown columns {extra}")

    if not required.issubset(set(fieldnames)):
        errors.append(
            f"{csv_path.name}: missing required columns "
            f"{sorted(required - set(fieldnames))}"
        )

    validator = Draft202012Validator(
        schema,
        registry=build_registry(ROOT),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    seen: dict[tuple[Any, ...], int] = {}
    for index, row in enumerate(rows, start=2):  # header is line 1
        if None in row:
            errors.append(
                f"{csv_path.name}:{index}: row has more columns than the header"
            )
        if any(value is None for key, value in row.items() if key is not None):
            errors.append(
                f"{csv_path.name}:{index}: row has fewer columns than the header"
            )
        typed = {
            key: coerce(value, properties.get(key, {}))
            for key, value in row.items()
            if key is not None
        }
        for error in validator.iter_errors(typed):
            location = "/".join(str(part) for part in error.absolute_path)
            prefix = f"{csv_path.name}:{index}"
            if location:
                prefix += f"/{location}"
            errors.append(f"{prefix}: {error.message}")

        if primary_key:
            key = tuple(typed.get(name) for name in primary_key)
            if key in seen:
                errors.append(
                    f"{csv_path.name}:{index}: duplicate primary key {key} "
                    f"(first at line {seen[key]})"
                )
            else:
                seen[key] = index

    return errors


def main() -> int:
    all_errors: list[str] = []
    checked = 0
    for csv_path in sorted(INPUT_DIR.glob("*.csv")):
        schema_path = SCHEMA_DIR / f"{csv_path.stem}.schema.json"
        if not schema_path.is_file():
            all_errors.append(f"{csv_path.name}: missing schema {schema_path.name}")
            continue
        all_errors.extend(validate_table(csv_path, schema_path))
        checked += 1

    if all_errors:
        print(f"synthetic CSV check: FAILED ({len(all_errors)} errors)")
        for error in all_errors:
            print(f"  - {error}")
        return 1

    print(f"synthetic CSV check: OK ({checked} tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
