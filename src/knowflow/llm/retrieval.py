"""Retrieve the course content a question actually needs.

``chat.build_facts`` carries **learner data** (aggregates only).  This module adds
**course content** — 课标原文、学习卡、题面与解析 — so the companion can teach
instead of answering "当前数据没有这项信息".

Boundary: course content is not student data.  Nothing here reads records,
names, rubric scores or free-text answers; ``build_facts`` still only sends
aggregates.  ``answer_key`` is added for teachers only.

Owner: R3.
"""

from __future__ import annotations

from .contract import answer_key_visible

MAX_SOURCES = 5
MAX_BODY = 220
MAX_EXPLANATION = 160
MAX_OBJECTIVE = 120
MAX_TITLE = 40

# Bigrams made only of these characters carry no topic: "的知"、"是在" 之类。
_STOP_CHARS = set(
    "的了着过吗呢吧啊呀是我你他她它在有和与或就都也还很最更不没这那哪个些怎样如何为什么可以能"
    "请问一下把被从对给让向于以之其而及等并又再才只刚将会要去来到做用使"
)


def _clip(text: object, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _bigrams(text: str) -> set[str]:
    return {
        text[index : index + 2]
        for index in range(len(text) - 1)
        if not (set(text[index : index + 2]) & _STOP_CHARS)
    }


def _overlap(message: str, target: object) -> int:
    """Count topic bigrams of ``target`` that also appear in the message.

    Chinese has no word boundaries; on 9 knowledge names a bigram overlap beats
    a tokenizer we would have to ship and justify.
    """

    if not target:
        return 0
    return sum(1 for gram in _bigrams(str(target)) if gram in message)


def _score(message: str, knowledge: dict, objective: dict | None) -> float:
    score = 0.0
    if knowledge["knowledge_id"] in message:
        score += 100.0
    score += 2.0 * _overlap(message, knowledge.get("name"))
    if objective:
        score += 0.5 * _overlap(message, objective.get("objective_text"))
    return score


def select_sources(
    *,
    knowledge: dict,
    message: str,
    knowledge_ids: list[str],
    plan_material_ids: list[str],
    audience: str = "student",
) -> list[dict]:
    """Pick at most ``MAX_SOURCES`` course snippets for one question.

    Order of preference: the knowledge the question names, then the knowledge the
    student is actually working on.  Each picked knowledge contributes its
    objective wording, its 学习卡 and up to two worked items.
    """

    names = knowledge.get("knowledge") or []
    objectives = {item["objective_id"]: item for item in knowledge.get("objectives") or []}
    materials = {item["material_id"]: item for item in knowledge.get("materials") or []}
    links: dict[str, list[dict]] = {}
    for row in knowledge.get("qmatrix") or []:
        links.setdefault(row["knowledge_id"], []).append(row)

    ranked = sorted(
        ((_score(message, item, objectives.get(item["objective_id"])), item) for item in names),
        key=lambda pair: pair[0],
        reverse=True,
    )
    chosen = [item for score, item in ranked if score >= 2.0][:2]
    if not chosen:
        # No topic in the question ("S007 现在最需要补什么？"): use the knowledge
        # the fact card already put in front of the reader.
        chosen = [item for item in names if item["knowledge_id"] in knowledge_ids][:1]
    if not chosen:
        return []

    sources: list[dict] = []
    seen: set[str] = set()
    objective_seen: set[str] = set()

    def push(entry: dict) -> None:
        if entry["id"] in seen or len(sources) >= MAX_SOURCES:
            return
        seen.add(entry["id"])
        sources.append(entry)

    for position, item in enumerate(chosen):
        knowledge_id = item["knowledge_id"]
        objective = objectives.get(item["objective_id"])
        if objective and item["objective_id"] not in objective_seen:
            objective_seen.add(item["objective_id"])
            push(
                {
                    "id": objective["objective_id"],
                    "kind": "objective",
                    "title": _clip(objective.get("theme") or item["name"], MAX_TITLE),
                    "objective_text": _clip(objective.get("objective_text"), MAX_OBJECTIVE),
                }
            )

        rows = links.get(knowledge_id, [])
        for row in rows:
            material = materials.get(row["material_id"]) or {}
            if material.get("material_type") == "explain" and material.get("body"):
                push(
                    {
                        "id": material["material_id"],
                        "kind": "explain",
                        "title": _clip(material.get("title"), MAX_TITLE),
                        "body": _clip(material["body"], MAX_BODY),
                    }
                )
                break

        examples = [
            row
            for row in rows
            if (materials.get(row["material_id"]) or {}).get("material_type") == "assessment"
        ]
        # Worked items the plan already assigned come first: the reader sees the
        # same material on the page and in the answer.
        examples.sort(
            key=lambda row: (
                row["material_id"] not in plan_material_ids,
                row["material_id"],
            )
        )
        for row in examples[: 2 if position == 0 else 1]:
            material = materials[row["material_id"]]
            entry = {
                "id": material["material_id"],
                "kind": "example",
                "title": _clip(material.get("title"), MAX_TITLE),
                "body": _clip(material.get("body"), MAX_BODY),
            }
            if material.get("explanation"):
                entry["explanation"] = _clip(material["explanation"], MAX_EXPLANATION)
            if answer_key_visible(audience) and material.get("answer_key"):
                entry["answer_key"] = _clip(material["answer_key"], 80)
            push(entry)

    return sources
