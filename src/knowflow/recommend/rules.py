"""Deterministic Task-3 rules: issue → materials → reason/check → sequence.

No LLM and no free-form generation here.  Difficulty and time are explicitly
heuristic: the official materials carry no difficulty or duration, so every plan
item records a rule-derived value and the run README says so.
"""

from __future__ import annotations

POLICY_VERSION = "r3-rules-1"
MAX_PLAN_ITEMS = 3
MAX_PROBE_ITEMS = 12
MIN_EVIDENCE = 3
WEAK_STATUSES = {"confirmed_weak", "likely_weak", "mixed_performance"}
GAP_TYPES = {"score_point_gap", "performance_gap"}


def _state(profile: dict, knowledge_id: str) -> dict | None:
    return next(
        (s for s in profile["knowledge_states"] if s["knowledge_id"] == knowledge_id),
        None,
    )


def _priority(issue: dict, profile: dict, catalog: dict) -> tuple:
    state = _state(profile, issue["knowledge_id"]) or {}
    status = state.get("status")
    if status in {"confirmed_weak", "likely_weak"}:
        rank = 0
    elif issue["type"] == "score_point_gap":
        rank = 1
    elif issue["type"] == "performance_gap":
        rank = 2
    else:
        rank = 3
    knowledge = catalog["knowledge"].get(issue["knowledge_id"], {})
    objective_order = catalog["objective_order"].get(issue["objective_id"], 99)
    return (
        rank,
        int(state.get("evidence_count") or 0),
        objective_order,
        int(knowledge.get("sort_order") or 0),
        issue["issue_id"],
    )


def _assessment_pool(catalog: dict, knowledge_id: str, node_available: set[str]) -> list[str]:
    candidates = [
        material_id
        for material_id in catalog["by_knowledge"].get(knowledge_id, [])
        if catalog["materials"][material_id]["material_type"] == "assessment"
    ]
    return sorted(material_id for material_id in candidates if material_id in node_available)


def _unattempted(catalog: dict, knowledge_id: str, node_available: set[str], attempted: set[str]) -> list[str]:
    return [
        material_id
        for material_id in _assessment_pool(catalog, knowledge_id, node_available)
        if material_id not in attempted
    ]


def _matching_criteria(catalog: dict, material_id: str, criteria: set[str]) -> int:
    return sum(1 for point in catalog["materials"][material_id]["rubric"] if point["text"] in criteria)


def _select_assessments(
    issue: dict,
    catalog: dict,
    node_available: set[str],
    attempted: set[str],
    used: set[str],
) -> list[str]:
    """Choose redo/new practice for a gap, or unattempted items for a probe."""

    knowledge_id = issue["knowledge_id"]
    pool = [
        material_id
        for material_id in _assessment_pool(catalog, knowledge_id, node_available)
        if material_id not in used
    ]
    if not pool:
        return []

    if issue["type"] == "insufficient_evidence":
        return _unattempted(catalog, knowledge_id, node_available, attempted)[:3]

    criteria = {item["criterion"] for item in issue.get("rubric_evidence", [])}
    matching = [material_id for material_id in pool if _matching_criteria(catalog, material_id, criteria)]
    redo = next(
        (material_id for material_id in matching if material_id in attempted),
        matching[0] if matching else None,
    )
    fresh = next(
        (
            material_id
            for material_id in pool
            if material_id not in attempted and material_id != redo
        ),
        None,
    )
    selected = [material_id for material_id in (redo, fresh) if material_id]
    if not selected:
        selected = [pool[0]]
    return selected


def _explain(catalog: dict, knowledge_id: str, used: set[str]) -> str | None:
    for material_id in catalog["explain_by_knowledge"].get(knowledge_id, []):
        if material_id not in used:
            return material_id
    return None


def _difficulty(issue: dict, material_ids: list[str], catalog: dict) -> int:
    cognitive = catalog["knowledge"].get(issue["knowledge_id"], {}).get("cognitive_type")
    base = {"procedure": 2, "application": 3, "understanding": 2, "concept": 2}.get(cognitive, 3)
    if any(
        catalog["materials"][material_id]["item_format"] == "solution"
        for material_id in material_ids
        if catalog["materials"][material_id]["material_type"] == "assessment"
    ):
        base += 1
    return max(1, min(5, base))


def _minutes(material_ids: list[str], catalog: dict) -> int:
    total = 0
    for material_id in material_ids:
        material = catalog["materials"][material_id]
        source_minutes = material.get("est_minutes")
        if source_minutes not in (None, ""):
            total += int(source_minutes)
        elif material["material_type"] in {"explain", "reference"}:
            total += 5
        elif material["material_type"] == "assessment":
            total += {"choice": 2, "blank": 3, "solution": 8}.get(material["item_format"], 3)
    return max(1, min(120, total + 2))


def _prerequisite(issue: dict, profile: dict, catalog: dict) -> dict:
    missing = []
    for prerequisite in catalog["prerequisites"].get(issue["knowledge_id"], []):
        state = _state(profile, prerequisite) or {}
        if state.get("status") in WEAK_STATUSES | {"insufficient_evidence"}:
            missing.append(prerequisite)
    return {"satisfied": not missing, "missing_knowledge_ids": missing}


def _reason(
    issue: dict,
    profile: dict,
    catalog: dict,
    explain_id: str | None,
    assessment_ids: list[str],
) -> str:
    state = _state(profile, issue["knowledge_id"]) or {}
    knowledge = catalog["knowledge"].get(issue["knowledge_id"], {})
    name = knowledge.get("name", issue["knowledge_id"])
    n = int(state.get("evidence_count") or 0)
    full = int((state.get("state_counts") or {}).get("observed_correct") or 0)
    if issue["type"] == "insufficient_evidence":
        return (
            f"{issue['issue_id']} 显示 {issue['knowledge_id']}「{name}」仅有 {n} 次有效评分，"
            f"低于最低观测数 {MIN_EVIDENCE}；用 {'、'.join(assessment_ids)} 补充观测，"
            "暂不下“未掌握”结论。"
        )
    criteria = list(dict.fromkeys(item["criterion"] for item in issue.get("rubric_evidence", [])))
    loss = f"，失分集中在「{'、'.join(criteria)}」" if criteria else "，具体错因证据不足"
    lead = f"先用 {explain_id} 重建" if explain_id else "先看原题解析"
    return (
        f"{issue['issue_id']} 显示 {issue['knowledge_id']}「{name}」{n} 次有效评分中 "
        f"{full} 次满分{loss}；{lead}，再用 {'、'.join(assessment_ids)} 核对。"
    )


def _check(
    issue: dict,
    catalog: dict,
    explain_id: str | None,
    assessment_ids: list[str],
) -> str:
    if issue["type"] == "insufficient_evidence":
        return (
            f"完成 {'、'.join(assessment_ids)} 并获得评分；{issue['knowledge_id']} "
            f"有效评分达到 {MIN_EVIDENCE} 次后复核状态。"
        )
    criteria = list(dict.fromkeys(item["criterion"] for item in issue.get("rubric_evidence", [])))
    lead = f"完成 {explain_id} 学习卡 + " if explain_id else "完成 "
    if criteria:
        return (
            f"{lead}{'、'.join(assessment_ids)}；{assessment_ids[0]} 的「{criteria[0]}」"
            "评分点得满分，且至少 1 题全对。"
        )
    return f"{lead}{'、'.join(assessment_ids)}，至少 2 题全对；否则回到讲解材料重看。"


def _plan_item(
    seq: int,
    issue: dict,
    profile: dict,
    catalog: dict,
    node_available: set[str],
    attempted: set[str],
    used: set[str],
) -> dict | None:
    assessments = _select_assessments(issue, catalog, node_available, attempted, used)
    if not assessments:
        return None
    explain_id = None
    if issue["type"] != "insufficient_evidence":
        explain_id = _explain(catalog, issue["knowledge_id"], used | set(assessments))
    material_ids = ([explain_id] if explain_id else []) + assessments
    primary = assessments[0]
    if primary not in material_ids:
        return None
    for material_id in material_ids:
        if material_id not in catalog["materials"]:
            return None
    used.update(material_ids)
    activity_type = "probe" if issue["type"] == "insufficient_evidence" else "consolidate"
    activity = (
        "补充观测：未作答题"
        if activity_type == "probe"
        else "看学习卡 + 同评分点练习"
        if explain_id
        else "同评分点练习"
    )
    return {
        "seq": seq,
        "issue_id": issue["issue_id"],
        "activity": activity,
        "activity_type": activity_type,
        "material_ids": material_ids,
        "primary_material_id": primary,
        "objective_id": issue["objective_id"],
        "knowledge_ids": [issue["knowledge_id"]],
        "reason": _reason(issue, profile, catalog, explain_id, assessments),
        "check": _check(issue, catalog, explain_id, assessments),
        "est_minutes": _minutes(material_ids, catalog),
        "difficulty": _difficulty(issue, assessments, catalog),
        "prerequisite_check": _prerequisite(issue, profile, catalog),
        "teacher_adjustable": True,
    }


def _is_gap(issue: dict, profile: dict) -> bool:
    if issue["type"] in GAP_TYPES:
        return True
    state = _state(profile, issue["knowledge_id"]) or {}
    return state.get("status") in {"confirmed_weak", "likely_weak"}


def _probe_purpose(
    profile: dict,
    probe_items: list[str],
    probe_knowledge: list[str],
    had_probe_issue: bool = False,
) -> str:
    if not profile["coverage"]["scope_known"]:
        return "该生在该节点没有参与记录，先确认参与范围，不据此判断未掌握。"
    if not probe_items:
        if had_probe_issue:
            return "证据不足；本轮计划已满或该知识点没有可用未作答题，建议下一轮补充观测。"
        return "现有观测已达到判断门槛，无需补充观测。"
    return (
        f"{'、'.join(probe_knowledge)} 证据不足；用 {'、'.join(probe_items)} "
        f"补充观测，达到至少 {MIN_EVIDENCE} 次有效评分再判断。"
    )


def recommend_profile(
    profile: dict,
    catalog: dict,
    node_available: set[str],
    records: list[dict],
    generated_at: str,
    profile_sha256: str,
) -> dict:
    student_id, node_id = profile["student_id"], profile["node_id"]
    attempted = {
        record["material_id"]
        for record in records
        if record["student_id"] == student_id
        and record["node_id"] == node_id
        and record.get("attempted")
    }
    base = {
        "schema_version": "1.1.0",
        "student_id": student_id,
        "node_id": node_id,
        "generated_at": generated_at,
        "source": {
            "dataset_id": profile["source_dataset"],
            "profile_generated_at": profile["generated_at"],
            "profile_sha256": profile_sha256,
        },
        "generated_by": {
            "provider": "knowflow-rules",
            "model": "template-v1",
            "prompt_version": POLICY_VERSION,
        },
    }
    if not profile["coverage"]["scope_known"]:
        return {
            **base,
            "plan": [],
            "probe_plan": {
                "needed": False,
                "items": [],
                "purpose": _probe_purpose(profile, [], [], bool(profile.get("issues"))),
            },
        }

    issues = [issue for issue in profile.get("issues", []) if issue["type"] != "not_applicable"]
    issues.sort(key=lambda issue: _priority(issue, profile, catalog))
    gaps = [issue for issue in issues if _is_gap(issue, profile)]
    probes = [issue for issue in issues if issue["type"] == "insufficient_evidence"]
    selected = (gaps[:2] + probes[:1]) if gaps else probes[:MAX_PLAN_ITEMS]

    plan = []
    used: set[str] = set()
    for issue in selected:
        item = _plan_item(
            len(plan) + 1,
            issue,
            profile,
            catalog,
            node_available,
            attempted,
            used,
        )
        if item:
            plan.append(item)

    probe_items = []
    probe_knowledge = []
    for item in plan:
        if item["activity_type"] != "probe":
            continue
        for material_id in item["material_ids"]:
            if material_id not in probe_items:
                probe_items.append(material_id)
        if item["knowledge_ids"][0] not in probe_knowledge:
            probe_knowledge.append(item["knowledge_ids"][0])
    probe_items = probe_items[:MAX_PROBE_ITEMS]
    return {
        **base,
        "plan": plan,
        "probe_plan": {
            "needed": bool(probe_items),
            "items": probe_items,
            "purpose": _probe_purpose(profile, probe_items, probe_knowledge, bool(probes)),
        },
    }
