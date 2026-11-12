"""KnowFlow command line entry point.

Repository checks, single-file schema validation, and the Task-2 diagnosis flow
(``run`` / ``verify-run`` / ``evidence``). Task-3 remains out of scope.

Owner: R4.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
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


def _cmd_run(args: argparse.Namespace) -> int:
    from .diagnosis.mastery import DiagnosisConfig
    from .diagnosis.pipeline import build_bundle, run_diagnosis

    bundle, _ = build_bundle(args.dataset)
    config = (
        DiagnosisConfig(**json.loads(Path(args.config).read_text(encoding="utf-8")))
        if args.config
        else DiagnosisConfig()
    )
    output = (
        Path(args.output)
        if args.output
        else repo_root()
        / "artifacts"
        / "run"
        / f"{bundle['dataset_id']}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    )
    result = run_diagnosis(bundle, output, config, args.node)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _resolve_run(value: str | None) -> Path:
    from .diagnosis.pipeline import latest_run_dir

    if value in (None, "", "latest"):
        return latest_run_dir()
    return Path(value)


def _cmd_verify_run(args: argparse.Namespace) -> int:
    from .diagnosis.validation import validate_saved_run

    result = validate_saved_run(_resolve_run(args.run))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "pass" else 1


def _cmd_evidence(args: argparse.Namespace) -> int:
    from .diagnosis.pipeline import export_evidence

    path = export_evidence(_resolve_run(args.run), args.record)
    print(f"LOCAL EVIDENCE {path}")
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

    run_parser = subparsers.add_parser(
        "run", help="run Task 2 on canonical tables: cleaning view, profiles, verification"
    )
    run_parser.add_argument("--dataset", default="official-v1")
    run_parser.add_argument(
        "--node", default="all", help="all, latest, or a node ID such as N02"
    )
    run_parser.add_argument("--config", help="JSON diagnosis parameter overrides; recorded in the run")
    run_parser.add_argument(
        "--output", help="new run directory; defaults to artifacts/run/<dataset>-<timestamp>"
    )
    run_parser.set_defaults(func=_cmd_run)

    verify_parser = subparsers.add_parser(
        "verify-run", help="revalidate and recompute a saved Task-2 run"
    )
    verify_parser.add_argument(
        "--run",
        help="run directory or 'latest'; defaults to the newest run under artifacts/run",
    )
    verify_parser.set_defaults(func=_cmd_verify_run)

    evidence_parser = subparsers.add_parser(
        "evidence", help="export original answer/steps locally for a cited record"
    )
    evidence_parser.add_argument(
        "--run",
        help="run directory or 'latest'; defaults to the newest run under artifacts/run",
    )
    evidence_parser.add_argument("--record", required=True)
    evidence_parser.set_defaults(func=_cmd_evidence)

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"KnowFlow: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
