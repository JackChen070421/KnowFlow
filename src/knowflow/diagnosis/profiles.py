"""Student and class views; no original answer text or LLM is needed."""

from collections import Counter, defaultdict
from statistics import mean

from knowflow.cleaning import evidence_state
from knowflow.cleaning.records import STATES
from knowflow.diagnosis.mastery import DiagnosisConfig, estimate_mastery

MASTERED = {"likely_mastered", "confirmed_mastered"}
WEAK = {"likely_weak", "confirmed_weak"}


def optional_mean(values):
    xs = [x for x in values if x is not None]
    return round(mean(xs), 6) if xs else None


def build_student_profile(bundle: dict, student: dict, node: dict, config: DiagnosisConfig) -> dict:
    sid, node_id = student["student_id"], node["node_id"]
    known_scope = {"student_id": sid, "node_id": node_id} in bundle["participation"]
    applicable = set(node["material_ids"]) if known_scope else set()
    records = [r for r in bundle["records"] if r["student_id"] == sid and r["node_id"] == node_id]
    by_material = {r["material_id"]: r for r in records}
    states = []
    for knowledge in bundle["knowledge"]:
        kid = knowledge["knowledge_id"]
        items = {
            m["material_id"] for m in bundle["materials"] if kid in m["knowledge_ids"]
        } & applicable
        selected = [by_material[mid] for mid in sorted(items) if mid in by_material]
        counts = Counter(evidence_state(r) for r in selected)
        counts["unobserved"] = len(items) - len(selected)
        graded = [r for r in selected if r["attempted"] and r["score"] is not None]
        estimate = estimate_mastery(counts["observed_correct"], len(graded), config)
        if not known_scope:
            estimate["status_reason"] = "该学生没有此测验节点的参与记录，适用范围待确认。"
        elif not items:
            estimate.update(
                status="not_applicable",
                status_reason="此节点没有该知识点的可测题目；不据此判断学生未掌握。",
            )
        states.append(
            {
                "knowledge_id": kid,
                "objective_id": knowledge["objective_id"],
                **estimate,
                "evidence_count": len(graded),
                "state_counts": {s: counts[s] for s in STATES},
                "evidence": sorted(r["record_id"] for r in graded),
                "applicable_items": len(items),
                "performance": {
                    "full_credit": counts["observed_correct"],
                    "partial_credit": sum(0 < r["score"] < r["max_score"] for r in graded),
                    "zero_credit": sum(r["score"] == 0 for r in graded),
                    "mean_score_ratio": optional_mean(r["score"] / r["max_score"] for r in graded),
                },
            }
        )
    objectives = _objectives(states)
    issues = _issues(sid, states, records)
    lists = {"strengths": [], "needs_consolidation": [], "needs_observation": []}
    for state in states:
        status = state["status"]
        if status == "not_applicable":
            continue
        key = (
            "strengths"
            if status in MASTERED
            else "needs_observation"
            if status == "insufficient_evidence"
            else "needs_consolidation"
        )
        lists[key].append({"knowledge_id": state["knowledge_id"], "reason": state["status_reason"]})
    observed = {
        r["material_id"] for r in records if r["attempted"] and r["score"] is not None
    } & applicable
    return {
        "schema_version": "0.3.0",
        "student_id": sid,
        "group_id": student["group_id"],
        "node_id": node_id,
        "generated_at": bundle["generated_at"],
        "source_dataset": bundle["dataset_id"],
        "coverage": {
            "observed_items": len(observed),
            "applicable_items": len(applicable),
            "ratio": round(len(observed) / len(applicable), 6) if applicable else None,
            "scope_known": known_scope,
            "observed_knowledge": sum(s["evidence_count"] > 0 for s in states),
            "total_knowledge": sum(s["applicable_items"] > 0 for s in states),
        },
        "knowledge_states": states,
        "objective_states": objectives,
        "issues": issues,
        "lists": lists,
    }


def _objectives(states):
    grouped = defaultdict(list)
    for state in states:
        grouped[state["objective_id"]].append(state)
    result = []
    for oid, children in sorted(grouped.items()):
        applicable = [s for s in children if s["status"] != "not_applicable"]
        observed = [s for s in applicable if s["evidence_count"]]
        weight = sum(s["evidence_count"] for s in observed)
        mastery = (
            round(sum(s["mastery"] * s["evidence_count"] for s in observed) / weight, 6)
            if weight
            else None
        )
        statuses = {s["status"] for s in applicable}
        if not applicable:
            status = "not_applicable"
        elif "insufficient_evidence" in statuses:
            status = "insufficient_evidence"
        elif statuses <= MASTERED:
            status = (
                "confirmed_mastered" if statuses == {"confirmed_mastered"} else "likely_mastered"
            )
        elif statuses <= WEAK:
            status = "confirmed_weak" if statuses == {"confirmed_weak"} else "likely_weak"
        else:
            status = "mixed_performance"
        order = {"low": 0, "medium": 1, "high": 2}
        confidence = min((s["confidence"] for s in applicable), key=order.get, default="low")
        result.append(
            {
                "objective_id": oid,
                "mastery": mastery,
                "confidence": confidence,
                "evidence_count": len({r for s in observed for r in s["evidence"]}),
                "status": status,
                "derived_from": [s["knowledge_id"] for s in applicable],
                "unobserved_knowledge_ids": [
                    s["knowledge_id"] for s in applicable if not s["evidence_count"]
                ],
            }
        )
    return result


def _issues(sid, states, records):
    by_id = {r["record_id"]: r for r in records}
    issues = []
    for state in states:
        if state["status"] == "not_applicable":
            continue
        graded = [by_id[r] for r in state["evidence"]]
        loss = [
            {
                "record_id": r["record_id"],
                "material_id": r["material_id"],
                "point_id": p["point_id"],
                "criterion": p["label"],
                "score": p["score"],
                "max_score": p["max_score"],
            }
            for r in graded
            for p in r.get("score_points", [])
            if p["score"] < p["max_score"]
        ]
        n = len(graded)
        full = state["state_counts"]["observed_correct"]
        if state["status"] == "insufficient_evidence":
            kind = "insufficient_evidence"
            statement = state["status_reason"] + f" 有效评分{n}项；已有失分只作观察线索。"
        elif loss:
            kind = "score_point_gap"
            labels = list(dict.fromkeys(p["criterion"] for p in loss))
            statement = f"{n}项有效评分中{full}项满分；评分点失分涉及：{'、'.join(labels)}。评分点反映步骤表现，具体原因需核对原始过程。"
        elif state["status"] in WEAK or (state["status"] == "mixed_performance" and full < n):
            kind = "performance_gap"
            statement = f"{n}项有效评分中{full}项满分，具体错因尚无充分依据。"
        else:
            continue
        kid_number = int(state["knowledge_id"].split("-")[1])
        issues.append(
            {
                "issue_id": f"IS-{sid[1:]}-{kid_number:02d}",
                "type": kind,
                "knowledge_id": state["knowledge_id"],
                "objective_id": state["objective_id"],
                "statement": statement,
                "evidence": {
                    "records": sorted(r["record_id"] for r in graded),
                    "material_ids": sorted({r["material_id"] for r in graded}),
                    "stat": f"full_credit={full}/{n}; partial_credit={state['performance']['partial_credit']}",
                },
                "severity": "high"
                if state["status"] == "confirmed_weak"
                else "medium"
                if state["status"] in WEAK
                else "low",
                "rubric_evidence": loss,
            }
        )
    return issues


def build_class_profile(profiles: list[dict], class_id: str, bundle: dict, node_id: str) -> dict:
    selected = [p for p in profiles if class_id == "ALL" or p["group_id"] == class_id]
    count = len(selected)
    distributions = []
    for knowledge in bundle["knowledge"]:
        kid = knowledge["knowledge_id"]
        states = [
            next(s for s in p["knowledge_states"] if s["knowledge_id"] == kid) for p in selected
        ]
        distributions.append(
            {
                "knowledge_id": kid,
                "objective_id": knowledge["objective_id"],
                "student_count": count,
                "mastered_count": sum(s["status"] in MASTERED for s in states),
                "weak_count": sum(s["status"] in WEAK for s in states),
                "insufficient_count": sum(s["status"] == "insufficient_evidence" for s in states),
                "mixed_count": sum(s["status"] == "mixed_performance" for s in states),
                "not_applicable_count": sum(s["status"] == "not_applicable" for s in states),
                "observed_student_count": sum(s["evidence_count"] > 0 for s in states),
                "mean_mastery": optional_mean(s["mastery"] for s in states),
                "mean_score_ratio": optional_mean(
                    s["performance"]["mean_score_ratio"] for s in states
                ),
            }
        )
    grouped = defaultdict(list)
    for profile in selected:
        for issue in profile["issues"]:
            grouped[issue["knowledge_id"], issue["type"]].append(profile["student_id"])
    common = []
    for (kid, kind), ids in sorted(grouped.items(), key=lambda pair: (-len(set(pair[1])), pair[0])):
        ids = sorted(set(ids))
        common.append(
            {
                "issue_type": kind,
                "knowledge_id": kid,
                "statement": f"该知识点有{len(ids)}名学生出现此类学习需求；比例分母为所选班级全体学生。",
                "student_count": len(ids),
                "prevalence": round(len(ids) / count, 6) if count else 0,
                "example_student_ids": ids[:5],
                "denominator": count,
                "denominator_basis": "all_students_in_selected_class",
            }
        )
    tiers = []
    buckets = defaultdict(list)
    for p in selected:
        weak = tuple(s["knowledge_id"] for s in p["knowledge_states"] if s["status"] in WEAK)
        mixed = tuple(
            s["knowledge_id"] for s in p["knowledge_states"] if s["status"] == "mixed_performance"
        )
        if not p["coverage"]["scope_known"]:
            key = ("scope_unknown", ())
        elif weak:
            key = ("consolidate", weak)
        elif p["lists"]["needs_observation"]:
            key = ("observe", ())
        elif mixed:
            key = ("practice", mixed)
        else:
            key = ("extend", ())
        buckets[key].append(p["student_id"])
    labels = {
        "scope_unknown": "确认参与范围",
        "consolidate": "针对薄弱内容巩固",
        "observe": "补充观测",
        "practice": "分项练习",
        "extend": "变式与迁移",
    }
    for (kind, kids), ids in sorted(buckets.items()):
        tiers.append(
            {
                "tier_id": kind + ("-" + "-".join(kids) if kids else ""),
                "label": labels[kind],
                "student_ids": sorted(ids),
                "weak_knowledge_ids": list(kids) if kind == "consolidate" else [],
                "suggested_focus": labels[kind]
                + ("：" + "、".join(kids) if kids else "；具体材料与顺序由任务3制定。"),
            }
        )
    groups = sorted({p["group_id"] for p in selected})
    differences = []
    if len(groups) > 1:
        for knowledge in bundle["knowledge"]:
            kid = knowledge["knowledge_id"]
            differences.append(
                {
                    "dimension": kid,
                    "groups": [
                        {
                            "group_id": group,
                            "student_count": sum(p["group_id"] == group for p in selected),
                            "mean_mastery": optional_mean(
                                s["mastery"]
                                for p in selected
                                if p["group_id"] == group
                                for s in p["knowledge_states"]
                                if s["knowledge_id"] == kid
                            ),
                        }
                        for group in groups
                    ],
                    "note": "仅为该节点的描述性差异；题目覆盖与证据量不同，不推断班级能力高低或教学因果。",
                }
            )
    return {
        "schema_version": "0.3.0",
        "class_id": class_id,
        "node_id": node_id,
        "generated_at": bundle["generated_at"],
        "source_dataset": bundle["dataset_id"],
        "student_count": count,
        "coverage_summary": {
            "mean_ratio": optional_mean(p["coverage"]["ratio"] for p in selected),
            "students_below_0_5": sum(
                p["coverage"]["ratio"] is not None and p["coverage"]["ratio"] < 0.5
                for p in selected
            ),
            "students_with_insufficient_evidence": sum(
                bool(p["lists"]["needs_observation"]) for p in selected
            ),
            "students_with_known_scope": sum(p["coverage"]["scope_known"] for p in selected),
        },
        "knowledge_distribution": distributions,
        "common_issues": common,
        "rubric_patterns": rubric_patterns(bundle, node_id, {p["student_id"] for p in selected}),
        "tiers": tiers,
        "group_differences": differences,
    }


def rubric_patterns(bundle, node_id, student_ids):
    """Count actual rubric losses; denominator is students observed on that criterion."""
    materials = {m["material_id"]: m for m in bundle["materials"]}
    buckets = defaultdict(lambda: {"observed": set(), "affected": set(), "records": set()})
    for record in bundle["records"]:
        if record["node_id"] != node_id or record["student_id"] not in student_ids:
            continue
        for point in record["score_points"]:
            for kid in materials[record["material_id"]]["knowledge_ids"]:
                bucket = buckets[kid, point["label"]]
                bucket["observed"].add(record["student_id"])
                if point["score"] < point["max_score"]:
                    bucket["affected"].add(record["student_id"])
                    bucket["records"].add(record["record_id"])
    result = []
    for (kid, criterion), bucket in buckets.items():
        if bucket["affected"]:
            result.append(
                {
                    "knowledge_id": kid,
                    "criterion": criterion,
                    "affected_student_count": len(bucket["affected"]),
                    "observed_student_count": len(bucket["observed"]),
                    "affected_record_count": len(bucket["records"]),
                    "prevalence": round(len(bucket["affected"]) / len(bucket["observed"]), 6),
                    "example_record_ids": sorted(bucket["records"])[:5],
                }
            )
    return sorted(
        result, key=lambda r: (-r["affected_student_count"], r["knowledge_id"], r["criterion"])
    )
