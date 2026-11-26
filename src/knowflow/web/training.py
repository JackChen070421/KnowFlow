"""Local variant papers and reviewed scan evidence; canonical data stays immutable."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from knowflow.config import get_settings
from knowflow.diagnosis.statuses import LABELS, training_priority
from knowflow.llm.client import build_client


def now():
    return datetime.now(UTC).isoformat()


class TrainingStore:
    def __init__(self, root: Path, snapshot: dict):
        self.root, self.snapshot = root, snapshot
        self.lock = threading.RLock()

    def save(self, kind, item):
        folder = self.root / kind
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (item['id'] + '.json')
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')
        temp.replace(target)

    def get(self, kind, identifier):
        try:
            if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
                raise ValueError()
            item = json.loads((self.root / kind / (identifier + '.json')).read_text('utf-8'))
            if item.get('deleted_at'):
                raise ValueError()
            return item
        except (ValueError, TypeError, FileNotFoundError) as exc:
            raise ValueError('试卷或扫描记录不存在。') from exc

    def items(self, kind):
        return [json.loads(p.read_text('utf-8')) for p in sorted((self.root / kind).glob('*.json'))]

    def student(self, sid):
        if sid not in {s['student_id'] for s in self.snapshot['students']}:
            raise ValueError('学生不存在。')

    def generate(self, payload, client=None):
        sid, nid = payload.get('student_id'), payload.get('node_id')
        mode = payload.get('mode', 'personal')
        if mode not in {'personal', 'unified'} or nid not in self.snapshot['profiles']:
            raise ValueError('请选择有效的模式和测验。')
        count = payload.get('count', 5)
        if type(count) is not int or not 1 <= count <= 12:
            raise ValueError('每份试卷支持 1 至 12 题。')
        kb = self.snapshot['knowledge_base']
        knowledge = {k['knowledge_id']: k['name'] for k in kb['knowledge']}
        if mode == 'personal':
            self.student(sid)
            profile = self.snapshot['profiles'][nid].get(sid)
            if not profile:
                raise ValueError('当前学生在该测验没有画像。')
            states = profile['knowledge_states']
            eligible = [s for s in states if s['status'] not in {'not_applicable', 'insufficient_evidence'}]
            selected = sorted(eligible, key=lambda s: training_priority(s['status']))[:count]
            summary = [{'knowledge_id': s['knowledge_id'], 'name': knowledge[s['knowledge_id']],
                        'status': s['status'], 'status_label': LABELS.get(s['status'], '待核验')} for s in selected]
        else:
            sid = None
            summary = []
            for kid, name in knowledge.items():
                counts = {}
                for profile in self.snapshot['profiles'][nid].values():
                    for state in profile['knowledge_states']:
                        if state['knowledge_id'] == kid:
                            counts[state['status']] = counts.get(state['status'], 0) + 1
                summary.append({'knowledge_id': kid, 'name': name, 'status_counts': counts})
        if not summary:
            raise ValueError('没有可用于出题的知识点。')
        if payload.get('generator') == 'demo':
            if mode != 'unified' or self.snapshot.get('meta', {}).get('dataset_id') != 'official-v1':
                raise ValueError('全体 Demo 卷适用于 official-v1 的统一训练模式。')
            from knowflow.web.demo_training import build_demo
            questions, basis = build_demo(summary, count)
            paper = {'id': str(uuid.uuid4()), 'mode': mode, 'student_id': None, 'node_id': nid,
                     'created_at': now(), 'questions': questions, 'status': 'draft',
                     'generator': 'local_demo', 'title': '全体学生数学变式训练 · Demo',
                     'basis': basis, 'student_count': len(self.snapshot['profiles'][nid]),
                     'note': '依据全体诊断汇总选题，本地模板模拟生成，未调用模型 API；非真实考试或新增作答。'}
            with self.lock:
                self.save('papers', paper)
            return paper
        client = client or build_client(get_settings())
        if client is None:
            raise ValueError('请先在设置中启用并配置 LLM API，再生成变式训练。')
        raw = client.complete(
            '你是数学教师。根据汇总知识状态生成中文变式训练：薄弱（weak/confirmed_weak/likely_weak）与较差（sparse_poor）优先，较好（sparse_good）轻量复核，掌握用迁移题；未覆盖用基线题，待评分先等评分，不判薄弱。'
            '不要声称复刻原题。只返回 JSON 对象 questions 数组，每题含 knowledge_id、prompt、answer、explanation。'
            'knowledge_id 必须来自输入白名单。使用纯文本数学符号，不使用 Markdown 或 LaTex。'
            '题目完整、答案明确、解析可核对，不包含姓名或个人信息。',
            json.dumps({'count': count, 'llm_summary': summary}, ensure_ascii=False))
        try:
            result = json.loads(raw)
            questions = result['questions']
            allowed = {s['knowledge_id'] for s in summary}
            if not isinstance(questions, list) or len(questions) != count:
                raise ValueError()
            clean = []
            for i, q in enumerate(questions):
                if q['knowledge_id'] not in allowed:
                    raise ValueError()
                for key in ('prompt', 'answer', 'explanation'):
                    if not isinstance(q[key], str) or not 1 <= len(q[key].strip()) <= 1600:
                        raise ValueError()
                clean.append({key: q[key] for key in ('knowledge_id', 'prompt', 'answer', 'explanation')})
                clean[-1]['question_id'] = f'Q{i+1:02}'
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('模型返回格式不合格，请重新生成。') from exc
        paper = {'id': str(uuid.uuid4()), 'mode': mode, 'student_id': sid, 'node_id': nid,
                 'created_at': now(), 'questions': clean, 'status': 'draft'}
        with self.lock:
            self.save('papers', paper)
        return paper

    def delete(self, identifier):
        with self.lock:
            paper = self.get('papers', identifier)
            paper['deleted_at'] = now()
            self.save('papers', paper)
            return {'ok': True}

    def approve(self, identifier):
        with self.lock:
            paper = self.get('papers', identifier)
            paper['status'] = 'approved'
            self.save('papers', paper)
            return paper

    def scan(self, payload):
        paper = self.get('papers', payload.get('paper_id'))
        sid = payload.get('student_id')
        self.student(sid)
        if paper['status'] != 'approved' or paper['student_id'] not in (None, sid):
            raise ValueError('试卷未审核或不属于该学生。')
        try:
            data = base64.b64decode(payload.get('data', ''), validate=True)
            if not 1 <= len(data) <= 12 * 1024 * 1024:
                raise ValueError()
            if data.startswith(b'%PDF-'):
                import fitz
                with fitz.open(stream=data, filetype='pdf') as doc:
                    if doc.is_encrypted or not 1 <= len(doc) <= 30:
                        raise ValueError()
                    # Rasterize instead of retaining active PDF content.
                    previews = []
                    for page in doc:
                        scale = min(1, 1800 / max(page.rect.width, page.rect.height))
                        previews.append(page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes('png'))
                    preview = previews[0]
                ext = 'pdf'
            else:
                from PIL import Image
                with Image.open(io.BytesIO(data)) as img:
                    if img.format not in {'JPEG', 'PNG'} or img.width * img.height > 30_000_000:
                        raise ValueError()
                    img.load()
                    img.thumbnail((1500, 2000))
                    buf = io.BytesIO()
                    img.convert('RGB').save(buf, format='PNG')
                    preview = buf.getvalue()
                ext = 'image'
                previews = [preview]
        except Exception as exc:
            raise ValueError('扫描无效：请上传不超过 12 MB 的 PNG、JPEG 或未加密 PDF（最多 30 页）。') from exc
        item = {'id': str(uuid.uuid4()), 'paper_id': paper['id'], 'student_id': sid,
                'node_id': paper['node_id'], 'created_at': now(), 'status': 'pending', 'format': ext, 'pages': len(previews), 'sha256': hashlib.sha256(data).hexdigest()}
        with self.lock:
            self.get('papers', paper['id'])
            if any(s['paper_id'] == paper['id'] and s['student_id'] == sid and s.get('sha256') == item['sha256'] for s in self.items('scans')):
                raise ValueError('该学生的同一份扫描已上传，请勿重复入库。')
            folder = self.root / 'uploads'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (item['id'] + '.bin')).write_bytes(data)
            (folder / (item['id'] + '.png')).write_bytes(preview)
            for index, page in enumerate(previews):
                (folder / (item['id'] + f'-{index}.png')).write_bytes(page)
            self.save('scans', item)
        return item

    def review(self, payload, reviewer):
        with self.lock:
            scan = self.get('scans', payload.get('scan_id'))
            if scan['status'] != 'pending':
                raise ValueError('该扫描已入库，请勿重复评分。')
            paper = self.get('papers', scan['paper_id'])
            scores = payload.get('scores')
            ids = {q['question_id'] for q in paper['questions']}
            if not isinstance(scores, dict) or set(scores) != ids or any(
                type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
                for v in scores.values()
            ):
                raise ValueError('请逐题填写 0 至 1 的得分比例；空白不能直接入库。')
            scan.update(status='reviewed', scores=scores, reviewed_by=reviewer, reviewed_at=now())
            self.save('scans', scan)
            return scan

    def list_for(self, account):
        papers = [p for p in self.items('papers') if not p.get('deleted_at')]
        visible = {p['id'] for p in papers}
        scans = [s for s in self.items('scans') if s['paper_id'] in visible]
        if account.role == 'student':
            papers = [p for p in papers if p['status'] == 'approved' and p['student_id'] in (None, account.student_id)]
            scans = [s for s in scans if s['student_id'] == account.student_id]
            papers = [{**p, 'questions': [{k: v for k, v in q.items() if k not in {'answer', 'explanation'}} for q in p['questions']]} for p in papers]
        return {'papers': papers, 'scans': scans}

    def pdf(self, identifier, answers=False):
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer
        paper = self.get('papers', identifier)
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        style = ParagraphStyle('Chinese', fontName='STSong-Light', fontSize=11, leading=19, wordWrap='CJK')
        heading = ParagraphStyle('Heading', parent=style, fontSize=18, leading=26, spaceAfter=14)
        story = [Paragraph(escape(paper.get('title', 'KnowFlow 变式训练')) + (' · 答案与解析' if answers else ''), heading),
                 Paragraph('待教师核题草稿' if paper['status'] == 'draft' else '已由教师核对发布', style),
                 Paragraph('试卷编号：' + paper['id'], style),
                 Paragraph('学生：' + (paper['student_id'] or '____________') + '　日期：____________', style),
                 Paragraph('教师复核后使用；完成后扫描上传，逐题核对入库。', style), Spacer(1, 18)]
        if paper.get('generator') == 'local_demo':
            story.insert(2, Paragraph(f"本地模拟生成 · 面向 {paper['student_count']} 位学生 · {len(paper['questions'])} 题 · 每题 10 分 · 共 {len(paper['questions'])*10} 分", style))
            if answers:
                story.append(Paragraph('出题依据：'+escape('；'.join(f"{b['knowledge_id']}：{b.get('focus_label', '旧口径：薄弱／表现混合')} {b['focus_count']} 人，安排 {b['question_count']} 题" for b in paper['basis'])), style))
                story.append(Paragraph('待评分／核验、未覆盖和较好不计入优先巩固人数；无评分不当作答错。', style))
        for index, q in enumerate(paper['questions']):
            if paper.get('generator') == 'local_demo' and not answers and index and index % 4 == 0:
                story.extend([PageBreak(), Paragraph('全体学生变式训练 · Demo（续）', heading)])
            content = [Paragraph(escape(q['question_id'] + ' · ' + q['prompt']).replace('\n', '<br/>'), style)]
            if answers:
                content += [Paragraph('参考答案：' + escape(q['answer']), style), Paragraph('解析：' + escape(q['explanation']), style), Spacer(1, 16)]
            else:
                content += [Spacer(1, 95)]
            # Long items are allowed to split naturally instead of overflowing a page.
            if len(q['prompt']) < 600:
                story.append(KeepTogether(content))
            else:
                story.extend(content)
        output = io.BytesIO()
        def footer(canvas, doc):
            canvas.setFont('STSong-Light', 9)
            canvas.setFillColor(colors.grey)
            canvas.drawString(40, 25, paper['id'] + ' · ' + str(doc.page))
        SimpleDocTemplate(output, pagesize=(595.28, 841.89), rightMargin=44, leftMargin=44,
                          topMargin=40, bottomMargin=45).build(story, onFirstPage=footer, onLaterPages=footer)
        return output.getvalue()
