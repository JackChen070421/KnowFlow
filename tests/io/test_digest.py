"""Digest: content-free, stable across ids, strict on hashes and version."""

from __future__ import annotations

from knowflow.io.digest import compare, normalize_reason

BASE = {
    "canonical_version": "0.4.0",
    "tables": {"records": {"rows": 9, "sha256": "a" * 64}},
    "total_records": 9,
    "duplicates_removed": 1,
    "records_by_state": {"pending": 4},
    "missing": {"empty_answers": 1},
    "anomaly_counts": {"得分 <n> 超出满分 <n>": 2},
}


def test_reason_is_normalized_to_a_category() -> None:
    """Ids and concrete values must not leak into the digest keys."""

    assert normalize_reason("得分 10 超出满分 1") == "得分 <n> 超出满分 <n>"
    assert normalize_reason("学生 S017 只有 ['N01'] 的记录") == "学生 <id> 只有 [...] 的记录"


def test_identical_digests_have_no_problems() -> None:
    assert compare(BASE, dict(BASE)) == []


def test_row_count_and_hash_mismatch_are_reported() -> None:
    changed = {
        **BASE,
        "tables": {"records": {"rows": 8, "sha256": "b" * 64}},
    }
    problems = compare(BASE, changed)
    assert any("行数" in problem for problem in problems)
    assert any("sha256" in problem for problem in problems)


def test_version_mismatch_is_reported() -> None:
    older = {**BASE, "canonical_version": "0.3.0"}
    problems = compare(BASE, older)
    assert any("canonical_version" in problem for problem in problems)
