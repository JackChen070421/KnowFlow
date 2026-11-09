#!/usr/bin/env python3
"""Land the official competition package verbatim, then fingerprint it.

This is **not** the IO adapter (see ``schemas/CONTRACT.md`` §6): it never
renames a column or maps an ID. It copies the official tree byte-for-byte and
records ``sha256`` / bytes / rows, so that any teammate can rebuild the same
layout on their own machine from the same official package — ``data/raw`` is
git-ignored, so ``git pull`` alone deliberately brings no data.

Stdlib only: it must run on a fresh machine before ``pip install -e .``.

Usage
-----
    python scripts/ingest_raw.py --source "D:\\赛题数据"
    python scripts/ingest_raw.py --source "D:\\赛题数据" --force
    python scripts/ingest_raw.py --check
    python scripts/ingest_raw.py --check --expected teammate/manifest.json

Exit codes: 0 = OK, 1 = mismatch or usage error.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

DATASET_ID = "official-v1"
PACKAGE_MARKER = "1_赛题规则.pdf"  # 只在资料包根目录出现，用来识别源路径
LOOSE_FILE = "资料说明.txt"        # 与资料包同级、需要一并归档的说明
MANIFEST = "manifest.json"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def structure_path(root: Path, dataset_id: str) -> Path:
    """The committed fingerprint. Lives outside data/raw on purpose.

    data/raw/** is a closed wall (nothing from it is ever committed); this file
    holds no data, only paths/hashes/row counts, so it *is* committed and lets
    every teammate verify their copy byte-for-byte.
    """

    return root / "data" / "manifests" / f"{dataset_id}.structure.json"


def structure_payload(manifest: dict) -> dict:
    """Strip volatile fields so re-running on the same data is a no-op in Git."""

    return {
        "dataset_id": manifest["dataset_id"],
        "note": "纯指纹：路径 + sha256 + 字节数 + 行数；不含任何数据内容，可入库。",
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "files": manifest["files"],
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(path: Path) -> int:
    """Count data rows, honouring quoted newlines inside cells."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def xlsx_sheets(path: Path) -> int:
    """Count worksheets without needing openpyxl (xlsx is a zip)."""

    with zipfile.ZipFile(path) as archive:
        xml = archive.read("xl/workbook.xml").decode("utf-8", "replace")
    return len(re.findall(r"<sheet\b", xml))


def resolve_source(source: Path) -> tuple[Path, Path | None]:
    """Accept either the 资料包 folder itself or its parent 赛题数据 folder."""

    source = source.resolve()
    if (source / PACKAGE_MARKER).is_file():
        loose = source.parent / LOOSE_FILE
        return source, (loose if loose.is_file() else None)
    nested = source / "赛题资料包"
    if (nested / PACKAGE_MARKER).is_file():
        loose = source / LOOSE_FILE
        return nested, (loose if loose.is_file() else None)
    raise SystemExit(
        f"source does not look like the official package: {source}\n"
        f"  expected {PACKAGE_MARKER} either in it or under 赛题资料包/"
    )


def fingerprint(base: Path, files: list[str]) -> list[dict]:
    entries = []
    for rel in sorted(files):
        path = base / rel
        entry = {
            "path": Path(rel).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        suffix = path.suffix.lower()
        if suffix == ".csv":
            entry["rows"] = csv_rows(path)
        elif suffix == ".xlsx":
            entry["sheets"] = xlsx_sheets(path)
        entries.append(entry)
    return entries


def collect(target: Path) -> list[str]:
    return sorted(
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() and path.name != MANIFEST
    )


def describe_change(expected: list[dict], actual: list[dict]) -> list[str]:
    problems: list[str] = []
    exp = {item["path"]: item for item in expected}
    act = {item["path"]: item for item in actual}
    for path in sorted(exp.keys() - act.keys()):
        problems.append(f"missing: {path}")
    for path in sorted(act.keys() - exp.keys()):
        problems.append(f"extra:   {path}")
    for path in sorted(exp.keys() & act.keys()):
        for field in ("sha256", "bytes", "rows", "sheets"):
            if field in exp[path] and exp[path][field] != act[path].get(field):
                problems.append(
                    f"differs: {path} [{field}] expected={exp[path][field]} actual={act[path].get(field)}"
                )
    return problems


def cmd_ingest(args: argparse.Namespace) -> int:
    root = repo_root()
    source, loose = resolve_source(Path(args.source))
    target = root / "data" / "raw" / args.dataset_id

    if target.exists() and not args.force:
        print(f"REFUSED target already exists: {target}", file=sys.stderr)
        print("        pass --force to overwrite, or --check to verify it instead.", file=sys.stderr)
        return 1
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(source):
        rel_dir = os.path.relpath(dirpath, source)
        out_dir = target if rel_dir == "." else target / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            shutil.copy2(Path(dirpath) / name, out_dir / name)
            copied.append((out_dir / name).relative_to(target).as_posix())
    if loose is not None:
        shutil.copy2(loose, target / LOOSE_FILE)
        copied.append(LOOSE_FILE)

    entries = fingerprint(target, copied)
    total = sum(item["bytes"] for item in entries)
    manifest = {
        "dataset_id": args.dataset_id,
        "received_at": args.received_at,
        "source": "第二届北京市大学生“人工智能+”创新大赛 · “智慧学伴”赛题组",
        "placement": "官方资料包根目录内容原样置于本目录；文件名、目录结构、文件内容均未修改",
        "data_dictionary_version": "v1",
        "file_count": len(entries),
        "total_bytes": total,
        "files": entries,
        "notes": [
            "仅限本次大赛使用；不得外传或用于其他用途；赛后按赛题组要求删除。",
            "学生与作答记录均为模拟数据，不含真实学生个人信息。",
            "本文件与整个目录均被 .gitignore 忽略，永不入库。",
        ],
    }
    (target / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"INGEST OK dataset_id={args.dataset_id} files={len(entries)} bytes={total}")
    for item in entries:
        extra = f" rows={item['rows']}" if "rows" in item else (
            f" sheets={item['sheets']}" if "sheets" in item else ""
        )
        print(f"  {item['path']}  {item['bytes']} B{extra}")
    print(f"MANIFEST {target / MANIFEST}")

    if args.export_structure:
        pinned = structure_path(root, args.dataset_id)
        pinned.parent.mkdir(parents=True, exist_ok=True)
        pinned.write_text(
            json.dumps(structure_payload(manifest), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"PINNED {pinned}")
    else:
        print("HINT   pass --export-structure to refresh the committed fingerprint")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    root = repo_root()
    target = root / "data" / "raw" / args.dataset_id
    pinned = structure_path(root, args.dataset_id)

    if args.expected:
        manifest_path = Path(args.expected)
    elif pinned.is_file():
        # The committed fingerprint is the authority: it is how a teammate proves
        # their copy matches everyone else's, not just its own past self.
        manifest_path = pinned
    else:
        manifest_path = target / MANIFEST

    if not manifest_path.is_file():
        print(f"MISSING manifest: {manifest_path}", file=sys.stderr)
        print("        run ingest first, or pass --expected <manifest.json>.", file=sys.stderr)
        return 1
    if not target.is_dir():
        print(f"MISSING data directory: {target}", file=sys.stderr)
        print("        data/raw is git-ignored: git pull does not bring it.", file=sys.stderr)
        return 1

    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = fingerprint(target, collect(target))
    problems = describe_change(expected.get("files", []), actual)

    if problems:
        print(f"CHECK FAIL dataset_id={args.dataset_id} problems={len(problems)}")
        for problem in problems:
            print(f"  {problem}")
        return 1

    total = sum(item["bytes"] for item in actual)
    print(f"CHECK OK dataset_id={args.dataset_id} files={len(actual)} bytes={total}")
    print(f"  compared against {manifest_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Land the official package under data/raw/ and fingerprint it."
    )
    parser.add_argument("--dataset-id", default=DATASET_ID)
    parser.add_argument("--source", help="path to 赛题数据/ or 赛题资料包/ (ingest only)")
    parser.add_argument("--received-at", default=None, help="ISO 8601; defaults to now")
    parser.add_argument("--check", action="store_true", help="verify an existing copy instead of copying")
    parser.add_argument("--expected", help="compare against this manifest instead of the pinned one")
    parser.add_argument("--force", action="store_true", help="overwrite an existing target")
    parser.add_argument(
        "--export-structure",
        action="store_true",
        help="also rewrite data/manifests/<dataset_id>.structure.json (the committed fingerprint)",
    )
    args = parser.parse_args(argv)

    if args.check:
        return cmd_check(args)
    if not args.source:
        parser.error("--source is required unless --check is given")

    if args.received_at is None:
        import datetime

        args.received_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    return cmd_ingest(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
