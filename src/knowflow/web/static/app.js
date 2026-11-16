import { mountMap } from './knowledge-map.js';
let unmountMap;
import {
  esc,
  pct,
  states,
  categories,
  statusGroup,
  icon,
  badge,
  legend,
  donut,
  stateBars,
  lineChart,
  masteryBars
} from './charts.js';

let D, kb, storageOK = true,
  activeTask = null,
  drawerOrigin = null,
  llmSettings = null,
  settingsError = null,
  chatOpen = new URLSearchParams(location.search).get('chat') === '1',
  chatBusy = false,
  chatMessages = [];
const params = new URLSearchParams(location.search);
const state = {
  role: location.pathname === '/student' ? 'student' : 'teacher',
  view: params.get('view') || 'overview',
  node: params.get('node'),
  group: params.get('group') || 'ALL',
  student: params.get('student'),
  search: '',
  studentFilter: 'all',
  courseView: 'map',
  lab: 'axis',
  allHeatmap: false
};
const $ = s => document.querySelector(s);
const viewLabel = id => navItems().find(x => x[0] === id)?.[1] || (id === 'settings' ? '设置' : '工作台');
const nameFor = id => kb.knowledge.find(k => k.knowledge_id === id)?.name || id;
const objectiveFor = id => kb.objectives.find(o => o.objective_id === id);
const materialFor = id => kb.materials.find(m => m.material_id === id);
const node = () => D.nodes.find(n => n.node_id === state.node);
const currentProfile = () => D.profiles[state.node]?.[state.student];
const currentClass = () => D.classes[state.node]?.[state.group];
const profiles = () => Object.values(D.profiles[state.node]).filter(p => state.group === 'ALL' || p.group_id === state.group);
const groups = () => [...new Set(D.students.map(s => s.group_id))].sort();
const groupName = id => id === 'ALL' ? '全部班级' : `班级 ${id}`;
const note = text => `<p class="chart-note">${text}</p>`;
const empty = text => `<div class="empty">${text}</div>`;
const panelHead = (title, sub = '', extra = '') => `<div class="panel-header"><div><div class="panel-title"><h2>${title}</h2></div>${sub?`<p class="panel-sub">${sub}</p>`:''}</div>${extra}</div>`;
const listIds = items => (items || []).map(x => typeof x === 'string' ? x : x.knowledge_id);
const statusCount = p => categories.map(s => ({
  label: states[s].label,
  color: states[s].color,
  value: p.knowledge_states.filter(k => statusGroup(k.status) === s).length
}));

function stat(title, value, unit, foot, ico = 'target', accent = '#639782', shade = '#edf4ed') {
  return `<div class="stat-card" style="--accent:${accent};--shade:${shade}"><div class="stat-top"><span>${title}</span><span class="stat-icon">${icon(ico,17)}</span></div><div class="stat-value">${esc(value)}${unit?`<small>${unit}</small>`:''}</div><p class="stat-foot">${foot}</p></div>`;
}

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('visible');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('visible'), 3500);
}

function readWork() {
  try {
    const value = JSON.parse(localStorage.getItem('knowflow.practice.v1') || '{}');
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch {
    storageOK = false;
    return {};
  }
}

function workKey(sid, seq, mid) {
  return `${D.meta.dataset_id}|${D.recommendations[state.node][sid].source.profile_sha256}|${state.node}|${sid}|${seq}|${mid}`;
}

function submission(sid, seq, mid) {
  const v = readWork()[workKey(sid, seq, mid)];
  return v && typeof v.answer === 'string' && typeof v.submitted_at === 'string' ? v : null;
}

function planProgress(sid) {
  const plan = D.recommendations[state.node][sid]?.plan || [];
  const total = plan.reduce((a, p) => a + p.material_ids.length, 0);
  const done = plan.reduce((a, p) => a + p.material_ids.filter(m => submission(sid, p.seq, m)).length, 0);
  return {
    total,
    done
  };
}

function saveURL() {
  const q = new URLSearchParams({
    view: state.view,
    node: state.node,
    group: state.group,
    student: state.student
  });
  history.replaceState(null, '', `/${state.role}?${q}`);
}

function routeURL(role, view = 'overview') {
  return `/${role}?${new URLSearchParams({view,node:state.node,group:state.group,student:state.student})}`;
}

function normalize() {
  if (!D.nodes.some(n => n.node_id === state.node)) state.node = D.nodes.at(-1).node_id;
  if (!D.students.some(s => s.student_id === state.student)) state.student = D.students[0].student_id;
  if (!['ALL', ...groups()].includes(state.group)) state.group = 'ALL';
  if (![...navItems().map(x => x[0]), 'settings'].includes(state.view)) state.view = 'overview';
}

function navItems() {
  return state.role === 'teacher' ? [
    ['overview', '班级学情', 'overview'],
    ['course', '课程知识地图', 'map'],
    ['students', '学生明细', 'students'],
    ['reviews', '存疑证据', 'shield'],
    ['quality', '数据与证据', 'shield']
  ] : [
    ['overview', '学习总览', 'overview'],
    ['course', '我的知识地图', 'map'],
    ['plan', '练习与建议', 'book'],
    ['explore', '跨域探索', 'spark']
  ];
}

function shell() {
  const active = navItems().find(n => n[0] === state.view) || ['settings', '设置', 'settings'];
  return `<div class="app-shell"><aside class="sidebar"><a class="brand" href="${routeURL(state.role)}"><img src="/favicon.svg" alt=""><div><strong>KnowFlow</strong><small>让学习有迹可循</small></div></a><div class="sidebar-label">${state.role==='teacher'?'TEACHING WORKSPACE':'MY LEARNING SPACE'}</div><nav class="nav" aria-label="主要导航">${navItems().map(([id,label,ico])=>`<button data-view="${id}" class="${state.view===id?'active':''}" aria-label="${label}" ${state.view===id?'aria-current="page"':''} title="${label}">${icon(ico)}<span>${label}</span></button>`).join('')}</nav><div class="sidebar-tools"><button class="settings-link ${state.view==='settings'?'active':''}" data-view="settings" aria-label="设置" title="设置" ${state.view==='settings'?'aria-current="page"':''}>${icon('settings',16)}<span>设置</span></button></div><div class="side-story"><div class="eyebrow">EVIDENCE INTO ACTION</div><h3>看见学习的联系<br>找到下一步方向</h3><p>课程要求 · 学情证据 · 学习行动<br>每一条建议，都有据可循。</p><div class="steps"><span></span><span></span><span></span></div></div><div class="sidebar-footer"><strong><i class="live-dot"></i> 本机数据已就绪</strong><p>知识 · 画像 · 建议，校验通过<br>赛事模拟数据 / 本机演示</p></div></aside><div class="workspace"><header class="topbar"><div class="breadcrumb"><span>工作空间</span><span>/</span><b>${active[1]}</b></div><div class="top-actions"><div class="role-switch" aria-label="切换展示视角"><a href="${routeURL('teacher')}" class="${state.role==='teacher'?'active':''}">${icon('students',15)}教师视角</a><a href="${routeURL('student')}" class="${state.role==='student'?'active':''}">${icon('book',15)}学生视角</a></div><div class="avatar" title="本机演示，无登录账户">${state.role==='teacher'?'KF':'S'}</div></div></header><main id="main" tabindex="-1" class="fade-in">${content()}<footer class="page-footer"><strong>KnowFlow / 从理解课程，到理解每一个学生。</strong><span>赛事模拟数据 · ${esc(D.meta.dataset_id)} · 规则推荐 · 本机展示</span></footer></main></div>${chatWidget()}`;
}

function hero(eyebrow, title, desc) {
  return `<section class="hero"><div class="hero-copy"><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${desc}</p></div><div class="node-card"><div class="eyebrow">CURRENT OBSERVATION</div><strong>${esc(state.node)} · 学习观察节点</strong><p>${esc(node().date)} · ${node().taught_objective_ids.length} 个已教主题</p></div></section>`;
}

function filters(student = false) {
  return `<div class="toolbar"><div class="filters"><label class="filter">观察节点<select id="node-select">${D.nodes.map(n=>`<option value="${esc(n.node_id)}" ${n.node_id===state.node?'selected':''}>${esc(n.node_id)} · ${esc(n.date)}</option>`).join('')}</select></label>${state.role==='teacher'?`<label class="filter">班级范围<select id="group-select">${['ALL',...groups()].map(g=>`<option value="${esc(g)}" ${g===state.group?'selected':''}>${groupName(g)}</option>`).join('')}</select></label>`:''}${student?`<form id="student-form" class="search-field">${icon('search',16)}<input id="student-id" aria-label="输入学生 ID" list="student-ids" placeholder="输入学生 ID" value="${esc(state.student)}" autocomplete="off"><button class="text-button" type="submit">查看</button><datalist id="student-ids">${D.students.map(s=>`<option value="${esc(s.student_id)}">${esc(s.group_id)}</option>`).join('')}</datalist></form>`:''}</div><span class="date-caption">同一节点 · 统一范围 · 证据可追溯</span></div>`;
}

function content() {
  if (state.view === 'settings') return settingsPage();
  if (state.role === 'student') {
    if (state.view === 'course') return coursePage(true);
    if (state.view === 'plan') return studentPlans();
    if (state.view === 'explore') return explorePage();
    return studentHome();
  }
  if (state.view === 'course') return coursePage(false);
  if (state.view === 'students') return studentsPage();
  if (state.view === 'reviews') return reviewsPage();
  if (state.view === 'quality') return qualityPage();
  return overview();
}

function cohortStats() {
  const list = profiles();
  const stats = list.map(p => D.stats[state.node][p.student_id]);
  return {
    students: list.length,
    known: list.filter(p => p.coverage.scope_known).length,
    needs: list.filter(p => p.lists.needs_consolidation.length).length,
    assigned: stats.reduce((a, s) => a + s.assigned, 0),
    attempted: stats.reduce((a, s) => a + s.attempted, 0)
  };
}

function historicalItems(sid = null) {
  const ids = new Set(sid ? [sid] : profiles().map(p => p.student_id));
  const selected = D.records.filter(r => r.node_id === state.node && ids.has(r.student_id) && r.assigned);
  const full = selected.filter(r => r.attempted && r.score != null && r.score === r.max_score).length;
  const partial = selected.filter(r => r.attempted && r.score != null && r.score > 0 && r.score < r.max_score).length;
  const zero = selected.filter(r => r.attempted && r.score === 0).length;
  const pending = selected.filter(r => r.attempted && r.score == null).length;
  const not = selected.filter(r => !r.attempted).length;
  return [{
    label: '满分记录',
    value: full,
    color: '#438a74'
  }, {
    label: '部分得分',
    value: partial,
    color: '#a9bf9d'
  }, {
    label: '零分记录',
    value: zero,
    color: '#d8a16f'
  }, {
    label: '已作答待评分',
    value: pending,
    color: '#aa9bbf'
  }, {
    label: '已布置未作答',
    value: not,
    color: '#d9e2dd'
  }];
}

function trend() {
  return lineChart(groups().filter(g => state.group === 'ALL' || g === state.group).map((g, i) => ({
    label: groupName(g),
    color: ['#438a74', '#d4a16f'][i % 2],
    points: D.nodes.map(n => ({
      label: n.node_id,
      date: n.date,
      value: D.students.filter(s => s.group_id === g).reduce((sum, s) => sum + D.stats[n.node_id][s.student_id].graded, 0)
    }))
  })));
}

function commonIssues() {
  const rows = currentClass().rubric_patterns.slice(0, 4);
  return rows.length ? `<div class="issue-list">${rows.map((r,i)=>`<div class="issue-row"><div class="issue-number">0${i+1}</div><div class="issue-body"><h3><button class="text-button" data-knowledge="${esc(r.knowledge_id)}">${esc(r.knowledge_id)} · ${esc(r.criterion)}</button></h3><p>${esc(nameFor(r.knowledge_id))}</p><div class="issue-meter"><i style="width:${r.prevalence*100}%"></i></div></div><div class="issue-rate">${pct(r.prevalence)}<small>${r.affected_student_count} / ${r.observed_student_count} 人</small></div></div>`).join('')}</div>` : empty('当前范围没有可汇总的评分点失分证据。');
}

function overview() {
  const c = currentClass(),
    s = cohortStats(),
    items = historicalItems();
  return `${hero('TEACHING INSIGHT / 01','把班级的学习，看得更清楚。','从课程地图到共性问题，让每一次教学调整都能找到证据。')} ${filters()}<section class="stats-grid">${stat('当前学生',s.students,'人',`${s.known} 人的本节点范围已确认`,'students')}${stat('平均观测覆盖',pct(c.coverage_summary.mean_ratio),'',`按学生平均 · 已评分 / 节点可测题目`,'target','#889d6f','#f1f4eb')}${stat('建议巩固',s.needs,'人','至少一个知识点进入巩固清单，人数不重叠','book','#cd9a68','#faf2e7')}${stat('历史作答完成',pct(s.assigned?s.attempted/s.assigned:null),'',`${s.attempted} / ${s.assigned} 条已布置记录有作答`,'check','#9b88b4','#f2eef6')}</section><div class="grid-main"><section class="panel">${panelHead('知识点掌握分布','点击条形，追踪知识点的学生差异与依据。','<span class="pill">人数 · 互斥状态</span>')}${stateBars(c.knowledge_distribution,nameFor)}${legend()}${note('每行分母为所选班级全体学生。“待观察”表示证据不足；“本节点不适用”不参与能力判断。')}</section><section class="panel">${panelHead('历史作答构成','按本节点已布置、去重后的记录统计。')}${donut(items,s.assigned,'条已布置记录')}${note('部分得分与零分分开保留。缺少记录不在这张饼图的分母中，也不等于学生未完成。')}</section></div><div class="grid-half"><section class="panel">${panelHead('观察节点对照','各班已评分记录数量，了解证据积累情况。','<span class="pill">条数</span>')}${trend()}${note('两个节点的教学范围与题目不同，连线仅用于对照记录量，不代表成绩或能力的增长趋势。')}</section><section class="panel">${panelHead('共性失分线索','从评分点出发，安排有针对性的讲解。','<span class="pill warm">TOP 4</span>')}${commonIssues()}${note('比例 = 出现该评分点失分的学生 / 该知识点有观测的学生。具体原因仍需核对作答过程。')}</section></div>${heatmap()}<section class="panel">${panelHead('班级之间，有哪些值得关注的差异？','以已评分记录计算得分率；同节点对照也需结合材料覆盖范围。')}${groupComparison()}</section>`;
}

function groupComparison() {
  return `<div class="mini-metrics">${groups().map(g=>{const stats=D.students.filter(s=>s.group_id===g).map(s=>D.stats[state.node][s.student_id]);const score=stats.reduce((a,s)=>a+s.earned_score,0),max=stats.reduce((a,s)=>a+s.possible_score,0);const c=D.classes[state.node][g];return `<div class="mini-metric">${groupName(g)} · ${stats.length} 人<strong>${pct(max?score/max:null)}</strong><small>已评分得分 ${score} / ${max}<br>平均观测覆盖 ${pct(c.coverage_summary.mean_ratio)}</small></div>`;}).join('')}<div class="mini-metric">阅读提示<strong>${state.node}</strong><small>得分率只描述已评分题目。<br>覆盖少、材料不同，都可能影响比较。</small></div></div>`;
}

function heatmap() {
  const list = profiles(),
    visible = state.allHeatmap ? list : list.slice(0, 12);
  return `<section class="panel heatmap-panel">${panelHead('学生 × 知识点 · 学习全景','一个色块对应一名学生的一个知识点。点击即可查看个人证据。',`<button class="text-button" data-view="students">查看学生明细 ${icon('arrow',14)}</button>`)}<div class="table-scroll"><table class="data-table heatmap"><thead><tr><th>学生 / 知识点</th>${kb.knowledge.map(k=>`<th><button data-knowledge="${esc(k.knowledge_id)}" title="${esc(k.name)}">${esc(k.knowledge_id)}</button></th>`).join('')}</tr></thead><tbody>${visible.map(p=>`<tr><td><button class="text-button mono" data-student="${esc(p.student_id)}">${esc(p.student_id)}</button> <small class="muted">${esc(p.group_id)}</small></td>${kb.knowledge.map(k=>{const s=p.knowledge_states.find(x=>x.knowledge_id===k.knowledge_id);return `<td><button class="cell cell-${statusGroup(s.status)}" data-person-knowledge="${esc(k.knowledge_id)}" data-person="${esc(p.student_id)}" style="background:${states[s.status].color}" aria-label="${esc(p.student_id+' '+k.name+' '+states[s.status].label+'，'+s.evidence_count+'条有效评分')}" title="${esc(states[s.status].label+' · '+s.evidence_count+'条有效评分')}">${states[s.status].short}</button></td>`;}).join('')}</tr>`).join('')}</tbody></table></div><div class="table-footer"><span>显示 ${visible.length} / ${list.length} 人 · ${kb.knowledge.length} 个知识点</span><button class="text-button" data-toggle-heatmap>${state.allHeatmap?'收起列表':'展开全部学生'} ${icon('arrow',14)}</button></div>${legend()}</section>`;
}

function studentsPage() {
  let list = profiles().filter(p => p.student_id.toLowerCase().includes(state.search.toLowerCase()));
  if (state.studentFilter === 'needs') list = list.filter(p => p.lists.needs_consolidation.length);
  if (state.studentFilter === 'unknown') list = list.filter(p => !p.coverage.scope_known);
  if (state.studentFilter === 'submitted') list = list.filter(p => planProgress(p.student_id).done);
  return `${hero('STUDENT PORTRAITS / 02','每个学生，都有自己的学习路径。','把成绩、证据覆盖、知识状态和练习行动放在一起理解。')}${filters()}<section class="panel">${panelHead('学生明细','选择一名学生，在下方展开完整画像。',`<span class="pill">${list.length} 人</span>`)}<div class="toolbar"><label class="search-field">${icon('search',15)}<input id="student-search" placeholder="搜索学生 ID" aria-label="搜索学生 ID" value="${esc(state.search)}"></label><label class="filter">筛选<select id="student-filter"><option value="all" ${state.studentFilter==='all'?'selected':''}>全部学生</option><option value="needs" ${state.studentFilter==='needs'?'selected':''}>建议巩固</option><option value="unknown" ${state.studentFilter==='unknown'?'selected':''}>范围待确认</option><option value="submitted" ${state.studentFilter==='submitted'?'selected':''}>有本机练习提交</option></select></label></div><div class="table-scroll"><table class="data-table"><thead><tr><th>学生</th><th>已评分得分率</th><th>观测覆盖</th><th>历史作答</th><th>建议巩固 / 待观察</th><th>新计划本机提交</th><th></th></tr></thead><tbody>${list.map(p=>{const s=D.stats[state.node][p.student_id],pr=planProgress(p.student_id);return `<tr class="${p.student_id===state.student?'selected':''}"><td><button class="text-button mono" data-student="${esc(p.student_id)}">${esc(p.student_id)}</button> <small class="muted">${esc(p.group_id)}</small></td><td>${pct(s.score_ratio)}<small class="muted"> (${s.graded} 条)</small></td><td>${p.coverage.scope_known?pct(p.coverage.ratio):'范围待确认'}</td><td>${s.assigned?`${s.attempted} / ${s.assigned}`:'未记录'}</td><td>${p.lists.needs_consolidation.length} / ${p.lists.needs_observation.length}</td><td>${pr.done?`${pr.done} / ${pr.total} · 待评阅`:pr.total?'未记录':'无新计划'}</td><td><button class="text-button" data-student="${esc(p.student_id)}" aria-label="查看 ${esc(p.student_id)} 详情">${icon('arrow',15)}</button></td></tr>`;}).join('')}</tbody></table>${!list.length?empty('没有符合筛选条件的学生。'):''}</div>${note('“新计划本机提交”仅统计在此浏览器中实际提交的活动，不是历史作答完成度，也尚未进入正式画像。')}</section><div id="student-detail">${profileDetail(currentProfile(),true)}</div>`;
}

function profileDetail(p, teacher = false) {
  const s = D.stats[state.node][p.student_id];
  return `<section class="profile-banner"><div class="student-identity"><div class="student-avatar">${esc(p.student_id.slice(-3))}</div><div><h2>${esc(p.student_id)} <span class="pill">${esc(p.group_id)}</span></h2><p>${esc(state.node)} · ${p.coverage.scope_known?'节点范围已确认':'参与范围待确认'} · ${s.graded} 条有效评分</p></div></div><div class="profile-actions">${teacher?`<a class="button light" href="${routeURL('student')}">以学生视角打开 ${icon('arrow',14)}</a>`:''}<button class="button" data-export>${icon('download',14)}导出本机摘要</button></div></section><div class="mini-metrics"><div class="mini-metric">已评分得分率<strong>${pct(s.score_ratio)}</strong><small>${s.earned_score} / ${s.possible_score} 分 · 仅已评分题</small></div><div class="mini-metric">节点观测覆盖<strong>${p.coverage.scope_known?pct(p.coverage.ratio):'—'}</strong><small>${p.coverage.observed_items} / ${p.coverage.applicable_items ?? '—'} 个可测题目</small></div><div class="mini-metric">历史作答完成<strong>${pct(s.completion)}</strong><small>${s.attempted} / ${s.assigned} 条已布置记录</small></div></div><div class="grid-main"><section class="panel">${panelHead('知识表现与不确定性','点选一个知识点，查看评分证据、课程要求与学习建议。')}${masteryBars(p.knowledge_states,nameFor)}</section><section class="panel">${panelHead('知识状态分布','以本课程知识点为单位，每个知识点只归入一种状态。')}${donut(statusCount(p),p.knowledge_states.length,'个知识点')}${note('状态由诊断模块给出，不以得分率直接替代。证据不足时，优先补充观察。')}</section></div><div class="grid-half"><section class="panel">${panelHead('需要巩固的内容','结合模型状态与评分点表现，而不是只看单次分数。')}${knowledgeList(p.lists.needs_consolidation,'当前没有进入巩固清单的知识点。')}</section><section class="panel">${panelHead('优势与待观察','保留已知与未知的边界，避免给学生贴标签。')}<h3 class="muted" style="font-size:11px;margin-bottom:10px">掌握较好</h3>${knowledgeList(p.lists.strengths,'当前证据尚不足以确认优势知识点。')}<h3 class="muted" style="font-size:11px;margin:18px 0 10px">待观察 · ${p.lists.needs_observation.length} 个</h3><div class="material-buttons">${listIds(p.lists.needs_observation).map(k=>`<button class="material-chip" data-knowledge="${esc(k)}">${esc(k)} ${icon('arrow',12)}</button>`).join('')}</div></section></div><section class="panel">${panelHead('从学习问题，到下一步行动','建议由任务 3 的规则模块生成；原因、材料、验证标准逐条对应。','<span class="pill">可追溯建议</span>')}${plans(p.student_id,teacher)}</section>`;
}

function knowledgeList(list, fallback) {
  return list.length ? `<div class="path-list">${list.map((v,i)=>{const id=typeof v==='string'?v:v.knowledge_id;return `<div class="path-row"><span class="path-marker">${i+1}</span><div><button class="text-button" data-knowledge="${esc(id)}"><strong>${esc(nameFor(id))}</strong></button>${v.reason?`<p>${esc(v.reason)}</p>`:''}</div></div>`;}).join('')}</div>` : empty(fallback);
}

function plans(sid, teacher = false) {
  const r = D.recommendations[state.node][sid];
  if (!r.plan.length) return empty('此节点没有生成新计划。若参与范围不明，请先确认范围；表现较好时也不强行加练。');
  return `<div class="plan-list">${r.plan.map(p=>{const done=p.material_ids.filter(m=>submission(sid,p.seq,m)).length;return `<article class="plan-card ${p.activity_type==='probe'?'probe':''}"><div class="plan-top"><div class="plan-heading"><span class="plan-index">${String(p.seq).padStart(2,'0')}</span><div><h3>${esc(p.activity)}</h3><div class="plan-meta"><span>${esc(p.issue_id)}</span><span>${esc(p.knowledge_ids.join(' / '))}</span><span>预计 ${p.est_minutes} 分钟 · 规则估算</span></div></div></div><span class="pill ${p.activity_type==='probe'?'purple':'warm'}">${p.activity_type==='probe'?'先补充观察':'巩固与验证'}</span></div><p>${esc(p.reason)}</p><div class="check-line">${icon('check',15)}<span><strong>怎样判断完成有效：</strong>${esc(p.check)}</span></div>${(p.prerequisite_check?.missing_knowledge_ids||[]).length?`<div class="notice warm">先修待巩固：${p.prerequisite_check.missing_knowledge_ids.map(k=>esc(k)).join('、')}</div>`:''}${(p.prerequisite_check?.pending_knowledge_ids||[]).length?`<div class="notice">先修证据不足：${p.prerequisite_check.pending_knowledge_ids.map(k=>esc(k)).join('、')}，先补观测再判断。</div>`:''}${(p.prerequisite_check?.draft_edges||[]).length?`<div class="notice">关系待核验：${p.prerequisite_check.draft_edges.length} 条先修/关联关系尚未人工核对，本轮不参与排序。</div>`:''}${(p.relation_notes||[]).map(n=>`<div class="notice">${esc(n.note)}</div>`).join('')}<div class="material-buttons">${p.material_ids.map(m=>`<button class="material-chip" data-material="${esc(m)}" data-plan="${p.seq}" data-owner="${esc(sid)}">${icon(materialFor(m)?.material_type==='assessment'?'target':'book',13)}${esc(m)} · ${materialFor(m)?.material_type==='assessment'?'练习':'阅读'}${submission(sid,p.seq,m)?' ✓':''}</button>`).join('')}</div><div class="progress-strip"><span>${done?`本机已提交 ${done} / ${p.material_ids.length} 项 · 待评阅`:'新计划完成情况：未记录'}</span><div class="progress-track"><i style="width:${done/p.material_ids.length*100}%"></i></div><span>${teacher?'可查看学生在同一浏览器提交的内容':'点击材料开始活动'}</span></div></article>`;}).join('')}</div><div class="notice">${storageOK?'新练习保存在当前浏览器，教师页和学生页可在同一浏览器中查看。':'当前浏览器不允许本地存储，暂时无法保存新练习。'}提交后标记“待评阅”，不会自动改写历史成绩或知识状态。</div>`;
}

function coursePage(personal) {
  const p = personal ? currentProfile() : null;
  const g = kb.curriculum_graph;
  return `${hero('KNOWLEDGE ATLAS / 03',personal?'先看见全貌，再找到自己的方向。':'让课程结构、学习证据与材料连起来。','选取知识点，查看它的学习要求、教材出处与对应指标的学情证据。')}${filters(personal)}<section class="panel graph-panel"><div class="graph-toolbar"><div>${panelHead(personal?'我的课程地图':'课程知识地图','课程主题 → 知识指标 → 材料与学习证据')}</div><div class="tabs" aria-label="地图视图"><button class="${state.courseView==='map'?'active':''}" data-course-view="map">知识地图</button><button class="${state.courseView==='list'?'active':''}" data-course-view="list">课程要求清单</button></div></div>${state.courseView==='map'?knowledgeMap(p):requirements()}${D.meta.dataset_id==='official-v1'?'':personal?legend():note('色条表示本班知识状态构成。')}</section><div class="course-foot"><section class="panel">${panelHead('材料出处，随时可查','每个知识点的题目与学习材料由 Q-matrix 对应。')}<div class="source-row"><div class="source-icon">${icon('book',19)}</div><div><h3>课程要求与课程标准</h3><p>目标、章节与课标页码 · 逐字校对状态保留</p></div><button class="text-button" data-course-view="list">查看 ${icon('arrow',13)}</button></div>${kb.materials.filter(m=>m.material_type==='reference'&&kb.objectives.some(o=>o.objective_id===m.objective_id)).map(m=>`<div class="source-row"><div class="source-icon">${icon('link',18)}</div><div><h3>${esc(m.title)}</h3><p>${esc(m.material_id)} · 原始资料出处</p></div><button class="text-button" data-material="${esc(m.material_id)}">查看 ${icon('arrow',13)}</button></div>`).join('')}</section><section class="panel">${panelHead('关系有类型，连线有依据','保留课程的必要联系，也保留尚未确认的边界。')}<div class="mini-metrics">${g?[['先修',g.counts.prerequisite_count,'已入库关系'],['易混',g.counts.confusable_count,'已入库关系'],['相关',g.counts.related_count,'已入库关系'],['待核验',g.counts.draft_count,'未人工核对']].map(([label,value,note])=>`<div class="mini-metric">${label}关系<strong>${value}</strong><small>${note}</small></div>`).join(''):'<div class="mini-metric">课程图谱<strong>未载入</strong><small>请重新生成展示数据</small></div>'}</div><p class="panel-sub">此处统计正式课程图谱（教材细目层）。仅有 reviewed 的先修关系参与建议排序；draft 关系只展示并标“待核验”。</p><div class="notice">跨域实验放在学生页“跨域探索”中，明确标为自编拓展，方便在保留证据边界的同时展示交互学习。</div></section></div>`;
}

function knowledgeMap(p) {
  if(D.meta.dataset_id==='official-v1')return '<div data-interactive-map></div>';
  return `<div class="knowledge-map">${kb.objectives.map((o,i)=>`<div class="topic-column"><div class="topic-head"><div class="eyebrow">MODULE ${String(i+1).padStart(2,'0')}</div><h3>${esc(o.theme)}</h3><small>${esc(o.objective_id)}</small></div><div class="knowledge-branch">${kb.knowledge.filter(k=>k.objective_id===o.objective_id).map(k=>{const s=p?.knowledge_states.find(x=>x.knowledge_id===k.knowledge_id),c=currentClass().knowledge_distribution.find(x=>x.knowledge_id===k.knowledge_id);const materialCount=new Set(kb.qmatrix.filter(q=>q.knowledge_id===k.knowledge_id&&q.weight>0).map(q=>q.material_id)).size;return `<button class="knowledge-node" data-knowledge="${esc(k.knowledge_id)}"><span class="kn-top"><span>${esc(k.knowledge_id)}</span>${s?badge(s.status):`<span class="pill">${c.observed_student_count} 人有观测</span>`}</span><strong>${esc(k.name)}</strong><span class="kn-bottom"><span>${materialCount} 份关联材料</span>${s?`<span>${s.evidence_count} 条评分 ${icon('arrow',11)}</span>`:`<span class="kn-meter">${[['mastered_count','mastered'],['weak_count','weak'],['mixed_count','mixed'],['insufficient_count','insufficient_evidence'],['not_applicable_count','not_applicable']].filter(([f])=>c[f]>0).map(([f,t])=>`<i style="flex:${c[f]};background:${states[t].color}"></i>`).join('')}</span>`}</span></button>`;}).join('')}</div></div>`).join('')}</div>`;
}

function requirements() {
  return `<div class="requirement-grid">${kb.objectives.map(o=>`<article class="requirement-card"><span class="pill">${esc(o.objective_id)}</span><h3>${esc(o.theme)}</h3><p>${esc(o.objective_text)}</p><div class="material-buttons">${kb.knowledge.filter(k=>k.objective_id===o.objective_id).map(k=>`<button class="material-chip" data-knowledge="${esc(k.knowledge_id)}">${esc(k.knowledge_id)}</button>`).join('')}</div><div class="source"><strong>${esc(o.unit)}</strong><br>出处：${esc(o.source_locator)}<br>${esc(o.notes||'')}</div></article>`).join('')}</div>`;
}

function studentHome() {
  const p = currentProfile(),
    s = D.stats[state.node][state.student],
    focus = p.lists.needs_consolidation[0],
    next = focus?.knowledge_id || listIds(p.lists.needs_observation)[0],
    progress = planProgress(state.student);
  return `<section class="student-hero">${hero('YOUR LEARNING SPACE',`你好，${esc(state.student)}。<br>今天，让理解再向前一步。`,'不用一次解决所有问题。从一个有依据的小目标开始，逐渐连接知识、练习与真实世界。')}</section>${filters(true)}<section class="stats-grid">${stat('已评分得分率',pct(s.score_ratio),'',`${s.graded} 条有效评分 · 仅反映已评分题目`,'trend')}${stat('有评分的知识点',p.coverage.observed_knowledge,'个',`本节点可测 ${p.coverage.total_knowledge} 个知识点`,'map','#8a9d6e','#f0f4e8')}${stat('建议巩固',p.lists.needs_consolidation.length,'个',`另有 ${p.lists.needs_observation.length} 个知识点待观察`,'target','#cc9564','#faf1e6')}${stat('新计划本机提交',progress.done?`${progress.done} / ${progress.total}`:'未记录','',progress.total?'提交内容待评阅，历史画像不变':'当前没有新计划','check','#9a84ad','#f2edf6')}</section><div class="grid-main"><section class="focus-card"><div class="eyebrow">YOUR NEXT STEP</div><h2>${next?esc(nameFor(next)):'先确认观察范围，再决定下一步'}</h2><p>${focus?'从已有失分证据出发，先理解方法，再通过练习验证。':next?'这个知识点的证据还不够。先做少量探测练习，让我们更了解你的学习情况。':'当前没有可以确认的学习需求，可以查看已有课程材料或尝试自编拓展。'}</p><button class="button" ${next?`data-knowledge="${esc(next)}"`:'data-view="course"'}>${next?'看看为什么从这里开始':'打开课程地图'} ${icon('arrow',15)}</button></section><section class="panel">${panelHead('让一次练习形成闭环','从理解原因到检验结果。')}<div class="path-list">${[['01','看依据','先看评分与课程要求，理解学习目标。'],['02','做活动','使用关联材料，在本机提交学习过程。'],['03','再验证','按建议里的标准核对，等待教师评阅。']].map(([n,t,d])=>`<div class="path-row"><span class="path-marker">${n}</span><div><strong>${t}</strong><p>${d}</p></div></div>`).join('')}</div></section></div><section class="panel">${panelHead('我的知识地图','点击知识点，查看学习要求、依据与材料。',`<button class="text-button" data-view="course">完整课程要求 ${icon('arrow',14)}</button>`)}${knowledgeMap(p)}${D.meta.dataset_id==='official-v1'?'':legend()}</section>${profileDetail(p)}`;
}

function studentPlans() {
  return `${hero('LEARNING INTO ACTION / 04','让下一步，有目标，也有检验标准。','阅读材料、完成练习、记录思路。每一条学习建议都回到具体问题与具体证据。')}${filters(true)}<section class="panel">${panelHead(`${esc(state.student)} 的学习建议`,`${esc(state.node)} · 规则模块生成 · 用时为估算值`,'<span class="pill">任务 3 成果</span>')}${plans(state.student)}</section><section class="panel section-gap">${panelHead('想把学会的知识用起来？','试试自编互动实验，把抽象关系变成可观察的变化。')}<p class="panel-sub">先用数轴理解负数乘法的方向变化，再用预算方案练习建立数量关系。探索结果不计入正式评分。</p><button class="button light section-gap" data-view="explore">进入跨域探索 ${icon('arrow',15)}</button></section>`;
}

function qualityPage() {
  const q = D.quality;
  const labels = {
    observed_correct: '满分观测',
    observed_wrong: '非满分观测',
    pending: '已作答待评分',
    assigned_not_attempted: '已布置未作答',
    unobserved: '无观测'
  };
  return `${hero('TRUST & TRACEABILITY / 05','每一个结论，都经得起回看。','展示数据整理、质量检查和证据链，把“为什么这样判断”说清楚。')}<section class="panel">${panelHead('从原始记录到可用证据','此页为整个数据集的质量审计，跨两个节点；不受班级筛选影响。','<span class="pill">全数据集</span>')}<div class="audit-flow">${[[q.input_records,'输入逻辑记录','CSV 解析后的记录数'],[q.duplicates_removed,'修订 / 重复淘汰','按数据层规则保留版本'],[q.rejected_records,'不纳入记录','保留拒绝原因'],[q.total_records,'最终保留记录','进入画像与复算']].map(([v,t,d],i)=>`<div class="audit-step"><small>STEP ${String(i+1).padStart(2,'0')}</small><strong>${v}</strong><span>${t}<br>${d}</span></div>`).join('')}</div><div class="notice">核对关系：输入 ${q.input_records} = 保留 ${q.total_records} + 修订 / 重复淘汰 ${q.duplicates_removed} + 不纳入 ${q.rejected_records}。保留中包含 ${q.partial_credit_records} 条部分得分记录，未按“全错”抹掉。</div><div class="audit-status">${['知识底座结构与引用','个人 / 班级画像复算','学习建议约束与复算'].map(t=>`<span>${icon('shield',15)}${t} · 通过</span>`).join('')}</div>${note(`数据生成时间：${esc(D.meta.generated_at)}。成果保存在被 Git 忽略的本机目录；页面没有调用外部模型。`)}</section><div class="grid-half section-gap"><section class="panel">${panelHead('五态记录分布','按数据层整理结果统计。')}${donut(Object.entries(q.records_by_state).map(([k,v],i)=>({label:labels[k]||k,value:v,color:['#398575','#d6a16f','#ab98be','#cad6d0','#e6ece7'][i]})),q.total_records,'条保留记录')}${note('“无观测”的学生—材料组合不一定有实体记录，因此不能只看此处计数判断知识覆盖。')}</section><section class="panel">${panelHead('清洗与诊断的判断边界','缺失、待评分、未作答和部分得分分别处理。')}<ul class="rule-list">${q.handling_rules.map(r=>`<li>${esc(r)}</li>`).join('')}</ul><div class="notice warm">评分点失分是学习线索，不自动等于具体误概念。教师可以从知识点抽屉继续回查原始作答。</div></section></div><section class="panel">${panelHead('源文件与数据指纹','保留材料出处，支持本机核对版本。')}<div class="table-scroll"><table class="data-table"><thead><tr><th>输入文件</th><th>逻辑记录数</th><th>SHA-256 指纹</th></tr></thead><tbody>${q.input_files.map(f=>`<tr><td>${esc(f.path)}</td><td>${f.rows??'—'}</td><td class="mono" title="${esc(f.sha256)}">${esc(f.sha256.slice(0,16))}…</td></tr>`).join('')}</tbody></table></div></section><section class="panel section-gap">${panelHead('质量检查发现','规则和处理动作来自任务 2 输出。')}<div class="table-scroll"><table class="data-table"><thead><tr><th>字段 / 记录</th><th>问题</th><th>数量 / 处理</th></tr></thead><tbody>${q.field_quality.map(f=>`<tr><td>${esc(f.field)}</td><td>${esc(f.issue)}</td><td>${f.count}</td></tr>`).join('')}${q.anomalies.slice(0,25).map(a=>`<tr><td>${esc(a.record_id||'—')}</td><td>${esc(a.reason)}</td><td>${esc(a.action)}</td></tr>`).join('')}</tbody></table></div>${!q.anomalies.length&&!q.field_quality.length?empty('当前没有记录到质量异常。'):''}${q.anomalies.length>25?note(`异常共有 ${q.anomalies.length} 项，页面展示前 25 项；全部保留在本机质量报告中。`):''}</section>`;
}

const REVIEW_STATUS_LABEL = {
  flagged: '待复核',
  confirmed_issue: '已确认评分问题',
  dismissed: '已确认无误',
  needs_more_evidence: '需补证据'
};
const REVIEW_FLAG_LABEL = {
  answer_matches_key_under_credit: '作答=参考答案但未满分',
  rubric_total_mismatch: '得分≠评分点合计',
  score_exceeds_max_clamped: '得分超满分已截断',
  answer_key_mismatch_full_credit: '作答≠参考答案却满分'
};

function reviewsPage() {
  const r = D.reviews;
  if (!r) {
    return `${hero('DISPUTED EVIDENCE / 06', '先核对评分，再谈掌握。', '本机存疑评分审查产物未随快照生成。')}<section class="panel">${empty('本次快照没有存疑审查报告；请用 --refresh 重新生成本机展示数据。')}</section>`;
  }
  const list = r.candidates || [];
  const counts = r.counts || {};
  const rows = list.map(c => `<tr>
    <td class="mono">${esc(c.record_id)}</td>
    <td><button class="text-button mono" data-student="${esc(c.student_id)}">${esc(c.student_id)}</button></td>
    <td>${esc((c.knowledge_ids || []).join(' / ') || '—')}</td>
    <td>${esc(c.material_id)}<small class="muted"> · ${esc(c.node_id)}</small></td>
    <td>${c.official.score ?? '—'} / ${c.official.max_score}<small class="muted"> · 合计 ${c.official.rubric_sum ?? '—'}</small></td>
    <td>${c.flags.map(f => `<span class="pill ${f.excluded_by_default ? 'warm' : 'purple'}" title="${esc(f.code)}">${esc(REVIEW_FLAG_LABEL[f.code] || f.code)}</span>`).join(' ')}</td>
    <td><span class="pill ${c.disputed ? 'warm' : ''}">${esc(REVIEW_STATUS_LABEL[c.review_status] || c.review_status)}</span>${c.disputed ? '<small class="muted"><br>不进入结论</small>' : ''}</td>
    <td>${c.decisions.length ? `<small class="muted">${esc(c.decisions.at(-1).review_note)}</small>` : '<small class="muted">尚未人工复核</small>'}</td>
    <td><button class="text-button" data-evidence="${esc(c.record_id)}">查看原始证据 ${icon('arrow',13)}</button></td>
  </tr>`).join('');
  return `${hero('DISPUTED EVIDENCE / 06', '先核对评分，再谈掌握。', '规则只提出复核线索；官方分数原样保留，人工结论作为独立事件追加。')}
  <section class="panel">${panelHead('存疑评分审查', `规则 ${esc(D.review_meta?.rule_version || '—')} · 仅本机 · 不含原始作答`, `<button class="button light" data-export-reviews>${icon('download',14)}导出审核清单</button>`)}
    <div class="mini-metrics" style="grid-template-columns:repeat(4,1fr)">
      <div class="mini-metric">扫描记录<strong>${counts.records_scanned ?? '—'}</strong><small>条保留记录</small></div>
      <div class="mini-metric">复核线索<strong>${counts.candidates ?? 0}</strong><small>条候选</small></div>
      <div class="mini-metric">不进入结论<strong>${counts.disputed_records ?? 0}</strong><small>条待核或已确认</small></div>
      <div class="mini-metric">待人工复核<strong>${counts.flagged ?? 0}</strong><small>条尚无结论</small></div>
    </div>
    <div class="notice warm">被标记的记录已从问题识别与建议依据中排除，<strong>官方分数未被修改</strong>；已确认无误的记录会重新进入统计。原文请点“查看原始证据”，仅在本机读取。</div>
    <div class="table-scroll"><table class="data-table"><thead><tr><th>记录</th><th>学生</th><th>知识点</th><th>题目 / 节点</th><th>官方分</th><th>复核线索</th><th>审查状态</th><th>复核备注</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
    ${list.length ? '' : empty('当前没有发现需要复核的评分记录。')}
    ${note('结论追加命令：knowflow review-decide --record <ID> --status <...> --note "<理由>"。本机演示角色不是认证教师身份。')}
  </section>`;
}

function exportReviews() {
  const r = D.reviews;
  if (!r) return;
  const data = {
    notice: '本机存疑评分审核清单；不含原始作答，请勿提交公开 Git 仓库。',
    dataset_id: D.meta.dataset_id,
    snapshot_id: D.meta.snapshot_id,
    policy: r.policy,
    counts: r.counts,
    candidates: r.candidates
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json;charset=utf-8'
  }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `KnowFlow-review-${D.meta.snapshot_id}-local.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function explorePage() {
  return `${hero('EXPLORE & MAKE / 06','让抽象知识，变成看得见的变化。','用跨域类比帮助理解，再把数学放进可动手的小场景。此页为自编教学拓展，不属于官方测评。')}${filters(true)}<div class="lab-tabs"><button data-lab="axis" class="${state.lab==='axis'?'active':''}"><strong>01 / 数轴 × 镜像变换</strong><small>理解负数乘法为什么改变不等号方向</small></button><button data-lab="budget" class="${state.lab==='budget'?'active':''}"><strong>02 / 代数 × 活动预算</strong><small>找出两种方案的交点与适用范围</small></button></div><section class="panel">${state.lab==='axis'?axisLab():budgetLab()}</section>`;
}

function axisLab() {
  return `${panelHead('当数轴发生镜像，大小关系会怎样？','关联 K-07 · 从几何变换的角度理解代数运算。','<span class="pill purple">自编互动 · 非官方评分</span>')}<div class="grid-half"><div><div class="lab-stage"><div class="lab-label"><span>原关系：3 ＜ 5</span><strong id="factor-label">同乘 −2</strong></div><svg id="number-line" class="number-line" viewBox="0 0 500 100" role="img" aria-label="数轴上变换后的两个数"></svg><div class="lab-equation" id="axis-equation">−6 ＞ −10</div><label class="lab-label" for="factor"><span>拖动乘数 a</span><span>−3 至 3</span></label><input class="lab-range" type="range" id="factor" min="-3" max="3" step="0.5" value="-2"></div><div class="lab-output" id="axis-rule"></div></div><div><div class="eyebrow">TRANSFER THE IDEA</div><h2>放大、镜像与压缩到一点</h2><p class="panel-sub">正数相乘像沿数轴缩放，左右顺序保留。负数相乘除了缩放，还相当于关于原点镜像，因此左右顺序反转。乘以 0 会让两个数都落在原点，不能继续保留原来的严格大小关系。</p><div class="notice">类比的边界：这个演示解释的是数的顺序变化，不替代解不等式时的完整等价变形论证。</div><h3>小检验：−2x ＜ 6 的解是？</h3><div class="lab-quiz"><button class="button" data-quiz="wrong">x ＜ −3</button><button class="button" data-quiz="correct">x ＞ −3</button></div><div id="quiz-feedback" aria-live="polite" class="panel-sub">选择后查看解释。此练习不改变历史画像。</div><button class="text-button section-gap" data-knowledge="K-07">回到知识点与正式学习建议 ${icon('arrow',14)}</button></div></div>`;
}

function budgetLab() {
  return `${panelHead('策划一次社团活动，选哪个方案？','关联代数式、方程与不等式 · 一个自编的小型建模项目。','<span class="pill purple">自编拓展 · 非官方推荐</span>')}<div class="grid-half"><div><div class="lab-stage"><div class="lab-label"><span>方案 A：9 + 2n 元</span><span>方案 B：3 + 4n 元</span></div><div class="budget-bars"><div class="budget-row"><span>方案 A</span><div class="budget-track"><i id="budget-a-bar"></i></div><strong id="budget-a"></strong></div><div class="budget-row"><span>方案 B</span><div class="budget-track"><i id="budget-b-bar"></i></div><strong id="budget-b"></strong></div></div><label class="lab-label" for="people"><span>参与人数 n</span><strong id="people-label">3 人</strong></label><input id="people" class="lab-range" type="range" min="1" max="12" value="3" step="1"></div><div class="lab-output" id="budget-result" aria-live="polite"></div></div><div><div class="eyebrow">BUILD SOMETHING SMALL</div><h2>从公式到一个“方案选择器”</h2><ol class="rule-list"><li>解释两条公式中的固定费用与每人费用。</li><li>解方程 9 + 2n = 3 + 4n，找到费用相同的人数。</li><li>用不等式判断何时 A 更划算，并考虑人数必须为正整数。</li><li>试着用电子表格或几行代码，做一个可输入人数的选择器。</li></ol><div class="notice">项目验收：输入 2、3、4 人，分别给出方案 B、费用相同、方案 A，并解释原因。费用为自编示例。</div><button class="text-button" data-knowledge="K-09">回看范围约束知识点 ${icon('arrow',14)}</button></div></div>`;
}

function showDrawer(title, body, eyebrow = 'EVIDENCE & CONNECTIONS') {
  const dialog = $('#drawer');
  if (!dialog.open) drawerOrigin = document.activeElement;
  $('#drawer-content').innerHTML = `<header class="drawer-head"><div><div class="eyebrow">${eyebrow}</div><h2 id="drawer-title">${title}</h2></div><button class="icon-button" data-close aria-label="关闭详情">${icon('close')}</button></header><div class="drawer-body">${body}</div>`;
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
}

function closeDrawer() {
  ++requestVersion;
  $('#drawer').close();
  activeTask = null;
  if (drawerOrigin?.isConnected) drawerOrigin.focus();
}

function relationLabel(id) {
  return kb.knowledge.find(k => k.knowledge_id === id)?.name || objectiveFor(id)?.theme || materialFor(id)?.title || id;
}

function knowledgeRelations(id) {
  const relationNames = {
    contains: '包含',
    prerequisite: '先修 → 后续',
    confusable: '易混',
    related: '相关'
  };
  const edges = kb.edges.filter(e => e.from_id === id || e.to_id === id);
  return edges.map(e => `<div class="evidence-item"><div>${esc(relationLabel(e.from_id))} → ${esc(relationLabel(e.to_id))}<small>${esc(relationNames[e.edge_type]||e.edge_type)} · ${esc(e.note||'知识底座关系')}</small></div></div>`).join('') || empty('此知识点尚未登记显式关系。');
}

function openKnowledge(id, owner = null) {
  const k = kb.knowledge.find(x => x.knowledge_id === id);
  if (!k) return;
  const personal = owner || ((state.role === 'student' || state.view === 'students') ? state.student : null);
  const p = personal ? D.profiles[state.node][personal] : null,
    s = p?.knowledge_states.find(x => x.knowledge_id === id),
    o = objectiveFor(k.objective_id);
  const materials = [...new Set(kb.qmatrix.filter(q => q.knowledge_id === id && q.weight > 0).map(q => q.material_id))];
  let details = '';
  if (s) {
    const issue = p.issues.find(i => i.knowledge_id === id);
    const relevantPlan = D.recommendations[state.node][personal].plan.filter(i => i.knowledge_ids.includes(id));
    details = `<h3>${esc(personal)} 的学习证据 ${badge(s.status)}</h3><p>${esc(s.status_reason)}</p><div class="mini-metrics section-gap"><div class="mini-metric">有效评分<strong>${s.evidence_count}</strong><small>条观测</small></div><div class="mini-metric">满分 / 部分分<strong>${s.performance.full_credit} / ${s.performance.partial_credit}</strong><small>保留部分得分</small></div><div class="mini-metric">已评分得分率<strong>${pct(s.performance.mean_score_ratio)}</strong><small>仅此知识点观测</small></div></div>${issue?`<div class="notice"><strong>${esc(issue.issue_id)}</strong><br>${esc(issue.statement)}</div>`:''}${s.evidence.length?s.evidence.map(rid=>{const r=D.records.find(r=>r.record_id===rid);return `<div class="evidence-item"><div><strong>${esc(rid)} · ${esc(r?.material_id||'')}</strong><small>评分 ${r?.score??'待评分'} / ${r?.max_score??'—'}</small></div><button class="text-button" data-evidence="${esc(rid)}">查看原始证据 ${icon('arrow',13)}</button></div>`;}).join(''):empty('当前没有有效评分证据，不能据此认定学生未掌握。')}<h3>对应的学习行动</h3>${relevantPlan.length?relevantPlan.map(plan=>`<div class="notice"><strong>${esc(plan.activity)}</strong><br>${esc(plan.reason)}<br><strong>验证：</strong>${esc(plan.check)}<div class="material-buttons">${plan.material_ids.map(m=>`<button class="material-chip" data-material="${esc(m)}" data-owner="${esc(personal)}" data-plan="${plan.seq}">${esc(m)} ${icon('arrow',12)}</button>`).join('')}</div></div>`).join(''):empty('当前没有针对该知识点的具体计划，不强行补造建议。')}`;
  } else {
    const dist = currentClass().knowledge_distribution.find(x => x.knowledge_id === id);
    details = `<h3>${groupName(state.group)} · 学生差异</h3>${stateBars([dist],nameFor)}${legend()}<div class="section-gap">${profiles().map(p=>{const s=p.knowledge_states.find(x=>x.knowledge_id===id);return `<div class="evidence-item"><div><strong>${esc(p.student_id)}</strong><small>${s.evidence_count} 条有效评分 · ${esc(p.group_id)}</small></div>${badge(s.status)}<button class="text-button" data-person-knowledge="${esc(id)}" data-person="${esc(p.student_id)}">证据 ${icon('arrow',12)}</button></div>`;}).join('')}</div>`;
  }
  showDrawer(esc(k.name), `<div class="evidence-chain"><span>${esc(k.objective_id)}</span>→<span>${esc(k.knowledge_id)}</span>→<span>${materials.length} 份关联材料</span>${personal?`→<span>${esc(personal)}</span>`:''}</div><h3>课程学习要求</h3><p>${esc(o.objective_text)}</p><div class="source-detail">${esc(o.theme)} · ${esc(o.source_locator)}<br>${esc(o.notes||'')}</div><div class="drawer-section">${details}</div><div class="drawer-section"><h3>必要联系与依据</h3>${knowledgeRelations(id)}${!kb.edges.some(e=>e.edge_type==='prerequisite'&&(e.from_id===id||e.to_id===id))?'<p class="source-detail">此知识点暂无已核对的上下游先修连线。</p>':''}<h3>题目与学习材料</h3><div class="material-buttons">${materials.map(m=>`<button class="material-chip" data-material="${esc(m)}" title="${esc(materialFor(m)?.title||m)}">${esc(m)} · ${materialFor(m)?.material_type==='assessment'?'题目':'材料'}</button>`).join('')}</div></div>`);
}
let requestVersion = 0;
async function getJSON(url) {
  const r = await fetch(url, {
    cache: 'no-store'
  });
  if (!r.ok) {
    let message = '资料暂时无法读取。';
    try {
      message = (await r.json()).error || message;
    } catch {}
    const error = Error(message);
    error.status = r.status;
    throw error;
  }
  return r.json();
}
async function openMaterial(id, seq = null, owner = null) {
  const version = ++requestVersion;
  activeTask = null;
  showDrawer(esc(materialFor(id)?.title || id), '<p>正在读取本机材料…</p>', 'LEARNING MATERIAL');
  try {
    const m = await getJSON('/api/material/' + encodeURIComponent(id));
    if (version !== requestVersion || !$('#drawer').open) return;
    const plan = seq && owner ? D.recommendations[state.node][owner]?.plan.find(p => p.seq === Number(seq) && p.material_ids.includes(id)) : null;
    const saved = plan ? submission(owner, plan.seq, id) : null;
    activeTask = plan ? {
      material: m,
      plan,
      owner
    } : null;
    let options = '';
    try {
      const parsed = JSON.parse(m.options_json || 'null');
      if (parsed) options = `<div class="plain-text section-gap">${esc(typeof parsed==='object'?Object.entries(parsed).map(([k,v])=>`${k}．${typeof v==='string'?v:JSON.stringify(v)}`).join('\n'):String(parsed))}</div>`;
    } catch {}
    let rubric = '';
    try {
      const parsed = JSON.parse(m.rubric_json || '[]');
      if (parsed.length) rubric = `<h3>评分关注点</h3><div class="material-buttons">${parsed.map(x=>`<span class="pill">${esc(x.text)} · ${esc(x.points)} 分</span>`).join('')}</div>`;
    } catch {}
    const canSubmit = plan && state.role === 'student';
    const form = canSubmit ? `<form class="answer-form" id="practice-form"><label for="practice-answer">${m.material_type==='assessment'?'写下你的答案与解题过程':'写下阅读收获与需要继续确认的问题'}</label><textarea id="practice-answer" required maxlength="20000" placeholder="保留你的思路，方便教师随后评阅。">${esc(saved?.answer||'')}</textarea><small>仅保存于本机浏览器；提交不代表答对或已经掌握。${saved?'再次提交会更新此项本机记录。':''}</small><button type="submit" class="button primary">${saved?'更新本机提交':'提交本机练习'} ${icon('arrow',14)}</button></form>` : '';
    showDrawer(esc(m.title), `<div class="evidence-chain"><span>${esc(id)}</span><span>${esc(m.objective_id||'参考材料')}</span>${plan?`<span>${esc(owner)}</span><span>计划 ${plan.seq}</span>`:''}</div>${plan?`<div class="notice"><strong>本次目标：</strong>${esc(plan.activity)}<br><strong>验证标准：</strong>${esc(plan.check)}</div>`:''}<div class="plain-text">${esc(m.body||'此材料正文见原始资料文件。')}</div>${options}${m.document_url?`<a class="button light section-gap" href="${esc(m.document_url)}" target="_blank" rel="noopener">打开原始 PDF ${icon('arrow',14)}</a>`:''}<div class="source-detail">出处：${esc(m.source||'未提供')}<br>${esc(m.license||'')} · ${esc(id)}</div>${rubric}<div id="submission-status">${saved?`<div class="feedback">已于 ${esc(new Date(saved.submitted_at).toLocaleString('zh-CN'))} 本机提交 · 待教师评阅<br>历史画像尚未改变。</div>`:''}</div>${state.role==='teacher'&&saved?`<h3>学生本机提交</h3><div class="plain-text">${esc(saved.answer)}</div>`:''}${form}${!plan&&state.role==='student'?'<div class="notice">这是资料浏览。要记录计划完成情况，请从“练习与建议”中的指定材料进入。</div>':''}${m.answer_key||m.explanation?`<details class="drawer-section section-gap"><summary class="text-button">${state.role==='teacher'?'查看参考答案与解析':'完成思考后，展开参考答案与解析'}</summary><div class="plain-text section-gap">${esc(m.answer_key||'')}\n\n${esc(m.explanation||'')}</div></details>`:''}`, 'LEARNING MATERIAL');
  } catch (e) {
    if (version === requestVersion) showDrawer('材料读取失败', `<div class="error-box">${esc(e.message)}</div>`);
  }
}
async function openEvidence(id) {
  const version = ++requestVersion;
  activeTask = null;
  showDrawer(esc(id), '正在核对原始文件版本…', 'LOCAL EVIDENCE');
  try {
    const e = await getJSON('/api/evidence/' + encodeURIComponent(id));
    if (version !== requestVersion || !$('#drawer').open) return;
    const r = D.records.find(r => r.record_id === id);
    showDrawer(`${esc(id)} · 原始作答证据`, `<div class="evidence-chain"><span>${esc(r.student_id)}</span>→<span>${esc(r.material_id)}</span>→<span>${esc(id)}</span></div><div class="notice">${esc(r.node_id)} · 评分 ${r.score??'待评分'} / ${r.max_score}<br>对应源记录：${esc(e.source.source_record_id)} · CSV 逻辑记录序号 ${e.source.csv_record_number}</div><h3>最终答案</h3><div class="plain-text">${esc(e.detail.final_answer||'未填写')}</div><h3>解题过程</h3><div class="plain-text">${esc(e.detail.solution_process||'未提供过程')}</div><h3>原始评分点记录</h3><div class="plain-text">${esc(e.detail.scoring_point_scores||'未提供')}</div><p class="source-detail">来源：${esc(e.source.raw_file)}<br>仅本机核对，不发送外部模型。</p><button class="button light section-gap" data-material="${esc(r.material_id)}">查看对应题目 ${icon('arrow',14)}</button>`, 'LOCAL EVIDENCE');
  } catch (e) {
    if (version === requestVersion) showDrawer('证据读取失败', `<div class="error-box">${esc(e.message)}</div>`);
  }
}

function render() {
  normalize();
  saveURL();
  unmountMap?.();
  $('#app').innerHTML = shell();
  const map = $('#app [data-interactive-map]');
  unmountMap = map ? mountMap(map, kb, openKnowledge) : null;
  document.title = `${viewLabel(state.view)} · KnowFlow`;
  if (state.view === 'settings' && !llmSettings && !settingsError) {
    ensureSettings().then(() => {
      if (state.view === 'settings') render();
    }).catch(error => {
      settingsError = error.status === 404
        ? '当前后端进程还是旧版本，没有设置接口。请关闭所有启动窗口后重新运行 start-dashboard.cmd（不要同时开多个）。'
        : error instanceof TypeError
          ? '无法连接本机后端：请确认启动窗口仍在运行（不要关闭它），然后刷新页面重试。'
          : error.message;
      if (state.view === 'settings') render();
    });
  }
  if (state.view === 'explore') {
    if (state.lab === 'axis') updateAxis();
    else updateBudget();
  }
}

function updateAxis() {
  const a = Number($('#factor').value),
    x = 3 * a,
    y = 5 * a;
  const fmt = v => String(v).replace('-', '−');
  $('#factor-label').textContent = `同乘 ${fmt(a)}`;
  $('#axis-equation').textContent = `${fmt(x)} ${a>0?'＜':a<0?'＞':'＝'} ${fmt(y)}`;
  $('#axis-rule').textContent = a > 0 ? '乘以正数：顺序保留，3a ＜ 5a。' : a < 0 ? '乘以负数：数轴发生镜像，顺序反转，3a ＞ 5a。' : '乘以 0：两个数重合为 0。原来的严格不等关系不能保留；也不能用除以 0 逆推。';
  const position = v => 250 + v * 13;
  $('#number-line').innerHTML = `<line x1="30" x2="470" y1="48" y2="48" stroke="#9bad92" stroke-width="1.5"/>${[-15,-10,-5,0,5,10,15].map(t=>`<path d="M${position(t)} 43v10" stroke="#a1b296"/><text x="${position(t)}" y="75" text-anchor="middle" fill="#8b9f80" font-size="11">${t}</text>`).join('')}<circle cx="${position(x)}" cy="48" r="8" fill="#549477"/><text x="${position(x)}" y="22" text-anchor="middle" fill="#3f7d60" font-size="13">3a = ${x}</text><circle cx="${position(y)}" cy="48" r="${a===0?4:8}" fill="#c59968"/><text x="${position(y)}" y="97" text-anchor="middle" fill="#ad824f" font-size="13">5a = ${y}</text>`;
}

function updateBudget() {
  const n = Number($('#people').value),
    a = 9 + 2 * n,
    b = 3 + 4 * n;
  $('#people-label').textContent = `${n} 人`;
  $('#budget-a').textContent = `${a} 元`;
  $('#budget-b').textContent = `${b} 元`;
  $('#budget-a-bar').style.width = `${a/51*100}%`;
  $('#budget-b-bar').style.width = `${b/51*100}%`;
  $('#budget-result').textContent = a === b ? `两种方案同为 ${a} 元。交点满足 9 + 2n = 3 + 4n，所以 n = 3。` : `${n} 人时，方案 ${a<b?'A':'B'} 便宜 ${Math.abs(a-b)} 元。正整数人数 n > 3 时选 A，n < 3 时选 B。`;
}

function exportSummary() {
  const p = currentProfile(),
    s = D.stats[state.node][state.student];
  const data = {
    notice: '本机学情摘要，含模拟学生成果；请勿提交公开 Git 仓库。',
    dataset_id: D.meta.dataset_id,
    node_id: state.node,
    student_id: state.student,
    statistics: s,
    profile: p,
    recommendation: D.recommendations[state.node][state.student]
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json;charset=utf-8'
  }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `KnowFlow-${state.student}-${state.node}-local.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('已导出本机摘要，请勿将学生成果提交公开仓库。');
}

function chatContextLabel() {
  return `${state.node} · ${groupName(state.group)}${state.student ? ' · ' + state.student : ''}`;
}

function citeChip(id) {
  if (id.startsWith('M-')) return `<button type="button" class="chat-cite" data-material="${esc(id)}">${esc(id)}</button>`;
  if (id.startsWith('K-')) return `<button type="button" class="chat-cite" data-knowledge="${esc(id)}">${esc(id)}</button>`;
  if (id.startsWith('S')) return `<button type="button" class="chat-cite" data-student="${esc(id)}">${esc(id)}</button>`;
  return `<span class="chat-cite">${esc(id)}</span>`;
}

function chatLog() {
  if (!chatMessages.length) {
    return `<div class="chat-welcome"><strong>可以这样问</strong><p>回答只基于当前这份学情成果；没有依据时会直说。</p><div class="chat-prompts"><button type="button" data-chat-prompt="${esc(`${state.student} 现在最需要补什么？`)}">${esc(`${state.student} 现在最需要补什么？`)}</button><button type="button" data-chat-prompt="这个班最薄弱的三个知识点？">这个班最薄弱的三个知识点？</button><button type="button" data-chat-prompt="K-07 的课程要求是什么？">K-07 的课程要求是什么？</button></div></div>`;
  }
  return chatMessages.map(message => `<div class="chat-msg ${message.role} ${message.error ? 'error' : ''}"><div class="chat-bubble">${esc(message.text)}</div>${message.citations?.length?`<div class="chat-cites">${message.citations.map(citeChip).join('')}</div>`:''}${message.source?`<small class="chat-source">${message.source === 'llm' ? 'LLM 生成 · 已核对' : '本地规则回答'}</small>`:''}${message.note?`<small class="chat-note">${esc(message.note)}</small>`:''}</div>`).join('');
}

function chatPanel() {
  return `<section class="chat-panel" role="dialog" aria-label="与 AI 对话"><header class="chat-head"><div><strong>AI 学伴</strong><small>${esc(chatContextLabel())}</small></div><button type="button" class="icon-button" data-chat-close aria-label="关闭对话">${icon('close')}</button></header><div class="chat-log" id="chat-log" aria-live="polite">${chatLog()}</div>${chatBusy?'<div class="chat-typing">正在查阅本机证据…</div>':''}<form class="chat-form" id="chat-form"><textarea id="chat-input" rows="2" maxlength="500" placeholder="问当前班级、学生或知识点…" ${chatBusy?'disabled':''}></textarea><button class="button primary" type="submit" ${chatBusy?'disabled':''}>发送</button></form><div class="chat-foot">只发送聚合摘要 · 回答中的 ID 可点击查看依据</div></section>`;
}

function chatWidget() {
  return `<div id="chat-host">${chatOpen ? chatPanel() : ''}</div><button type="button" class="chat-fab ${chatOpen?'open':''}" id="chat-fab" aria-label="与 AI 对话" aria-expanded="${chatOpen}" title="与 AI 对话">${icon('chat',22)}<span>AI 学伴</span></button>`;
}

function scrollChat() {
  const log = document.querySelector('#chat-log');
  if (log) log.scrollTop = log.scrollHeight;
}

function renderChat() {
  const host = document.querySelector('#chat-host');
  if (host) host.innerHTML = chatOpen ? chatPanel() : '';
  const fab = document.querySelector('#chat-fab');
  if (fab) {
    fab.classList.toggle('open', chatOpen);
    fab.setAttribute('aria-expanded', String(chatOpen));
  }
  scrollChat();
}

async function sendChat(raw) {
  const text = (raw || '').trim();
  if (!text || chatBusy) return;
  chatMessages.push({
    role: 'user',
    text
  });
  chatBusy = true;
  renderChat();
  try {
    const data = await postJSON('/api/chat', {
      message: text,
      context: {
        node_id: state.node,
        group_id: state.group,
        student_id: state.student
      }
    }, 'X-KnowFlow-Chat');
    chatMessages.push({
      role: 'assistant',
      text: data.answer,
      citations: data.citations || [],
      source: data.source,
      note: data.note
    });
  } catch (error) {
    chatMessages.push({
      role: 'assistant',
      text: error.message,
      error: true
    });
  } finally {
    chatBusy = false;
    renderChat();
  }
}

async function postJSON(url, body, header = 'X-KnowFlow-Settings') {
  const send = () => fetch(url, {
    method: 'POST',
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      [header]: '1'
    },
    body: JSON.stringify(body)
  });
  let response;
  try {
    response = await send();
  } catch {
    // A restarted dashboard can reset one keep-alive socket; retry once, then
    // tell the user the backend is gone instead of leaking "Failed to fetch".
    await new Promise(resolve => setTimeout(resolve, 400));
    try {
      response = await send();
    } catch {
      throw Error('无法连接本机后端：请确认启动窗口仍在运行（不要关闭它），然后刷新页面重试。');
    }
  }
  let data = {};
  try {
    data = await response.json();
  } catch {}
  if (!response.ok) {
    const error = Error(data.error || `保存失败（${response.status}）`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function ensureSettings() {
  if (llmSettings) return llmSettings;
  llmSettings = await getJSON('/api/settings/llm');
  return llmSettings;
}

function settingsPage() {
  if (settingsError) {
    return `${hero('SETTINGS / 06','设置暂时读不到。','后端没有返回本机配置，请确认启动窗口仍在运行。')}<section class="panel"><div class="error-box">${esc(settingsError)}</div><button class="button light section-gap" data-view="settings">重试 ${icon('arrow',14)}</button></section>`;
  }
  if (!llmSettings) {
    return `${hero('SETTINGS / 06','正在读取本机配置…','设置只写这台电脑上的 .env，不会离开本机。')}<section class="panel"><div class="empty">读取中…</div></section>`;
  }
  const s = llmSettings;
  const provider = s.providers.find(p => p.value === s.provider) || s.providers[0];
  return `${hero('SETTINGS / 06','把模型接进来，但数字仍由代码算。','这里改的是本机后端配置；保存后对之后生成的建议生效，页面上已有成果不会自动重算。')}
  <div class="settings-grid">
    <section class="panel">
      ${panelHead('LLM 文字层','只改写 reason/check；输出要过数字锁与 ID 锁，失败逐条回退模板。','<span class="pill">本机设置</span>')}
      <form id="settings-form" class="settings-form" autocomplete="off">
        <label class="switch">
          <input type="checkbox" id="llm-enabled" ${s.enabled ? 'checked' : ''}>
          <span class="switch-track" aria-hidden="true"></span>
          <span class="switch-copy"><strong>启用 LLM 模式</strong><small>关闭时只用规则模板，不产生任何外部请求。</small></span>
        </label>
        <div id="llm-config" class="llm-config" ${s.enabled ? '' : 'hidden'}>
          <div class="field">
            <label for="llm-provider">模型厂商</label>
            <select id="llm-provider">${s.providers.map(p => `<option value="${esc(p.value)}" ${p.value === s.provider ? 'selected' : ''}>${esc(p.label)}</option>`).join('')}</select>
          </div>
          <div class="field">
            <label for="llm-api-key">API Key</label>
            <input id="llm-api-key" type="password" value="" maxlength="200" autocomplete="new-password" placeholder="${s.api_key_set ? '已保存；留空表示不修改' : '粘贴 API Key'}">
            <small>只写入本机 .env（Git 忽略），不会回显，也不会进入页面快照。</small>
          </div>
          <div class="settings-row">
            <div class="field"><label for="llm-model">模型</label><input id="llm-model" value="${esc(s.model)}" maxlength="100"></div>
            <div class="field"><label for="llm-base-url">Base URL</label><input id="llm-base-url" value="${esc(s.base_url)}" maxlength="200"></div>
          </div>
        </div>
        <div class="settings-actions">
          <button class="button primary" type="submit">保存设置</button>
          <span id="settings-result" class="settings-result" role="status"></span>
        </div>
      </form>
    </section>
    <section class="panel">
      ${panelHead('当前状态','后端已解析的值；保存成功后立即刷新。')}
      <div class="settings-status">
        <div><span>开关</span><strong>${s.enabled ? '已启用' : '未启用'}</strong></div>
        <div><span>可调用</span><strong>${s.ready ? '是' : '否（缺 Key 或未启用）'}</strong></div>
        <div><span>厂商</span><strong>${esc(provider.label)}</strong></div>
        <div><span>模型</span><strong>${esc(s.model)}</strong></div>
        <div><span>API Key</span><strong>${s.api_key_set ? '已保存' : '未保存'}</strong></div>
        <div><span>写入文件</span><code>${esc(s.env_file)}</code></div>
      </div>
      <div class="notice"><strong>生效方式：</strong>保存只改后端配置，已有成果不自动重算。要让页面里的建议文字也更新：<br><code>python -m knowflow.web --refresh --llm</code></div>
      <div class="notice"><strong>边界：</strong>模型只接收聚合摘要（计数、比率、状态），不接收原始作答；输出必须引用 issue_id 与真实材料 ID。</div>
    </section>
  </div>`;
}

document.addEventListener('click', event => {
  const b = event.target.closest('button');
  if (!b) return;
  if (b.id === 'chat-fab') {
    chatOpen = !chatOpen;
    renderChat();
    if (chatOpen) document.querySelector('#chat-input')?.focus();
    return;
  }
  if (b.hasAttribute('data-chat-close')) {
    chatOpen = false;
    renderChat();
    return;
  }
  if (b.dataset.chatPrompt) {
    sendChat(b.dataset.chatPrompt);
    return;
  }
  if (b.hasAttribute('data-close')) {
    closeDrawer();
    return;
  }
  if (b.dataset.view) {
    state.view = b.dataset.view;
    if (state.view === 'settings') {
      llmSettings = null;
      settingsError = null;
    }
    render();
    window.scrollTo(0, 0);
    return;
  }
  if (b.dataset.student) {
    state.student = b.dataset.student;
    state.view = 'students';
    render();
    $('#student-detail').scrollIntoView({
      behavior: 'smooth',
      block: 'start'
    });
    return;
  }
  if (b.dataset.personKnowledge) {
    openKnowledge(b.dataset.personKnowledge, b.dataset.person);
    return;
  }
  if (b.dataset.knowledge) {
    openKnowledge(b.dataset.knowledge);
    return;
  }
  if (b.dataset.material) {
    openMaterial(b.dataset.material, b.dataset.plan, b.dataset.owner);
    return;
  }
  if (b.dataset.evidence) {
    openEvidence(b.dataset.evidence);
    return;
  }
  if (b.dataset.courseView) {
    state.courseView = b.dataset.courseView;
    render();
    return;
  }
  if (b.dataset.lab) {
    state.lab = b.dataset.lab;
    render();
    return;
  }
  if (b.dataset.quiz) {
    $('#quiz-feedback').textContent = b.dataset.quiz === 'correct' ? '正确。两边除以 −2，不等号反向，得到 x ＞ −3。这次自编检验不会改动历史画像。' : '再想一想：两边除以负数时，数轴左右顺序会反转。试着把乘数拖到负数区域再观察。';
    return;
  }
  if (b.hasAttribute('data-toggle-heatmap')) {
    const top = window.scrollY;
    state.allHeatmap = !state.allHeatmap;
    render();
    window.scrollTo(0, top);
    return;
  }
  if (b.hasAttribute('data-export-reviews')) {
    exportReviews();
    return;
  }
  if (b.hasAttribute('data-export')) exportSummary();
});
document.addEventListener('change', event => {
  if (event.target.id === 'llm-enabled') {
    const config = document.querySelector('#llm-config');
    if (config) config.hidden = !event.target.checked;
  }
  if (event.target.id === 'llm-provider') {
    const preset = llmSettings?.providers.find(p => p.value === event.target.value);
    if (preset && preset.value !== 'custom') {
      const model = document.querySelector('#llm-model');
      const baseUrl = document.querySelector('#llm-base-url');
      if (model) model.value = preset.model;
      if (baseUrl) baseUrl.value = preset.base_url;
    }
  }
  if (event.target.id === 'node-select') {
    state.node = event.target.value;
    render();
  }
  if (event.target.id === 'group-select') {
    state.group = event.target.value;
    if (state.group !== 'ALL' && !profiles().some(p => p.student_id === state.student)) state.student = profiles()[0].student_id;
    render();
  }
  if (event.target.id === 'student-filter') {
    state.studentFilter = event.target.value;
    render();
  }
});
document.addEventListener('input', event => {
  if (event.target.id === 'student-search') {
    const position = event.target.selectionStart;
    state.search = event.target.value;
    render();
    const el = $('#student-search');
    el.focus();
    el.setSelectionRange(position, position);
  }
  if (event.target.id === 'factor') updateAxis();
  if (event.target.id === 'people') updateBudget();
});
document.addEventListener('submit', async event => {
  if (event.target.id === 'chat-form') {
    event.preventDefault();
    const input = document.querySelector('#chat-input');
    const text = input ? input.value : '';
    if (input) input.value = '';
    await sendChat(text);
    return;
  }
  if (event.target.id === 'settings-form') {
    event.preventDefault();
    const result = document.querySelector('#settings-result');
    if (result) result.textContent = '正在保存…';
    try {
      llmSettings = await postJSON('/api/settings/llm', {
        enabled: document.querySelector('#llm-enabled').checked,
        provider: document.querySelector('#llm-provider').value,
        model: document.querySelector('#llm-model').value.trim(),
        base_url: document.querySelector('#llm-base-url').value.trim(),
        api_key: document.querySelector('#llm-api-key').value
      });
      settingsError = null;
      render();
      toast('LLM 设置已保存到本机 .env');
    } catch (error) {
      if (result) result.textContent = error.message;
    }
    return;
  }
  if (event.target.id === 'student-form') {
    event.preventDefault();
    const id = $('#student-id').value.trim().toUpperCase();
    if (!D.students.some(s => s.student_id === id)) {
      toast('没有找到该学生 ID，请从下拉提示中选择。');
      $('#student-id').focus();
      return;
    }
    state.student = id;
    render();
  }
  if (event.target.id === 'practice-form') {
    event.preventDefault();
    if (!activeTask) return;
    const answer = $('#practice-answer').value.trim();
    if (!answer) {
      toast('请先写下答案或阅读收获。');
      return;
    }
    const {
      owner,
      plan,
      material
    } = activeTask;
    const store = readWork();
    store[workKey(owner, plan.seq, material.material_id)] = {
      answer,
      submitted_at: new Date().toISOString()
    };
    try {
      localStorage.setItem('knowflow.practice.v1', JSON.stringify(store));
      storageOK = true;
      render();
      $('#submission-status').innerHTML = '<div class="feedback">本机提交已保存 · 待教师评阅。历史画像尚未改变。</div>';
      toast('练习已保存在本机，教师页可以查看。');
    } catch {
      storageOK = false;
      $('#submission-status').innerHTML = '<div class="error-box">浏览器未能保存，请保留当前输入内容并检查本地存储设置。</div>';
    }
  }
});
$('#drawer').addEventListener('click', event => {
  if (event.target === $('#drawer')) closeDrawer();
});
$('#drawer').addEventListener('cancel', () => {
  ++requestVersion;
  activeTask = null;
});
document.addEventListener('keydown', event => {
  if (document.querySelector('#drawer')?.open) return;
  if (event.key === 'Escape' && chatOpen) {
    chatOpen = false;
    renderChat();
    return;
  }
  if (event.key === 'Enter' && !event.shiftKey && event.target.id === 'chat-input') {
    event.preventDefault();
    const value = event.target.value;
    event.target.value = '';
    sendChat(value);
  }
});
window.addEventListener('storage', event => {
  if (event.key === 'knowflow.practice.v1' && D) {
    render();
    toast('本机练习记录已更新。');
  }
});
async function init() {
  try {
    D = await getJSON('/api/snapshot');
    kb = D.knowledge_base;
    readWork();
    render();
  } catch (e) {
    $('#app').innerHTML = `<div class="loading"><span class="brand-symbol">K</span><h1>暂时无法连接本机成果</h1><p>${esc(e.message)}</p><p>请检查启动窗口是否仍在运行，然后刷新页面。</p></div>`;
  }
}
init();
