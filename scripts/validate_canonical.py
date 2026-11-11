#!/usr/bin/env python3
"""Re-verify the canonical tables on disk (G2 references + G3 consistency).

    python scripts/validate_canonical.py --dataset-id official-v1

It recomputes the pipeline in memory and compares every file byte-for-byte,
so a hand-edited CSV or a stale report is caught instead of trusted.

Exit codes: 0 = OK, 1 = errors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowflow.io import AdaptError, verify_written  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate canonical tables against references and invariants."
    )
    parser.add_argument("--dataset-id", default="official-v1")
    parser.add_argument("--raw", default=None, help="default: data/raw/<dataset_id>")
    parser.add_argument("--out", default=None, help="default: data/interim/<dataset_id>")
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)

    raw = Path(args.raw) if args.raw else ROOT / "data" / "raw" / args.dataset_id
    out = Path(args.out) if args.out else ROOT / "data" / "interim" / args.dataset_id

    try:
        errors, bundle = verify_written(raw, out, args.dataset_id, args.generated_at)
    except AdaptError as exc:
        print(f"VALIDATE FAILED: {exc}", file=sys.stderr)
        return 1

    if errors:
        print(f"VALIDATE FAIL dataset_id={args.dataset_id} errors={len(errors)}")
        for error in errors:
            print(f"  - {error}")
        return 1

    counts = bundle.counts()
    print(
        f"VALIDATE OK dataset_id={args.dataset_id} "
        f"tables={len(counts)} records={counts['records']} "
        f"anomalies={len(bundle.report['anomalies'])}"
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
