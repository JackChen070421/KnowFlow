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
