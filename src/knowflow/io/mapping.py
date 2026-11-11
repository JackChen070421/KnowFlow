"""Official → canonical ID mapping (official-v1).

Pure functions and lookup tables only: no file I/O, no pandas.  Every rule here
is documented in ``schemas/CONTRACT.md`` §7; tests pin the one-to-one property.

Owner: R2 (data & diagnosis).
"""

from __future__ import annotations

DATASET_ID = "official-v1"
CANONICAL_VERSION = "0.3.0"

#: Official CSV locations, relative to ``data/raw/<dataset_id>/``.
OFFICIAL_FILES: dict[str, str] = {
    "course": "4_赛题数据/模拟学情数据/课程要求.csv",
    "materials": "4_赛题数据/模拟学情数据/题目与材料.csv",
    "students": "4_赛题数据/模拟学情数据/模拟学生.csv",
    "nodes": "4_赛题数据/模拟学情数据/测验节点.csv",
    "records": "4_赛题数据/模拟学情数据/作答记录.csv",
}

#: Header of every official table.  A column outside this list is an unknown
#: schema (for example a new eval dataset) and must fail loudly, not be dropped.
OFFICIAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "course": (
        "主题编号", "主题", "主题目标", "指标编号", "观察指标",
        "课标整理编号", "课标文件页／正文页", "教材正文页",
    ),
    "materials": (
        "材料编号", "主题编号", "材料类型", "题型", "题干或内容", "选项",
        "参考答案", "参考解析", "满分", "评分点", "指标编号", "来源或资料文件",
    ),
    "students": ("学生编号", "模拟班级编号", "年级"),
    "nodes": ("节点编号", "模拟测验日期", "已教及测量主题", "说明", "可用题目编号"),
    "records": (
        "记录编号", "学生编号", "材料编号", "主题编号", "节点编号", "作答事件编号",
        "修订版本", "模拟提交时间", "评分状态", "得分", "满分", "学生最终作答",
        "解答过程", "评分点得分",
    ),
}

#: Theme → objective (课标整理编号 CR01–CR03 preserve their ordinal).
THEME_TO_OBJECTIVE: dict[str, str] = {
    "T01": "OBJ-7M-01",
    "T02": "OBJ-7M-02",
    "T03": "OBJ-7M-03",
}

#: Indicator (TxxIy) → knowledge (theme order, then indicator order).
INDICATOR_TO_KNOWLEDGE: dict[str, str] = {
    f"T{theme:02d}I{indicator}": f"K-{(theme - 1) * 3 + indicator:02d}"
    for theme in range(1, 4)
    for indicator in range(1, 4)
}

#: Textbook slice → objective.  Only these three slices are tied to the three
#: themes; the other five are unrelated textbook chapters (disclosed by the
#: official data as “未标注主题和指标”).
B_SLICE_OBJECTIVE: dict[str, str | None] = {
    "B01": None,
    "B02": "OBJ-7M-03",
    "B03": None,
    "B04": None,
    "B05": "OBJ-7M-01",
    "B06": "OBJ-7M-02",
    "B07": None,
    "B08": None,
}

#: Indicator → cognitive type (human-reviewed 9-row table, CONTRACT §7).
COGNITIVE_TYPE: dict[str, str] = {
    "T01I1": "application",
    "T01I2": "procedure",
    "T01I3": "application",
    "T02I1": "procedure",
    "T02I2": "procedure",
    "T02I3": "application",
    "T03I1": "procedure",
    "T03I2": "procedure",
    "T03I3": "application",
}

#: Official material category → canonical material_type.
MATERIAL_TYPE: dict[str, str] = {
    "题目": "assessment",
    "学习卡": "explain",
    "教材": "reference",
}

#: Official question format → canonical item_format.
ITEM_FORMAT: dict[str, str] = {
    "选择题": "choice",
    "填空题": "blank",
    "解答题": "solution",
}

#: Official class → canonical group.
GROUP_ID: dict[str, str] = {"DC01": "G1", "DC02": "G2"}

#: Score status values; anything else aborts the run.
RECORD_STATUS = ("已评分", "待评分", "未作答")

#: Q → 1–54, L01–L03 → 55–57, B01–B08 → 58–65.
MATERIAL_OFFSET: dict[str, int] = {"Q": 0, "L": 54, "B": 57}


def _digits(value: str, width: int, label: str) -> int:
    value = value.strip()
    if not value.isdigit() or len(value) != width:
        raise ValueError(f"{label}: expected {width} digits, got {value!r}")
    return int(value)


def material_id_for(official_id: str) -> str:
    """Map an official material id (Q001/L01/B01) to ``M-0xx``."""

    official_id = official_id.strip()
    prefix = official_id[:1]
    if prefix not in MATERIAL_OFFSET:
        raise ValueError(f"unknown material id: {official_id!r}")
    number = int(official_id[1:])
    index = MATERIAL_OFFSET[prefix] + number
    if not 1 <= index <= 65:
        raise ValueError(f"material id out of range: {official_id!r}")
    return f"M-{index:03d}"


def material_official_id(material_id: str) -> str:
    """Inverse of :func:`material_id_for` (used by tests and traceability)."""

    index = _digits(material_id[2:], 3, "material id")
    if 1 <= index <= 54:
        return f"Q{index:03d}"
    if 55 <= index <= 57:
        return f"L{index - 54:02d}"
    if 58 <= index <= 65:
        return f"B{index - 57:02d}"
    raise ValueError(f"material id out of range: {material_id!r}")


def record_id_for(official_id: str) -> str:
    """Map ``DR0001`` to ``R-0001``."""

    official_id = official_id.strip()
    if not official_id.startswith("DR") or len(official_id) != 6:
        raise ValueError(f"unknown record id: {official_id!r}")
    return f"R-{_digits(official_id[2:], 4, 'record id'):04d}"


def student_id_for(official_id: str) -> str:
    """Map ``D01`` to ``S001``."""

    official_id = official_id.strip()
    if not official_id.startswith("D"):
        raise ValueError(f"unknown student id: {official_id!r}")
    return f"S{_digits(official_id[1:], 2, 'student id'):03d}"


def group_id_for(official_id: str) -> str:
    official_id = official_id.strip()
    if official_id not in GROUP_ID:
        raise ValueError(f"unknown class id: {official_id!r}")
    return GROUP_ID[official_id]


def objective_for_theme(theme_id: str) -> str:
    theme_id = theme_id.strip()
    if theme_id not in THEME_TO_OBJECTIVE:
        raise ValueError(f"unknown theme: {theme_id!r}")
    return THEME_TO_OBJECTIVE[theme_id]


def knowledge_for_indicator(indicator_id: str) -> str:
    indicator_id = indicator_id.strip()
    if indicator_id not in INDICATOR_TO_KNOWLEDGE:
        raise ValueError(f"unknown indicator: {indicator_id!r}")
    return INDICATOR_TO_KNOWLEDGE[indicator_id]


def split_ids(text: str) -> list[str]:
    """Split official multi-value cells on ``、`` / ``；`` / ``;`` / ``,``."""

    import re

    parts = [part.strip() for part in re.split(r"[、；;,]", text or "") if part.strip()]
    return parts
