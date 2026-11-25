"""Executable half of the interaction contract (交互契约的机检部分).

The boundary this module enforces:

* **决定层** — 材料、完成门槛、排序、诊断结论：由确定性代码产出，语言层不得改动。
* **语言层** — ``reason`` 等文字：模型可以改写措辞，但只能引用决定层已经给出的对象。

These rules used to live as prose inside the prompts; as prose they could be, and
were, ignored (see CHANGELOG 2026-11-25).  As pure functions they become
assertions both layers can share.

Owner: R3.
"""

from __future__ import annotations

import re

# Same token shape as guard.ID, but only the material subset; kept local so this
# module does not import the guard that may later import it back.
_MATERIAL = re.compile(r"(?<![A-Za-z0-9])M-\d{3}(?![A-Za-z0-9])")


def materials_mentioned(text: str) -> set[str]:
    """Every material ID a piece of prose cites."""

    return set(_MATERIAL.findall(text or ""))


def plan_material_ids(item: dict) -> set[str]:
    """The materials the decision layer actually assigned to one plan item."""

    return {str(value) for value in item.get("material_ids") or [] if isinstance(value, str)}


def material_drift(text: str, item: dict) -> list[str]:
    """Material IDs the language layer cited but the decision layer did not assign.

    A non-empty result means the model silently rewrote the plan (the 22% drift
    observed on 2026-11-25), so the rewrite must be rejected in favour of the
    deterministic wording.
    """

    return sorted(materials_mentioned(text) - plan_material_ids(item))


def answer_key_visible(role: str | None) -> bool:
    """Only a teacher may see an answer key.  Unknown callers get nothing."""

    return role == "teacher"


# --- 行为红线：推荐与对话两条路径共用，prompt 与代码同源 -------------------

MUST_NOT_INFER = (
    "不得把未记录或未作答说成未掌握",
    "不得新增摘要白名单之外的数字或 ID",
    "不得推断姓名、学号或原始作答内容",
    "不得改变诊断状态、掌握度或建议顺序",
    "不得改动材料选择或完成门槛",
)

BOUNDARY_NOTE = (
    "学习者数据只发聚合事实；课程内容（课标原文、学习卡、题面与解析）可随问题发送，"
    "学生端不含参考答案。"
)


def forbidden_text() -> str:
    """The one shared "do not" line every prompt and card carries verbatim."""

    return "；".join(MUST_NOT_INFER)
