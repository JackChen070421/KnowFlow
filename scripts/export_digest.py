#!/usr/bin/env python3
"""Emit or check a content-free digest of the canonical tables.

    python scripts/export_digest.py --write   # 首次：生成 data/manifests/<id>.expected.json
    python scripts/export_digest.py --check   # 复刻后：与仓库里的指纹比对

The digest lives in ``data/manifests/<dataset_id>.expected.json`` and contains
only row counts, per-file sha256 and aggregate counters — no cell content.
It is how a teammate proves their local build equals yours without either side
sending the data.

Exit codes: 0 = OK, 1 = mismatch, 2 = usage/state problem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowflow.io.digest import build_digest, compare  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="canonical 产物的跨机指纹")
    parser.add_argument("--dataset-id", default="official-v1")
    parser.add_argument("--interim", default=None, help="default: data/interim/<dataset_id>")
    parser.add_argument("--digest", default=None, help="default: data/manifests/<id>.expected.json")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="写入指纹（确认过产物后才执行）")
    mode.add_argument("--check", action="store_true", help="与仓库里的指纹比对")
    args = parser.parse_args(argv)

    interim = Path(args.interim) if args.interim else ROOT / "data" / "interim" / args.dataset_id
    digest_path = (
        Path(args.digest)
        if args.digest
        else ROOT / "data" / "manifests" / f"{args.dataset_id}.expected.json"
    )

    try:
        actual = build_digest(interim)
    except FileNotFoundError as exc:
        print(f"DIGEST FAILED: {exc}", file=sys.stderr)
        return 2

    if args.write:
        if digest_path.exists():
            print(
                f"REFUSE: {digest_path} 已存在；换数据集请用新的 --dataset-id，不要覆盖",
                file=sys.stderr,
            )
            return 2
        digest_path.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"DIGEST WRITTEN {digest_path}")
        print(f"  tables={len(actual['tables'])} records={actual['total_records']}")
        return 0

    if not digest_path.is_file():
        print(f"MISSING {digest_path}: 仓库里还没有这份指纹", file=sys.stderr)
        return 2
    expected = json.loads(digest_path.read_text(encoding="utf-8"))
    problems = compare(expected, actual)
    if problems:
        print(f"DIGEST MISMATCH dataset={args.dataset_id} problems={len(problems)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"DIGEST OK dataset={args.dataset_id} tables={len(actual['tables'])} "
        f"records={actual['total_records']} "
        f"anomalies={sum(actual['anomaly_counts'].values())}"
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
