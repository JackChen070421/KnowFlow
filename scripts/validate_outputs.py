#!/usr/bin/env python3
"""Validate a JSON artifact against one of the KnowFlow schemas.
拿一份 JSON 对一份 schema
Usage:
    python scripts/validate_outputs.py \
        --schema schemas/output/student_profile.schema.json \
        --data tests/fixtures/student_profile.min.json

Exit code 0 means the document is valid. Errors are printed as
``/<json-pointer>: <message>``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowflow.contracts import repo_root, validate_instance  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_outputs",
        description="Validate a KnowFlow JSON artifact against a JSON Schema.",
    )
    parser.add_argument("--schema", required=True, help="path to *.schema.json")
    parser.add_argument("--data", required=True, help="path to the JSON document")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    schema_path = Path(args.schema)
    data_path = Path(args.data)

    for path, label in ((schema_path, "schema"), (data_path, "data")):
        if not path.is_file():
            print(f"{label} not found: {path}", file=sys.stderr)
            return 2

    try:
        errors = validate_instance(schema_path, data_path, root=repo_root(ROOT))
    except Exception as exc:  # noqa: BLE001 - surface the actual validation error
        print(f"validation error: {exc}", file=sys.stderr)
        return 2

    if errors:
        print(f"schema validation: FAILED ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("schema validation: OK (0 errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
