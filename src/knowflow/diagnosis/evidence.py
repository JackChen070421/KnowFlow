"""已有诊断状态到学习动作的统一映射。

较好轻量复核、较差针对失分巩固；未覆盖补基线题，待评分先等待。
历史 insufficient_evidence 产物保留后验分支兼容；新产物按对错计数分类。
"""

from __future__ import annotations

# 仅用于历史 insufficient_evidence 产物兼容。
SPARSE_WEAK_P = 0.6
SPARSE_MASTERED_P = 0.4

ACTIONS = (
    "probe",  # 没有任何记录：先布置基线题
    "not_attempted",  # 记录存在但未作答：可能是难度或动机
    "pending",  # 已作答待评分：本轮不追加练习
    "sparse_weak",  # 较差：针对失分巩固
    "sparse_mastered",  # 较好：轻量复核
    "sparse_mixed",  # 评分少且表现中间：继续补观测
)


def evidence_action(state: dict) -> str | None:
    """Return the graded next step for a sparse state, or None when not sparse.

    ``state`` is a ``knowledge_states`` entry: only facts the diagnosis already
    produced are read (counts, posterior probabilities, review block). No new
    inference happens here.
    """

    if state.get("status") in {"sparse_good", "sparse_poor"}:
        if state.get("review"):
            return "probe"
        return "sparse_mastered" if state["status"] == "sparse_good" else "sparse_weak"
    if state.get("status") not in {"insufficient_evidence", "unobserved"}:
        return None

    observed = int(state.get("evidence_count") or 0)
    counts = state.get("state_counts") or {}
    if observed == 0:
        if state.get("review"):
            return "probe"
        if int(counts.get("pending") or 0) > 0:
            return "pending"
        if int(counts.get("assigned_not_attempted") or 0) > 0:
            return "not_attempted"
        return "probe"
    if state.get("review"):
        return "probe"
    weak = state.get("weak_probability")
    mastered = state.get("mastered_probability")
    if weak is None or mastered is None:
        return "probe"
    if weak >= SPARSE_WEAK_P:
        return "sparse_weak"
    if mastered >= SPARSE_MASTERED_P:
        return "sparse_mastered"
    return "sparse_mixed"
