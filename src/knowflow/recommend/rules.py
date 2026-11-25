"""Deterministic Task-3 rules: issue → materials → reason/check → sequence.

No LLM and no free-form generation here.  Difficulty and time are explicitly
heuristic: the official materials carry no difficulty or duration, so every plan
item records a rule-derived value and the run README says so.
"""

from __future__ import annotations

from . import path as path_module
from . import probe as probe_module

POLICY_VERSION = "r3-rules-2"
MAX_PLAN_ITEMS = 3
MAX_PROBE_PER_ISSUE = 3
MAX_PROBE_ITEMS = 12
MIN_EVIDENCE = 3
WEAK_STATUSES = {"confirmed_weak", "likely_weak", "mixed_performance"}
GAP_TYPES = {"score_point_gap", "performance_gap"}


def _state(profile: dict, knowledge_id: str) -> dict | None:
    return next(
        (s for s in profile["knowledge_states"] if s["knowledge_id"] == knowledge_id),
        None,
    )


def _planning_view(profile: dict, knowledge_id: str, review: dict | None) -> dict:
    """Evidence view used for planning: disputed records are already excluded.

    The profile keeps the official ledger untouched, so planning reads the
    ``review.usable_*`` numbers instead of the official ones. Without a review
    block this is exactly the official view.
    """

    state = _state(profile, knowledge_id) or {}
    block = state.get("review")
    if not block:
        return {
            "status": state.get("status"),
            "evidence_count": int(state.get("evidence_count") or 0),
            "full_credit": int((state.get("state_counts") or {}).get("observed_correct") or 0),
            "review": None,
        }
    return {
        "status": block["usable_status"],
        "evidence_count": int(block["usable_evidence_count"]),
        "full_credit": int(block["usable_full_credit"]),
        "review": block,
    }


def _effective_type(issue: dict, view: dict) -> str:
    """Downgrade to a probe when the usable evidence no longer supports a claim."""

    if issue["type"] == "insufficient_evidence":
        return "insufficient_evidence"
    if view["review"] and view["status"] == "insufficient_evidence":
        return "insufficient_evidence"
    return issue["type"]


def _planning_issue(issue: dict, view: dict) -> dict:
    kind = _effective_type(issue, view)
    return issue if kind == issue["type"] else {**issue, "type": kind}


def _priority(issue: dict, profile: dict, catalog: dict, review: dict | None = None) -> tuple:
    view = _planning_view(profile, issue["knowledge_id"], review)
    status = view.get("status")
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
        view["evidence_count"],
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


def _prerequisite(issue: dict, profile: dict, catalog: dict, review: dict | None = None) -> dict:
    """Reviewed prerequisites only; draft relations are reported, never obeyed."""

    target = issue["knowledge_id"]
    reviewed = catalog.get("reviewed_prerequisites", {}).get(target, [])
    missing: list[str] = []
    pending: list[str] = []
    for entry in reviewed:
        view = _planning_view(profile, entry["source_knowledge_id"], review)
        if view["status"] in {"confirmed_weak", "likely_weak"}:
            missing.append(entry["source_knowledge_id"])
        elif view["status"] == "insufficient_evidence":
            pending.append(entry["source_knowledge_id"])
    draft_edges = [entry["edge_id"] for entry in catalog.get("pending_prerequisites", {}).get(target, [])]
    draft_edges += catalog.get("pending_node_relations", {}).get(target, [])
    note = "另有先修/关联关系待核验，未参与排序。" if draft_edges else ""
    return {
        "satisfied": not missing,
        "missing_knowledge_ids": sorted(set(missing)),
        "pending_knowledge_ids": sorted(set(pending)),
        "reviewed_edges": [entry["edge_id"] for entry in reviewed],
        "draft_edges": sorted(set(draft_edges)),
        "note": note,
    }


def _dependency_issues(
    issue: dict,
    issues_by_knowledge: dict[str, dict],
    profile: dict,
    catalog: dict,
    review: dict | None,
) -> list[dict]:
    """Issues that must be planned before this one, from reviewed prerequisites."""

    dependencies = []
    for entry in catalog.get("reviewed_prerequisites", {}).get(issue["knowledge_id"], []):
        source = entry["source_knowledge_id"]
        view = _planning_view(profile, source, review)
        if view["status"] not in {"confirmed_weak", "likely_weak", "insufficient_evidence"}:
            continue
        dependency = issues_by_knowledge.get(source)
        if dependency is not None:
            dependencies.append(dependency)
    return dependencies


def _relation_notes(
    issue: dict, catalog: dict, material_ids: list[str], used: set[str]
) -> tuple[list[dict], list[str]]:
    """Comparison material for reviewed confusable pairs; never a diagnosis."""

    notes: list[dict] = []
    extra: list[str] = []
    knowledge_id = issue["knowledge_id"]
    for entry in catalog.get("reviewed_confusable", {}).get(knowledge_id, []):
        partner = entry["partner_knowledge_id"]
        pair = tuple(sorted((knowledge_id, partner)))
        shared = catalog.get("shared_materials", {}).get(pair, [])
        candidate = next(
            (
                material_id
                for material_id in shared
                if material_id not in used
                and material_id not in material_ids
                and material_id in catalog["materials"]
            ),
            None,
        )
        if candidate:
            extra.append(candidate)
            used.add(candidate)
            note = f"与 {partner} 易混：用 {candidate} 做对比辨析。"
        elif any(material_id in material_ids or material_id in used for material_id in shared):
            chosen = next(m for m in shared if m in material_ids or m in used)
            note = f"与 {partner} 易混：本次已包含 {chosen}，可作对比辨析。"
        else:
            note = f"与 {partner} 易混：本机没有明确映射的对比材料，建议教师补充对比观察（非现有资源）。"
        notes.append(
            {
                "relation_type": "confusable_with",
                "edge_id": entry["edge_id"],
                "review_status": entry["review_status"],
                "note": note,
            }
        )
    for entry in catalog.get("pending_confusable", {}).get(knowledge_id, []):
        notes.append(
            {
                "relation_type": "confusable_with",
                "edge_id": entry["edge_id"],
                "review_status": entry["review_status"],
                "note": f"与 {entry['partner_knowledge_id']} 的对照关系待核验，本轮不据此安排材料。",
            }
        )
    for entry in catalog.get("pending_node_confusable", {}).get(knowledge_id, []):
        notes.append(
            {
                "relation_type": "confusable_with",
                "edge_id": entry["edge_id"],
                "review_status": entry["review_status"],
                "note": (
                    f"教材细目 {entry['other_node_id']} 与本知识点存在待核验的对照关系，"
                    "本轮不据此安排材料。"
                ),
            }
        )
    return notes, extra


def _reason(
    issue: dict,
    profile: dict,
    catalog: dict,
    explain_id: str | None,
    assessment_ids: list[str],
    review: dict | None = None,
) -> str:
    view = _planning_view(profile, issue["knowledge_id"], review)
    knowledge = catalog["knowledge"].get(issue["knowledge_id"], {})
    name = knowledge.get("name", issue["knowledge_id"])
    n = view["evidence_count"]
    full = view["full_credit"]
    note = ""
    if view["review"]:
        note = f"（已排除 {len(view['review']['disputed_record_ids'])} 条存疑评分，待人工复核）"
    if issue["type"] == "insufficient_evidence":
        return (
            f"{issue['issue_id']} 显示 {issue['knowledge_id']}「{name}」仅有 {n} 次有效评分，"
            f"低于最低观测数 {MIN_EVIDENCE}；用 {'、'.join(assessment_ids)} 补充观测，"
            f"暂不下“未掌握”结论。{note}"
        )
    criteria = list(dict.fromkeys(item["criterion"] for item in issue.get("rubric_evidence", [])))
    loss = f"，失分集中在「{'、'.join(criteria)}」" if criteria else "，具体错因证据不足"
    lead = f"先用 {explain_id} 重建" if explain_id else "先看原题解析"
    return (
        f"{issue['issue_id']} 显示 {issue['knowledge_id']}「{name}」{n} 次有效评分中 "
        f"{full} 次满分{loss}{note}；{lead}，再用 {'、'.join(assessment_ids)} 核对。"
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


def refresh_item_wording(
    item: dict,
    issue: dict,
    profile: dict,
    catalog: dict,
    review: dict | None = None,
) -> None:
    """Regenerate reason/check after the decision layer changed the materials.

    A teacher's ``replace_materials`` changes the decision, so the language must
    follow.  Called with the final material list; the completion ``check`` stays
    deterministic and only ever cites those materials.
    """

    materials = [m for m in item["material_ids"] if m in catalog["materials"]]
    explain_id = next(
        (
            m
            for m in materials
            if catalog["materials"][m]["material_type"] == "explain"
        ),
        None,
    )
    assessments = [
        m
        for m in materials
        if catalog["materials"][m]["material_type"] == "assessment"
    ]
    view = _planning_view(profile, issue["knowledge_id"], review)
    planning = _planning_issue(issue, view)
    if not assessments:
        names = "、".join(catalog["materials"][m].get("title", m) for m in materials)
        item["reason"] = (
            f"{issue['issue_id']} 对应 {issue['knowledge_id']}；"
            f"按计划先看 {names or '相关材料'}，再按要求自检。"
        )
        item["check"] = "完成计划材料并自检。"
        return
    item["reason"] = _reason(planning, profile, catalog, explain_id, assessments, review)
    item["check"] = _check(planning, catalog, explain_id, assessments)


def _plan_item(
    seq: int,
    issue: dict,
    profile: dict,
    catalog: dict,
    node_available: set[str],
    attempted: set[str],
    used: set[str],
    review: dict | None = None,
    assessments: list[str] | None = None,
) -> dict | None:
    view = _planning_view(profile, issue["knowledge_id"], review)
    planning = _planning_issue(issue, view)
    if assessments is None:
        assessments = _select_assessments(planning, catalog, node_available, attempted, used)
    if not assessments:
        return None
    explain_id = None
    if planning["type"] != "insufficient_evidence":
        explain_id = _explain(catalog, issue["knowledge_id"], used | set(assessments))
    material_ids = ([explain_id] if explain_id else []) + assessments
    primary = assessments[0]
    if primary not in material_ids:
        return None
    for material_id in material_ids:
        if material_id not in catalog["materials"]:
            return None
    notes, extra = _relation_notes(issue, catalog, material_ids, used)
    material_ids = material_ids + extra
    used.update(material_ids)
    activity_type = "probe" if planning["type"] == "insufficient_evidence" else "consolidate"
    activity = (
        "补充观测：未作答题"
        if activity_type == "probe"
        else "看学习卡 + 同评分点练习"
        if explain_id
        else "同评分点练习"
    )
    item = {
        "seq": seq,
        "issue_id": issue["issue_id"],
        "activity": activity,
        "activity_type": activity_type,
        "material_ids": material_ids,
        "primary_material_id": primary,
        "objective_id": issue["objective_id"],
        "knowledge_ids": [issue["knowledge_id"]],
        "reason": _reason(planning, profile, catalog, explain_id, assessments, review),
        "check": _check(planning, catalog, explain_id, assessments),
        "est_minutes": _minutes(material_ids, catalog),
        "difficulty": _difficulty(issue, assessments, catalog),
        "prerequisite_check": _prerequisite(issue, profile, catalog, review),
        "teacher_adjustable": True,
    }
    if notes:
        item["relation_notes"] = notes
    if review is not None:
        item["basis_records"] = sorted({point["record_id"] for point in planning["rubric_evidence"]})
        if view["review"]:
            item["review_flags"] = [
                {"record_id": flag["record_id"], "review_status": flag["review_status"]}
                for flag in view["review"]["flags"]
            ]
    return item


def _finalize_plan(
    plan: list[dict],
    issues_by_id: dict[str, dict],
    student_id: str,
    node_id: str,
    version: int,
    catalog: dict,
    carried_ids: set[str],
) -> None:
    """Assign stable path IDs, statuses, completion conditions and dependency links."""

    for index, item in enumerate(plan, 1):
        item["seq"] = index
        if item["issue_id"] in carried_ids:
            item["status"] = "in_progress"
        elif item.get("plan_item_id"):
            item.setdefault("plan_version", version)
            item.setdefault("status", "planned")
        else:
            item["status"] = "planned"
            item["plan_item_id"] = path_module.plan_item_id(
                student_id, node_id, version, item["knowledge_ids"][0]
            )
            item["plan_version"] = version
    for index, item in enumerate(plan):
        issue = issues_by_id.get(item["issue_id"], {})
        criteria = [
            point["criterion"] for point in issue.get("rubric_evidence", []) if point.get("criterion")
        ]
        item["completion_condition"] = path_module.completion_condition(
            item["activity_type"], item["material_ids"], criteria
        )
        knowledge_id = item["knowledge_ids"][0]
        earlier = {
            other["knowledge_ids"][0]: other["plan_item_id"] for other in plan[:index]
        }
        reviewed = {
            entry["source_knowledge_id"]
            for entry in catalog.get("reviewed_prerequisites", {}).get(knowledge_id, [])
        }
        item["prerequisite_item_ids"] = [
            earlier[source] for source in sorted(reviewed) if source in earlier
        ]
        check = item["prerequisite_check"]
        linked = set(check.get("missing_knowledge_ids") or []) | set(
            check.get("pending_knowledge_ids") or []
        )
        linked |= reviewed & set(earlier)
        item["prerequisite_knowledge_ids"] = sorted(linked)


def _is_gap(issue: dict, profile: dict, review: dict | None = None) -> bool:
    view = _planning_view(profile, issue["knowledge_id"], review)
    if view["review"] and view["status"] == "insufficient_evidence":
        return False
    if issue["type"] in GAP_TYPES:
        return True
    return view.get("status") in {"confirmed_weak", "likely_weak"}


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


def _review_required(
    issues: list[dict], profile: dict, review: dict | None
) -> list[dict]:
    """Issues whose usable evidence cannot support a consolidation plan."""

    if review is None:
        return []
    required = []
    for issue in issues:
        view = _planning_view(profile, issue["knowledge_id"], review)
        block = view["review"]
        if not block:
            continue
        only_disputed = not issue["rubric_evidence"] and bool(
            issue.get("disputed_rubric_evidence")
        )
        too_little = view["status"] == "insufficient_evidence"
        if not (only_disputed or too_little):
            continue
        count = len(block["disputed_record_ids"])
        reason = (
            f"{count} 条评分存疑，已排除出结论；先人工复核原始评分，"
            "本轮只安排补充观测，不据此安排巩固。"
        )
        required.append(
            {
                "issue_id": issue["issue_id"],
                "record_ids": sorted(block["disputed_record_ids"]),
                "reason": reason,
            }
        )
    return required


def _attach_review(result: dict, review: dict | None, required: list[dict] | None = None) -> dict:
    states = result.pop("_states", [])
    if review is None:
        return result
    excluded = sorted(
        {
            record_id
            for state in states
            for record_id in (state.get("review") or {}).get("disputed_record_ids", [])
        }
    )
    result["review_context"] = {
        "applied": True,
        "policy": review["policy"],
        "report_sha256": review["report_sha256"],
        "excluded_record_ids": excluded,
        "note": "存疑评分已排除出结论；官方分数未修改。",
    }
    result["review_required"] = required or []
    return result


def recommend_profile(
    profile: dict,
    catalog: dict,
    node_available: set[str],
    records: list[dict],
    generated_at: str,
    profile_sha256: str,
    review: dict | None = None,
    path: dict | None = None,
) -> dict:
    student_id, node_id = profile["student_id"], profile["node_id"]
    attempted = {
        record["material_id"]
        for record in records
        if record["student_id"] == student_id
        and record["node_id"] == node_id
        and record.get("attempted")
    }
    pending = {
        record["material_id"]
        for record in records
        if record["student_id"] == student_id
        and record["node_id"] == node_id
        and record.get("attempted")
        and record.get("score") is None
    }
    scored = {
        record["material_id"]
        for record in records
        if record["student_id"] == student_id
        and record["node_id"] == node_id
        and record.get("score") is not None
    }
    disputed = {
        record["material_id"]
        for record in records
        if record["student_id"] == student_id
        and record["node_id"] == node_id
        and review
        and review["index"].get(record["record_id"], {}).get("disputed")
    }
    version = int((path or {}).get("version") or 1)
    completed = list((path or {}).get("completed") or [])
    started = list((path or {}).get("started") or [])
    locked = list((path or {}).get("locked") or [])
    removed = list((path or {}).get("removed") or [])
    history = list((path or {}).get("history") or [])
    weights = (path or {}).get("probe_weights") or probe_module.ProbeWeights()
    reserved = {item["knowledge_ids"][0] for item in completed}
    carried_ids = {event["issue_id"] for event in started}
    reserved |= {event["knowledge_id"] for event in started}
    reserved |= {entry["knowledge_id"] for entry in locked}
    reserved |= {entry["knowledge_id"] for entry in removed if entry.get("knowledge_id")}
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
    states = profile["knowledge_states"]
    if not profile["coverage"]["scope_known"]:
        result = _attach_review(
            {
                **base,
                "plan": [],
                "probe_plan": {
                    "needed": False,
                    "items": [],
                    "purpose": _probe_purpose(profile, [], [], bool(profile.get("issues"))),
                },
                "deferred": [],
                "_states": states,
            },
            review,
        )
        return _attach_path(result, path, student_id, node_id, version, history, len(completed), 0, 0)

    issues = [issue for issue in profile.get("issues", []) if issue["type"] != "not_applicable"]
    issues.sort(key=lambda issue: _priority(issue, profile, catalog, review))
    issues_by_id = {issue["issue_id"]: issue for issue in issues}
    issues_by_knowledge = {issue["knowledge_id"]: issue for issue in issues}

    plan: list[dict] = []
    used: set[str] = set()
    unmatched = 0
    for event in sorted(started, key=lambda item: (item["plan_version"], item["seq"])):
        issue = issues_by_id.get(event["issue_id"])
        if issue is None:
            unmatched += 1
            continue
        item = _plan_item(
            0, issue, profile, catalog, node_available, attempted, used, review
        )
        if item is None:
            unmatched += 1
            continue
        item["plan_item_id"] = event["plan_item_id"]
        item["plan_version"] = event["plan_version"]
        plan.append(item)

    locked_issues = 0
    for entry in sorted(locked, key=lambda item: (item.get("seq", 1), item["plan_item_id"])):
        issue = issues_by_id.get(entry.get("issue_id")) or issues_by_knowledge.get(
            entry.get("knowledge_id")
        )
        if issue is None:
            unmatched += 1
            continue
        item = _plan_item(
            0, issue, profile, catalog, node_available, attempted, used, review
        )
        if item is None:
            unmatched += 1
            continue
        item["plan_item_id"] = entry["plan_item_id"]
        item["plan_version"] = int(entry.get("plan_version") or version)
        item["status"] = "planned"
        item["teacher_locked"] = True
        if entry.get("material_ids"):
            materials = [mid for mid in entry["material_ids"] if mid in catalog["materials"]]
            if materials:
                item["material_ids"] = materials
                item["primary_material_id"] = materials[0]
        if entry.get("est_minutes") is not None:
            item["est_minutes"] = int(entry["est_minutes"])
        if entry.get("difficulty") is not None:
            item["difficulty"] = int(entry["difficulty"])
        plan.append(item)
        locked_issues += 1

    fresh_issues = [issue for issue in issues if issue["knowledge_id"] not in reserved]
    gaps = []
    probes = []
    for issue in fresh_issues:
        view = _planning_view(profile, issue["knowledge_id"], review)
        if _effective_type(issue, view) == "insufficient_evidence":
            probes.append(issue)
        elif _is_gap(issue, profile, review):
            gaps.append(issue)
    base_selected = (gaps[:2] + probes[:1]) if gaps else probes[:MAX_PLAN_ITEMS]
    ordered: list[dict] = []
    seen_ids: set[str] = set()
    for issue in base_selected:
        for dependency in _dependency_issues(
            issue, issues_by_knowledge, profile, catalog, review
        ):
            if dependency["knowledge_id"] in reserved:
                continue
            if dependency["issue_id"] not in seen_ids:
                ordered.append(dependency)
                seen_ids.add(dependency["issue_id"])
        if issue["issue_id"] not in seen_ids:
            ordered.append(issue)
            seen_ids.add(issue["issue_id"])
    budget_left = max(0, MAX_PLAN_ITEMS - len(plan))
    selected = ordered[:budget_left]
    deferred = [
        {
            "issue_id": issue["issue_id"],
            "reason": "计划预算为 3 项；已开始/已完成/教师锁定的计划项占用预算，本轮暂不列入。"
            if plan
            else "计划预算为 3 项；先修巩固/补充观测优先，本轮暂不列入，下一轮重新规划。",
        }
        for issue in ordered[budget_left:]
    ]
    for entry in removed:
        deferred.append(
            {
                "issue_id": entry.get("issue_id"),
                "knowledge_id": entry.get("knowledge_id"),
                "reason": f"教师移除：{entry.get('reason', '')}（事件 {entry.get('event_id')}）",
            }
        )

    unresolved = {issue["knowledge_id"] for issue in issues}
    probe_candidates: dict[str, list[dict]] = {}
    selected_probe_materials: list[str] = []
    for issue in selected:
        view = _planning_view(profile, issue["knowledge_id"], review)
        assessments = None
        if _effective_type(issue, view) == "insufficient_evidence":
            assessments, candidates = probe_module.select_probes(
                issue,
                profile=profile,
                catalog=catalog,
                node_available=node_available,
                attempted=attempted,
                pending=pending,
                scored=scored,
                disputed=disputed,
                unresolved_knowledge=unresolved,
                selected=selected_probe_materials,
                weights=weights,
                limit=MAX_PROBE_PER_ISSUE,
            )
            probe_candidates[issue["issue_id"]] = candidates
            selected_probe_materials.extend(assessments)
        item = _plan_item(
            len(plan) + 1,
            issue,
            profile,
            catalog,
            node_available,
            attempted,
            used,
            review,
            assessments,
        )
        if item:
            plan.append(item)
    _finalize_plan(plan, issues_by_id, student_id, node_id, version, catalog, carried_ids)
    planned_ids = {item["issue_id"] for item in plan}
    for issue in selected:
        if issue["issue_id"] not in planned_ids:
            deferred.append(
                {
                    "issue_id": issue["issue_id"],
                    "reason": "该知识点在本节点没有可用材料，无法生成计划项。",
                }
            )

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
    probe_plan = {
        "needed": bool(probe_items),
        "items": probe_items,
        "purpose": _probe_purpose(profile, probe_items, probe_knowledge, bool(probes)),
    }
    merged = {}
    for issue_id, candidates in probe_candidates.items():
        if issue_id not in planned_ids:
            continue
        for candidate in candidates:
            current = merged.get(candidate["material_id"])
            if current is None or candidate["total"] > current["total"]:
                merged[candidate["material_id"]] = candidate
    if merged:
        probe_plan["scoring"] = probe_module.scoring_block(
            weights,
            sorted(merged.values(), key=lambda item: (-item["total"], item["material_id"])),
            must_include=set(probe_items),
        )
    result = _attach_review(
        {
            **base,
            "plan": plan,
            "probe_plan": probe_plan,
            "deferred": deferred,
            "_states": states,
        },
        review,
        _review_required(issues, profile, review),
    )
    return _attach_path(
        result,
        path,
        student_id,
        node_id,
        version,
        history,
        len(completed),
        len(plan) - len(selected),
        unmatched,
    )


def _attach_path(
    result: dict,
    path: dict | None,
    student_id: str,
    node_id: str,
    version: int,
    history: list[dict],
    completed_items: int,
    in_progress_items: int,
    unmatched_events: int,
) -> dict:
    path = path or {}
    result["plan_id"] = path_module.plan_id(student_id, node_id, version)
    result["plan_version"] = version
    result["history"] = history
    result["progress"] = {
        "events_applied": len(path.get("events") or []),
        "completed_items": completed_items,
        "in_progress_items": max(0, in_progress_items),
        "unmatched_events": unmatched_events,
        "source": str(path.get("source") or "none"),
    }
    return result
