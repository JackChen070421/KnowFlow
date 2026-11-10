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
from .config import get_settings
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


def _cmd_config(_: argparse.Namespace) -> int:
    """Print resolved settings (never the key itself) to debug local setup."""

    settings = get_settings()
    print(f"llm.enabled   = {settings.llm_enabled}")
    print(f"llm.ready     = {settings.llm_ready}")
    print(f"llm.provider  = {settings.llm_provider}")
    print(f"llm.model     = {settings.llm_model}")
    print(f"llm.base_url  = {settings.llm_base_url}")
    print(f"llm.api_key   = {'(set)' if settings.llm_api_key else '(empty)'}")
    print(f"llm.timeout   = {settings.llm_timeout_seconds}s")
    print(f"data_dir      = {settings.data_dir}")
    print(f"artifact_dir  = {settings.artifact_dir}")
    print(f"log_level     = {settings.log_level}")
    print(f"random_seed   = {settings.random_seed}")
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

    config_parser = subparsers.add_parser(
        "config", help="print resolved settings (keys are masked)"
    )
    config_parser.set_defaults(func=_cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
