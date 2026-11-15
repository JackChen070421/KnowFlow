"""Grounded Q&A over the validated dashboard snapshot.

Only aggregated facts (counts, statuses, IDs, plan wording) are sent.  The model
answer is rejected if it mentions a number or ID outside that fact card; when it
fails twice, or when no client is configured, a deterministic rule answer is
returned instead.
"""

from __future__ import annotations

import json
from typing import Any

from knowflow.config import get_settings

from .client import ChatClient, build_client
from .guard import ID, NUMBER

MAX_ANSWER = 900
SYSTEM_PROMPT = """你是 KnowFlow 的学情助手，面向教师和学生解释已有诊断结果。

必须遵守：
1. 只根据 FACTS 回答；FACTS 没有的信息直接说“当前数据没有这项信息”，不要猜。
2. 只能使用 FACTS 中出现过的数字和 ID（如 S001 / K-07 / M-021 / IS-001-07）。
3. 中文，简洁，先结论后依据，不超过 200 字。
4. 不输出 URL、代码块、姓名或原始作答；不要把“缺少记录”说成“未掌握”。
5. 不改变诊断结论、掌握度或建议顺序，只做解释与串联。
"""


def _collect(value: Any, numbers: set[float], ids: set[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        numbers.add(float(value))
    elif isinstance(value, str):
        numbers.update(float(item) for item in NUMBER.findall(value))
        ids.update(ID.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            _collect(item, numbers, ids)
    elif isinstance(value, list):
        for item in value:
            _collect(item, numbers, ids)


def _weak(state: dict) -> bool:
    return state.get("status") in {"confirmed_weak", "likely_weak", "mixed_performance"}


def build_facts(snapshot: dict, message: str, context: dict | None = None) -> dict:
    """Build a compact, number/ID-whitelisted fact card for one question."""

    context = context or {}
    kb = snapshot["knowledge_base"]
    names = {item["knowledge_id"]: item["name"] for item in kb["knowledge"]}
    materials = {item["material_id"]: item for item in kb["materials"]}
    nodes = {item["node_id"]: item for item in snapshot["nodes"]}
    students = {item["student_id"]: item for item in snapshot["students"]}
    node_id = context.get("node_id") if context.get("node_id") in nodes else None
    node_id = node_id or snapshot["nodes"][-1]["node_id"]

    mentioned = set(ID.findall(message))
    if node_id not in nodes:
        node_id = snapshot["nodes"][-1]["node_id"]
    for value in mentioned:
        if value in nodes:
            node_id = value

    student_id = context.get("student_id")
    if student_id not in students:
        student_id = None
    for value in mentioned:
        if value.startswith("S") and value in students:
            student_id = value

    group_id = context.get("group_id") or "ALL"
    for value in mentioned:
        if value.startswith("G") and value[1:].isdigit():
            group_id = value

    node = nodes[node_id]
    facts: dict = {
        "dataset": {
            "id": snapshot["meta"]["dataset_id"],
            "subject": snapshot["meta"]["subject"],
            "grade": snapshot["meta"]["grade"],
        },
        "node": {"id": node_id, "date": node["date"], "objectives": len(node["taught_objective_ids"])},
    }

    classes = snapshot["classes"].get(node_id, {})
    class_profile = classes.get(group_id) if group_id in classes else classes.get("ALL")
    if class_profile:
        distribution = sorted(
            class_profile["knowledge_distribution"],
            key=lambda item: (item["weak_count"] + item["insufficient_count"]),
            reverse=True,
        )
        facts["class"] = {
            "id": class_profile["class_id"],
            "students": class_profile["student_count"],
            "coverage": class_profile["coverage_summary"],
            "knowledge": [
                {
                    "id": item["knowledge_id"],
                    "name": names.get(item["knowledge_id"], item["knowledge_id"]),
                    "weak": item["weak_count"],
                    "insufficient": item["insufficient_count"],
                    "mastered": item["mastered_count"],
                    "observed": item["observed_student_count"],
                    "mean_mastery": item["mean_mastery"],
                }
                for item in distribution[:6]
            ],
            "common_issues": [
                {
                    "type": issue["issue_type"],
                    "knowledge_id": issue["knowledge_id"],
                    "statement": issue["statement"][:100],
                    "students": issue["student_count"],
                }
                for issue in class_profile["common_issues"][:4]
            ],
        }

    profile = snapshot["profiles"].get(node_id, {}).get(student_id) if student_id else None
    if profile:
        states = profile["knowledge_states"]
        chosen = ([state for state in states if _weak(state)] + states)[:6]
        plan = snapshot["recommendations"].get(node_id, {}).get(student_id, {}).get("plan", [])[:3]
        facts["student"] = {
            "id": student_id,
            "group": profile["group_id"],
            "coverage": {
                "observed": profile["coverage"]["observed_items"],
                "applicable": profile["coverage"]["applicable_items"],
                "ratio": profile["coverage"]["ratio"],
                "scope_known": profile["coverage"]["scope_known"],
            },
            "needs_consolidation": [
                item["knowledge_id"] for item in profile["lists"]["needs_consolidation"]
            ][:5],
            "needs_observation": [
                item["knowledge_id"] for item in profile["lists"]["needs_observation"]
            ][:5],
            "states": [
                {
                    "id": state["knowledge_id"],
                    "name": names.get(state["knowledge_id"], state["knowledge_id"]),
                    "status": state["status"],
                    "mastery": state["mastery"],
                    "evidence": state["evidence_count"],
                }
                for state in chosen
            ],
            "issues": [
                {
                    "id": issue["issue_id"],
                    "type": issue["type"],
                    "knowledge_id": issue["knowledge_id"],
                    "statement": issue["statement"][:100],
                }
                for issue in profile["issues"][:4]
            ],
            "plan": [
                {
                    "seq": item["seq"],
                    "issue_id": item["issue_id"],
                    "activity": item["activity"],
                    "material_ids": item["material_ids"],
                    "check": item["check"],
                }
                for item in plan
            ],
        }
        mentioned |= {item["issue_id"] for item in profile["issues"]}
        mentioned |= {material_id for item in plan for material_id in item["material_ids"]}

    knowledge_ids = {value for value in mentioned if value.startswith("K-") and value in names}
    if facts.get("student"):
        knowledge_ids |= set(facts["student"]["needs_consolidation"])
        knowledge_ids |= set(facts["student"]["needs_observation"])
        knowledge_ids |= {state["id"] for state in facts["student"]["states"]}
    if not knowledge_ids and facts.get("class"):
        knowledge_ids = {item["id"] for item in facts["class"]["knowledge"][:3]}
    facts["knowledge"] = [
        {"id": knowledge_id, "name": names[knowledge_id], "objective_id": next(
            item["objective_id"] for item in kb["knowledge"] if item["knowledge_id"] == knowledge_id
        )}
        for knowledge_id in sorted(knowledge_ids)
    ]
    material_ids = {value for value in mentioned if value in materials}
    if facts.get("student"):
        for item in facts["student"]["plan"]:
            material_ids |= set(item["material_ids"])
    facts["materials"] = [
        {
            "id": material_id,
            "title": materials[material_id]["title"],
            "type": materials[material_id]["material_type"],
        }
        for material_id in sorted(material_ids)[:6]
    ]
    return facts


def allowed_sets(facts: dict) -> tuple[set[float], set[str]]:
    numbers: set[float] = {1.0, 2.0, 3.0, 5.0}
    ids: set[str] = set()
    _collect(facts, numbers, ids)
    return numbers, ids


def validate_answer(answer: str, numbers: set[float], ids: set[str]) -> list[str]:
    problems: list[str] = []
    text = (answer or "").strip()
    if not text:
        problems.append("empty answer")
    if len(text) > MAX_ANSWER:
        problems.append("answer too long")
    unlocked = {float(value) for value in NUMBER.findall(text)} - numbers
    if unlocked:
        problems.append(f"numbers outside facts: {sorted(unlocked)}")
    unknown = set(ID.findall(text)) - ids
    if unknown:
        problems.append(f"ids outside facts: {sorted(unknown)}")
    if "http://" in text or "https://" in text or "```" in text:
        problems.append("urls or code fences are not allowed")
    return problems


def _ratio(value: Any) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "—"


def rules_answer(facts: dict) -> str:
    """Deterministic answer used when the model is absent or rejected twice."""

    node_id = facts["node"]["id"]
    student = facts.get("student")
    if student:
        parts = [
            f"{student['id']} 在 {node_id} 的观测覆盖为 {_ratio(student['coverage']['ratio'])}"
            f"（{student['coverage']['observed']}/{student['coverage']['applicable']} 个可测题目）。"
        ]
        needs = student.get("needs_consolidation") or []
        names = {item["id"]: item["name"] for item in facts.get("knowledge", [])}
        if needs:
            parts.append("建议巩固：" + "、".join(f"{kid}（{names.get(kid, kid)}）" for kid in needs[:3]) + "。")
        plan = student.get("plan") or []
        if plan:
            first = plan[0]
            parts.append(
                f"下一步：{first['activity']}，材料 {'、'.join(first['material_ids'])}；验证：{first['check']}"
            )
        if student.get("needs_observation"):
            parts.append("另有知识点证据不足，先补观测，不能据此判为未掌握。")
        return "".join(parts)

    class_facts = facts.get("class") or {}
    if class_facts:
        coverage = class_facts.get("coverage") or {}
        parts = [
            f"当前节点 {node_id}，{class_facts['id']} 共 {class_facts['students']} 名学生，"
            f"平均观测覆盖 {_ratio(coverage.get('mean_ratio'))}。"
        ]
        weak = class_facts.get("knowledge") or []
        if weak:
            parts.append(
                "最需要关注："
                + "、".join(
                    f"{item['id']}（{item['name']}，薄弱 {item['weak']} 人 / 待观测 {item['insufficient']} 人）"
                    for item in weak[:3]
                )
                + "。"
            )
        issues = class_facts.get("common_issues") or []
        if issues:
            first = issues[0]
            parts.append(f"共性问题示例：{first['knowledge_id']}，涉及 {first['students']} 人。")
        return "".join(parts)

    knowledge = facts.get("knowledge") or []
    if knowledge:
        first = knowledge[0]
        return f"{first['id']}（{first['name']}）属于课程要求 {first['objective_id']}；当前数据没有更多细节。"
    return "当前数据没有这项信息。可以换一个学生 ID、知识点 ID（如 K-07）或节点再问。"


def answer_question(
    *,
    snapshot: dict,
    message: str,
    context: dict | None = None,
    client: ChatClient | None = None,
) -> dict:
    """Return ``{answer, source, citations, model, note?}`` for one question."""

    text = (message or "").strip()
    if not text:
        raise ValueError("问题不能为空")
    if len(text) > 500:
        raise ValueError("问题过长，请控制在 500 字以内")
    facts = build_facts(snapshot, text, context)
    numbers, ids = allowed_sets(facts)

    llm = client if client is not None else build_client(get_settings())
    note = None
    llm_failed = False
    if llm is not None:
        user_prompt = (
            "FACTS（唯一可用信息）：\n"
            + json.dumps(facts, ensure_ascii=False)
            + "\n\n用户问题："
            + text
        )
        for _ in range(2):
            try:
                answer = llm.complete(SYSTEM_PROMPT, user_prompt).strip()
            except Exception:
                llm_failed = True
                break
            if not validate_answer(answer, numbers, ids):
                citations = sorted(set(ID.findall(answer)))[:8]
                return {
                    "answer": answer,
                    "source": "llm",
                    "citations": citations,
                    "model": getattr(llm, "model", "unknown"),
                }
    else:
        note = "未启用 LLM：当前为本地规则回答。可在左下角「设置」中开启。"

    if llm is not None:
        note = (
            "模型调用失败，已回退为本地规则回答。"
            if llm_failed
            else "模型回答未通过数字/ID 校验，已回退为本地规则回答。"
        )
    answer = rules_answer(facts)
    return {
        "answer": answer,
        "source": "rules",
        "citations": sorted(set(ID.findall(answer)))[:8],
        "model": "rules",
        "note": note,
    }
