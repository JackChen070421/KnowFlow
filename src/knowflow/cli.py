"""KnowFlow command line entry point.

Includes repository checks and the local Task-2 pipeline. Task-3 remains separate.

Owner: R4.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
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
    from .diagnosis.pipeline import prepare_dataset

    bundle, path = prepare_dataset(
        args.dataset, Path(args.knowledge_base) if args.knowledge_base else None
    )
    print(f"ADAPT OK retained_records={len(bundle['records'])} output={path}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from .diagnosis.mastery import DiagnosisConfig
    from .diagnosis.pipeline import prepare_dataset, run_diagnosis

    if args.input and args.knowledge_base:
        raise ValueError(
            "--input cannot be combined with --knowledge-base; apply R1 mapping during adapt"
        )
    if args.input:
        bundle = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        bundle, _ = prepare_dataset(
            args.dataset, Path(args.knowledge_base) if args.knowledge_base else None
        )
    config = (
        DiagnosisConfig(**json.loads(Path(args.config).read_text(encoding="utf-8")))
        if args.config
        else DiagnosisConfig()
    )
    output = (
        Path(args.output)
        if args.output
        else repo_root()
        / "artifacts/run"
        / f"{bundle['dataset_id']}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    )
    result = run_diagnosis(bundle, output, config, args.node)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_verify_run(args: argparse.Namespace) -> int:
    from .diagnosis.validation import validate_saved_run

    result = validate_saved_run(Path(args.run))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "pass" else 1


def _cmd_evidence(args: argparse.Namespace) -> int:
    from .diagnosis.pipeline import export_evidence

    path = export_evidence(Path(args.run), args.record)
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

    adapt_parser = subparsers.add_parser(
        "adapt", help="adapt official CSV into local task-2 inputs"
    )
    adapt_parser.add_argument("--dataset", default="official-v1")
    adapt_parser.add_argument(
        "--knowledge-base", help="optional validated Task-1 knowledge_base.json"
    )
    adapt_parser.set_defaults(func=_cmd_adapt)

    run_parser = subparsers.add_parser(
        "run", help="run Task 2: cleaning, student/class profiles and verification"
    )
    run_parser.add_argument("--dataset", default="official-v1")
    run_parser.add_argument("--input", help="reuse an adapted diagnosis_input.json")
    run_parser.add_argument("--knowledge-base", help="optional Task-1 mapping, used with --dataset")
    run_parser.add_argument("--node", default="all", help="all, latest, or a node ID such as N02")
    run_parser.add_argument(
        "--config", help="JSON diagnosis parameter overrides; recorded in the run"
    )
    run_parser.add_argument(
        "--output", help="new run directory; defaults to artifacts/run/<dataset>-<timestamp>"
    )
    run_parser.set_defaults(func=_cmd_run)

    verify_parser = subparsers.add_parser(
        "verify-run", help="revalidate and recompute saved Task-2 outputs"
    )
    verify_parser.add_argument("--run", required=True)
    verify_parser.set_defaults(func=_cmd_verify_run)

    evidence_parser = subparsers.add_parser(
        "evidence", help="export original answer/steps locally for a cited record"
    )
    evidence_parser.add_argument("--run", required=True)
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
