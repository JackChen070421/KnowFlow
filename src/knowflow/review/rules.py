"""Deterministic review rules for disputed scores (direction 1).

The rules only raise **review clues**. They never judge correctness, never change
an official score, and never read anything outside the canonical tables. A text
comparison is used only for single-value items (``blank`` / ``choice``) and only
answers "is the recorded answer literally the reference answer?" — it is not a
maths grader and it cannot decide that a student was wrong.

Everything here is pure: inputs in, flags out. Persistence lives in ``store``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass

RULE_VERSION = "review-rules-1"
POLICY_NAME = "exclude_flagged_evidence"

#: Clues that are strong enough to keep a record out of conclusions until a
#: human dismisses them. Both are self-contradictions inside the official data.
EXCLUDED_FLAG_CODES: tuple[str, ...] = (
    "answer_matches_key_under_credit",
    "rubric_total_mismatch",
)
#: Audit-only clues: already handled by a documented data-layer rule, so
#: excluding them would throw away evidence instead of protecting it.
AUDIT_ONLY_FLAG_CODES: tuple[str, ...] = ("score_exceeds_max_clamped",)
#: Implemented but off by default: notation variants make it useless in practice
#: ("x=9" vs "9" would flag every correct answer written with a variable name).
DISABLED_FLAG_CODES: tuple[str, ...] = ("answer_key_mismatch_full_credit",)

FLAG_CODES: tuple[str, ...] = EXCLUDED_FLAG_CODES + AUDIT_ONLY_FLAG_CODES + DISABLED_FLAG_CODES

SINGLE_VALUE_FORMATS = {"blank", "choice"}

_TRANSLATE = str.maketrans(
    {
        "×": "*",
        "·": "*",
        "（": "(",
        "）": ")",
        "，": ",",
        "；": ";",
        "：": ":",
    }
)


@dataclass(frozen=True)
class Flag:
    """One rule hit. ``excluded_by_default`` decides whether it isolates evidence."""

    code: str
    reason: str
    excluded_by_default: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "reason": self.reason,
            "excluded_by_default": self.excluded_by_default,
        }


def normalize_answer(value: str | None) -> str:
    """Normalise a short answer for literal comparison only.

    NFKC folds superscripts and full-width forms; whitespace and a trailing
    Chinese/ASCII full stop are dropped. No algebraic rewriting happens here.
    """

    text = unicodedata.normalize("NFKC", value or "")
    text = text.translate(_TRANSLATE)
    text = re.sub(r"\s+", "", text)
    return text.strip("。.")


def _attempted(record: dict) -> bool:
    return str(record.get("attempted", "")).strip().lower() in {"true", "1"}


def _number(value) -> float | None:
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rubric_definition(raw: str | None) -> list[dict]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return [
        {"point_id": str(item["id"]), "label": str(item.get("text", item["id"])), "max_score": float(item.get("points", 0))}
        for item in items
        if isinstance(item, dict) and "id" in item
    ]


def parse_point_scores(raw: str | None) -> dict[str, float] | None:
    """Parse ``rubric_scores_json``; return ``None`` when it is absent/unusable."""

    text = (raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    scores: dict[str, float] = {}
    for key, value in payload.items():
        number = _number(value)
        if number is None:
            return None
        scores[str(key)] = number
    return scores


def official_snapshot(record: dict, material: dict) -> dict:
    """Read-only copy of the official score and rubric points for the report."""

    score = _number(record.get("score"))
    points = parse_point_scores(record.get("rubric_scores_json"))
    definitions = _rubric_definition(material.get("rubric_json"))
    rubric_points = [
        {
            "point_id": item["point_id"],
            "label": item["label"],
            "score": (points or {}).get(item["point_id"], 0.0),
            "max_score": item["max_score"],
        }
        for item in definitions
    ]
    return {
        "score": score,
        "max_score": _number(record.get("max_score")) or 0.0,
        "is_correct": str(record.get("is_correct", "")).strip().lower() in {"true", "1"},
        "rubric_points": rubric_points,
        "rubric_sum": sum(points.values()) if points else None,
    }


def _answer_matches_key(record: dict, material: dict) -> bool:
    answer = normalize_answer(record.get("answer"))
    key = normalize_answer(material.get("answer_key"))
    return bool(answer) and bool(key) and answer == key


def rule_answer_matches_key_under_credit(record: dict, material: dict) -> Flag | None:
    """Answer literally equals the reference answer, yet the item is not full credit."""

    if not _attempted(record):
        return None
    score = _number(record.get("score"))
    max_score = _number(record.get("max_score"))
    if score is None or max_score is None or score >= max_score:
        return None
    if not _answer_matches_key(record, material):
        return None
    single_value = (material.get("item_format") or "") in SINGLE_VALUE_FORMATS
    # On solution items the final-answer field is only one part of the work; a
    # literal match is meaningful only when the whole item scored zero.
    if not single_value and score != 0:
        return None
    if single_value:
        reason = (
            f"作答与参考答案字面一致，但官方只给 {score:g}/{max_score:g} 分；"
            "需人工核对是否漏判，本规则不判定学生答对。"
        )
    else:
        reason = (
            f"解答题最终作答与参考答案字面一致，但官方给 0/{max_score:g} 分；"
            "需人工核对过程分是否误判，本规则不判定学生答对。"
        )
    return Flag("answer_matches_key_under_credit", reason, True)


def rule_rubric_total_mismatch(record: dict, material: dict) -> Flag | None:
    """Official total contradicts the sum of its own rubric point scores."""

    score = _number(record.get("score"))
    if score is None or not _attempted(record):
        return None
    points = parse_point_scores(record.get("rubric_scores_json"))
    if points is None:
        return None
    total = sum(points.values())
    if abs(total - score) <= 1e-9:
        return None
    labels = {item["point_id"]: item["label"] for item in _rubric_definition(material.get("rubric_json"))}
    zero_labels = [
        f"{labels.get(point_id, point_id)}={value:g}"
        for point_id, value in sorted(points.items())
        if abs(value) <= 1e-9
    ]
    detail = f"；0 分评分点：{'、'.join(zero_labels)}" if zero_labels else ""
    return Flag(
        "rubric_total_mismatch",
        f"官方得分 {score:g} 与评分点合计 {total:g} 不一致{detail}。以官方得分为准，但需人工核对评分。",
        True,
    )


def rule_score_exceeds_max_clamped(record: dict, material: dict, anomaly: str) -> Flag | None:
    """The official score was above the maximum and the data layer clamped it."""

    return Flag(
        "score_exceeds_max_clamped",
        f"数据层异常：{anomaly.strip()}；已按评分点合计截断，官方原值只在本机原始数据中。",
        False,
    )


def rule_answer_key_mismatch_full_credit(record: dict, material: dict) -> Flag | None:
    """Disabled by default: a literal mismatch is mostly a notation variant."""

    if not _attempted(record):
        return None
    score = _number(record.get("score"))
    max_score = _number(record.get("max_score"))
    if score is None or max_score is None or score != max_score:
        return None
    if (material.get("item_format") or "") not in SINGLE_VALUE_FORMATS:
        return None
    answer = normalize_answer(record.get("answer"))
    key = normalize_answer(material.get("answer_key"))
    if not answer or not key or answer == key:
        return None
    return Flag(
        "answer_key_mismatch_full_credit",
        "作答与参考答案字面不一致却给满分；写法差异很常见，仅作参考线索，默认不参与隔离。",
        False,
    )


#: Enabled rules, in deterministic order.
RULES: dict[str, Callable[[dict, dict], Flag | None]] = {
    "answer_matches_key_under_credit": rule_answer_matches_key_under_credit,
    "rubric_total_mismatch": rule_rubric_total_mismatch,
}
#: Implemented but not part of a default scan; tests and future opt-in use it.
DISABLED_RULES: dict[str, Callable[[dict, dict], Flag | None]] = {
    "answer_key_mismatch_full_credit": rule_answer_key_mismatch_full_credit,
}


def scan_record(
    record: dict,
    material: dict,
    anomalies: Iterable[str] = (),
) -> list[Flag]:
    """Run every enabled rule on one canonical record."""

    flags = [flag for rule in RULES.values() if (flag := rule(record, material)) is not None]
    for anomaly in anomalies:
        flag = rule_score_exceeds_max_clamped(record, material, anomaly)
        if flag is not None:
            flags.append(flag)
    return flags
