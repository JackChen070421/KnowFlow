"""Structured acceptance helpers (test-only, not a runtime guard).

The runtime audit answers one question: *is this number somewhere in the fact
card?*  Acceptance needs a different one: *does this number belong to the object
the sentence names?*  A test that only searches for a keyword cannot tell a
wrong fact card from a wrong sentence, so these helpers compare an answer with
the structured rows instead.

``misattributed_counts`` is the prototype for task B (number-object binding).
It lives here on purpose: B is a design this round, so the prototype *measures*
the current gap instead of becoming a runtime rule.  It reuses the 口径 proven in
:func:`knowflow.llm.audit.knowledge_legal_counts` rather than keeping a second
copy of the rules.
"""

from __future__ import annotations

import re

from knowflow.llm.audit import knowledge_legal_counts

_SENTENCE = re.compile(r"[^。！？!?；;\n]+")
_COUNT = re.compile(r"(\d+)\s*[个名位]?\s*(?:人|学生|同学)")

# The metric a count belongs to, in the order a sentence usually writes it.
METRIC_WORDS = {
    "weak": ("薄弱", "较弱", "学得差", "吃力"),
    "mixed": ("混合", "半会", "半懂", "不稳定"),
    "insufficient": ("证据不足", "证据不够", "评分太少", "记录不足", "证据还不够"),
    "unobserved": ("没有作答", "没有记录", "无记录", "未观测", "没有观测", "没测到"),
    "mastered": ("已掌握", "掌握"),
}
_METRIC_AFTER = 12


def _mentions(text: str, row: dict) -> bool:
    for key in ("id", "short", "name"):
        value = row.get(key)
        if value and value in text:
            return True
    return False


def _metric_after(sentence: str, end: int) -> str | None:
    tail = sentence[end : end + _METRIC_AFTER]
    for metric, words in METRIC_WORDS.items():
        if any(word in tail for word in words):
            return metric
    return None


def misattributed_counts(answer: str, rows: list[dict]) -> list[dict]:
    """Counts attached to a knowledge point that the data does not support.

    This is the acceptance instrument for "把某个知识点的数字挂到另一个知识点上":
    it names the sentence, the row it is talking about, and the value, so a
    failure report can say *what* was misattributed instead of "assert failed".
    """

    problems: list[dict] = []
    for sentence_match in _SENTENCE.finditer(answer or ""):
        sentence = sentence_match.group()
        named = [row for row in rows if _mentions(sentence, row)]
        if not named:
            continue
        for count_match in _COUNT.finditer(sentence):
            value = int(count_match.group(1))
            metric = _metric_after(sentence, count_match.end())
            if metric is None:
                continue
            if not any(value in knowledge_legal_counts(row) for row in named):
                problems.append(
                    {
                        "sentence": sentence.strip(),
                        "knowledge": [row.get("id") for row in named],
                        "metric": metric,
                        "value": value,
                        "legal": sorted(knowledge_legal_counts(named[0])),
                    }
                )
    return problems
