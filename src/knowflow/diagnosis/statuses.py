"""Shared display names and teaching priorities; never infer status from color."""

MASTERED = frozenset({"mastered", "confirmed_mastered", "likely_mastered"})
WEAK = frozenset({"weak", "confirmed_weak", "likely_weak"})
SUPPORT = WEAK | {"sparse_poor"}
LABELS = {
    **dict.fromkeys(MASTERED, "掌握"),
    **dict.fromkeys(WEAK, "薄弱"),
    "sparse_good": "较好",
    "sparse_poor": "较差",
    "insufficient_evidence": "待评分／核验",
    "unobserved": "未覆盖",
    "not_applicable": "本节点不适用",
    "mixed_performance": "知识点表现不一",
}


def training_priority(status: str) -> int:
    """Weak and poor first; do not treat ungraded work as a wrong answer."""
    if status in WEAK:
        return 0
    return {
        "sparse_poor": 1,
        "mixed_performance": 2,  # Historical or theme summary, not a time trend.
        "unobserved": 3,
        "sparse_good": 4,
        **dict.fromkeys(MASTERED, 5),
        "insufficient_evidence": 6,
        "not_applicable": 7,
    }.get(status, 7)
