"""Apply the guarded language layer to an already rule-built recommendation."""

from __future__ import annotations

from ..recommend.validation import allowed_numbers
from .contract import material_drift
from .service import PROMPT_VERSION, ReasonWriter
from .summary import build_issue_summary, summary_errors

# 决定层已经判成"巩固"时，文案必须给出巩固动作；只写"补充观测"就是把动作说反了。
CONSOLIDATE_WORDS = ("巩固", "练习", "重做", "学习卡", "复核", "讲解")


def _advice_conflict(item: dict, reason: str) -> str | None:
    """Reject a rewrite that flattens an actionable item into "observe more"."""

    if item.get("activity_type") != "consolidate":
        return None
    if any(word in reason for word in CONSOLIDATE_WORDS):
        return None
    if "补观测" in reason or "补充观测" in reason:
        return "consolidate advice collapsed to observation"
    return None


def _state(profile: dict, knowledge_id: str) -> dict:
    return next(
        (item for item in profile["knowledge_states"] if item["knowledge_id"] == knowledge_id),
        {},
    )


def rewrite_plan(
    rec: dict,
    profile: dict,
    catalog: dict,
    dataset_id: str,
    writer: ReasonWriter,
) -> dict:
    """Rewrite plan wording in place and return honest per-run counters.

    Only ``reason`` is rewritten: the completion ``check`` is a decision (the
    evidence threshold), so it stays deterministic.  The model may cite only the
    materials the plan already assigned; anything else is rejected as drift.
    """

    issues = {issue["issue_id"]: issue for issue in profile.get("issues", [])}
    used = fallback = attempts = 0
    errors: list[str] = []
    for item in rec["plan"]:
        issue = issues.get(item["issue_id"])
        if issue is None:
            fallback += 1
            continue
        state = _state(profile, issue["knowledge_id"])
        citation_ids = {
            profile["student_id"],
            profile["node_id"],
            issue["issue_id"],
            issue["knowledge_id"],
            issue["objective_id"],
        }
        # 决定层已选定材料：语言层只能引用计划里的这几份，不能自行换材料。
        citation_ids |= set(item["material_ids"])
        titles = {
            material_id: catalog["materials"][material_id]["title"]
            for material_id in item["material_ids"]
            if material_id in catalog["materials"]
        }
        summary = build_issue_summary(
            profile=profile,
            issue=issue,
            dataset_id=dataset_id,
            allowed_numbers=allowed_numbers(issue, state),
            allowed_ids=citation_ids,
            material_titles=titles,
        )
        problems = summary_errors(summary)
        if problems:
            fallback += 1
            attempts += 1
            errors.extend(problems[:2])
            continue
        reason, _check, meta = writer.write(summary, item["reason"], item["check"])
        attempts += meta.attempts
        if meta.source != "llm":
            fallback += 1
            errors.extend(meta.errors)
            continue
        drift = material_drift(reason, item)
        if drift:
            fallback += 1
            errors.append(f"materials outside plan: {drift}")
            continue
        conflict = _advice_conflict(item, reason)
        if conflict:
            fallback += 1
            errors.append(conflict)
            continue
        item["reason"] = reason
        # check 是完成门槛（决定层），保持确定性文案，不做改写。
        used += 1
    if used:
        rec["generated_by"] = {
            "provider": writer.provider,
            "model": writer.model,
            "prompt_version": PROMPT_VERSION,
        }
    return {
        "items_used": used,
        "items_fallback": fallback,
        "attempts": attempts,
        "errors": errors[:5],
    }
