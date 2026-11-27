import {esc, icon} from './charts.js';

const PRACTICE = new Set(['assessment', 'practice', 'probe']);
const WEAK = new Set(['confirmed_weak', 'likely_weak', 'sparse_poor']);
const GOOD = new Set(['confirmed_mastered', 'likely_mastered', 'sparse_good']);
const UNKNOWN = new Set(['unobserved', 'insufficient_evidence']);
const unique = values => [...new Set(values.filter(Boolean))];

// A view of the existing recommendation, not a second recommendation algorithm.
export function buildAdviceSummary(profile = {}, recommendation = {}, knowledge = {}) {
  const states = profile.knowledge_states || [];
  const points = new Map((knowledge.knowledge || []).map(k => [k.knowledge_id, k]));
  const materials = new Map((knowledge.materials || []).map(m => [m.material_id, m]));
  const objectives = new Map((knowledge.objectives || []).map(o => [o.objective_id, o]));
  const plan = [...(recommendation?.plan || [])].sort((a, b) => a.seq - b.seq);
  const items = plan.map(item => {
    const ids = unique(item.knowledge_ids || []);
    const issue = (profile.issues || []).find(i => i.issue_id === item.issue_id);
    const evidence = ids.map(id => states.find(s => s.knowledge_id === id)).filter(Boolean);
    const linked = unique(item.material_ids || []).map(id => materials.get(id)).filter(Boolean);
    const reading = linked.filter(m => !PRACTICE.has(m.material_type));
    const practice = linked.filter(m => PRACTICE.has(m.material_type));
    const losses = unique((issue?.rubric_evidence || [])
      .filter(r => Number.isFinite(r.score) && Number.isFinite(r.max_score) && r.score < r.max_score)
      .map(r => r.criterion));
    const specific = losses.filter(s => s !== '答案正确');
    let basis;
    // Counts are shown per knowledge point: summing them could double-count a question.
    if (evidence.length === 1) {
      const s = evidence[0];
      if (s.status === 'unobserved') basis = '暂无已评分作答，需要先补充观察，不能据此判断不会。';
      else if (s.status === 'insufficient_evidence') basis = '可用评分不足，先核验已有作答，再补充观察。';
      else if (Number.isFinite(s.evidence_count)) {
        basis = `${s.evidence_count} 条有效评分`;
        if (Number.isFinite(s.performance?.full_credit)) basis += `，${s.performance.full_credit} 条满分`;
        basis += specific.length ? `；关注「${specific[0]}」。` : losses.length ? '；仍有失分需核对。' : '。';
      }
    }
    basis ||= issue?.statement || item.reason || '查看原始作答与评分后，再核对本项安排。';
    const isProbe = item.activity_type === 'probe';
    const action = practice.length
      ? `${reading.length ? `先看 ${reading.length} 份学习材料，再` : '先独立'}完成 ${practice.length} 道${isProbe ? '补充题' : '练习'}，保留关键步骤。`
      : reading.length ? `阅读 ${reading.length} 份学习材料，梳理关键步骤，再按完成标准复核。` : item.activity;
    const condition = item.completion_condition || {};
    let check = item.check || '完成后核对作答与评分，再决定下一步。';
    if (condition.type === 'probe_evidence' && Number.isFinite(condition.min_graded)) {
      check = `取得 ${condition.min_graded} 道有效评分后复核；若发现失分，再转入针对性巩固。`;
    } else if (condition.type === 'full_credit' && Number.isFinite(condition.min_full_credit)) {
      check = `${condition.criterion && item.primary_material_id ? `${item.primary_material_id}「${condition.criterion}」得满分，且` : ''}至少 ${condition.min_full_credit} 题全对。`;
    }
    return {
      ...item, ids, materials: linked, basis, action, check, rawCheck: item.check,
      title: ids.map(id => points.get(id)?.name || id).join('、') || item.activity,
      objective: objectives.get(item.objective_id),
      records: unique([...(item.basis_records || []), ...(issue?.evidence?.records || [])]),
      label: isProbe ? '补充观察' : item.activity_type === 'transfer' ? '迁移应用' : '巩固与验证',
      tone: isProbe ? 'observe' : 'practice',
    };
  });
  return {
    items,
    minutes: items.every(i => Number.isFinite(i.est_minutes)) ? items.reduce((n, i) => n + i.est_minutes, 0) : null,
    weak: states.filter(s => WEAK.has(s.status)).length,
    good: states.filter(s => GOOD.has(s.status)).length,
    unknown: states.filter(s => UNKNOWN.has(s.status)).length,
    deferred: recommendation?.deferred?.length || 0,
    review: recommendation?.review_required?.length || 0,
  };
}

function adviceCard(item) {
  const materialLinks = item.materials.map(m => `<button type="button" class="advice-source" data-material="${esc(m.material_id)}" title="${esc(m.title)}" aria-label="查看材料 ${esc(m.material_id)} ${esc(m.title)}">${esc(m.material_id)} · ${PRACTICE.has(m.material_type) ? '练习' : '阅读'}</button>`).join('');
  return `<article class="advice-card ${item.tone}">
    <header class="advice-card-head"><span class="advice-step" aria-label="第 ${item.seq} 项">${String(item.seq).padStart(2, '0')}</span><span class="advice-kind">${esc(item.label)}</span>${Number.isFinite(item.est_minutes) ? `<span class="advice-duration">约 ${item.est_minutes} 分钟</span>` : ''}</header>
    <h3>${esc(item.title)}</h3>
    <dl class="advice-facts"><div><dt>依据</dt><dd>${esc(item.basis)}</dd></div><div><dt>安排</dt><dd>${esc(item.action)}</dd></div><div><dt>复核</dt><dd>${esc(item.check)}</dd></div></dl>
    <div class="advice-sources" aria-label="推荐材料">${materialLinks || '<span>本项暂无可打开的材料。</span>'}</div>
    <details class="advice-details"><summary>课程要求与完整依据 ${icon('arrow', 13)}</summary><div class="advice-detail-body">
      ${item.objective ? `<h4>课程要求</h4><p>${esc(item.objective.objective_text)}</p><p class="advice-locator">${esc(item.objective.unit)} · ${esc(item.objective.source_locator)}</p>` : ''}
      <div class="advice-detail-links">${item.ids.map(id => `<button type="button" class="text-button" data-knowledge="${esc(id)}">${esc(id)} · 知识联系与教材 ${icon('arrow', 13)}</button>`).join('')}</div>
      <h4>推荐依据</h4><p>${esc(item.reason || item.basis)}</p>
      ${item.records.length ? `<div class="advice-detail-links">${item.records.map(id => `<button type="button" class="advice-source" data-evidence="${esc(id)}">作答 ${esc(id)}</button>`).join('')}</div>` : '<p>当前没有可引用的作答记录，先补充观察。</p>'}
      <h4>原计划完成标准</h4><p>${esc(item.rawCheck || item.check)}</p>
      ${(item.teacher_comments || []).map(c => `<p><strong>教师提示：</strong>${esc(c.text)}</p>`).join('')}
    </div></details>
  </article>`;
}

export function renderAdviceSummary(profile, recommendation, knowledge) {
  const summary = buildAdviceSummary(profile, recommendation, knowledge);
  const visible = summary.items.slice(0, 3);
  return `<section class="advice-summary" aria-label="个人学习建议汇总">
    <div class="advice-overview"><div><h2>本轮学习建议</h2><p>${visible.length ? `优先完成以下 ${visible.length} 项${summary.minutes != null && summary.items.length <= 3 ? ` · 预计 ${summary.minutes} 分钟` : ''} · 按顺序推进` : '本轮暂无待执行建议，可进入学习空间继续练习。'}</p></div>
      <div class="advice-counts" aria-label="本次测验知识点概况"><span><b>${summary.weak}</b> 项需巩固</span><span><b>${summary.unknown}</b> 项待观察</span><span><b>${summary.good}</b> 项掌握或较好</span></div>
    </div>
    ${visible.length ? `<div class="advice-grid">${visible.map(adviceCard).join('')}</div>` : '<div class="advice-empty">没有新建议不等于已经全部掌握，仍以知识明细中的证据为准。</div>'}
    ${summary.deferred || summary.review ? `<p class="advice-pending">另有 ${summary.deferred} 项暂缓安排、${summary.review} 项需人工复核，核对后再调整计划。</p>` : ''}
    <footer class="advice-footer"><p>${summary.items.length > 3 ? `共 ${summary.items.length} 项安排，此处展示前三项。` : '先独立作答，再看提示；失分先订正，达标后尝试变式。'}<span>待观察表示证据不足；练习结果不自动改写正式画像。</span></p><button type="button" class="button primary" data-view="plan">进入学习空间 ${icon('arrow', 16)}</button></footer>
  </section>`;
}
