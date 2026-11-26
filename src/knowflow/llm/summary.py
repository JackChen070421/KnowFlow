"""Build ``llm_summary``: the only object allowed to leave this machine.

The summary carries aggregated counts, ratios, statuses and error-pattern labels
plus the exact number/ID whitelist the model may use.  It never carries raw
answers, free text, names or record content.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.contracts import build_registry, repo_root
from knowflow.diagnosis.evidence import evidence_action

from .contract import MUST_NOT_INFER

STATUS_VALUES = {
    "confirmed_weak",
    "likely_weak",
    "insufficient_evidence",
    "unobserved",
    "likely_mastered",
    "confirmed_mastered",
    "mixed_performance",
}


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    root = repo_root()
    schema = json.loads(
        (root / "schemas" / "llm" / "llm_summary.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        schema, registry=build_registry(root), format_checker=FormatChecker()
    )


def summary_errors(summary: dict) -> list[str]:
    """Return schema violations for one ``llm_summary`` object."""

    return [
        f"llm_summary:{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in _validator().iter_errors(summary)
    ]


def _confidence(state: dict) -> str:
    value = state.get("confidence")
    return value if value in {"low", "medium", "high"} else "low"


def _status(state: dict) -> str:
    value = state.get("status")
    if value in STATUS_VALUES:
        return value
    # ``not_applicable`` never reaches a plan item; fail closed to "unknown".
    return "insufficient_evidence"


def _error_patterns(issue: dict) -> list[dict]:
    """Group rubric criteria into labels without inventing new text."""

    grouped: dict[str, dict[str, Any]] = {}
    for point in issue.get("rubric_evidence") or []:
        label = str(point.get("criterion") or "").strip()
        if not label:
            continue
        entry = grouped.setdefault(label, {"label": label, "count": 0, "material_ids": set()})
        entry["count"] += 1
        material_id = point.get("material_id")
        if material_id:
            entry["material_ids"].add(str(material_id))
    patterns = [
        {
            "label": entry["label"],
            "count": int(entry["count"]),
            "material_ids": sorted(entry["material_ids"]),
        }
        for entry in grouped.values()
    ]
    patterns.sort(key=lambda pattern: (-pattern["count"], pattern["label"]))
    if not patterns:
        evidence = issue.get("evidence") or {}
        patterns = [
            {
                "label": "有效评分不足"
                if issue.get("type") == "insufficient_evidence"
                else "评分点失分",
                "count": len(evidence.get("records") or []),
                "material_ids": sorted(set(evidence.get("material_ids") or [])),
            }
        ]
    return patterns[:4]


def build_issue_summary(
    *,
    profile: dict,
    issue: dict,
    dataset_id: str,
    allowed_numbers: set[float],
    allowed_ids: set[str],
    material_titles: dict[str, str] | None = None,
    audience: str = "teacher",
) -> dict:
    """Build one schema-valid summary for a single issue.

    ``allowed_numbers`` must be the same set the deterministic validator accepts
    (see ``knowflow.recommend.validation.allowed_numbers``), so a model paragraph
    that passes the guard also passes ``verify-recommend``.
    """

    state = next(
        (
            item
            for item in profile["knowledge_states"]
            if item["knowledge_id"] == issue["knowledge_id"]
        ),
        {},
    )
    counts = state.get("state_counts") or {}
    coverage = profile.get("coverage") or {}
    ratio = coverage.get("ratio")
    facts = {
        "dataset_id": dataset_id,
        "observed_records": int(state.get("evidence_count") or 0),
        "correct": int(counts.get("observed_correct") or 0),
        "wrong": int(counts.get("observed_wrong") or 0),
        "not_attempted": int(counts.get("assigned_not_attempted") or 0),
        "mastery": state.get("mastery"),
        "confidence": _confidence(state),
        "evidence_count": int(state.get("evidence_count") or 0),
        "status": _status(state),
        # 动作和状态分开：状态说“能不能下结论”，动作说“下一步做什么”。
        "evidence_action": evidence_action(state),
        "coverage_ratio": float(ratio) if isinstance(ratio, (int, float)) else 0.0,
        "error_patterns": _error_patterns(issue),
    }
    citation_ids = {str(value) for value in allowed_ids if value}
    if material_titles:
        citation_ids |= set(material_titles)
    return {
        "summary_id": f"LS-{issue['issue_id']}",
        "scope": "issue",
        "ref_id": issue["issue_id"],
        "locale": "zh-CN",
        "audience": audience,
        "facts": facts,
        "constraints": {
            "must_not_infer": list(MUST_NOT_INFER),
            "allowed_numbers": sorted({float(value) for value in allowed_numbers}),
            "allowed_ids": sorted(citation_ids),
        },
    }
