"""Deterministic audit of one chat answer.

Three different things are checked, and they are deliberately kept apart so the
caller can say *which* one failed:

* **数据数字** — 人数、比例、掌握度、覆盖、各类计数.  These are claims about
  learners and must be traceable to the fact card.
* **业务实体 ID** — 学生/知识点/题目/记录编号.  These must exist in the snapshot.
* **教学数字** — 做几道题、几分钟、第几步、第几周、某个年份.  These describe a
  lesson, not a learner, and are *not* database facts.

The rule is contextual, not lexical: "8 人薄弱" is a claim, "先做 8 道题" is a
lesson plan, and "建议每组 4 人" is advice.  Making the audit understand the third
case is what stops a good teaching suggestion from being rejected as a fabricated
statistic — while a fabricated statistic still cannot pass.

An answer is also rejected when it states an absolute conclusion ("全班都没掌握")
that the evidence gaps in the fact card contradict.

Owner: R3.
"""

from __future__ import annotations

import re
from typing import Protocol

from .guard import ID, NUMBER

MAX_ANSWER = 1200


class SpanLike(Protocol):
    """What :func:`classify_number` needs: a start, an end and the matched text."""

    def start(self) -> int: ...

    def end(self) -> int: ...

    def group(self) -> str: ...

# --- 词表 -------------------------------------------------------------------

# 数量跟在后面就是"多少个学习者"，不是在讲怎么做题。
DATA_UNITS = ("人", "名", "位", "员")
DATA_TAILS = ("学生", "同学", "孩子", "人")

# 这些词一出现，整句就是在讲学情数据，数字必须可核对（"平均分 45"不能被当成教法）。
STRONG_DATA_WORDS = (
    "覆盖", "掌握", "薄弱", "较好", "较差", "待评分／核验", "证据", "得分", "评分",
    "平均", "占比", "排名", "比例", "人数", "率", "％", "%", "及格", "错误率", "正确率", "分层",
)

WEAK_DATA_NOUNS = ("学生", "同学", "孩子", "班级", "全班")

# 教学量：做几道、几分钟、第几轮。
TEACHING_UNITS = (
    "道", "题", "步", "分钟", "分", "秒", "小时", "遍", "周", "天", "日",
    "页", "章", "节", "个", "条", "次", "本", "张", "组", "轮", "篇", "份",
    "套", "课时", "年级", "以内", "以上", "以下", "点", "项",
)

# 日期/时长："6 月 17 日"、"12 周" 是时间表达，不是学习者统计。
TIME_UNITS = ("年", "月", "日", "号", "时")

# "第 3 步"、"第 12 周" 是序号。
ORDINAL_UNITS = (
    "步", "题", "节", "章", "课", "周", "天", "遍", "点", "部分", "环节",
    "阶段", "小节", "小题", "问", "轮", "次", "条", "项", "个",
)

# 建议性语境：出现这些词，且数字前没有断言标记，就按"建议里的数量"放行。
# "可以""安排"刻意不在此列：它们太宽，"这 17 人可以直接小练"不是建议里的数量，
# 而是在指一批具体学生。
ADVICE_WORDS = (
    "建议", "不妨", "试着", "分成", "分组", "每组", "每次",
    "每天", "每周", "每轮", "整套", "合班", "分两", "分三",
)
ASSERT_MARKERS = (
    "有", "共", "是", "达", "占", "仅", "已", "其中", "超", "低于", "高于", "只",
    # 指示代词 + 数量 = "这批学生"，是断言而不是建议
    "这", "那",
)

_APPROX = ("约", "大约", "大概", "近", "左右", "超过", "不到")
_SENTENCE = re.compile(r"[^。！？!?；;\n]+")

# 绝对化结论：与"证据不足"的事实直接冲突。
ABSOLUTE_GROUPS = (
    (
        (
            "全班都",
            "全班同学都",
            "全班学生都",
            "所有学生都",
            "所有人都",
            "全部学生都",
            "全都",
        ),
        ("没掌握", "没有掌握", "不会", "没学会", "薄弱", "掌握", "学会", "懂了"),
    ),
)
HEDGES = (
    "不能", "不是", "不等于", "并非", "不宜", "无法", "不足以", "不成立", "未必",
    "别把", "不要", "别", "说不上", "很难说", "不一定", "不能算",
)

# 引用用户自己说的话：这些数字属于"用户提供"，不是数据库事实。只在带归属
# 的句子里放行，避免模型把用户说的数直接当成学情统计。
ATTRIBUTION = (
    "你说的", "你说", "你提到", "你补充", "按你说", "你统计", "你刚才", "你刚刚",
    "你记的", "你给的", "你提供的",
)


# --- 中文数字 ---------------------------------------------------------------
#
# 只认阿拉伯数字时，模型写"四十三人"就能完全绕开白名单。这里把中文数字解析成
# 数值，再交给同一个 :func:`classify_number` 判定语境——不是另写一套规则，所以
# "十人一组""第一步""十几个人"仍然按原来的语境规则处理。

CN_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_CN_CLASS = "零〇一二两三四五六七八九十百千万"
CN_TOKEN = re.compile(
    rf"百分之(?P<percent>[{_CN_CLASS}]+)"
    rf"|(?P<denominator>[{_CN_CLASS}]+)分之(?P<numerator>[{_CN_CLASS}]+)"
    rf"|(?P<fuzzy>[{_CN_CLASS}]+[几数余多]|[几数余多][十百千万])"
    rf"|(?P<plain>[{_CN_CLASS}]+)"
)
_FUZZY_TAIL = ("几", "数", "余", "多")


def parse_chinese_number(text: str) -> int | None:
    """Parse 四十三 / 一百零五 / 两千零二十六; ``None`` when it is not a number.

    Consecutive digit characters ("一两"、"二三") are intentionally unparsable:
    they are approximations ("一两个人") or a range, and an approximation must not
    silently become an exact fact.
    """

    if not text:
        return None
    total = 0
    section = 0
    number = 0
    previous_digit = False
    for char in text:
        if char in ("零", "〇"):
            number = 0
            previous_digit = False
        elif char in CN_DIGITS:
            if previous_digit:
                return None
            number = CN_DIGITS[char]
            previous_digit = True
        elif char in CN_UNITS:
            unit = CN_UNITS[char]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
            previous_digit = False
        else:
            return None
    return total + section + number


class _Numeral:
    """Minimal ``re.Match`` stand-in so the Chinese spans reuse the audit rules."""

    __slots__ = ("_start", "_end", "_raw")

    def __init__(self, start: int, end: int, raw: str) -> None:
        self._start = start
        self._end = end
        self._raw = raw

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end

    def group(self) -> str:
        return self._raw


def chinese_number_tokens(text: str) -> list[tuple[_Numeral, float | None, str]]:
    """Chinese numbers as ``(span, value, state)``.

    ``state`` is ``exact`` (a parsable number), ``fuzzy`` (十几/几十/百余) or
    ``invalid`` (a run we cannot parse, e.g. "一两").  Neither fuzzy nor invalid
    may pass as an exact learner fact.
    """

    tokens: list[tuple[_Numeral, float | None, str]] = []
    for match in CN_TOKEN.finditer(text):
        span = _Numeral(match.start(), match.end(), match.group())
        if match.group("percent") is not None:
            value = parse_chinese_number(match.group("percent"))
            tokens.append((span, float(value) if value is not None else None, "exact"))
        elif match.group("denominator") is not None:
            whole = parse_chinese_number(match.group("denominator"))
            part = parse_chinese_number(match.group("numerator"))
            if whole and part is not None:
                tokens.append((span, part / whole, "exact"))
            else:
                tokens.append((span, None, "fuzzy"))
        elif match.group("fuzzy") is not None:
            tokens.append((span, None, "fuzzy"))
        else:
            raw = match.group("plain")
            # 单独出现的"千万/千/万"多半是语气词（"千万不要"），不是数量。
            bare_magnitude = any(unit in raw for unit in ("千", "万")) and not any(
                char in CN_DIGITS for char in raw
            )
            if bare_magnitude:
                tokens.append((span, None, "invalid"))
            elif text[match.end() : match.end() + 1] in _FUZZY_TAIL:
                tokens.append((span, None, "fuzzy"))
            elif parse_chinese_number(raw) is None:
                tokens.append((span, None, "invalid"))
            else:
                tokens.append((span, float(parse_chinese_number(raw)), "exact"))
    return tokens


def _number_tokens(text: str) -> list[tuple[SpanLike, float | None, str, str]]:
    """Every number token: ``(span, value, source, state)``."""

    tokens: list[tuple[SpanLike, float | None, str, str]] = [
        (match, float(match.group()), "arabic", "exact") for match in NUMBER.finditer(text)
    ]
    tokens.extend(
        (span, value, "chinese", state)
        for span, value, state in chinese_number_tokens(text)
    )
    tokens.sort(key=lambda item: item[0].start())
    return tokens


def numbers_in(text: str) -> set[float]:
    """Every number the text states, Arabic or Chinese (for user-supplied numbers)."""

    values = {float(value) for value in NUMBER.findall(text or "")}
    for _, value, state in chinese_number_tokens(text or ""):
        if state == "exact" and value is not None:
            values.add(value)
    return values


# --- 句子与上下文 -----------------------------------------------------------


def sentence_of(text: str, index: int) -> str:
    """The sentence (split on 。！？；) that contains ``index``."""

    for match in _SENTENCE.finditer(text):
        if match.start() <= index < match.end():
            return match.group()
    return text


def _tail(text: str, index: int, width: int = 8) -> str:
    return text[index : index + width].lstrip()


def _head(text: str, index: int, width: int = 10) -> str:
    return text[max(0, index - width) : index]


def _starts_with_any(value: str, words: tuple[str, ...]) -> bool:
    return any(value.startswith(word) for word in words)


def _is_ordinal(text: str, start: int, end: int) -> bool:
    """第 3 步 / 第 12 周 — a position in a sequence, not a count of learners."""

    if not text[:start].rstrip().endswith("第"):
        return False
    return _starts_with_any(_tail(text, end), ORDINAL_UNITS)


def _is_time(text: str, end: int) -> bool:
    return _starts_with_any(_tail(text, end), TIME_UNITS)


def _is_data_unit(text: str, end: int) -> bool:
    """“8 人”、“12 名”、“8 个学生”——a count of people or records."""

    tail = _tail(text, end)
    if _starts_with_any(tail, DATA_UNITS):
        return True
    for unit in ("个", "条", "份"):
        if tail.startswith(unit) and _starts_with_any(tail[len(unit) :].lstrip(), DATA_TAILS):
            return True
    return False


def _is_teaching_unit(text: str, end: int) -> bool:
    return _starts_with_any(_tail(text, end), TEACHING_UNITS)


def _has_strong_data_word(value: str) -> bool:
    return any(word in value for word in STRONG_DATA_WORDS)


def _near_weak_noun(text: str, start: int, end: int) -> bool:
    window = _head(text, start, 8) + _tail(text, end, 6)
    return any(word in window for word in WEAK_DATA_NOUNS)


def _advice_frame(text: str, start: int) -> bool:
    """Is this number part of a suggestion ("建议每组 4 人") rather than a claim?"""

    sentence = sentence_of(text, start)
    if not any(word in sentence for word in ADVICE_WORDS):
        return False
    return not any(word in _head(text, start, 8) for word in ASSERT_MARKERS)


# --- 数字分类 ---------------------------------------------------------------


def classify_number(text: str, match: SpanLike) -> str:
    """Return ``claim`` / ``teaching`` / ``advisory`` / ``other``.

    The class says *what role the number plays*, not whether it is correct;
    :func:`validate_answer` then checks ``claim``/``other`` against the whitelist.
    Keeping the two apart is what lets the audit report "these are learner facts,
    those are lesson quantities" instead of one undifferentiated list.

    The data-word test looks *around the number*, not at the whole sentence.  A
    long lesson-plan sentence can contain "36 名证据不足的学生" and "10 分钟" at
    once; a sentence-wide test used to reject the 10 minutes as a fabricated
    statistic (observed on the real model: "开场用 10 分钟做一次统一小测…").
    """

    if _is_ordinal(text, match.start(), match.end()):
        return "teaching"
    if _is_time(text, match.end()):
        return "teaching"
    near = _head(text, match.start(), 6) + _tail(text, match.end(), 6)
    strong = _has_strong_data_word(near)
    if _is_data_unit(text, match.end()):
        # "8 人"、"12 名"、"8 个学生" — always a learner count; only a suggestion
        # word ("建议每组 4 人") may turn it into advice.
        return "claim" if strong or not _advice_frame(text, match.start()) else "advisory"
    if _is_teaching_unit(text, match.end()):
        # "平均 45 分" is still a learner number; "10 分钟" is not.
        return "claim" if strong else "teaching"
    if strong:
        return "claim"
    if _near_weak_noun(text, match.start(), match.end()):
        return "claim"
    return "other"


def _rounds_to_fact(
    value: float,
    allowed: set[float],
    *,
    percent_slack: float,
    integer_slack: float,
    percent: bool = True,
) -> bool:
    """Is ``value`` a rounded/percentage restatement of one allowed fact?

    The percentage branches only run when the text actually wrote a percentage
    ("23%"、"百分之二十三").  Without that, a coverage ratio of 0.17 would license
    "17 人" as "17 percent of 0.17" — a fabricated headcount.

    The "×100" branch also only applies to a ratio (``0 < base <= 1``): a real
    count of 10 in the card once licensed "999 人" as "999% of 10".
    """

    for base in allowed:
        if abs(value - base) <= 0.005:
            return True
        if percent and 0 < base < 1 and abs(value / 100 - base) <= percent_slack / 100:
            return True
        if percent and 0 < base <= 1 and abs(value - base * 100) <= percent_slack:
            return True
        if float(value).is_integer() and abs(value - round(base)) <= integer_slack:
            return True
    return False


def _number_ok(value: float, allowed: set[float]) -> bool:
    """Admit a number used while teaching (steps, item numbers, years)."""

    if value in allowed:
        return True
    if float(value).is_integer():
        integer = int(value)
        if 0 <= integer <= 10 or 2000 <= integer <= 2100:
            return True
    return _rounds_to_fact(value, allowed, percent_slack=1.5, integer_slack=0.5)


def _claim_ok(value: float, allowed: set[float], near: str, percent: bool = False) -> bool:
    """A learner-data number must be traceable; "约/不到" buys a wider rounding band.

    The approximation marker has to sit next to *this* number.  A sentence like
    "这个班有 41 人，39 人覆盖率不到一半" must not lend "不到" to the 41: that is
    how an off-by-one fabricated count would slip through a sentence-wide check.
    """

    if value in allowed:
        return True
    if _rounds_to_fact(value, allowed, percent_slack=1.5, integer_slack=0.5, percent=percent):
        return True
    if any(mark in near for mark in _APPROX):
        return _rounds_to_fact(
            value, allowed, percent_slack=5.0, integer_slack=1.0, percent=percent
        )
    return False


def _chinese_quantity(text: str, span: SpanLike) -> bool:
    """Is this Chinese numeral stating a count (rather than an idiom)?"""

    raw = span.group()
    if raw.startswith("百分之") or "分之" in raw:
        return True
    return _is_data_unit(text, span.end())


def audit_numbers(
    answer: str, numbers: set[float], user_numbers: set[float] | None = None
) -> list[dict]:
    """One record per number in the answer: value, role, source and verdict.

    Arabic and Chinese numbers go through the same context rules; the difference
    is only that a Chinese token may be *fuzzy* ("十几") or *invalid* ("一两"),
    and neither may pass as an exact learner fact.
    """

    items: list[dict] = []
    text = answer or ""
    user_numbers = user_numbers or set()
    for span, value, source, state in _number_tokens(text):
        kind = classify_number(text, span)
        near = _head(text, span.start(), 6) + _tail(text, span.end(), 6)
        sentence = sentence_of(text, span.start())
        if state != "exact":
            if kind in {"teaching", "advisory"}:
                verified = True
            else:
                kind = "claim" if _is_data_unit(text, span.end()) else "other"
                verified = kind != "claim"
            items.append(
                {
                    "value": None,
                    "raw": span.group(),
                    "source": source,
                    "state": state,
                    "kind": kind,
                    "verified": verified,
                    "sentence": sentence[:80],
                    "near": near,
                }
            )
            continue
        if source == "chinese" and kind == "claim" and not _chinese_quantity(text, span):
            # “一半”“两个群体”“三个方面” are quantifier/proportion words, not stated
            # counts.  Without a data unit they are not treated as a learner claim;
            # a real fabricated count (十九人) is still caught by _number_ok.
            kind = "other"
        items.append(
            {
                "value": value,
                "raw": span.group(),
                "source": source,
                "state": state,
                "kind": kind,
                "verified": _verified(
                    kind, value, near, numbers, sentence, user_numbers, _is_percent(text, span)
                ),
                "sentence": sentence[:80],
                "near": near,
            }
        )
    return items


def _is_percent(text: str, span: SpanLike) -> bool:
    """Was this number written as a percentage (not merely equal to a ratio×100)?"""

    if span.group().startswith("百分之"):
        return True
    return text[span.end() : span.end() + 2].lstrip().startswith(("%", "％"))


def number_audit(
    answer: str, numbers: set[float], user_numbers: set[float] | None = None
) -> dict:
    """Summarise how the answer's numbers divide into data claims and teaching."""

    items = audit_numbers(answer, numbers, user_numbers)
    return {
        "data_claims": sum(1 for item in items if item["kind"] == "claim"),
        "teaching_numbers": sum(1 for item in items if item["kind"] == "teaching"),
        "advisory_numbers": sum(1 for item in items if item["kind"] == "advisory"),
        "unverified": [item["raw"] for item in items if not item["verified"]],
        "unparsed": [item["raw"] for item in items if item["state"] != "exact"],
        "items": items,
    }


def _verified(
    kind: str,
    value: float | None,
    near: str,
    numbers: set[float],
    sentence: str,
    user_numbers: set[float],
    percent: bool = False,
) -> bool:
    if kind in {"teaching", "advisory"}:
        return True
    if value is None:
        return False
    if kind == "claim":
        # A number the user supplied may be quoted back *with attribution*
        # ("你说的 12 人"), never as an unattributed database fact.
        if value in user_numbers and any(word in sentence for word in ATTRIBUTION):
            return True
        return _claim_ok(value, numbers, near, percent)
    return _number_ok(value, numbers)


def validate_answer(
    answer: str,
    numbers: set[float],
    ids: set[str],
    user_numbers: set[float] | None = None,
) -> list[str]:
    """Every reason this answer may not be shown as-is (empty list = accepted)."""

    problems: list[str] = []
    text = (answer or "").strip()
    if not text:
        problems.append("empty answer")
        return problems
    if len(text) > MAX_ANSWER:
        problems.append("answer too long")
    unlocked = number_audit(text, numbers, user_numbers)["unverified"]
    if unlocked:
        problems.append(f"numbers outside facts: {unlocked}")
    unknown = set(ID.findall(text)) - ids
    if unknown:
        problems.append(f"ids outside facts: {sorted(unknown)}")
    if "http://" in text or "https://" in text or "```" in text:
        problems.append("urls or code fences are not allowed")
    return problems


# --- 证据边界 ---------------------------------------------------------------


def has_evidence_gaps(facts: dict) -> bool:
    """Does the fact card contain learners whose state is *unknown*?

    Only then can an absolute "everyone failed / everyone mastered" claim be
    contradicted by the data itself.
    """

    class_facts = facts.get("class") or {}
    for item in class_facts.get("knowledge") or []:
        if (item.get("insufficient") or 0) > 0 or (item.get("unobserved") or 0) > 0:
            return True
    student = facts.get("student") or {}
    if (student.get("needs_observation") or []) or (student.get("needs_coverage") or []):
        return True
    counts = student.get("status_counts") or {}
    if (counts.get("insufficient_evidence") or 0) + (counts.get("unobserved") or 0) > 0:
        return True
    return False


def claim_problems(answer: str, facts: dict) -> list[str]:
    """Absolute conclusions the evidence gaps do not support."""

    text = answer or ""
    if not has_evidence_gaps(facts):
        return []
    for match in _SENTENCE.finditer(text):
        sentence = match.group()
        if any(hedge in sentence for hedge in HEDGES):
            continue
        for subjects, predicates in ABSOLUTE_GROUPS:
            if any(subject in sentence for subject in subjects) and any(
                predicate in sentence for predicate in predicates
            ):
                return [
                    "unsupported claim: 用“全班/所有学生”下绝对结论，但事实卡里还有证据不足的学生"
                ]
    return []


def verdict(
    answer: str,
    numbers: set[float],
    ids: set[str],
    facts: dict,
    user_numbers: set[float] | None = None,
) -> dict:
    """Structured guard result: which kind of problem, if any.

    The caller uses ``kind`` to tell the reader whether the model was unreachable,
    invented a number, invented an ID, or over-claimed — instead of one vague
    "回答未通过核对".
    """

    problems = validate_answer(answer, numbers, ids, user_numbers)
    claims = claim_problems(answer, facts) if answer else []
    problems = problems + claims
    kinds: list[str] = []
    if any(problem.startswith("numbers") for problem in problems):
        kinds.append("number")
    if any(problem.startswith("ids") for problem in problems):
        kinds.append("id")
    if any(problem.startswith("unsupported claim") for problem in problems):
        kinds.append("claim")
    if any(problem in {"empty answer", "answer too long"} for problem in problems):
        kinds.append("model")
    if any(problem.startswith("urls") for problem in problems):
        kinds.append("model")
    return {"ok": not problems, "problems": problems, "kinds": kinds}


def knowledge_legal_counts(row: dict) -> set[int]:
    """Counts a sentence may legitimately attach to one knowledge point.

    Verified against ``diagnosis/profiles.py`` (2026-11-26): every student carries
    exactly one status per knowledge point, so

        weak + mixed + insufficient + unobserved + mastered + not_applicable
        == student_count

    and only *disjoint* sums are legal.  ``observed_student_count`` is
    ``evidence_count > 0``, not a status bucket; on the official snapshot it
    disagrees with the buckets on 2 of 18 rows, so it is excluded here.  This is
    the 口径 that task B's number-object binding must build on.
    """

    weak = int(row.get("weak") or 0)
    mixed = int(row.get("mixed") or 0)
    insufficient = int(row.get("insufficient") or 0)
    unobserved = int(row.get("unobserved") or 0)
    mastered = int(row.get("mastered") or 0)
    not_applicable = int(row.get("not_applicable") or 0)
    observed = int(row.get("observed") or 0)
    total = int(row.get("student_count") or 0)
    values = {
        weak,
        mixed,
        insufficient,
        unobserved,
        mastered,
        not_applicable,
        observed,
        total,
        weak + mixed,
        insufficient + unobserved,
        total - not_applicable,
    }
    return {value for value in values if value >= 0}
