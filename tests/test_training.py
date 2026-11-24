import base64
import io
import json

import pytest

from knowflow.web.auth import Account
from knowflow.web.training import TrainingStore


@pytest.fixture
def store(tmp_path):
    return TrainingStore(tmp_path, {
        'students': [{'student_id': 'S001'}, {'student_id': 'S002'}],
        'knowledge_base': {'knowledge': [{'knowledge_id': 'K-01', 'name': '一元一次方程'}]},
        'profiles': {'N01': {'S001': {'knowledge_states': [
            {'knowledge_id': 'K-01', 'status': 'weak'}]}}}})


class Client:
    def complete(self, system, user):
        assert 'S001' not in user
        assert 'llm_summary' in user
        return json.dumps({'questions': [{'knowledge_id': 'K-01', 'prompt': '求解 2x + 3 = 9。',
                                         'answer': 'x = 3', 'explanation': '移项后两边同除以 2。'}]})


def paper(store):
    return store.generate({'student_id': 'S001', 'node_id': 'N01', 'count': 1}, Client())


def image_data():
    Image = pytest.importorskip('PIL.Image')
    buffer = io.BytesIO()
    Image.new('RGB', (100, 100), 'white').save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def test_generation_scope_and_answer_privacy(store):
    p = paper(store)
    student = Account('S001', 'student', 'S001', 'Student')
    assert not store.list_for(student)['papers']
    store.approve(p['id'])
    visible = store.list_for(student)['papers']
    assert len(visible) == 1
    assert 'answer' not in visible[0]['questions'][0]
    assert not store.list_for(Account('S002', 'student', 'S002', 'Other'))['papers']
    with pytest.raises(ValueError):
        store.get('papers', '../secrets')


def test_scan_review_is_validated_persistent_and_not_repeated(store):
    p = paper(store)
    payload = {'paper_id': p['id'], 'student_id': 'S001', 'data': image_data()}
    with pytest.raises(ValueError):
        store.scan(payload)  # Unapproved paper.
    store.approve(p['id'])
    with pytest.raises(ValueError):
        store.scan({**payload, 'student_id': 'S002'})
    scan = store.scan(payload)
    with pytest.raises(ValueError):
        store.scan(payload)
    for scores in ({}, {'Q01': None}, {'Q01': True}, {'Q01': float('nan')}, {'Q01': 2}):
        with pytest.raises(ValueError):
            store.review({'scan_id': scan['id'], 'scores': scores}, 'teacher')
    store.review({'scan_id': scan['id'], 'scores': {'Q01': .5}}, 'teacher')
    reopened = TrainingStore(store.root, store.snapshot)
    assert reopened.get('scans', scan['id'])['scores'] == {'Q01': .5}
    with pytest.raises(ValueError):
        reopened.review({'scan_id': scan['id'], 'scores': {'Q01': 1}}, 'teacher')


def test_invalid_model_response_cannot_be_saved(store):
    class Invalid:
        def complete(self, *_):
            return '{"questions": []}'
    with pytest.raises(ValueError):
        store.generate({'student_id': 'S001', 'node_id': 'N01', 'count': 1}, Invalid())
    assert not store.items('papers')


def test_demo_uses_all_students_without_calling_api(store):
    store.snapshot['meta'] = {'dataset_id': 'official-v1'}
    store.snapshot['profiles']['N01']['S002'] = {'knowledge_states': [
        {'knowledge_id': 'K-01', 'status': 'insufficient_evidence'}]}
    class NoAPI:
        def complete(self, *_):
            raise AssertionError('demo must be offline')
    p = store.generate({'mode': 'unified', 'node_id': 'N01', 'count': 12, 'generator': 'demo'}, NoAPI())
    assert p['generator'] == 'local_demo' and p['student_count'] == 2
    assert len(p['questions']) == 12 and p['basis'][0]['focus_count'] == 1
    assert p['basis'][0]['question_count'] == 12
    assert p['status'] == 'draft' and p['student_id'] is None
    assert len({q['question_id'] for q in p['questions']}) == 12


def test_print_pdf_and_multipage_scan(store):
    pytest.importorskip('reportlab')
    fitz = pytest.importorskip('fitz')
    p = paper(store)
    pdf = store.pdf(p['id'])
    with fitz.open(stream=pdf, filetype='pdf') as doc:
        text = ''.join(page.get_text() for page in doc)
        assert p['id'] in text and '参考答案' not in text
        doc.new_page()
        scan_pdf = doc.tobytes()
    store.approve(p['id'])
    scan = store.scan({'paper_id': p['id'], 'student_id': 'S001',
                       'data': base64.b64encode(scan_pdf).decode()})
    assert scan['pages'] == 2
    assert (store.root / 'uploads' / (scan['id'] + '-1.png')).is_file()


def test_delete_hides_paper_and_scans_and_prevents_reuse(store):
    p = paper(store)
    store.approve(p['id'])
    scan = store.scan({'paper_id': p['id'], 'student_id': 'S001', 'data': image_data()})
    assert store.delete(p['id']) == {'ok': True}
    teacher = Account('teacher', 'teacher', None, 'Teacher')
    assert store.list_for(teacher) == {'papers': [], 'scans': []}
    assert store.items('papers')[0]['deleted_at']
    assert store.items('scans')[0]['id'] == scan['id']
    with pytest.raises(ValueError):
        store.approve(p['id'])
    with pytest.raises(ValueError):
        store.delete('../invalid')
    with pytest.raises(ValueError):
        store.review({'scan_id': scan['id'], 'scores': {'Q01': 1}}, 'teacher')
