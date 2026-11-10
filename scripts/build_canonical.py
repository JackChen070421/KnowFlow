#!/usr/bin/env python3
"""Build canonical tables from the landed official package.

    python scripts/build_canonical.py --dataset-id official-v1
    python scripts/build_canonical.py --generated-at 2026-11-10T00:00:00+08:00

Reads ``data/raw/<dataset_id>/`` and writes ``data/interim/<dataset_id>/``
(9 canonical CSVs + ``data_quality_report.json``).  Both directories are
git-ignored: the output never leaves the machine.

Exit codes: 0 = OK, 1 = data/validation error, 2 = usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowflow.io import AdaptError, run_adapt  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Official raw CSV → canonical CSV + data_quality_report.json."
    )
    parser.add_argument("--dataset-id", default="official-v1")
    parser.add_argument("--raw", default=None, help="default: data/raw/<dataset_id>")
    parser.add_argument("--out", default=None, help="default: data/interim/<dataset_id>")
    parser.add_argument(
        "--generated-at",
        default=None,
        help="ISO 8601 timestamp; fixed value makes the run byte-identical",
    )
    args = parser.parse_args(argv)

    raw = Path(args.raw) if args.raw else ROOT / "data" / "raw" / args.dataset_id
    out = Path(args.out) if args.out else ROOT / "data" / "interim" / args.dataset_id

    try:
        summary = run_adapt(raw, out, args.dataset_id, args.generated_at)
    except AdaptError as exc:
        print(f"ADAPT FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        f"ADAPT OK dataset_id={summary['dataset_id']} "
        f"generated_at={summary['generated_at']}"
    )
    for name, count in summary["counts"].items():
        print(f"  {name:<12} {count}")
    states = summary["report"]["records_by_state"]
    print(
        "  records_by_state "
        f"correct={states['observed_correct']} wrong={states['observed_wrong']} "
        f"pending={states['pending']} not_attempted={states['assigned_not_attempted']} "
        f"unobserved={states['unobserved']}"
    )
    print(
        f"  duplicates_removed={summary['report']['duplicates_removed']} "
        f"anomalies={len(summary['report']['anomalies'])}"
    )
    print(f"REPORT {summary['report_path']}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
