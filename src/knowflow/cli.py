"""KnowFlow command line entry point.

Current scope (M0): repository contract checks and single-file schema
validation. Business commands (``run``/``validate --run``) arrive in M1–M3.

Owner: R4.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .contracts import (
    check_repo,
    iter_schema_paths,
    repo_root,
    validate_instance,
)


def _cmd_check(_: argparse.Namespace) -> int:
    root = repo_root()
    errors = check_repo(root)
    if errors:
        print("KnowFlow contract check: FAILED")
        for error in errors:
            print(f"  - {error}")
        return 1
    count = len(iter_schema_paths(root))
    print(f"KnowFlow contract check: OK ({count} schemas)")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    schema_path = Path(args.schema)
    data_path = Path(args.data)
    for path, label in ((schema_path, "schema"), (data_path, "data")):
        if not path.is_file():
            print(f"{label} not found: {path}", file=sys.stderr)
            return 2
    errors = validate_instance(schema_path, data_path)
    if errors:
        print(f"schema validation: FAILED ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("schema validation: OK (0 errors)")
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"knowflow {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowflow",
        description="KnowFlow: evidence-traceable learning diagnosis.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check", help="check repository structure, schemas and data hygiene"
    )
    check_parser.set_defaults(func=_cmd_check)

    validate_parser = subparsers.add_parser(
        "validate", help="validate one JSON document against a schema"
    )
    validate_parser.add_argument("--schema", required=True, help="path to *.schema.json")
    validate_parser.add_argument("--data", required=True, help="path to JSON data")
    validate_parser.set_defaults(func=_cmd_validate)

    version_parser = subparsers.add_parser("version", help="print version")
    version_parser.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
