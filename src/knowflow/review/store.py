"""Append-only local review ledger (human decisions, never rewrites history).

The ledger lives under ``data/reviews/<dataset_id>/`` (Git-ignored).  It is
pinned to the three canonical tables by SHA-256: if the data is rebuilt with
different bytes, old conclusions are refused instead of silently re-applied.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.contracts import build_registry, repo_root

from .rules import RULE_VERSION

LEDGER_SCHEMA_VERSION = "1.0.0"
LEDGER_DIR = "data/reviews"
LEDGER_FILE = "decisions.jsonl"
META_FILE = "ledger_meta.json"
DECISION_STATUSES: tuple[str, ...] = ("confirmed_issue", "dismissed", "needs_more_evidence")
SOURCE_FILES: tuple[str, ...] = ("records.csv", "materials.csv", "record_details.csv")


def source_hashes(base: Path) -> dict[str, str]:
    """SHA-256 of the canonical tables the ledger and report are pinned to."""

    base = Path(base)
    return {
        name: hashlib.sha256((base / name).read_bytes()).hexdigest() for name in SOURCE_FILES
    }


def ledger_dir(dataset_id: str, root: Path | None = None) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dataset_id):
        raise ValueError("dataset ID must be a safe directory name")
    base = Path(root) if root is not None else repo_root()
    return base / LEDGER_DIR / dataset_id


@lru_cache(maxsize=1)
def _decision_validator() -> Draft202012Validator:
    root = repo_root()
    schema = json.loads(
        (root / "schemas" / "output" / "review_report.schema.json").read_text(encoding="utf-8")
    )
    wrapper = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"{schema['$id']}#/$defs/decision",
    }
    return Draft202012Validator(
        wrapper, registry=build_registry(root), format_checker=FormatChecker()
    )


def decision_errors(decision: dict) -> list[str]:
    return [
        f"decision:{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in _decision_validator().iter_errors(decision)
    ]


def load_meta(directory: Path) -> dict:
    path = Path(directory) / META_FILE
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_meta(
    directory: Path, dataset_id: str, hashes: dict[str, str], generated_at: str
) -> dict:
    """Create the ledger binding once, or refuse when the source data changed.

    Refusing is the point: a conclusion about ``R-0685`` must not be re-applied
    to a rebuilt dataset whose rows may mean something else.
    """

    directory = Path(directory)
    meta = load_meta(directory)
    expected = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "rule_version": RULE_VERSION,
        "source_sha256": dict(hashes),
    }
    if not meta:
        directory.mkdir(parents=True, exist_ok=True)
        meta = {**expected, "created_at": generated_at}
        (directory / META_FILE).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return meta
    if meta.get("dataset_id") != dataset_id:
        raise ValueError("review ledger belongs to another dataset; refuse to reuse it")
    if meta.get("source_sha256") != expected["source_sha256"]:
        raise ValueError(
            "canonical tables changed since the review ledger was created; "
            "re-run the scan and review the flagged records again"
        )
    return meta


def load_decisions(path: Path) -> list[dict]:
    """Read the append-only ledger, validating every line."""

    path = Path(path)
    if not path.is_file():
        return []
    decisions: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text:
            continue
        try:
            decision = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {number} is not valid JSON: {exc}") from exc
        if not isinstance(decision, dict):
            raise ValueError(f"{path}: line {number} must be a JSON object")
        errors = decision_errors(decision)
        if errors:
            raise ValueError(f"{path}: line {number}: {errors[0]}")
        decisions.append(decision)
    return decisions


def append_decision(path: Path, decision: dict) -> None:
    """Append one validated decision. Never rewrites or deletes existing lines."""

    errors = decision_errors(decision)
    if errors:
        raise ValueError("invalid review decision:\n" + "\n".join(errors))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(decision, ensure_ascii=False) + "\n")


def latest_by_record(decisions: list[dict]) -> dict[str, dict]:
    """Latest decision per record; earlier ones stay available as history."""

    latest: dict[str, dict] = {}
    for decision in decisions:
        record_id = decision.get("record_id")
        if isinstance(record_id, str):
            latest[record_id] = decision
    return latest


def ledger_digest(directory: Path) -> str | None:
    path = Path(directory) / LEDGER_FILE
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
