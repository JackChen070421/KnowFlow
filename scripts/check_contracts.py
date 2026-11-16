#!/usr/bin/env python3
"""Check repository structure, JSON Schemas and data-hygiene rules.
检查必需目录/文件、schema 能否解析、$id 是否唯一、受限数据是否被 Git 忽略、.gitignore 规则
Usage:
    python scripts/check_contracts.py

Exit code 0 means all checks passed. This script intentionally does not need
pandas/scipy; it only needs stdlib (schema parsing) plus the repository code.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowflow.contracts import check_repo, iter_schema_paths  # noqa: E402
from knowflow.knowledge.graph import graph_warnings, load_graph, validate_graph  # noqa: E402


def main() -> int:
    errors = check_repo(ROOT)
    graph = None
    warnings: list[str] = []
    if not errors:
        try:
            graph = load_graph(ROOT / "knowledge" / "curriculum_graph.json")
            validate_graph(graph)
            warnings = graph_warnings(graph)
        except ValueError as exc:
            errors.append(f"curriculum graph: {exc}")
    if errors:
        print("KnowFlow contract check: FAILED")
        for error in errors:
            print(f"  - {error}")
        return 1

    schema_count = len(iter_schema_paths(ROOT))
    print(f"KnowFlow contract check: OK ({schema_count} schemas)")
    print("  - required directories/files present")
    print("  - schemas parse and $id values are unique")
    print(
        "  - files under data/raw, data/interim, data/reviews and data/progress "
        "are git-ignored (never committed)"
    )
    print(
        "  - curriculum graph structure validated "
        f"({graph['counts']['node_count']} nodes / {graph['counts']['edge_count']} edges)"
    )
    for warning in warnings:
        print(f"  - note: {warning}")
    print("  - .gitignore keeps data, secrets and model weights out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
