"""Grounded Q&A over the validated dashboard snapshot.

Two kinds of context are sent, with different rules:

* **learner data** — aggregate counts, states, IDs and plan wording.  Facts only;
  nothing here reads records, names or free-text answers.
* **course content** — 课标原文、学习卡、题面与解析, selected by
  :mod:`knowflow.llm.retrieval`.  This is what lets the companion teach.

A number that states a *learner fact* (人数、比例、掌握度、覆盖) must come from the
fact card; numbers used while teaching ("先做 3 道题"、"第 12 周") are allowed.
When the model cannot be reached or keeps citing data it cannot support, a
deterministic rule answer is returned instead.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from knowflow.config import get_settings

from .client import ChatClient, LLMError, build_client
from .guard import ID, NUMBER
from .retrieval import select_sources

LOGGER = logging.getLogger(__name__)

MAX_ANSWER = 1200
# One retry, then give the answer back to the rule path: a user waiting on a
# chat bubble must never sit through three timeouts.
RETRY_SLEEP_SECONDS = 0.6
MAX_CALLS = 3
MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 2400
MAX_HISTORY_ITEM = 600
SYSTEM_PROMPT = """你是「AI 学伴」，一位耐心的初中数学老师。你和一位学生或他的老师一起看这份学情，也负责把不会的题讲明白。

两类信息，规则不同：
A. 学习者数据（人数、比例、掌握度、覆盖率、知识点/材料/计划编号）只能来自 FACTS。
   FACTS 没有的就直说“这份数据里没有”，不要估算、不要编造；不要把“证据不足”说成“未掌握”；
   不要改动诊断结论、掌握度或建议顺序。
B. 学科知识（概念、方法、例题思路）可以正常讲，可以用 FACTS.sources 里的课标原文、学习卡与题面。
   但不能借学科知识编造任何学生数据、分数或排名。

怎么说话：
- 先直接回答问题，再补建议；不要每句都先报数据。
- 读者是学生：口语、短句、一次只推进一步，先肯定再纠正；讲题给思路和第一步，不直接报最终答案。
- 读者是教师：结论先行，给可执行的教学动作，可以引用编号。
- 学生闲聊就正常回应，不必强行转回诊断；拿不准就说“这份数据里看不出来”。
- 回答显示在纯文本气泡里：不要用 Markdown（不要 **、#、- 列表符号），分段用换行。
- 提到材料时用它的 M- 编号（如 M-057），不要只写题号；编号要来自 FACTS。
- 不输出 URL、代码块、学生姓名或原始作答；不输出字段名（如 needs_consolidation、seq、coverage）。

示例（只示范语气与结构）：
问：K-07 到底怎么算？
答：先看未知数的系数是正是负——两边同乘或同除一个负数时，不等号要反过来，这是最容易漏的一步。你上次的失分也集中在这里。要不要先过一遍学习卡，再做两道同类题？

问：你好
答：你好！我在。想先从你最近卡住的那道题聊起，还是先看看这周先补哪块？
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


def _audience(snapshot: dict) -> str:
    """Who is reading. Unknown callers get the student wording: an answer key must
    never leak just because a snapshot had no viewer attached."""

    viewer = (snapshot.get("meta") or {}).get("viewer") or {}
    return "teacher" if viewer.get("role") == "teacher" else "student"


def build_facts(
    snapshot: dict,
    message: str,
    context: dict | None = None,
    knowledge: dict | None = None,
) -> dict:
    """Build a compact, number/ID-whitelisted fact card for one question.

    ``knowledge`` is the full knowledge base (it carries material bodies) when the
    caller has it; the snapshot view is enough for everything else.
    """

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
        # A named knowledge point must bring its own state even when it is not
        # among the six the card shows by default — otherwise "K-07 我掌握得怎么样"
        # gets answered from the course content alone.
        for state in states:
            if state["knowledge_id"] in mentioned and state not in chosen:
                chosen.append(state)
        chosen = chosen[:8]
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

    ordered: list[str] = []
    student_facts = facts.get("student") or {}
    for knowledge_id in student_facts.get("needs_consolidation", []):
        ordered.append(knowledge_id)
    for state in student_facts.get("states", []):
        if state["id"] not in ordered:
            ordered.append(state["id"])
    for item in facts["knowledge"]:
        if item["id"] not in ordered:
            ordered.append(item["id"])
    plan_materials = [
        material_id
        for item in student_facts.get("plan", [])
        for material_id in item["material_ids"]
    ]
    facts["sources"] = select_sources(
        knowledge=knowledge or snapshot["knowledge_base"],
        message=message,
        knowledge_ids=ordered,
        plan_material_ids=plan_materials,
        audience=_audience(snapshot),
    )
    return facts


def _count_lists(value: Any, numbers: set[float]) -> None:
    """A list length is itself a fact ("建议巩固 4 个" is traceable when 4 items
    are listed), so counts of listed items join the whitelist."""

    if isinstance(value, dict):
        for item in value.values():
            _count_lists(item, numbers)
    elif isinstance(value, list):
        numbers.add(float(len(value)))
        for item in value:
            _count_lists(item, numbers)


def allowed_sets(facts: dict) -> tuple[set[float], set[str]]:
    numbers: set[float] = {1.0, 2.0, 3.0, 5.0}
    ids: set[str] = set()
    _collect(facts, numbers, ids)
    _count_lists(facts, numbers)
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


def _rounds_to_fact(
    value: float, allowed: set[float], *, percent_slack: float, integer_slack: float
) -> bool:
    """Is ``value`` a rounded/percentage restatement of one allowed fact?"""

    for base in allowed:
        if abs(value - base) <= 0.005:
            return True
        if 0 < base < 1 and abs(value / 100 - base) <= percent_slack / 100:
            return True
        if abs(value - base * 100) <= percent_slack:
            return True
        if float(value).is_integer() and abs(value - round(base)) <= integer_slack:
            return True
    return False


def _number_ok(value: float, allowed: set[float]) -> bool:
    """Admit a number used while teaching (steps, item numbers, years).

    "3 个步骤"、"1/2 + 1/3" 不是对学习者的断言，所以不拿事实卡去卡它。
    """

    if value in allowed:
        return True
    if float(value).is_integer():
        integer = int(value)
        if 0 <= integer <= 10 or 2000 <= integer <= 2100:
            return True
    return _rounds_to_fact(value, allowed, percent_slack=1.5, integer_slack=0.5)


# A number carrying one of these units is a teaching quantity ("做 14 道题",
# "第 12 周"), not a claim about a learner.
TEACHING_UNITS = (
    "道", "题", "步", "分钟", "分", "秒", "小时", "遍", "周", "天", "日",
    "页", "章", "节", "个", "条", "次", "本", "张", "组", "年级", "以内", "以上", "以下",
)


def _unit_follows(text: str, index: int) -> bool:
    tail = text[index : index + 4].lstrip()
    return any(tail.startswith(unit) for unit in TEACHING_UNITS)


# A sentence that talks about learners is making a claim; a sentence that talks
# about the subject is teaching.  Only the first kind is checked against FACTS.
DATA_WORDS = (
    "人", "名", "位", "学生", "同学", "孩子", "率", "％", "%", "掌握", "覆盖",
    "薄弱", "待观察", "证据", "得分", "评分", "巩固", "平均", "占比", "排名", "比例",
)
_APPROX = ("约", "大约", "大概", "近", "左右", "超过", "不到")
_SENTENCE = re.compile(r"[^。！？!?；;\n]+")


def _sentence_of(text: str, index: int) -> str:
    for match in _SENTENCE.finditer(text):
        if match.start() <= index < match.end():
            return match.group()
    return text


def _is_data_claim(sentence: str) -> bool:
    return any(word in sentence for word in DATA_WORDS)


def _claim_ok(value: float, allowed: set[float], sentence: str) -> bool:
    """A learner-data number must be traceable; "约" buys a wider rounding band."""

    if value in allowed:
        return True
    if _rounds_to_fact(value, allowed, percent_slack=1.5, integer_slack=0.5):
        return True
    if any(mark in sentence for mark in _APPROX):
        return _rounds_to_fact(value, allowed, percent_slack=5.0, integer_slack=1.0)
    return False


def number_audit(answer: str, numbers: set[float]) -> dict:
    """Split the numbers of an answer into data claims and teaching numbers."""

    claims: list[float] = []
    teaching = 0
    for match in NUMBER.finditer(answer or ""):
        sentence = _sentence_of(answer, match.start())
        if _is_data_claim(sentence):
            claims.append(float(match.group()))
        else:
            teaching += 1
    return {"data_claims": len(claims), "teaching_numbers": teaching}


def validate_answer(answer: str, numbers: set[float], ids: set[str]) -> list[str]:
    problems: list[str] = []
    text = (answer or "").strip()
    if not text:
        problems.append("empty answer")
        return problems
    if len(text) > MAX_ANSWER:
        problems.append("answer too long")
    unlocked: set[float] = set()
    for match in NUMBER.finditer(text):
        value = float(match.group())
        sentence = _sentence_of(text, match.start())
        if _is_data_claim(sentence):
            if not _claim_ok(value, numbers, sentence):
                unlocked.add(value)
        elif not (_unit_follows(text, match.end()) or _number_ok(value, numbers)):
            unlocked.add(value)
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


def build_trace(
    facts: dict,
    mode: str,
    source: str,
    fallback_reason: str | None = None,
    *,
    audience: str = "student",
    history_turns: int = 0,
) -> dict:
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

    sources = facts.get("sources") or []
    if sources:
        labels = {"objective": "课标要求", "explain": "学习卡", "example": "例题"}
        kinds = list(dict.fromkeys(labels.get(item["kind"], item["kind"]) for item in sources))
        steps.append({"label": "查课程内容", "detail": "、".join(kinds)})
        for item in sources:
            text = item.get("objective_text") if item["kind"] == "objective" else item.get("body")
            evidence.append(
                {
                    "kind": "source",
                    "id": item["id"],
                    "text": f"{item.get('title') or item['id']}：{str(text or '')[:70]}",
                }
            )

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
            "detail": "学情数字与 ID 来自事实卡；教材内容可引用；未读取姓名或原始作答。",
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
        "evidence": deduped[:12],
        "guard": {
            "numbers_checked": True,
            "ids_checked": True,
            "source": source,
            "fallback_reason": fallback_reason,
            "audience": audience,
            "history_turns": history_turns,
            "sources": len(sources),
        },
        "note": "展示事实卡、课程内容与规则步骤；不包含模型隐藏思维链。",
    }


NEXT_STEPS = (
    "下一步按计划先看学习卡，再做同评分点练习；完成后按计划里的验证标准自查。",
    "接着照计划走：先过一遍学习卡，再做同评分点练习，最后用计划里的标准自查。",
    "建议从学习卡开始，配两道同评分点练习；做完对照验证标准检查一遍。",
)


def _pick(options: tuple[str, ...], key: str) -> str:
    """Deterministic variety: the same question keeps the same wording."""

    return options[sum(ord(character) for character in key) % len(options)]


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
            parts.append(_pick(NEXT_STEPS, student["id"] + mode))
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
        objective = next(
            (item for item in facts.get("sources") or [] if item["kind"] == "objective"), None
        )
        requirement = (
            f"课程要求是“{objective['objective_text']}”。"
            if objective and objective.get("objective_text")
            else f"属于课程要求 {first['objective_id']}。"
        )
        if mode == "evidence":
            return (
                f"结论：{first['id']}（{first['name']}）{requirement}"
                f"\n依据：当前数据只有课程映射，没有更多作答细节。"
            )
        return f"{first['name']}：{requirement}当前数据没有更多作答细节。"
    return "当前数据没有这项信息。可以换一个学生 ID、知识点 ID（如 K-07）或节点再问。"


CHAT_MODES = {"concise", "evidence"}
MODE_PROMPTS = {
    "concise": (
        "回答方式：简洁。先说现状或直接回答，再给下一步；尽量少列数字和 ID，"
        "不要写“由……推断出”；建议 120 字左右。"
    ),
    "evidence": (
        "回答方式：证据。尽量按两段写：第一行“结论：……”，随后“依据：……”逐条说明；"
        "依据里引用学情就用 FACTS 的数字或 ID，讲做法可以引用 sources；建议 200 字左右。"
    ),
}

AUDIENCE_PROMPTS = {
    "student": "读者是学生：口语、少术语，一次只推进一步；讲题给思路和第一步，不直接报最终答案。",
    "teacher": "读者是教师：结论先行，给可执行的教学动作，可以引用编号与班级数据。",
}

TONE_PROMPTS = {
    "warm": "语气温和，先肯定已有进步，再给建议。",
    "direct": "语气简洁直接，直接给结论与下一步。",
    "rigorous": "语气严谨，先给依据再给判断，避免口语化。",
}

LENGTH_PROMPTS = {
    "brief": "篇幅建议：不超过 120 字。",
    "standard": "篇幅建议：不超过 200 字。",
    "detailed": "篇幅建议：不超过 320 字，可分点说明。",
}

INSUFFICIENT_PROMPTS = {
    "prompt": "若 FACTS 显示证据不足，直接说明信息不足，不要推测。",
    "probe": "若 FACTS 显示证据不足，建议先做一次摸底测试来补充证据。",
}


def style_note(preferences: dict | None, audience: str = "student") -> str:
    parts = [AUDIENCE_PROMPTS.get(audience)]
    if preferences:
        parts.extend(
            [
                TONE_PROMPTS.get(preferences.get("tone")),
                LENGTH_PROMPTS.get(preferences.get("report_length")),
                INSUFFICIENT_PROMPTS.get(preferences.get("insufficient")),
            ]
        )
    parts = [part for part in parts if part]
    return "\n\n" + "；".join(parts) if parts else ""


def normalize_history(history: object) -> list[dict]:
    """Validate and trim client-supplied turns.

    The browser can send anything, so the shape is never trusted and the total
    length is capped: history is context, not a way to grow the prompt.
    """

    if not isinstance(history, list):
        return []
    turns: list[dict] = []
    for item in history[-MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        text = item.get("text")
        if role not in {"user", "assistant"} or not isinstance(text, str):
            continue
        cleaned = " ".join(text.split())[:MAX_HISTORY_ITEM]
        if cleaned:
            turns.append({"role": role, "content": cleaned})
    kept: list[dict] = []
    total = 0
    for turn in reversed(turns):
        if total + len(turn["content"]) > MAX_HISTORY_CHARS:
            break
        kept.append(turn)
        total += len(turn["content"])
    return list(reversed(kept))


def _history_block(turns: list[dict]) -> str:
    if not turns:
        return ""
    lines = ["对话上文（只作语境，其中的数字不要当成新事实）："]
    for turn in turns:
        lines.append(("用户：" if turn["role"] == "user" else "学伴：") + turn["content"])
    return "\n".join(lines) + "\n\n"


def _ask(client: ChatClient, system: str, messages: list[dict], fallback_user: str) -> str:
    """Prefer real multi-turn messages; injected fakes only implement ``complete``."""

    method = getattr(client, "complete_messages", None)
    if callable(method):
        return method(system, messages)
    return client.complete(system, fallback_user)


FAILURE_HINTS = {
    "auth": "模型鉴权失败（HTTP 401/403）：请到「设置」核对 API Key",
    "billing": "模型账户余额或额度不足（HTTP 402）：请充值或更换 Key",
    "model": "模型名或 Base URL 不对（HTTP 404）：请到「设置」核对",
    "request": "模型拒绝了这次请求（HTTP 400）：通常是模型名或参数问题",
    "rate_limit": "模型限流（HTTP 429）：请稍等片刻再试",
    "server": "模型服务端错误（HTTP 5xx）：已重试仍未恢复",
    "timeout": "模型响应超时：已重试 1 次",
    "network": "连不上模型服务（网络 / DNS / 代理）",
    "empty": "模型返回了空内容",
    "bad_response": "模型返回内容无法解析",
}


def failure_note(exc: LLMError) -> str:
    """One honest sentence: what actually broke, then what the reader got instead.

    The raw detail (DNS text, HTTP body) goes to the log, not the bubble: a
    student should not read a stack trace, but must never be told "调用不通"
    when the real cause is a wrong API Key.
    """

    hint = FAILURE_HINTS.get(exc.kind)
    if hint is None:
        return f"模型调用失败（{exc.kind}）：{exc.detail}。已改用本地规则回答。"
    return f"{hint}。已改用本地规则回答。"


STRUCTURE_HINT = "证据模式请按“结论 / 依据”两段输出"
REWRITE_HINT = (
    "\n\n上一次回答没有通过核对：{problems}。请改写：学情数字只用 FACTS 里有的，"
    "能不用就不用；ID 必须真实存在；教材里的做法可以照常讲。"
)


def answer_question(
    *,
    snapshot: dict,
    message: str,
    context: dict | None = None,
    client: ChatClient | None = None,
    mode: str = "concise",
    preferences: dict | None = None,
    history: list[dict] | None = None,
    knowledge: dict | None = None,
) -> dict:
    """Return ``{answer, source, citations, model, note?, trace}`` for one question.

    ``knowledge`` is the full knowledge base; without it the fact card still
    carries 课标要求 but no material bodies.  ``history`` is optional context.
    """

    if mode not in CHAT_MODES:
        raise ValueError("回答方式必须是 concise 或 evidence")
    text = (message or "").strip()
    if not text:
        raise ValueError("问题不能为空")
    if len(text) > 500:
        raise ValueError("问题过长，请控制在 500 字以内")

    audience = _audience(snapshot)
    turns = normalize_history(history)
    facts = build_facts(snapshot, text, context, knowledge)
    numbers, ids = allowed_sets(facts)
    ids |= snapshot_ids(snapshot)
    # Numbers the reader already saw in an earlier answer were checked then;
    # quoting them back is not a new fabrication.
    for turn in turns:
        if turn["role"] == "assistant":
            numbers.update(float(value) for value in NUMBER.findall(turn["content"]))

    settings = get_settings()
    llm = (
        client
        if client is not None
        else build_client(
            settings,
            temperature=settings.llm_chat_temperature,
            max_tokens=settings.llm_chat_max_tokens,
        )
    )
    note = None
    failure: LLMError | None = None
    guard_problems: list[str] = []
    if llm is not None:
        facts_block = (
            "FACTS（唯一可用信息）：\n"
            + json.dumps(facts, ensure_ascii=False)
            + "\n\n用户问题："
            + text
        )
        prefix = _history_block(turns)
        system = SYSTEM_PROMPT + "\n" + MODE_PROMPTS[mode] + style_note(preferences, audience)
        feedback = ""
        calls = 0
        content_retry_used = False
        network_retry_used = False
        while calls < MAX_CALLS:
            calls += 1
            attempt = facts_block + feedback
            messages = [*turns, {"role": "user", "content": attempt}]
            try:
                answer = _ask(llm, system, messages, prefix + attempt).strip()
            except LLMError as exc:
                failure = exc
                LOGGER.warning(
                    "chat model call failed: kind=%s status=%s model=%s detail=%s",
                    exc.kind,
                    exc.status,
                    getattr(llm, "model", "unknown"),
                    exc.detail,
                )
                if exc.retryable and not network_retry_used:
                    network_retry_used = True
                    time.sleep(RETRY_SLEEP_SECONDS)
                    continue
                break
            except Exception as exc:  # an injected client must never hide its cause
                failure = LLMError("unknown", f"{type(exc).__name__}: {exc}")
                LOGGER.warning("chat model call failed: kind=unknown detail=%s", failure.detail)
                break
            problems = validate_answer(answer, numbers, ids)
            structured_only = False
            if mode == "evidence" and ("结论" not in answer or "依据" not in answer):
                if not problems and calls < 2:
                    # Nudge once, then keep whatever it wrote: a missing heading
                    # is a formatting miss, not a reason to throw the answer away.
                    problems = [STRUCTURE_HINT]
                    structured_only = True
            if not problems:
                citations = sorted(set(ID.findall(answer)))[:8]
                return {
                    "answer": answer,
                    "source": "llm",
                    "citations": citations,
                    "model": getattr(llm, "model", "unknown"),
                    "trace": build_trace(
                        facts, mode, "llm", audience=audience, history_turns=len(turns)
                    ),
                }
            guard_problems = problems
            failure = None
            LOGGER.info("chat answer rejected (call %d): %s", calls, "；".join(problems))
            if content_retry_used:
                break
            content_retry_used = True
            feedback = (
                "\n\n请按“结论：…… / 依据：……”两段重写，不要省略这两个小标题。"
                if structured_only
                else REWRITE_HINT.format(problems="；".join(problems))
            )
    else:
        note = "未启用 LLM：当前为本地规则回答。可在左下角「设置」中开启。"

    if llm is not None:
        if failure is not None:
            note = failure_note(failure)
        elif guard_problems:
            note = "模型这次给了无法核对的数字或编号，已改用本地规则回答。"
    LOGGER.info("chat fell back to rules: llm=%s note=%s", llm is not None, note or "-")
    answer = rules_answer(facts, mode)
    return {
        "answer": answer,
        "source": "rules",
        "citations": sorted(set(ID.findall(answer)))[:8],
        "model": "rules",
        "note": note,
        "trace": build_trace(
            facts, mode, "rules", note, audience=audience, history_turns=len(turns)
        ),
    }
