"""Run the structured acceptance suites and report counts per failure category.

``tests/diagnosis/test_acceptance.py`` names every test with its category prefix,
so this script can run one category at a time and print a table.  That is what
turns "a test failed" into "the fact card is wrong / the 口径 is wrong / the model
said it wrong / the audit let it through / the ID is unknown".

Usage (from the repo root, with the project's Python):

    python scripts/check_acceptance.py
    python scripts/check_acceptance.py --category 表达

Exit code is 1 when any category fails, so it can sit in CI as a separate gate.
Owner: R3.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from knowflow.contracts import repo_root

CATEGORIES = (
    ("数据提取", "test_data_"),
    ("统计口径", "test_metric_"),
    ("表达", "test_expression_"),
    ("数字审计", "test_audit_"),
    ("实体引用", "test_entity_"),
)
TEST_PATH = "tests/diagnosis/test_acceptance.py"


def _run(root, selector: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            "--tb=line",
            TEST_PATH,
            "-k",
            selector,
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )


def _summary(stdout: str) -> str:
    for line in reversed((stdout or "").strip().splitlines()):
        if any(word in line for word in ("passed", "failed", "no tests ran", "error")):
            return line.strip()
    return "no result"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="结构化验收：按失败类别统计")
    parser.add_argument(
        "--category",
        default=None,
        help="只跑一类（数据提取/统计口径/表达/数字审计/实体引用）",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    selected = [
        item for item in CATEGORIES if args.category is None or item[0] == args.category
    ]
    if not selected:
        print(f"未知类别：{args.category}；可选：{'、'.join(name for name, _ in CATEGORIES)}")
        return 2

    results = []
    for label, selector in selected:
        proc = _run(root, selector)
        results.append((label, selector, proc.returncode == 0, _summary(proc.stdout), proc.stdout))

    width = max(len(label) for label, _ in selected)
    failed = 0
    for label, _selector, ok, line, _ in results:
        print(f"{label:<{width}}  {'PASS' if ok else 'FAIL'}  {line}")
        failed += not ok

    for label, selector, ok, _line, stdout in results:
        if ok:
            continue
        print(f"\n--- {label} 失败原因（{selector}）")
        for line in (stdout or "").strip().splitlines()[-14:]:
            print(line)

    print(f"\n未通过分类 {failed}/{len(selected)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
