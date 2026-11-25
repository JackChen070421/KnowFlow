"""分级动作：稀疏观测下"该做哪一件事"的唯一出处。

状态（``status``）回答"能不能下结论"，动作（``evidence_action``）回答"下一步
做什么"。两者不是一回事：同样是 ``insufficient_evidence``，"交了没评分"和
"做了两道但方向不明"的教师动作完全不同。诊断层、建议层和语言层都读这一个
函数，避免各写一套阈值后互相打架。
"""

from __future__ import annotations

# 稀疏观测（低于 min_evidence）下，后验概率达到这些门槛就把"证据不足"拆成梯度判断。
SPARSE_WEAK_P = 0.6
SPARSE_MASTERED_P = 0.4

ACTIONS = (
    "probe",  # 没有任何记录：先布置基线题
    "not_attempted",  # 记录存在但未作答：可能是难度或动机
    "pending",  # 已作答待评分：本轮不追加练习
    "sparse_weak",  # 评分少但后验偏弱：低置信度巩固
    "sparse_mastered",  # 评分少但都对：一次轻量复核
    "sparse_mixed",  # 评分少且表现中间：继续补观测
)


def evidence_action(state: dict) -> str | None:
    """Return the graded next step for a sparse state, or None when not sparse.

    ``state`` is a ``knowledge_states`` entry: only facts the diagnosis already
    produced are read (counts, posterior probabilities, review block). No new
    inference happens here.
    """

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
