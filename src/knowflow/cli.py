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


def _cmd_adapt(args: argparse.Namespace) -> int:
    """Official package → canonical tables (layer 2)."""

    from .io import AdaptError, run_adapt

    root = repo_root()
    raw = Path(args.raw) if args.raw else root / "data" / "raw" / args.dataset_id
    out = Path(args.out) if args.out else root / "data" / "interim" / args.dataset_id
    try:
        summary = run_adapt(raw, out, args.dataset_id, args.generated_at)
    except AdaptError as exc:
        print(f"adapt: FAILED\n  {exc}", file=sys.stderr)
        return 1
    print(f"adapt: OK ({summary['dataset_id']}, {summary['generated_at']})")
    for name, count in summary["counts"].items():
        print(f"  {name:<12} {count}")
    print(f"  report       {summary['report_path']}")
    return 0


def _cmd_validate_canonical(args: argparse.Namespace) -> int:
    """Re-verify canonical tables on disk (G2/G3)."""

    from .io import AdaptError, verify_written

    root = repo_root()
    raw = Path(args.raw) if args.raw else root / "data" / "raw" / args.dataset_id
    out = Path(args.out) if args.out else root / "data" / "interim" / args.dataset_id
    try:
        errors, bundle = verify_written(raw, out, args.dataset_id, args.generated_at)
    except AdaptError as exc:
        print(f"validate-canonical: FAILED\n  {exc}", file=sys.stderr)
        return 1
    if errors:
        print(f"validate-canonical: FAILED ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "validate-canonical: OK "
        f"({bundle.counts()['records']} records, "
        f"{len(bundle.report['anomalies'])} anomalies)"
    )
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

    adapt_parser = subparsers.add_parser(
        "adapt", help="official raw CSV → canonical tables (layer 2)"
    )
    adapt_parser.add_argument("--dataset-id", default="official-v1")
    adapt_parser.add_argument("--raw", default=None, help="default: data/raw/<dataset_id>")
    adapt_parser.add_argument("--out", default=None, help="default: data/interim/<dataset_id>")
    adapt_parser.add_argument("--generated-at", default=None, help="ISO 8601 timestamp")
    adapt_parser.set_defaults(func=_cmd_adapt)

    validate_canonical_parser = subparsers.add_parser(
        "validate-canonical", help="verify canonical tables on disk (G2/G3)"
    )
    validate_canonical_parser.add_argument("--dataset-id", default="official-v1")
    validate_canonical_parser.add_argument("--raw", default=None)
    validate_canonical_parser.add_argument("--out", default=None)
    validate_canonical_parser.add_argument("--generated-at", default=None)
    validate_canonical_parser.set_defaults(func=_cmd_validate_canonical)

    version_parser = subparsers.add_parser("version", help="print version")
    version_parser.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
