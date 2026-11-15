"""Apply the guarded language layer to an already rule-built recommendation."""

from __future__ import annotations

from ..recommend.validation import allowed_numbers
from .service import PROMPT_VERSION, ReasonWriter
from .summary import build_issue_summary, summary_errors


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
    """Rewrite plan wording in place and return honest per-run counters."""

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
        citation_ids |= set((issue.get("evidence") or {}).get("material_ids") or [])
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
        reason, check, meta = writer.write(summary, item["reason"], item["check"])
        item["reason"], item["check"] = reason, check
        attempts += meta.attempts
        if meta.source == "llm":
            used += 1
        else:
            fallback += 1
            errors.extend(meta.errors)
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
