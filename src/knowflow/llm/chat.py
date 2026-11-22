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
6. 不输出 FACTS 的字段名或 JSON 键（如 needs_consolidation、seq、coverage），用中文教学语言描述。
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
                    "plan_item_id": item.get("plan_item_id"),
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


def snapshot_ids(snapshot: dict) -> set[str]:
    """Every real ID in the snapshot; citing one is verifiable even outside the card."""

    ids: set[str] = set()
    for student in snapshot["students"]:
        ids.add(student["student_id"])
        ids.add(student["group_id"])
    for node in snapshot["nodes"]:
        ids.add(node["node_id"])
    kb = snapshot["knowledge_base"]
    for item in kb["knowledge"]:
        ids.add(item["knowledge_id"])
        ids.add(item["objective_id"])
    for item in kb["materials"]:
        ids.add(item["material_id"])
    for node_profiles in snapshot["profiles"].values():
        for profile in node_profiles.values():
            for issue in profile.get("issues", []):
                ids.add(issue["issue_id"])
    for record in snapshot["records"]:
        ids.add(record["record_id"])
    return ids


def _number_ok(value: float, allowed: set[float]) -> bool:
    """Accept exact facts plus reasonable rounding of them.

    A model may write "24%" for 0.2422 or "约 67%" for 0.666667; those are still
    traceable.  Small ordinals ("3 个步骤") and years are harmless.  A fabricated
    count such as "999 人" stays rejected.
    """

    if value in allowed:
        return True
    if float(value).is_integer():
        integer = int(value)
        if 0 <= integer <= 10 or 2000 <= integer <= 2100:
            return True
    for base in allowed:
        if abs(value - base) <= 0.005:
            return True
        if 0 < base < 1 and abs(value / 100 - base) <= 0.015:
            return True
        if abs(value - base * 100) <= 1.5:
            return True
        if float(value).is_integer() and abs(value - round(base)) <= 0.5:
            return True
    return False


def validate_answer(answer: str, numbers: set[float], ids: set[str]) -> list[str]:
    problems: list[str] = []
    text = (answer or "").strip()
    if not text:
        problems.append("empty answer")
    if len(text) > MAX_ANSWER:
        problems.append("answer too long")
    unlocked = {float(value) for value in NUMBER.findall(text) if not _number_ok(float(value), numbers)}
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


def build_trace(facts: dict, mode: str, source: str, fallback_reason: str | None = None) -> dict:
    """Deterministic, inspectable basis for one answer.

    This is *not* a model chain-of-thought: it is the fact card, rule steps and
    evidence IDs the answer is allowed to use, so a reader can check it.
    """

    node_id = facts["node"]["id"]
    steps: list[dict] = []
    evidence: list[dict] = []
    student = facts.get("student")
    class_facts = facts.get("class") or {}
    knowledge = facts.get("knowledge") or []
    if student:
        names = {item["id"]: item["name"] for item in knowledge}
        steps.append({"label": "定位对象", "detail": f"学生 {student['id']} · 节点 {node_id}"})
        coverage = student["coverage"]
        steps.append(
            {
                "label": "读取现状",
                "detail": (
                    f"观测覆盖 {coverage['observed']}/{coverage['applicable']}；"
                    f"建议巩固 {len(student['needs_consolidation'])} 个，"
                    f"待观察 {len(student['needs_observation'])} 个"
                ),
            }
        )
        if student["plan"]:
            first = student["plan"][0]
            steps.append(
                {
                    "label": "确定下一步",
                    "detail": f"计划 {len(student['plan'])} 项；第一项：{first['activity']}",
                }
            )
        for state in student["states"][:4]:
            evidence.append(
                {
                    "kind": "state",
                    "id": state["id"],
                    "text": f"{names.get(state['id'], state['id'])} · {state['status']} · "
                    f"{state['evidence']} 条评分",
                }
            )
        for issue in student["issues"][:4]:
            evidence.append(
                {"kind": "issue", "id": issue["id"], "text": issue["statement"]}
            )
        for item in student["plan"][:3]:
            evidence.append(
                {
                    "kind": "plan",
                    "id": item.get("plan_item_id"),
                    "text": f"计划 {item['seq']}：{item['activity']}；验证：{item['check'][:60]}",
                }
            )
            for material_id in item["material_ids"][:3]:
                material = next(
                    (m for m in facts.get("materials", []) if m["id"] == material_id), None
                )
                evidence.append(
                    {
                        "kind": "material",
                        "id": material_id,
                        "text": (material or {}).get("title", material_id),
                    }
                )
    elif class_facts:
        names = {item["id"]: item["name"] for item in class_facts["knowledge"]}
        steps.append({"label": "定位对象", "detail": f"班级 {class_facts['id']} · 节点 {node_id}"})
        steps.append(
            {
                "label": "读取现状",
                "detail": (
                    f"{class_facts['students']} 名学生；平均覆盖 "
                    f"{_ratio((class_facts.get('coverage') or {}).get('mean_ratio'))}"
                ),
            }
        )
        for item in class_facts["knowledge"][:4]:
            evidence.append(
                {
                    "kind": "class_state",
                    "id": item["id"],
                    "text": f"{names.get(item['id'], item['id'])} · 薄弱 {item['weak']} 人 / "
                    f"待观察 {item['insufficient']} 人",
                }
            )
        for issue in class_facts.get("common_issues", [])[:3]:
            evidence.append(
                {
                    "kind": "class_issue",
                    "id": issue["knowledge_id"],
                    "text": issue["statement"],
                }
            )
    elif knowledge:
        first = knowledge[0]
        steps.append({"label": "定位对象", "detail": f"知识点 {first['id']} · 节点 {node_id}"})
        evidence.append(
            {
                "kind": "knowledge",
                "id": first["id"],
                "text": f"{first['name']} · 课程要求 {first['objective_id']}",
            }
        )
    else:
        steps.append({"label": "定位对象", "detail": f"节点 {node_id}；问题未命中具体学生/知识点"})

    steps.append(
        {
            "label": "组织回答",
            "detail": (
                "先说现状和下一步，少列数字"
                if mode == "concise"
                else "按“结论 / 依据”分点，依据逐条引用事实"
            ),
        }
    )
    steps.append(
        {
            "label": "核对",
            "detail": "数字与 ID 均来自当前事实卡；未读取姓名或原始作答。",
        }
    )
    deduped, seen = [], set()
    for item in evidence:
        key = (item["kind"], item.get("id") or item["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return {
        "mode": mode,
        "source": source,
        "steps": steps,
        "evidence": deduped[:10],
        "guard": {
            "numbers_checked": True,
            "ids_checked": True,
            "source": source,
            "fallback_reason": fallback_reason,
        },
        "note": "展示事实卡、规则步骤与证据；不包含模型隐藏思维链。",
    }


def rules_answer(facts: dict, mode: str = "concise") -> str:
    """Deterministic answer used when the model is absent or rejected twice."""

    student = facts.get("student")
    knowledge = facts.get("knowledge") or []
    names = {item["id"]: item["name"] for item in knowledge}
    if student:
        needs = student.get("needs_consolidation") or []
        plan = student.get("plan") or []
        if mode == "evidence":
            conclusion = (
                f"结论：{student['id']} 当前优先巩固 "
                + "、".join(f"{names.get(k, k)}" for k in needs[:2])
                if needs
                else f"结论：{student['id']} 当前证据不足，先补观测，不急着判断。"
            )
            coverage = student["coverage"]
            basis = [
                f"观测覆盖 {coverage['observed']}/{coverage['applicable']}"
                f"（{_ratio(coverage['ratio'])}）",
                f"建议巩固 {len(needs)} 个，待观察 {len(student.get('needs_observation') or [])} 个",
            ]
            if plan:
                first = plan[0]
                basis.append(
                    f"计划第一项：{first['activity']}；材料 {'、'.join(first['material_ids'])}"
                )
            return conclusion + "\n依据：" + "；".join(basis) + "。"
        parts = [f"{student['id']} 当前"]
        if needs:
            parts.append("先处理 " + "、".join(names.get(k, k) for k in needs[:2]) + "。")
        else:
            parts.append("证据还不够，先补几次观测再判断。")
        if plan:
            parts.append("下一步按计划先看学习卡，再做同评分点练习；完成后按计划里的验证标准自查。")
        if student.get("needs_observation"):
            parts.append("证据不足的知识点先补观测，不急着下结论。")
        return "".join(parts)

    class_facts = facts.get("class") or {}
    if class_facts:
        weak = class_facts.get("knowledge") or []
        if mode == "evidence":
            conclusion = (
                "结论：当前班级最需要关注 "
                + "、".join(f"{item['id']}（{item['name']}）" for item in weak[:2])
                if weak
                else "结论：当前班级没有足够证据指出薄弱知识点。"
            )
            coverage = class_facts.get("coverage") or {}
            basis = [
                f"{class_facts['id']} 共 {class_facts['students']} 名学生",
                f"平均观测覆盖 {_ratio(coverage.get('mean_ratio'))}",
            ]
            if weak:
                basis.append(
                    f"{weak[0]['id']} 薄弱 {weak[0]['weak']} 人 / 待观察 {weak[0]['insufficient']} 人"
                )
            return conclusion + "\n依据：" + "；".join(basis) + "。"
        if weak:
            return (
                f"{class_facts['id']} 当前先关注 "
                + "、".join(f"{item['name']}" for item in weak[:2])
                + "；先补观测，再安排巩固。"
            )
        return f"{class_facts['id']} 当前没有足够证据指出薄弱知识点，先扩大观测。"

    if knowledge:
        first = knowledge[0]
        if mode == "evidence":
            return (
                f"结论：{first['id']}（{first['name']}）属于课程要求 {first['objective_id']}。"
                f"\n依据：当前数据只有课程映射，没有更多作答细节。"
            )
        return f"{first['name']} 属于当前课程要求；当前数据没有更多细节。"
    return "当前数据没有这项信息。可以换一个学生 ID、知识点 ID（如 K-07）或节点再问。"


CHAT_MODES = {"concise", "evidence"}
MODE_PROMPTS = {
    "concise": (
        "回答方式：简洁。先描述现状，再给下一步行动；少引用数字和 ID，"
        "不要写“由……推断出”；不超过 120 字。"
    ),
    "evidence": (
        "回答方式：证据。必须按两段输出：第一行“结论：……”，随后“依据：……”，"
        "依据分点编号并逐条引用 FACTS 中的数字或 ID；不超过 200 字。"
    ),
}


TONE_PROMPTS = {
    "warm": "语气温和，先肯定已有进步，再给建议。",
    "direct": "语气简洁直接，直接给结论与下一步。",
    "rigorous": "语气严谨，先给依据再给判断，避免口语化。",
}

LENGTH_PROMPTS = {
    "brief": "篇幅：不超过 120 字。",
    "standard": "篇幅：不超过 200 字。",
    "detailed": "篇幅：不超过 320 字，可分点说明。",
}

INSUFFICIENT_PROMPTS = {
    "prompt": "若 FACTS 显示证据不足，直接说明信息不足，不要推测。",
    "probe": "若 FACTS 显示证据不足，建议先做一次摸底测试来补充证据。",
}


def style_note(preferences: dict | None) -> str:
    if not preferences:
        return ""
    parts = [
        TONE_PROMPTS.get(preferences.get("tone")),
        LENGTH_PROMPTS.get(preferences.get("report_length")),
        INSUFFICIENT_PROMPTS.get(preferences.get("insufficient")),
    ]
    parts = [part for part in parts if part]
    return ("\n\n附加要求：" + "；".join(parts)) if parts else ""


def answer_question(
    *,
    snapshot: dict,
    message: str,
    context: dict | None = None,
    client: ChatClient | None = None,
    mode: str = "concise",
    preferences: dict | None = None,
) -> dict:
    """Return ``{answer, source, citations, model, note?, trace}`` for one question."""

    if mode not in CHAT_MODES:
        raise ValueError("回答方式必须是 concise 或 evidence")
    text = (message or "").strip()
    if not text:
        raise ValueError("问题不能为空")
    if len(text) > 500:
        raise ValueError("问题过长，请控制在 500 字以内")
    facts = build_facts(snapshot, text, context)
    numbers, ids = allowed_sets(facts)
    ids |= snapshot_ids(snapshot)

    llm = client if client is not None else build_client(get_settings())
    note = None
    llm_failed = False
    if llm is not None:
        base_prompt = (
            MODE_PROMPTS[mode]
            + style_note(preferences)
            + "\n\nFACTS（唯一可用信息）：\n"
            + json.dumps(facts, ensure_ascii=False)
            + "\n\n用户问题："
            + text
        )
        feedback = ""
        for _ in range(2):
            try:
                answer = llm.complete(SYSTEM_PROMPT, base_prompt + feedback).strip()
            except Exception:
                llm_failed = True
                break
            problems = validate_answer(answer, numbers, ids)
            if mode == "evidence" and ("结论" not in answer or "依据" not in answer):
                problems.append("证据模式必须按“结论 / 依据”输出")
            if not problems:
                citations = sorted(set(ID.findall(answer)))[:8]
                return {
                    "answer": answer,
                    "source": "llm",
                    "citations": citations,
                    "model": getattr(llm, "model", "unknown"),
                    "trace": build_trace(facts, mode, "llm"),
                }
            feedback = (
                "\n\n上一次回答没有通过核对："
                + "；".join(problems)
                + "。请改写：只使用 FACTS 中的数字，能不用数字就不用；ID 必须真实存在。"
            )
    else:
        note = "未启用 LLM：当前为本地规则回答。可在左下角「设置」中开启。"

    if llm is not None:
        note = (
            "模型暂时调用不通，已改用本地规则回答。"
            if llm_failed
            else "模型这次给了无法核对的数字或编号，已改用本地规则回答。"
        )
    answer = rules_answer(facts, mode)
    return {
        "answer": answer,
        "source": "rules",
        "citations": sorted(set(ID.findall(answer)))[:8],
        "model": "rules",
        "note": note,
        "trace": build_trace(facts, mode, "rules", note),
    }
