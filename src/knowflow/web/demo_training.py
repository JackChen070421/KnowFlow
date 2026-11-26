"""Deterministic, labelled demo paper selected using aggregate observed states."""
from collections import Counter

from knowflow.diagnosis.statuses import SUPPORT


def question(kid, variant):
    a = variant + 2
    bank = {
        'K-01': (f'某文具每本 {a} 元，另付包装费 3 元。用含 n 的式子表示购买 n 本的总费用，并求 n=5 时的费用。',
                 f'{a}n+3；{5*a+3} 元。', '总费用等于单价乘数量再加固定费用。'),
        'K-02': (f'化简：{a}(2x-3)-({a+1}x-5)。',
                 f'{a-1}x+({5-3*a})。', f'去括号得 {2*a}x-{3*a}-{a+1}x+5，再合并同类项。'),
        'K-03': (f'用小棒摆图形，第 n 个图形用 {a}n+1 根。写出前三个图形所用根数，并解释每增加一个图形增加几根。',
                 f'{a+1}、{2*a+1}、{3*a+1} 根；每次增加 {a} 根。', '依次代入 n=1、2、3；相邻两项之差等于 n 的系数。'),
        'K-04': (f'解方程：{a}(x-2)+3={a+3}。', 'x=3。', f'去括号移项得 {a}x={3*a}，两边同除以 {a}。'),
        'K-05': (f'用消元法解方程组：x+y={a+4}，2x-y={2*a-1}。写出消元步骤。',
                 f'x={a+1}，y=3。', f'两式相加得 3x={3*a+3}；代回第一式求 y。'),
        'K-06': (f'买 2 本笔记本和 3 支笔共 {2*(a+3)+6} 元，买 1 本笔记本和 2 支笔共 {a+7} 元。设笔记本单价为 x、笔单价为 y，列方程组并求解。',
                 f'2x+3y={2*a+12}，x+2y={a+7}；x={a+3} 元，y=2 元。', '将第二式乘 2 后减去第一式得 y=2，代回求 x，并核对总价。'),
        'K-07': (f'解不等式：-{a}x+3>{3-4*a}，并说明最后一步不等号方向是否改变。',
                 'x<4；不等号方向改变。', f'移项得 -{a}x>{-4*a}，两边同除以负数 -{a}，不等号必须反向。'),
        'K-08': (f'解不等式组：2x>{2*a}，x+1≤{a+5}。写出其中的全部整数解。',
                 f'{a}<x≤{a+4}；整数解为 {a+1}、{a+2}、{a+3}、{a+4}。', '先分别求解，再取公共部分；左端为开端点，右端为闭端点。'),
        'K-09': (f'班级购买每本 {a+3} 元的练习本，另付运费 8 元，预算不超过 {10*(a+3)+8} 元。设购买 n 本，列不等式并求最多可买几本。',
                 f'{a+3}n+8≤{10*(a+3)+8}，n 为非负整数；最多 10 本。', '总支出不能超过预算，先扣除运费，再除以单价并考虑整数条件。'),
    }
    prompt, answer, explanation = bank[kid]
    return dict(knowledge_id=kid, prompt=prompt, answer=answer, explanation=explanation)


def build_demo(summary, count):
    eligible = [s for s in summary if s['knowledge_id'] in {f'K-{i:02}' for i in range(1, 10)}]
    if not eligible:
        raise ValueError('演示题模板仅支持当前七年级数学知识指标。')
    def priority(s):
        c = s.get('status_counts', {})
        return sum(c.get(k, 0) for k in SUPPORT)
    ranked = sorted(eligible, key=lambda s: (-priority(s), s['knowledge_id']))
    selected = ranked[:count]
    while len(selected) < count:
        selected.append(ranked[(len(selected)-len(ranked)) % len(ranked)])
    occurrence = Counter()
    questions = []
    for index, item in enumerate(selected):
        kid = item['knowledge_id']
        q = question(kid, occurrence[kid])
        occurrence[kid] += 1
        q.update(question_id=f'Q{index+1:02}', max_score=10)
        questions.append(q)
    return questions, [dict(s, focus_label='薄弱／较差', focus_count=priority(s), question_count=occurrence[s['knowledge_id']]) for s in ranked]
