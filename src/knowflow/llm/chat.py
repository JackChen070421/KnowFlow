"""Grounded Q&A over the validated dashboard snapshot.

Two kinds of context are sent, with different rules:

* **learner data** — aggregate counts, states, IDs and plan wording.  Facts only;
  nothing here reads records, names or free-text answers.
* **course content** — 课标原文、学习卡、题面与解析, selected by
  :mod:`knowflow.llm.retrieval`.  This is what lets the companion teach.

The division of labour this module implements:

* **program** — extract facts, compute the statistics, resolve what the question
  is about (student / knowledge point / class), decide which state each entity is
  in, and audit every number and ID the answer uses.
* **model** — understand what the teacher actually wants, pick the relevant facts,
  explain how the signals relate, separate fact from inference from unknown, and
  write a teaching answer instead of a database dump.

The fact card therefore carries *signal structure* (``weak_signal`` vs
``evidence_gap``, tiers, group spreads, a node timeline) rather than a flat list
of counts: the model cannot tell a weak knowledge point from an unmeasured one if
the card hands it a single merged ranking.  The fallback (:func:`rules_answer`)
answers the question that was asked — a count question gets a count, not a report.

Owner: R3.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from knowflow.config import get_settings
from knowflow.diagnosis.statuses import LABELS, SUPPORT

from . import audit as _audit
from .client import ChatClient, LLMError, build_client
from .contract import forbidden_text
from .guard import ID, NUMBER
from .intent import classify_intent, guide_block
from .retrieval import select_sources
from .ui_guide import NUMERIC_LABELS, webui_guide

LOGGER = logging.getLogger(__name__)

MAX_ANSWER = _audit.MAX_ANSWER
# One retry, then give the answer back to the rule path: a user waiting on a
# chat bubble must never sit through three timeouts.
RETRY_SLEEP_SECONDS = 0.6
MAX_CALLS = 3
MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 2400
MAX_HISTORY_ITEM = 600

SYSTEM_PROMPT = f"""你是 KnowFlow 的「AI 学伴」，一位懂初中数学、也带过班的老师。教师或学生拿着这份学情来问你，你要像一个了解课堂的人那样回答，而不是把统计表念一遍。

一、事实从哪里来
A. 学习者数据——人数、比例、掌握度、覆盖率、薄弱／较好／较差／待评分／核验人数、各类计数，以及学生、知识点、题目编号——只能来自 FACTS。FACTS 里没有就直说“这份数据里没有”，不估算、不推算、不编造。也不要把已经算好的掌握度、覆盖率再算一遍或换个说法重报：程序负责数字，你负责解释。状态名称以 status_label 为准：掌握、较好、较差、薄弱；较好不等于全对，较差不等于零分，颜色不参与判断。
B. 学科知识——概念、方法、例题思路——可以正常讲，可以用 FACTS.sources 里的课标原文、学习卡和题面；但不能借学科知识编造任何学生数据、分数或排名。

二、怎么分析（先想清楚，再动笔）
1. 分清三类内容：事实（数据里明确记录的）、推断（由几条事实合理推导，要用“这可能说明”“从现有记录看”“一个值得注意的信号是”这类说法）、未知（证据不够，要明确说缺什么）。
2. 下面几组不能混为一谈：
   - 覆盖率低，不等于学生能力差；
   - 待评分／核验，不等于没有掌握；
   - 薄弱人数多，不等于全班都要补课；
   - 某个知识点没有评分记录，不等于学生没学过；
   - 有答题记录，也不等于掌握情况已经可靠；
   - “有评分但太少”（FACTS 里的 insufficient）和“一条记录都没有”（unobserved）都不是“没掌握”，但两者也不是一回事，需要分清时就说清是哪一种；
   - 一个知识点的“薄弱／较差”状态和“待评分／核验”状态是两件事，不能合成一句“都比较薄弱”。
3. 不要用单一指标推出超出证据的结论。数据撑不住一个判断时，把话说回来：“目前能确定的是……，暂时还不能据此判断……，需要补的是……”。
4. FACTS.intent 说明这次问的是哪一类问题，FACTS.focus 是问题点名的对象。FACTS.class.weak_signal 与 FACTS.class.evidence_gap 已经把“有薄弱证据”和“只是缺记录”分开了，别让它们在同一句里混着说。FACTS.lookup 是程序已经定位好的一次数据查询，直接把那个数说出来。

三、怎么表达
- 先给最重要的判断，再给支撑；不要一上来报指标，也不要按顺序把指标念一遍。
- 不要固定段落模板（“结论”“知识点上”“建议教学动作”这类小标题都不要），也不要在每次回答末尾都加建议——只问一个事实时就只回答事实。
- 尽量说知识点名称，编号只在需要精确定位时出现一次；题目编号只在教师确实要去找题时才给。
- 用自然、准确的中文，像同事讨论教学；不长篇堆术语，不为显得专业而用术语。
- 篇幅跟着问题走：简单问题一两句，综合问题才展开。不要重复用户已经知道的信息。
- 回答显示在纯文本气泡里：不要用 Markdown（不要 **、#、- 列表符号），分段用换行。
- 不输出 URL、代码块、学生姓名或原始作答；不输出字段名（如 needs_consolidation、seq、coverage）。
- 读者是教师时，可以用教学里的说法（巩固、补测、分层、课堂节奏）；读者是学生时用口语，一次只推进一步。

四、红线（与建议语言层一致）：{forbidden_text()}。
"""

HISTORY_RULE = """多轮对话的边界：
- 历史（用户与学伴的旧回答）只能用来理解指代和上下文，不是事实来源。
- 旧回答里的数字、比例、状态与结论不能自动当作当前事实；引用事实只以本轮 FACTS 为准。
- FACTS.dialogue.supplement 是用户补充的信息：可以引用，但要说明来源，不能当作数据库已更新，也不能与统计数字相加。
- 出现 FACTS.dialogue.conflicts 时，先说明现有记录是多少，再问对方是否指另一批人；不要沿用冲突的数字当事实。
- FACTS.dialogue.clarify 为真时，先问清是哪个知识点或学生，不要猜。"""


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
    return state.get("status") in SUPPORT


def _audience(snapshot: dict) -> str:
    """Who is reading. Unknown callers get the student wording: an answer key must
    never leak just because a snapshot had no viewer attached."""

    viewer = (snapshot.get("meta") or {}).get("viewer") or {}
    return "teacher" if viewer.get("role") == "teacher" else "student"


def _name_hit(message: str, name: str) -> bool:
    """Does the question name this knowledge point in ordinary words?

    Teachers say "列方程" rather than the full 课标 name, so the first three
    characters and any four-character window count as a hit.  A hit only adds
    context to the fact card; it never invents a fact.
    """

    if not name:
        return False
    if name in message:
        return True
    if name[:3] in message:
        return True
    return any(
        name[index : index + 4] in message for index in range(max(0, len(name) - 3))
    )


def _short_name(name: str) -> str:
    """A knowledge name a teacher would actually say.

    课标 names run long ("运用不等式性质求解，负数乘除时正确改变方向"); the first
    clause is the part people use in a sentence.  This only shortens a display
    name — the full name stays in the fact card and the ID is unchanged.
    """

    head = (name or "").split("，")[0].strip()
    return head or name


def _knowledge_rows(names: dict[str, str], distribution: list[dict]) -> list[dict]:
    """Every knowledge point with its counts, kept flat and unsorted by "badness".

    Sorting by ``weak + insufficient`` is what made the old card rank K-06 (mostly
    unmeasured) above K-05 (mostly weak); the model must see the components, not
    one merged rank.
    """

    return [
        {
            "id": item["knowledge_id"],
            "name": names.get(item["knowledge_id"], item["knowledge_id"]),
            "short": _short_name(names.get(item["knowledge_id"], item["knowledge_id"])),
            "weak": item["weak_count"],
            "mixed": item.get("mixed_count", 0),
            # PR #33 的稀疏评分状态：0<n<证据门槛时全对为较好、有错为较差。
            # 二者与 weak/mixed 互斥，单独成桶，不能并进"薄弱"里说。
            "sparse_good": item.get("sparse_good_count", 0),
            "sparse_poor": item.get("sparse_poor_count", 0),
            "insufficient": item["insufficient_count"],
            "unobserved": item.get("unobserved_count", 0),
            "mastered": item["mastered_count"],
            "not_applicable": item.get("not_applicable_count", 0),
            "student_count": item.get("student_count", 0),
            # 口径：每个学生在该知识点上只有一个状态（diagnosis/profiles.py），
            # 所以 insufficient 与 unobserved 互斥，可以相加；not_applicable
            # （本节点没有可测题）不属于"学习者缺口"，不计入。
            "unknown": item["insufficient_count"] + item.get("unobserved_count", 0),
            "observed": item["observed_student_count"],
            "mean_mastery": item["mean_mastery"],
        }
        for item in distribution
    ]


def _tier_summary(tiers: list[dict]) -> dict:
    """Aggregate the descriptive groupings; never present them as ability tiers."""

    if not tiers:
        return {}
    ordered = sorted(tiers, key=lambda item: -len(item["student_ids"]))
    multi = sum(1 for item in tiers if len(item["student_ids"]) >= 2)
    largest = len(ordered[0]["student_ids"])
    return {
        "count": len(tiers),
        "multi_student": multi,
        "largest": largest,
        "top": [
            {
                "label": item["label"],
                "students": len(item["student_ids"]),
                "focus": item["suggested_focus"],
            }
            for item in ordered[:3]
        ],
        # The counts are repeated in prose on purpose: a model discussing group
        # sizes reads the sentence next to the topic more reliably than it
        # cross-references three separate numeric fields.
        "note": (
            f"共 {len(tiers)} 个描述性分组，其中 {multi} 组是 2 人以上，最大一组 {largest} 人；"
            "这是按薄弱知识点组合的归组，不是能力分层，覆盖不足时不能据此分班。"
        ),
    }


def _group_summary(snapshot: dict, class_profile: dict, names: dict[str, str]) -> dict:
    """Between-group spreads, labelled as description rather than ability."""

    group_ids = sorted({student["group_id"] for student in snapshot["students"]})
    counts = {
        group_id: sum(1 for s in snapshot["students"] if s["group_id"] == group_id)
        for group_id in group_ids
    }
    spreads: list[dict] = []
    for row in class_profile.get("group_differences") or []:
        values = {
            item["group_id"]: item["mean_mastery"]
            for item in row.get("groups") or []
            if item.get("mean_mastery") is not None
        }
        if len(values) < 2:
            continue
        spreads.append(
            {
                "knowledge_id": row["dimension"],
                "name": names.get(row["dimension"], row["dimension"]),
                "values": values,
                "spread": round(max(values.values()) - min(values.values()), 2),
            }
        )
    spreads.sort(key=lambda item: -item["spread"])
    return {
        "ids": group_ids,
        "students": counts,
        "differences": spreads[:3],
        "note": "同一节点内的描述性差异；题目覆盖与证据量不同，不推断能力高低或教学因果。",
    }


def _timeline(snapshot: dict, names: dict[str, str]) -> list[dict]:
    """One row per node, for "最近有没有变化" questions.

    Nodes teach different objectives, so this supports "the observed scope moved",
    not "the students improved".  The note says so before the model can overclaim.
    """

    rows: list[dict] = []
    for node in snapshot["nodes"]:
        class_profile = (snapshot.get("classes") or {}).get(node["node_id"], {}).get("ALL")
        if not class_profile:
            continue
        coverage = class_profile.get("coverage_summary") or {}
        distribution = class_profile.get("knowledge_distribution") or []
        leaders = sorted(
            (item for item in distribution if item["weak_count"] > 0),
            key=lambda item: -item["weak_count"],
        )[:2]
        rows.append(
            {
                "node": node["node_id"],
                "date": node.get("date"),
                "objectives": len(node.get("taught_objective_ids") or []),
                "students": class_profile["student_count"],
                "mean_coverage": coverage.get("mean_ratio"),
                "students_with_insufficient_evidence": coverage.get(
                    "students_with_insufficient_evidence"
                ),
                "weak_leaders": [
                    {
                        "id": item["knowledge_id"],
                        "name": names.get(item["knowledge_id"], item["knowledge_id"]),
                        "weak": item["weak_count"],
                    }
                    for item in leaders
                ],
            }
        )
    return rows


def _resolve_lookup(
    *,
    intent: dict,
    message: str,
    class_facts: dict | None,
    student_facts: dict | None,
    focus_knowledge: list[dict],
    rows: dict[str, dict],
) -> dict | None:
    """Turn a count question into the exact number the program already computed.

    The model is told to answer ``facts.lookup`` directly, and the fallback prints
    it verbatim, so "全班有多少人" cannot become a page of analysis in either path.

    Returns ``None`` when the question asks for a count that is *not* the class
    size — "有多少人掌握" is a question about a knowledge point, and answering
    "全班 40 人" would be a confident answer to a different question.
    """

    if intent.get("primary") != "lookup" and intent.get("form") != "how_many":
        return None
    wants_records = any(word in message for word in ("完成", "做了", "做过", "作答", "交"))
    if student_facts and wants_records:
        records = student_facts.get("records") or {}
        if records:
            return {
                "kind": "student_records",
                "label": f"{student_facts['id']} 在这个节点的作答记录",
                "asked": "attempted",
                "value": records.get("attempted"),
                "detail": records,
            }
    mastery_words = ("掌握", "薄弱", "证据", "不会", "学会", "学得", "没学好")
    asks_about_mastery = any(word in message for word in mastery_words)
    if focus_knowledge:
        row = rows.get(focus_knowledge[0]["id"]) if class_facts else None
        if row is None:
            # A named knowledge point we cannot count: better to say so than to
            # answer with an unrelated number.
            return None
        if any(word in message for word in ("薄弱", "不会", "差")):
            asked = "weak"
        elif any(word in message for word in ("证据", "待观察", "没测", "缺")):
            asked = "insufficient"
        elif any(word in message for word in ("掌握", "会了", "学会")):
            asked = "mastered"
        else:
            asked = "observed"
        return {
            "kind": "knowledge_counts",
            "label": f"{row['name']} 的人数分布",
            "asked": asked,
            "value": row[asked],
            "knowledge": row,
        }
    if asks_about_mastery:
        return None
    if class_facts:
        return {
            "kind": "class_students",
            "label": "全班人数",
            "asked": "students",
            "value": class_facts["students"],
        }
    return None


# --- 多轮对话：指代解析、用户补充、冲突 ------------------------------------
#
# 历史只用来回答"他在说哪个对象"，从不提供事实：指代解析出一个 K-/S- 编号后，
# 数字仍然从当前快照的行里取。用户自己补充的数量属于"用户提供"，可以带归属地
# 复述，但既不算数据库更新，也不进入事实白名单。

_ENTITY_REFERENCE = re.compile(
    r"(它|该知识点|该学生|这个?知识点|那个?知识点|这个?学生|那个?学生|上述|"
    r"刚才(?:提到|说)的|前面(?:提到|说)的|这几个|那几个|这些(?:学生|同学)|"
    r"这\s*\d+\s*[个名位]?\s*(?:人|学生|同学)|"
    r"这\s*[零〇一二两三四五六七八九十百千万]+\s*[个名位]?\s*(?:人|学生|同学))"
)
_GROUP_REFERENCE = re.compile(
    r"这\s*(?P<count>\d+|[零〇一二两三四五六七八九十百千万]+)\s*[个名位]?\s*(?:人|学生|同学)"
)
_SUPPLEMENT = re.compile(
    r"(我(?:刚刚|刚才|刚)?(?:又|还)?(?:统计|测|登记|补充|记录|数|点)到?|补充一下|另外(?:还)?有)"
)


def _turn_text(turn: dict) -> str:
    """History arrives as ``{"role","text"}`` from the browser and as
    ``{"role","content"}`` after :func:`normalize_history`; both are accepted."""

    value = turn.get("content") or turn.get("text") or ""
    return value if isinstance(value, str) else ""


def _history_target(history: list[dict], names: dict[str, str], students: dict) -> dict | None:
    """The most recent knowledge point / student the conversation mentioned."""

    for turn in reversed(history):
        for value in ID.findall(_turn_text(turn)):
            if value.startswith("K-") and value in names:
                return {"knowledge_id": value, "name": names[value], "source": "history"}
            if value.startswith("S") and value in students:
                return {"student_id": value, "source": "history"}
    return None


def _supplement(message: str, history: list[dict]) -> dict | None:
    """What the user says they measured themselves — a *source*, not a database update."""

    candidates = [message] + [
        _turn_text(turn) for turn in reversed(history) if turn.get("role") == "user"
    ]
    for text in candidates[:4]:
        if text and _SUPPLEMENT.search(text):
            return {"text": text[:120], "numbers": sorted(_audit.numbers_in(text))}
    return None


def _dialogue_facts(
    *,
    message: str,
    history: list[dict],
    target: dict | None,
    clarify: bool,
    rows: dict[str, dict],
) -> dict:
    """The dialogue-only part of the fact card: references, conflicts, supplements."""

    supplement = _supplement(message, history)
    conflicts: list[dict] = []
    if target and target.get("knowledge_id"):
        row = rows.get(target["knowledge_id"])
        if row:
            legal = _audit.knowledge_legal_counts(row)
            for match in _GROUP_REFERENCE.finditer(message):
                raw = match.group("count")
                value = int(raw) if raw.isdigit() else _audit.parse_chinese_number(raw)
                if value is None or value in legal:
                    continue
                conflicts.append(
                    {
                        "said": value,
                        "knowledge_id": row["id"],
                        "name": row["short"],
                        "actual": {
                            key: row[key]
                            for key in ("weak", "mixed", "insufficient", "unobserved", "mastered")
                        },
                    }
                )
    dialogue: dict = {}
    if history:
        dialogue["history_turns"] = len(history)
    if target:
        dialogue["referenced"] = target
    if supplement:
        dialogue["supplement"] = supplement
    if conflicts:
        dialogue["conflicts"] = conflicts
    if clarify:
        dialogue["clarify"] = True
    return dialogue


def build_facts(
    snapshot: dict,
    message: str,
    context: dict | None = None,
    knowledge: dict | None = None,
    history: list[dict] | None = None,
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

    history = history or []
    message_entity = any(
        (value.startswith("K-") and value in names)
        or (value.startswith("S") and value in students)
        for value in mentioned
    )
    referential = bool(_ENTITY_REFERENCE.search(message))
    known_student = context.get("student_id") in students
    history_target = None
    if referential and not message_entity and not known_student:
        history_target = _history_target(history, names, students)
        if history_target and history_target.get("student_id"):
            student_id = history_target["student_id"]
    clarify = referential and not message_entity and not known_student and history_target is None

    named_knowledge = [
        {"id": knowledge_id, "name": name}
        for knowledge_id, name in names.items()
        if knowledge_id in mentioned or _name_hit(message, name)
    ]
    if history_target and history_target.get("knowledge_id"):
        knowledge_id = history_target["knowledge_id"]
        if all(item["id"] != knowledge_id for item in named_knowledge):
            named_knowledge.append(
                {"id": knowledge_id, "name": names[knowledge_id], "via": "history"}
            )
    # Only a student *named in the question* makes it an individual-student
    # question.  A logged-in student's context id must not turn "班上整体学得
    # 怎么样" into a question about that one student.
    mentioned_student = any(
        value.startswith("S") and value in students for value in mentioned
    )
    intent = classify_intent(
        message,
        student_named=mentioned_student,
        knowledge_named=bool(named_knowledge),
    )

    node = nodes[node_id]
    facts: dict = {
        "dataset": {
            "id": snapshot["meta"]["dataset_id"],
            "subject": snapshot["meta"]["subject"],
            "grade": snapshot["meta"]["grade"],
        },
        "node": {"id": node_id, "date": node["date"], "objectives": len(node["taught_objective_ids"])},
        "intent": {
            "primary": intent["primary"],
            "label": intent["label"],
            "all": intent["all"],
            "labels": intent["labels"],
            "form": intent["form"],
            "teach": intent["teach"],
        },
        "focus": {
            "knowledge": named_knowledge,
            "student": student_id,
        },
    }

    classes = snapshot["classes"].get(node_id, {})
    class_profile = classes.get(group_id) if group_id in classes else classes.get("ALL")
    rows: dict[str, dict] = {}
    if class_profile:
        distribution = class_profile["knowledge_distribution"]
        rows = {
            item["knowledge_id"]: row
            for item, row in zip(
                distribution,
                _knowledge_rows(names, distribution),
                strict=False,
            )
        }
        # 较差（sparse_poor）按 PR #33 的口径也属于"需要支持"的状态：排序与
        # weak_signal 都用 SUPPORT（薄弱 + 较差），否则"2 对 1 错"这类知识点会被
        # 只按 weak 数的旧排序挤到后面。
        weak_signal = sorted(
            (row for row in rows.values() if (row["weak"] + row["sparse_poor"]) > 0),
            key=lambda row: (-(row["weak"] + row["sparse_poor"]), -row["observed"]),
        )[:3]
        evidence_gap = sorted(
            (
                row
                for row in rows.values()
                if (row["insufficient"] + row["unobserved"]) > 0
            ),
            # "有记录但太少" is the actionable group (a re-test fixes it), so it
            # ranks above "一条记录都没有"; unobserved stays visible in the row and
            # gets its own list below so a fully unrecorded knowledge point can
            # still reach the fallback answer.
            key=lambda row: (-row["insufficient"], -row["unobserved"]),
        )[:3]
        no_record = sorted(
            (row for row in rows.values() if row["unobserved"] > 0),
            key=lambda row: -row["unobserved"],
        )[:3]
        facts["class"] = {
            "id": class_profile["class_id"],
            "students": class_profile["student_count"],
            "coverage": class_profile["coverage_summary"],
            "knowledge": list(rows.values()),
            "weak_signal": weak_signal,
            "evidence_gap": evidence_gap,
            "no_record": no_record,
            "common_issues": [
                {
                    "type": issue["issue_type"],
                    "knowledge_id": issue["knowledge_id"],
                    "knowledge_name": names.get(issue["knowledge_id"], issue["knowledge_id"]),
                    "statement": issue["statement"][:100],
                    "students": issue["student_count"],
                }
                for issue in class_profile["common_issues"][:4]
            ],
            "tiers": _tier_summary(class_profile.get("tiers") or []),
            "groups": _group_summary(snapshot, class_profile, names),
        }
    facts["timeline"] = _timeline(snapshot, names)
    if facts["timeline"]:
        facts["timeline_note"] = (
            "节点之间教学目标不同：跨节点只能说明观测范围的变化，不能当作学生进步或退步。"
        )

    profile = snapshot["profiles"].get(node_id, {}).get(student_id) if student_id else None
    if profile:
        states = profile["knowledge_states"]
        chosen = sorted(states, key=lambda state: not _weak(state))[:6]
        # A named knowledge point must bring its own state even when it is not
        # among the six the card shows by default — otherwise "K-07 我掌握得怎么样"
        # gets answered from the course content alone.
        named_ids = {item["id"] for item in named_knowledge}
        for state in states:
            if state["knowledge_id"] in (mentioned | named_ids) and state not in chosen:
                chosen.append(state)
        chosen = chosen[:8]
        plan = snapshot["recommendations"].get(node_id, {}).get(student_id, {}).get("plan", [])[:3]
        status_counts: dict[str, int] = {}
        for state in states:
            status_counts[state["status"]] = status_counts.get(state["status"], 0) + 1
        stats = (snapshot.get("stats") or {}).get(node_id, {}).get(student_id) or {}
        facts["student"] = {
            "id": student_id,
            "group": profile["group_id"],
            "coverage": {
                "observed": profile["coverage"]["observed_items"],
                "applicable": profile["coverage"]["applicable_items"],
                "ratio": profile["coverage"]["ratio"],
                "scope_known": profile["coverage"]["scope_known"],
            },
            # 原始状态名计数（confirmed_weak / sparse_poor / …）：``_state_counts``
            # 与 ``audit.has_evidence_gaps`` 都按这个口径读，中文标签在 states[].status_label。
            # 合并 PR #33 时同一键曾出现两处定义（中文标签版在后、会静默覆盖），已合并为一处。
            "status_counts": {key: value for key, value in status_counts.items() if value},
            "needs_consolidation": [
                item["knowledge_id"] for item in profile["lists"]["needs_consolidation"]
            ][:5],
            "needs_observation": [
                item["knowledge_id"] for item in profile["lists"]["needs_observation"]
            ][:5],
            "needs_coverage": [
                item["knowledge_id"] for item in profile["lists"].get("needs_coverage", [])
            ][:5],
            "states": [
                {
                    "id": state["knowledge_id"],
                    "name": names.get(state["knowledge_id"], state["knowledge_id"]),
                    "status": state["status"],
                    "status_label": LABELS.get(state["status"], "待核验"),
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
            "records": {
                key: stats.get(key)
                for key in ("assigned", "attempted", "graded", "pending", "completion")
                if key in stats
            },
        }
        mentioned |= {item["issue_id"] for item in profile["issues"]}
        mentioned |= {material_id for item in plan for material_id in item["material_ids"]}

    knowledge_ids = {value for value in mentioned if value.startswith("K-") and value in names}
    knowledge_ids |= {item["id"] for item in named_knowledge}
    if facts.get("student"):
        knowledge_ids |= set(facts["student"]["needs_consolidation"])
        knowledge_ids |= set(facts["student"]["needs_observation"])
        knowledge_ids |= set(facts["student"].get("needs_coverage") or [])
        knowledge_ids |= {state["id"] for state in facts["student"]["states"]}
    if not knowledge_ids and facts.get("class"):
        knowledge_ids = {item["id"] for item in facts["class"]["knowledge"][:3]}
    facts["knowledge"] = [
        {
            "id": knowledge_id,
            "name": names[knowledge_id],
            "short": _short_name(names[knowledge_id]),
            "objective_id": next(
                item["objective_id"]
                for item in kb["knowledge"]
                if item["knowledge_id"] == knowledge_id
            ),
        }
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
    facts["lookup"] = _resolve_lookup(
        intent=intent,
        message=message,
        class_facts=facts.get("class"),
        student_facts=facts.get("student"),
        focus_knowledge=named_knowledge,
        rows=rows,
    )
    dialogue = _dialogue_facts(
        message=message,
        history=history,
        target=history_target,
        clarify=clarify,
        rows=rows,
    )
    if dialogue:
        facts["dialogue"] = dialogue

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
    """Numbers/IDs an answer may cite as *learner facts*.

    The whitelist starts empty on purpose: teaching numbers (0–10, "第 3 步",
    "14 道题") are admitted by context in :mod:`audit`, so pre-seeding small
    numbers here only had one effect — "有 3 人薄弱" passed even when the card
    never said 3.

    The ``dialogue`` block is skipped: it carries numbers the *user* said
    ("你说的 17 人"), and those must never be licensed as database facts.  They
    are admitted only in attributed sentences, via ``user_numbers``.
    """

    numbers: set[float] = set()
    ids: set[str] = set()
    payload = {key: value for key, value in facts.items() if key != "dialogue"}
    _collect(payload, numbers, ids)
    _count_lists(payload, numbers)
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


# --- 校验：数字、编号、证据边界 --------------------------------------------
#
# The implementation lives in :mod:`knowflow.llm.audit` (one place for "is this a
# learner fact or a teaching quantity").  These wrappers keep the module's public
# names stable for callers and tests that import them from ``chat``.


def number_audit(
    answer: str,
    numbers: set[float],
    user_numbers: set[float] | None = None,
    *,
    names: tuple[str, ...] = (),
) -> dict:
    """Split the numbers of an answer into data claims and teaching numbers."""

    return _audit.number_audit(answer, numbers, user_numbers, names=names)


def validate_answer(
    answer: str,
    numbers: set[float],
    ids: set[str],
    user_numbers: set[float] | None = None,
    *,
    names: tuple[str, ...] = (),
) -> list[str]:
    """Every reason this answer may not be shown as-is (empty list = accepted)."""

    return _audit.validate_answer(answer, numbers, ids, user_numbers, names=names)


def _ratio(value: Any) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "—"


def _state_counts(facts: dict) -> dict:
    counts = (facts.get("student") or {}).get("status_counts") or {}
    return {
        "weak": counts.get("confirmed_weak", 0) + counts.get("likely_weak", 0),
        "sparse_poor": counts.get("sparse_poor", 0),
        "sparse_good": counts.get("sparse_good", 0),
        "mixed": counts.get("mixed_performance", 0),
        "insufficient": counts.get("insufficient_evidence", 0),
        "unobserved": counts.get("unobserved", 0),
        "mastered": counts.get("confirmed_mastered", 0) + counts.get("likely_mastered", 0),
    }


def build_trace(
    facts: dict,
    mode: str,
    source: str,
    fallback_reason: str | None = None,
    *,
    audience: str = "student",
    history_turns: int = 0,
    attempts: int = 0,
    problems: list[str] | None = None,
    failure_kind: str | None = None,
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
    intent = facts.get("intent") or {}

    if intent.get("primary"):
        form_labels = {
            "yes_no": "是/否判断",
            "how_many": "问数量",
            "which": "问哪些",
            "how_to": "问怎么做",
            "open": "开放提问",
        }
        steps.append(
            {
                "label": "理解问题",
                "detail": f"意图：{intent.get('label')}；形式："
                f"{form_labels.get(intent.get('form'), '开放提问')}",
            }
        )

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
                    f"待评分／核验 {len(student['needs_observation'])} 个，"
                    f"未覆盖 {len(student.get('needs_coverage') or [])} 个"
                ),
            }
        )
        counts = _state_counts(facts)
        steps.append(
            {
                "label": "区分证据",
                "detail": (
                    f"薄弱 {counts['weak']} 个、较差 {counts['sparse_poor']} 个、"
                    f"待评分／核验 {counts['insufficient']} 个、"
                    f"未覆盖 {counts['unobserved']} 个；待评分／核验不等于没掌握"
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
        coverage = class_facts.get("coverage") or {}
        steps.append({"label": "定位对象", "detail": f"班级 {class_facts['id']} · 节点 {node_id}"})
        steps.append(
            {
                "label": "读取现状",
                "detail": (
                    f"{class_facts['students']} 名学生；平均覆盖 {_ratio(coverage.get('mean_ratio'))}；"
                    f"{coverage.get('students_with_insufficient_evidence', 0)} 人待评分／核验"
                ),
            }
        )
        weak = class_facts.get("weak_signal") or []
        gaps = class_facts.get("evidence_gap") or []
        steps.append(
            {
                "label": "区分证据",
                "detail": (
                    "有薄弱证据："
                    + ("、".join(f"{item['name']}（{item['weak']} 人）" for item in weak) or "无")
                    + "；只有证据缺口："
                    + ("、".join(item["name"] for item in gaps) or "无")
                ),
            }
        )
        lookup = facts.get("lookup")
        if lookup:
            steps.append(
                {
                    "label": "查数",
                    "detail": f"{lookup['label']}：{lookup['value']}（程序计算，直接引用）",
                }
            )
        for item in weak[:4]:
            evidence.append(
                {
                    "kind": "class_state",
                    "id": item["id"],
                    "text": f"{item['name']} · 薄弱 {item['weak']} 人 / "
                    f"较好 {item['sparse_good']} 人 / 较差 {item['sparse_poor']} 人 / "
                    f"待评分／核验 {item['insufficient']} 人 / 已观察 {item['observed']} 人",
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
        tiers = class_facts.get("tiers") or {}
        if tiers.get("count"):
            evidence.append(
                {
                    "kind": "tiers",
                    "id": None,
                    "text": f"描述性分组 {tiers['count']} 组，最多一组 {tiers['largest']} 人；不是能力分层",
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

    if facts.get("timeline"):
        steps.append(
            {
                "label": "查时间线",
                "detail": "、".join(
                    f"{row['node']}（{row['date']}）覆盖 {_ratio(row['mean_coverage'])}"
                    for row in facts["timeline"]
                )
                + "；跨节点只描述观测范围，不作进步结论",
            }
        )

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
                "先给判断或直接回答，少列数字，按意图取舍"
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
            "claims_checked": True,
            "source": source,
            "fallback_reason": fallback_reason,
            "failure_kind": failure_kind,
            "problems": list(problems or []),
            "attempts": attempts,
            "intent": intent.get("primary"),
            "intent_label": intent.get("label"),
            "audience": audience,
            "history_turns": history_turns,
            "sources": len(sources),
        },
        "note": "展示事实卡、课程内容与规则步骤；不包含模型隐藏思维链。",
    }


# --- 规则兜底：按问题类型组织，而不是套同一段模板 ---------------------------


def _label(row: dict) -> str:
    """The display name of a knowledge row inside a sentence."""

    return row.get("short") or row.get("name") or row.get("id", "")


def _support(row: dict) -> int:
    """How many students this knowledge point needs support for.

    PR #33 的口径：``SUPPORT = WEAK | {"sparse_poor"}``——薄弱与较差都该排进
    "先处理"的一侧，但它们在报告里仍是两个状态，不能合成一个"薄弱"数字。
    """

    return (row.get("weak") or 0) + (row.get("sparse_poor") or 0)


def _support_phrase(row: dict) -> str:
    """``薄弱 3 人、较差 2 人`` — only the buckets that are actually non-zero."""

    parts = []
    if row.get("weak"):
        parts.append(f"薄弱 {row['weak']} 人")
    if row.get("sparse_poor"):
        parts.append(f"较差 {row['sparse_poor']} 人")
    return "、".join(parts)


def _lookup_answer(facts: dict) -> str:
    lookup = facts["lookup"]
    kind = lookup["kind"]
    if kind == "class_students":
        class_id = (facts.get("class") or {}).get("id") or ""
        scope = "全班" if class_id in {"", "ALL"} else class_id
        return f"{scope}共 {lookup['value']} 人。"
    if kind == "knowledge_counts":
        row = lookup["knowledge"]
        labels = {
            "weak": "薄弱",
            "sparse_poor": "较差",
            "insufficient": "待评分／核验",
            "mastered": "已掌握",
            "observed": "有作答记录",
        }
        return f"{_label(row)}：{lookup['value']} 人{labels.get(lookup['asked'], '有记录')}。"
    if kind == "student_records":
        detail = lookup["detail"]
        return (
            f"{facts['student']['id']} 在这个节点共布置 {detail.get('assigned', 0)} 题，"
            f"已完成 {detail.get('attempted', 0)} 题，其中 {detail.get('graded', 0)} 题已评分。"
        )
    return f"{lookup['label']}：{lookup['value']}。"


def _focus_rows(facts: dict) -> list[dict]:
    """The knowledge points the question named, with their class counts."""

    rows = (facts.get("class") or {}).get("knowledge") or []
    by_id = {row["id"]: row for row in rows}
    return [
        by_id[item["id"]]
        for item in (facts.get("focus") or {}).get("knowledge", [])
        if item["id"] in by_id
    ]


def _gap_sentence(gaps: list[dict], no_record: list[dict]) -> str:
    """The one gap sentence the fallback is allowed to say.

    ``evidence_gap`` is ranked by ``insufficient`` (a re-test fixes it), which used
    to hide a knowledge point where *nobody* has a record — often the bigger
    finding.  Whichever number is larger leads; the other may be added once.
    """

    zero = no_record[0] if no_record else None
    primary = gaps[0] if gaps else None
    if zero and (primary is None or zero["unobserved"] > primary["insufficient"]):
        text = f"{_label(zero)}有 {zero['unobserved']} 人完全没有作答记录"
        if primary and primary["id"] != zero["id"]:
            text += f"，{_label(primary)}有 {primary['insufficient']} 人待评分／核验"
        return text
    if primary:
        text = f"{_label(primary)}有 {primary['insufficient']} 人待评分／核验"
        if primary["unobserved"]:
            text += f"、{primary['unobserved']} 人没有作答记录"
        return text
    return "证据还不够"


def _class_paragraphs(facts: dict, primary: str | None) -> list[str]:
    class_facts = facts.get("class") or {}
    coverage = class_facts.get("coverage") or {}
    students = class_facts.get("students", 0)
    weak = class_facts.get("weak_signal")
    if weak is None:
        # 只有 knowledge 行的裁剪事实卡（上游或测试）也要能找出需要支持的知识点。
        weak = [row for row in (class_facts.get("knowledge") or []) if _support(row) > 0]
    gaps = class_facts.get("evidence_gap") or []
    no_record = class_facts.get("no_record") or []
    insufficient = coverage.get("students_with_insufficient_evidence")
    below_half = coverage.get("students_below_0_5")
    form = (facts.get("intent") or {}).get("form")
    focus = _focus_rows(facts)

    def names_of(items: list[dict], limit: int = 2) -> str:
        return "、".join(_label(item) for item in items[:limit])

    # 是/否型知识点问题：先把“是不是没掌握”正面回答掉。
    if form == "yes_no" and focus:
        row = focus[0]
        parts = [f"{row['observed']} 人留下过评分"]
        detail = []
        if row["mastered"]:
            detail.append(f"{row['mastered']} 人已掌握")
        if row.get("sparse_good"):
            detail.append(f"{row['sparse_good']} 人较好")
        if row["weak"]:
            detail.append(f"{row['weak']} 人薄弱")
        if row.get("sparse_poor"):
            detail.append(f"{row['sparse_poor']} 人较差")
        if row["insufficient"]:
            detail.append(f"{row['insufficient']} 人待评分／核验")
        counts = "，其中 " + "、".join(detail) if detail else ""
        if row["unobserved"]:
            counts += f"，另有 {row['unobserved']} 人没有作答记录"
        return [
            f"不是。{_label(row)}目前 {parts[0]}{counts}。",
            "待评分／核验说明还没测出来，不等于没有掌握；要把“全班都没掌握”说清楚，得先补齐这些记录。",
        ]

    if primary == "strategy":
        parts = []
        if weak:
            parts.append(
                f"可以按“先补证据、再巩固”来排：{_label(weak[0])}{_support_phrase(weak[0])}"
                "，可以直接安排针对性练习。"
            )
        if gaps or no_record:
            parts.append(f"{_gap_sentence(gaps, no_record)}，先用一节课做基线题，别急着讲难题。")
        parts.append("一轮之后看这几块的证据有没有变多，再决定要不要加深。")
        return parts

    if primary == "group":
        tiers = class_facts.get("tiers") or {}
        groups = class_facts.get("groups") or {}
        if students and insufficient is not None:
            lead = (
                f"现在直接按掌握度分层，证据还不够：{students} 人里 {below_half} 人覆盖率不到一半，"
                f"{insufficient} 人待评分／核验，而覆盖率低并不等于水平低。"
            )
        else:
            lead = "现在直接按掌握度分层，证据还不够。"
        parts = [lead]
        if weak:
            parts.append(
                "能先做的是按薄弱知识点分组："
                + "、".join(f"{_label(item)} {_support(item)} 人" for item in weak[:2])
                + "，这属于按知识点补差，不是能力分层。"
            )
        if groups.get("differences"):
            spread = groups["differences"][0]["spread"]
            parts.append(f"两个群体在同一知识点上的平均掌握度最多相差 {spread}，看不出稳定分层。")
        if tiers.get("count"):
            parts.append("现有的分组只是把薄弱知识点相同的同学归到一起，等基线题补完再看是否真有差异。")
        return parts

    if primary == "progress":
        timeline = facts.get("timeline") or []
        if len(timeline) >= 2:
            first, last = timeline[0], timeline[-1]
            return [
                (
                    f"现在只有两个节点：{first['node']}（{first['date']}）平均观测覆盖 "
                    f"{_ratio(first['mean_coverage'])}，{last['node']}（{last['date']}）是 "
                    f"{_ratio(last['mean_coverage'])}。"
                ),
                "两个节点教的目标点不同，这只能说明观测范围变了，不能当作学生进步或退步。",
                "要判断趋势，需要在同一批知识点上再测一次。",
            ]
        return ["这份数据只有一个节点，看不出趋势；要在同一批知识点上再测一次才能比较。"]

    if primary == "knowledge":
        if weak:
            lead = (
                f"按现有证据，最需要关注的是{_label(weak[0])}（{_support_phrase(weak[0])}）"
                + (f"，{names_of(weak[1:])}也有偏弱学生" if len(weak) > 1 else "")
            )
        else:
            lead = "现有数据里还没有能确认的薄弱或较差知识点"
        parts = [lead + "。"]
        if gaps or no_record:
            parts.append(f"{_gap_sentence(gaps, no_record)}，这些是缺记录，还不能算薄弱。")
        parts.append("要排出“最薄弱”，先把待评分／核验的这几块补测一轮。")
        return parts

    # 默认：整体学情
    if students and insufficient is not None:
        lead = (
            f"这个班现在最缺的不是练习，而是能判断学情的记录：{students} 人里 "
            f"{below_half} 人覆盖率不到一半，{insufficient} 人还有知识点只有一两条评分。"
        )
    else:
        lead = "这个班目前的记录还不足以判断整体掌握情况。"
    parts = [lead]
    if weak:
        parts.append(
            f"已经需要支持的是{_label(weak[0])}：{_support_phrase(weak[0])}"
            + (f"；{names_of(weak[1:])}也偏弱" if len(weak) > 1 else "")
            + "。"
        )
    if gaps or no_record:
        parts.append(f"{_gap_sentence(gaps, no_record)}，不能当成没学会。")
    if weak:
        parts.append(f"下一步先把基线题补齐，再单独巩固{_label(weak[0])}这 {_support(weak[0])} 人。")
    else:
        parts.append("下一步先补齐基线题，再看哪些知识点真的需要巩固。")
    return parts


def _student_paragraphs(facts: dict) -> list[str]:
    student = facts["student"]
    names = {
        item["id"]: item.get("short") or item["name"]
        for item in (facts.get("knowledge") or [])
    }
    needs = student.get("needs_consolidation") or []
    pending = student.get("needs_observation") or []
    uncovered = student.get("needs_coverage") or []
    counts = _state_counts(facts)
    coverage = student.get("coverage") or {}
    if not coverage.get("applicable"):
        # "已观察到 0/0 个可测知识点" is arithmetic noise, not a finding: the node
        # has nothing measurable for this student, so say what is actually missing
        # instead of "没有明显薄弱点".  A caller that passes only the lists (no
        # coverage) also lands here.
        gap = f"，{counts['unobserved']} 个知识点都没有覆盖" if counts["unobserved"] else ""
        head = f"{student['id']} 在这个节点还没有可判断的记录{gap}；先补一次完整作答再判断。"
        return [head, *_student_actions(needs, pending, uncovered)]
    if needs:
        first = names.get(needs[0], needs[0])
        head = f"{student['id']} 现在最需要补的是{first}。"
    elif counts["insufficient"] or counts["unobserved"] or pending or uncovered:
        head = f"{student['id']} 目前的记录还不够，先补一次完整作答再判断。"
    else:
        head = f"{student['id']} 目前没有明显的薄弱点。"
    buckets = []
    if counts["weak"]:
        buckets.append(f"薄弱 {counts['weak']} 个")
    if counts["sparse_poor"]:
        buckets.append(f"较差 {counts['sparse_poor']} 个")
    if counts["insufficient"]:
        buckets.append(f"待评分／核验 {counts['insufficient']} 个")
    if counts["unobserved"]:
        buckets.append(f"未覆盖 {counts['unobserved']} 个")
    detail = "、".join(buckets) or "没有待评分／核验或未覆盖的知识点"
    parts = [
        head,
        f"已观察到 {coverage['observed']}/{coverage['applicable']} 个可测知识点，{detail}。",
        *_student_actions(needs, pending, uncovered),
    ]
    if student.get("plan"):
        parts.append("下一步按计划走：先看学习卡，再做同类练习，最后用计划里的验证标准自查。")
    return parts


def _student_actions(needs: list[str], pending: list[str], uncovered: list[str]) -> list[str]:
    """What to do next, one line per gap kind — pending work is not a wrong answer."""

    parts = []
    if pending:
        parts.append("有待评分／核验的知识点，先完成评分或核验，不追加练习。")
    if uncovered:
        parts.append("还有些知识点一条评分都没有，先布置基线题；未覆盖不等于没掌握。")
    if not needs and not pending and not uncovered:
        # 「没有列入巩固清单」不等于「证据不足」：说复核，不要说补测。
        parts.append("没有列入巩固清单的知识点，可结合已有状态轻量复核。")
    return parts


def _knowledge_paragraphs(facts: dict) -> list[str]:
    first = facts["knowledge"][0]
    objective = next(
        (item for item in facts.get("sources") or [] if item["kind"] == "objective"), None
    )
    requirement = (
        f"课程要求是“{objective['objective_text']}”。"
        if objective and objective.get("objective_text")
        else f"属于课程要求 {first['objective_id']}。"
    )
    return [
        f"{first.get('short') or first['name']}{requirement}",
        "当前数据只有课程映射，没有这个学生或这个班的作答细节。",
    ]


def _teach_paragraphs(facts: dict) -> list[str]:
    """A subject question ("K-07 怎么算") answered from the course content only."""

    sources = facts.get("sources") or []
    explain = next((item for item in sources if item["kind"] == "explain"), None)
    objective = next((item for item in sources if item["kind"] == "objective"), None)
    if explain and explain.get("body"):
        return [
            f"先看方法：{explain['body']}",
            "看完再做一道同类题，做完对照解析检查每一步，特别是容易漏的那一步。",
        ]
    if objective and objective.get("objective_text"):
        return [
            f"课程标准对这块的要求是：{objective['objective_text']}",
            "可以按这条要求先看学习卡，再做一道同类题检验。",
        ]
    return ["这份数据里还没有这个知识点的课程内容，暂时没法展开讲解。"]


def evidence_sections(facts: dict) -> bool:
    """Does this answer belong to the two-section "结论 / 依据" format?

    A single-fact answer has no second section to write.  Forcing one produced
    "依据：当前数据只有课程映射……" under "全班有多少人" — a heading that reads
    like an explanation but explains nothing, and contradicts the intent rule
    that a count question gets only the count.
    """

    intent = facts.get("intent") or {}
    if intent.get("greeting"):
        return False
    return not facts.get("lookup")


def _counts_of(row: dict) -> str:
    """The counts of one knowledge point, zero buckets omitted."""

    parts = []
    if row["weak"]:
        parts.append(f"{row['weak']} 人薄弱")
    if row.get("sparse_good"):
        parts.append(f"{row['sparse_good']} 人较好")
    if row.get("sparse_poor"):
        parts.append(f"{row['sparse_poor']} 人较差")
    if row["mixed"]:
        parts.append(f"{row['mixed']} 人表现混合")
    if row["insufficient"]:
        parts.append(f"{row['insufficient']} 人待评分／核验")
    if row["unobserved"]:
        parts.append(f"{row['unobserved']} 人没有作答记录")
    if row["mastered"]:
        parts.append(f"{row['mastered']} 人已掌握")
    return "、".join(parts) or "还没有可核对的记录"


def _reference_paragraphs(facts: dict, dialogue: dict) -> list[str] | None:
    """Answer about the knowledge point the conversation pointed at.

    "这 8 个人应该怎么安排" is a question about K-05, not about the class: the
    pronoun resolved to a knowledge point, and the counts must come from its row,
    never from the old answer that mentioned it.
    """

    target = dialogue.get("referenced") or {}
    knowledge_id = target.get("knowledge_id")
    if not knowledge_id:
        return None
    row = next(
        (
            item
            for item in (facts.get("class") or {}).get("knowledge", [])
            if item["id"] == knowledge_id
        ),
        None,
    )
    if row is None:
        return None
    if row["weak"]:
        action = f"这 {row['weak']} 人可以直接安排针对性练习。"
    elif row["unknown"]:
        action = f"先把这 {row['unknown']} 人的测评补齐，再决定讲到什么程度。"
    else:
        action = "这块可以先看学习卡，再做同类题巩固。"
    return [f"{_label(row)}目前 {_counts_of(row)}。", action]


def _conflict_paragraphs(facts: dict, conflict: dict) -> list[str]:
    """The user cited a number that the record does not support.

    One judgement (the record says otherwise) and one action (ask which group they
    mean, or go with the recorded number) — no analysis on top.
    """

    row = next(
        (item for item in (facts.get("class") or {}).get("knowledge", [])
         if item["id"] == conflict["knowledge_id"]),
        None,
    )
    said = conflict["said"]
    if row is None:
        return [f"你说的 {said} 人和现有记录对不上，先按记录里的数看，或者说明这 {said} 人的来源。"]
    detail = [f"{row['weak']} 人薄弱"] if row["weak"] else []
    if row.get("sparse_poor"):
        detail.append(f"{row['sparse_poor']} 人较差")
    if row["insufficient"]:
        detail.append(f"{row['insufficient']} 人待评分／核验")
    if row["unobserved"]:
        detail.append(f"{row['unobserved']} 人没有作答记录")
    actual = "、".join(detail) or "还没有可核对的记录"
    return [
        f"你说的 {said} 人和现有记录对不上：{_label(row)}目前有 {actual}。",
        f"如果这 {said} 人是你另外统计的，请说明来源；否则先按记录里的人数安排。",
    ]


def _supplement_note() -> str:
    return "你补充的补测情况还没有进入统计，下面的判断仍按原有记录；"


def _answer_paragraphs(facts: dict, intent: dict) -> list[str]:
    if intent.get("greeting"):
        return ["你好！我可以帮你看这个班或某个学生的学情，也可以把某道题讲清楚。"]
    if facts.get("lookup"):
        return [_lookup_answer(facts)]
    if intent.get("primary") == "lookup":
        return [
            "这个数在现有数据里查不到。如果问的是某个知识点的掌握人数，请指明是哪个知识点；"
            "如果问的是某个学生，请指明学生。"
        ]
    if intent.get("teach"):
        return _teach_paragraphs(facts)
    if facts.get("student"):
        return _student_paragraphs(facts)
    if facts.get("class"):
        return _class_paragraphs(facts, intent.get("primary"))
    if facts.get("knowledge"):
        return _knowledge_paragraphs(facts)
    return ["当前数据没有这项信息。可以换一个学生、知识点或节点再问。"]


def rules_answer(facts: dict, mode: str = "concise") -> str:
    """Deterministic answer used when the model is absent or rejected twice.

    It answers the question that was asked — a count question gets a count, a
    yes/no question gets yes or no — and it refuses to invent teaching analysis it
    cannot support.  The structure is composed per intent instead of one template,
    which is what used to make every failed call look identical.

    Dialogue state comes first: an unclear reference is *asked about*, and a number
    the user cited that contradicts the record is *corrected*, because guessing
    either one would manufacture a fact.
    """

    dialogue = facts.get("dialogue") or {}
    intent = facts.get("intent") or {}
    if dialogue.get("clarify"):
        paragraphs = ["你指的是哪个知识点或哪个学生？说一下名字或编号，我再查。"]
    elif dialogue.get("conflicts"):
        paragraphs = _conflict_paragraphs(facts, dialogue["conflicts"][0])
    else:
        reference = _reference_paragraphs(facts, dialogue)
        if reference and intent.get("primary") not in {"lookup", "student"}:
            paragraphs = reference
        else:
            paragraphs = _answer_paragraphs(facts, intent)
        if dialogue.get("supplement"):
            paragraphs[0] = _supplement_note() + paragraphs[0]

    if mode == "evidence" and evidence_sections(facts):
        conclusion = paragraphs[0]
        basis = paragraphs[1:] or ["当前数据只有课程映射，没有更多作答细节。"]
        return f"结论：{conclusion}\n依据：" + "；".join(basis).rstrip("。") + "。"
    return "\n".join(paragraph.strip() for paragraph in paragraphs if paragraph.strip())


CHAT_MODES = {"concise", "evidence"}
MODE_PROMPTS = {
    "concise": (
        "回答方式：简洁。先直接回答或先给判断，再按需要给一两点支撑；不要固定小标题，"
        "不要为了凑结构而分点；简单的数据问题一两句话就够。"
    ),
    "evidence": (
        "回答方式：证据。按两段写：第一行“结论：……”，随后“依据：……”逐条说明；"
        "依据里引用学情就用 FACTS 的数字或名称，讲做法可以引用 sources。"
        "这两段是本模式的要求，不是所有问题都要套用的模板；"
        "数据查询和寒暄只要一句话，不要为了凑格式再加“依据”。"
    ),
}

AUDIENCE_PROMPTS = {
    "student": "读者是学生：口语、少术语，一次只推进一步；讲题给思路和第一步，不直接报最终答案。",
    "teacher": "读者是教师：先给判断，再给可执行的教学动作；可以用班级数据，不必回避教学术语。",
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
    "prompt": "若 FACTS 显示待评分／核验或未覆盖，直接说明信息不足，不要推测。",
    "probe": "若 FACTS 显示未覆盖，建议做基线题；若待评分／核验，先评分或核验，不追加练习。",
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
#: Why a rejected answer was rejected; the reader deserves to know which one.
GUARD_NOTES = {
    "number": "模型这次写了事实卡里没有的数字，无法核对，已改用本地规则回答。",
    "id": "模型这次引用了不存在的编号，无法核对，已改用本地规则回答。",
    "claim": "模型这次把证据不足说成了确定结论，已改用本地规则回答。",
    "model": "模型这次的内容没通过核对，已改用本地规则回答。",
    "structure": "模型这次没有按证据格式回答，已改用本地规则回答。",
}
REWRITE_HINT = "\n\n上一次回答没有通过核对：{problems}。请改写：{advice}"


def _rewrite_advice(kinds: list[str]) -> str:
    parts = []
    if "number" in kinds:
        parts.append("学情数字只能用 FACTS 里已经算好的；建议里的数量（几道题、几分钟）不受限制")
    if "id" in kinds:
        parts.append("编号必须是 FACTS 里真实存在的")
    if "claim" in kinds:
        parts.append("不要把证据不足说成没掌握，也不要用“全班都……”下绝对结论")
    if not parts:
        parts.append("学情数字只用 FACTS 里有的，能不用就不用；教材里的做法可以照常讲")
    return "；".join(parts) + "。"


def _guard_note(kinds: list[str]) -> str:
    if not kinds:
        return GUARD_NOTES["model"]
    if len(kinds) > 1 and set(kinds) >= {"number", "id"}:
        return "模型这次给了无法核对的数字或编号，已改用本地规则回答。"
    return GUARD_NOTES.get(kinds[0], GUARD_NOTES["model"])


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
    # The interface map is navigation help, not learner data: it is sent with the
    # fact card so "在哪里看" questions get the real page/tab/button names.
    ui = webui_guide(audience, (context or {}).get("view"))
    turns = normalize_history(history)
    facts = build_facts(snapshot, text, context, knowledge, history=turns)
    numbers, ids = allowed_sets(facts)
    ids |= snapshot_ids(snapshot)
    # Only numbers the *user* supplied may be quoted back — and only with
    # attribution ("你说的 12 人").  Numbers from earlier model answers are never
    # added to the whitelist: a wrong number from turn 1 must not become a "fact"
    # that turn 3 can restate.  Correct numbers are already grounded in FACTS.
    user_numbers = _audit.numbers_in(text)
    supplement = (facts.get("dialogue") or {}).get("supplement") or {}
    user_numbers |= {float(value) for value in supplement.get("numbers") or []}

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
    guard_kinds: list[str] = []
    attempts = 0
    if llm is not None:
        facts_block = (
            "FACTS（唯一可用信息）：\n"
            + json.dumps(facts, ensure_ascii=False)
            + "\n\n用户问题："
            + text
        )
        prefix = _history_block(turns)
        dialogue = facts.get("dialogue") or {}
        system = (
            SYSTEM_PROMPT
            + "\n"
            + MODE_PROMPTS[mode]
            + style_note(preferences, audience)
            + "\n\n"
            + guide_block(facts.get("intent") or {})
            + "\n\n"
            + ui
            + ("\n\n" + HISTORY_RULE if dialogue else "")
        )
        feedback = ""
        calls = 0
        content_retry_used = False
        network_retry_used = False
        while calls < MAX_CALLS:
            calls += 1
            attempts = calls
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
            result = _audit.verdict(
                answer, numbers, ids, facts, user_numbers, names=NUMERIC_LABELS
            )
            problems = result["problems"]
            kinds = result["kinds"]
            structured_only = False
            if (
                mode == "evidence"
                and evidence_sections(facts)
                and ("结论" not in answer or "依据" not in answer)
            ):
                if not problems and calls < 2:
                    # Nudge once, then keep whatever it wrote: a missing heading
                    # is a formatting miss, not a reason to throw the answer away.
                    problems = [STRUCTURE_HINT]
                    kinds = ["structure"]
                    structured_only = True
            if not problems:
                citations = sorted(set(ID.findall(answer)))[:8]
                return {
                    "answer": answer,
                    "source": "llm",
                    "citations": citations,
                    "model": getattr(llm, "model", "unknown"),
                    "trace": build_trace(
                        facts,
                        mode,
                        "llm",
                        audience=audience,
                        history_turns=len(turns),
                        attempts=attempts,
                    ),
                }
            guard_problems = problems
            guard_kinds = kinds
            failure = None
            LOGGER.info("chat answer rejected (call %d): %s", calls, "；".join(problems))
            if content_retry_used:
                break
            content_retry_used = True
            feedback = (
                "\n\n请按“结论：…… / 依据：……”两段重写，不要省略这两个小标题。"
                if structured_only
                else REWRITE_HINT.format(
                    problems="；".join(problems), advice=_rewrite_advice(kinds)
                )
            )
    else:
        note = "未启用 LLM：当前为本地规则回答。可在左下角「设置」中开启。"

    failure_kind = None
    if llm is not None:
        if failure is not None:
            note = failure_note(failure)
            failure_kind = failure.kind
        elif guard_problems:
            note = _guard_note(guard_kinds)
            failure_kind = guard_kinds[0] if guard_kinds else "model"
    LOGGER.info(
        "chat fell back to rules: llm=%s kind=%s note=%s",
        llm is not None,
        failure_kind or "-",
        note or "-",
    )
    answer = rules_answer(facts, mode)
    return {
        "answer": answer,
        "source": "rules",
        "citations": sorted(set(ID.findall(answer)))[:8],
        "model": "rules",
        "note": note,
        "trace": build_trace(
            facts,
            mode,
            "rules",
            note,
            audience=audience,
            history_turns=len(turns),
            attempts=attempts,
            problems=guard_problems,
            failure_kind=failure_kind,
        ),
    }
