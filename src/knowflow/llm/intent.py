"""Lightweight question-intent detection for the AI 学伴 chat.

The model does the analysis; this module only answers two questions the program
is better at:

* **问的是哪一类问题** — 整体学情、知识点、学生群体、个体学生、教学安排、
  进度趋势，还是一个具体数字查询。  一个教师的话可以同时属于多类。
* **回答要长成什么样** — 数据查询只要那个数字；整体学情才值得展开。

It is deliberately a keyword table, not an agent framework: nine knowledge
points and a classroom-sized fact card do not need a planner, and a deterministic
classifier can be unit-tested and cannot hallucinate.  The intent never decides a
fact — it only steers which part of the fact card the prompt asks the model to
look at, and which fallback answer is appropriate when the model is unavailable.

Owner: R3.
"""

from __future__ import annotations

INTENT_LABELS = {
    "overview": "整体学情",
    "knowledge": "知识点分析",
    "group": "学生群体与分层",
    "student": "个体学生",
    "strategy": "教学安排建议",
    "progress": "进度与趋势",
    "lookup": "数据查询",
}

# Tie-break order: the more specific question wins when scores are equal, so
# "分层" is not swallowed by "整体" and "多少人" is not swallowed by "知识点".
INTENT_ORDER = (
    "lookup",
    "student",
    "group",
    "strategy",
    "progress",
    "knowledge",
    "overview",
)

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "overview": (
        "学情", "整体", "总体", "大体", "概况", "班级情况", "班上情况", "班上的情况",
        "学习情况", "学习状况", "学得怎么样", "学得如何", "整体水平", "总体水平",
        "整体怎么样", "全班情况",
    ),
    "knowledge": (
        "知识点", "薄弱点", "考点", "难点", "重点讲", "掌握得最差", "掌握最差",
        "哪些内容", "哪一块", "困难", "卡在", "没掌握", "薄弱", "掌握情况",
        "需要重点", "讲哪", "哪几块内容",
    ),
    "group": (
        "分层", "差异", "群体", "哪些学生", "哪几个学生", "重点关注", "需要关注",
        "层次", "分化", "小组", "分组", "快慢班", "学生之间", "学生间",
    ),
    "student": (
        "这个学生", "该生", "这名学生", "这位同学", "某个学生", "某位学生",
        "他", "她", "孩子", "补什么", "最需要补", "学得怎么样",
    ),
    "strategy": (
        "下一节课", "下节课", "怎么安排", "如何安排", "安排", "复习", "教学建议",
        "怎么讲", "讲什么", "重点讲解", "课时", "备课", "教学设计", "怎么带",
        "下一步", "如何复习",
    ),
    "progress": (
        "趋势", "变化", "最近", "近来", "进步", "提升", "退步", "改善", "好转",
        "进度", "这段时间", "上周", "本周", "逐步", "正在", "对比之前", "相比之前",
    ),
    "lookup": (
        "多少人", "几个人", "几人", "人数", "多少个", "多少道", "多少条",
        "完成多少", "做了多少", "几道", "几次", "总数", "一共有", "总共",
    ),
}

_YES_NO = ("吗", "是不是", "是否", "对不对", "有没有", "能不能", "需不需要", "要不要", "会不会", "算不算")
_HOW_MANY = ("多少", "几人", "几个人", "几个", "几道", "几次", "几条", "几项")
_WHICH = ("哪些", "哪几个", "哪几块", "哪一个", "哪门")
_HOW_TO = ("怎么安排", "如何安排", "怎么讲", "如何讲", "怎么复习", "应该讲什么", "怎么带", "如何带")
_GREETING = ("你好", "您好", "hi", "hello", "在吗", "谢谢", "早上好", "下午好", "晚上好")

# "K-07 怎么算" is a subject question, not a learning-data question: the companion
# should teach the method, and only mention learner data if the reader asked.
_TEACH_WORDS = (
    "怎么算", "怎么做", "怎么解", "怎么求", "怎么判断", "为什么", "讲讲", "讲一下",
    "什么意思", "如何理解", "解题", "步骤",
)
_TEACH_SUPPRESS = ("薄弱", "学情", "分层", "趋势", "整体", "哪些知识点", "重点关注")

# Words that mean "this is an analysis question, not a lookup" even when a count
# word is present: "这个班有多少人，学情如何" is not a one-line query.
_ANALYSIS_WORDS = ("分析", "建议", "判断", "为什么", "原因", "学情", "整体", "趋势", "分层", "薄弱", "怎么样", "如何")


def question_form(message: str) -> str:
    """The shape of the answer the question needs.

    ``yes_no``   — 是不是 / 有没有 / 需不需要
    ``how_many`` — 多少个 / 几人
    ``which``    — 哪些
    ``how_to``   — 怎么安排 / 应该讲什么
    ``open``     — everything else
    """

    text = message or ""
    if any(word in text for word in _HOW_MANY):
        return "how_many"
    if any(word in text for word in _YES_NO):
        return "yes_no"
    if any(word in text for word in _WHICH):
        return "which"
    if any(word in text for word in _HOW_TO):
        return "how_to"
    return "open"


def _score(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for word in words if word in text)


def classify_intent(
    message: str,
    *,
    student_named: bool = False,
    knowledge_named: bool = False,
) -> dict:
    """Classify one teacher/student question.

    ``student_named``/``knowledge_named`` come from :func:`chat.build_facts`
    after it resolves the mentioned IDs, so "S002 怎么样" is an individual-student
    question even though it contains no analysis vocabulary.

    The return value is metadata only: it never adds a fact and never removes one.
    """

    text = (message or "").strip()
    scores = {name: _score(text, words) for name, words in _KEYWORDS.items()}
    if student_named:
        scores["student"] += 2
    if knowledge_named:
        scores["knowledge"] += 1

    form = question_form(text)
    # A pure count question should not be answered with a paragraph: lookup wins
    # unless the question also asks for an analysis ("这个班有多少人，学情如何").
    if form == "how_many" and scores["lookup"]:
        if any(word in text for word in _ANALYSIS_WORDS):
            scores["lookup"] -= 1
        else:
            scores["lookup"] += 2

    ranked = sorted(
        (name for name, value in scores.items() if value > 0),
        key=lambda name: (-scores[name], INTENT_ORDER.index(name)),
    )
    primary = ranked[0] if ranked else None
    greeting = any(word in text.lower() for word in _GREETING) and not ranked
    teach = any(word in text for word in _TEACH_WORDS) and not any(
        word in text for word in _TEACH_SUPPRESS
    )
    intents = ranked[:3]
    return {
        "primary": primary,
        "label": INTENT_LABELS.get(primary or "", "开放提问"),
        "all": intents,
        "labels": [INTENT_LABELS[name] for name in intents],
        "form": form,
        "greeting": greeting,
        "teach": teach,
        "scores": {name: value for name, value in scores.items() if value},
    }


# --- 分析重点：写给模型的“怎么想”，不是“怎么排版” ---------------------------
#
# Each entry is guidance the model may follow, not a section it must print.  The
# four-part structure the task brief rejected (结论/知识点/建议) is deliberately
# absent: the prompt asks for a judgement first and leaves the paragraphs to the
# model.

ANALYSIS_GUIDE: dict[str, dict[str, tuple[str, ...]]] = {
    "overview": {
        "think": (
            "先回答“整体怎么样”，并说清这个判断有多少证据支撑；覆盖率低、证据不足只能说明“还看不出来”，不能推出“学生基础差”。",
            "把知识点分成两类再说话：已有明确薄弱证据的，和只是缺记录的。这两类不是一回事。",
            "看学生差异时只用事实卡里的分组与差异数据，它们只是描述性差异，不支撑“能力分层”的结论。",
            "最后给一到两个优先动作，并说明为什么先做这个（补证据，还是先巩固已证实的薄弱）。",
        ),
        "shape": "2–4 段自然中文。先给判断，再给一两点支撑，最后给下一步；不要罗列全部指标，不要用固定小标题。",
    },
    "knowledge": {
        "think": (
            "只有“有薄弱证据”的知识点才能称为薄弱；证据不足、未覆盖的要单独说明缺什么，不能混进薄弱名单。",
            "“有评分但太少”和“一条记录都没有”是两种缺口，能分开说就分开说。",
            "薄弱人数相同也要看观察人数：观察 36 人的 8 人和观察 11 人的 8 人，证据强度不同。",
            "如果证据不足以判断“最薄弱”，就直说需要补哪种测评，不要硬排序。",
        ),
        "shape": "先给结论（哪几个真的薄弱），再区分证据不足的几个，最后一句建议；不逐条播报数字。",
    },
    "group": {
        "think": (
            "先直接回答“能不能分层”这个问题本身：现有数据支持到什么程度。",
            "分层需要的是学生之间稳定的差异证据；覆盖率低、证据不足不能当作差异。",
            "如果按薄弱知识点组合已经能形成小组，说明这是“按知识点分组补差”，不是“按能力分层”，两者要分开说。",
            "说分组规模就用 FACTS.class.tiers 里的 count / multi_student / largest，不要自己数或换别的数。",
            "群体间差异只作描述，不能推成因果或能力高低。",
        ),
        "shape": "先判断，再说依据，再给一个可行的做法；不要先报一串分布数字。",
    },
    "student": {
        "think": (
            "围绕这一个学生：现在能确定什么、还缺什么、下一步先做什么。",
            "不要把班级统计当成他的个人事实，也不要把“证据不足”当作“学得差”。",
            "如果问题问的是进步或趋势，先确认有没有可比较的两次观测。",
        ),
        "shape": "口语、简短，一次只推进一步；学生读者不要直接报最终答案。",
    },
    "strategy": {
        "think": (
            "把安排分成两类：已有证据、可以直接巩固的；证据不足、需要先补测评的。",
            "每个动作说明为什么这样做、预期解决什么问题；不要暗示某种教法已被数据证明有效。",
            "除非教师明确要题目安排，否则用自然语言描述做法，不要抛题目编号。",
        ),
        "shape": "给一个 2–3 步的可执行安排，每步带理由；不要写成通用教研套话。",
    },
    "progress": {
        "think": (
            "先看有没有可比较的两次观测：本系统的节点快照教学目标不同，跨节点对比只能说明“观测范围变了”，不能直接当作学生进步或退步。",
            "没有时间序列就直说无法判断趋势，并说明需要什么数据才能判断。",
            "不要把“这次记录少”说成“退步”。",
        ),
        "shape": "先回答趋势问题本身；没有数据就一句话说清，再给一个补数据的建议。",
    },
    "lookup": {
        "think": (
            "用户只要那个数字或那条事实，直接在事实卡里找到它。",
            "不要附加学情分析、不要给建议、不要提醒风险；除非这个数字本身容易被误解。",
        ),
        "shape": "一句话，只说被问到的数据。",
    },
}

GENERIC_GUIDE = {
    "think": ("先判断问题要的是事实、判断，还是做法；只回答被问到的部分。",),
    "shape": "按需要回答，简单的就一句话。",
}

# A subject question ("K-07 怎么算") is not a learning-data question.  Reusing the
# knowledge-analysis guide for it told the model to rank weak knowledge points
# while the reader was asking how to solve an equation.
TEACH_GUIDE = {
    "think": (
        "这次问的是学科本身：先给做法或概念，讲清关键一步和最容易错的地方。",
        "可以用 FACTS.sources 里的课标原文、学习卡和题面；不要主动铺开学情分析。",
        "只有在学生数据确实相关时（比如他刚在这类题上失分）补一句，不要写成学情报告。",
    ),
    "shape": "像讲题一样：思路、第一步、一处易错提醒；不要分点罗列统计。",
}


def guide_block(intent: dict) -> str:
    """Render the per-question analysis guidance appended to the system prompt.

    This is the only place intent influences the model, and it is guidance about
    reasoning, not a required output skeleton.  Only the *primary* intent gets a
    guide: stacking a class-level guide onto a single-student question produces
    contradictory advice ("look at the tiers" while discussing one child).
    """

    codes = list(intent.get("all") or [])
    primary = intent.get("primary")
    if primary and primary not in codes:
        codes.insert(0, primary)
    lines: list[str] = []
    label = intent.get("label") or "开放提问"
    extra = [INTENT_LABELS[code] for code in codes if code != primary and code in INTENT_LABELS]
    lines.append(f"本次问题：{label}" + (f"（同时涉及：{'、'.join(extra)}）" if extra else ""))
    form_labels = {
        "yes_no": "是/否判断",
        "how_many": "问数量",
        "which": "问哪些",
        "how_to": "问怎么做",
        "open": "开放提问",
    }
    lines.append(f"提问形式：{form_labels.get(intent.get('form'), '开放提问')}")
    if intent.get("teach"):
        guide = TEACH_GUIDE
        lines.append("【学科问题怎么想】")
    else:
        guide = ANALYSIS_GUIDE.get(primary or "") or GENERIC_GUIDE
        lines.append(f"【{INTENT_LABELS.get(primary or '', '这类问题')}怎么想】")
    lines.extend(f"- {item}" for item in guide["think"])
    lines.append(f"【回答形态】{guide['shape']}")
    if primary == "lookup":
        lines.append("【硬要求】这次是数据查询：只回答数据本身，不展开学情分析，不建议教学动作。")
    if extra:
        lines.append("【多类问题】先回答主问题；另一类只在确实相关时补一两句，不要平铺成两份报告。")
    return "\n".join(lines)
