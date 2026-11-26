from knowflow.diagnosis.profiles import _objectives
from knowflow.llm.chat import _weak, rules_answer


def test_theme_keeps_unobserved_separate_from_pending():
    state = {'objective_id': 'OBJ-1', 'knowledge_id': 'K-01',
             'evidence_count': 0, 'confidence': 'low', 'status': 'unobserved'}
    assert _objectives([state])[0]['status'] == 'unobserved'
    assert _objectives([{**state, 'status': 'insufficient_evidence'}])[0]['status'] == 'insufficient_evidence'


def test_ai_prioritizes_poor_without_treating_good_as_weak():
    assert _weak({'status': 'sparse_poor'})
    assert _weak({'status': 'confirmed_weak'})
    assert not _weak({'status': 'sparse_good'})
    assert not _weak({'status': 'unobserved'})


def test_no_consolidation_is_not_reported_as_missing_evidence():
    facts = {'student': {'id': 'S001', 'needs_consolidation': [], 'needs_observation': [], 'needs_coverage': [], 'plan': [], 'coverage': {'observed': 4, 'applicable': 4, 'ratio': 1}}}
    for mode in ['concise', 'evidence']:
        answer = rules_answer(facts, mode)
        assert '证据不足' not in answer
        assert '证据还不够' not in answer
        assert '复核' in answer


def test_pending_advice_waits_for_scoring_instead_of_another_test():
    facts = {'student': {'id': 'S001', 'needs_observation': ['K-01']}}
    answer = rules_answer(facts)
    assert '先完成评分或核验' in answer
    assert '再测一次就能定性' not in answer


def test_class_poor_is_included_in_ai_focus():
    facts = {'class': {'id': 'ALL', 'students': 4, 'coverage': {}, 'knowledge': [{'id': 'K-01', 'name': '方程', 'weak': 0, 'sparse_poor': 3, 'insufficient': 0}]}}
    answer = rules_answer(facts, 'evidence')
    # 较差与薄弱同属需要支持的一侧；两者仍是分开报的数字，不能合成“薄弱 3 人”。
    assert '较差 3 人' in answer
    assert '薄弱 3 人' not in answer
