import {describe, distribution, aggregateRecords, topics} from './analytics.mjs';
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
  masteryBars,
  histogram,
  comparisonBars
} from './charts.js';

let D, kb, storageOK = true,
  activeTask = null,
  drawerOrigin = null,
  llmSettings = null,
  settingsError = null,
  chatOpen = new URLSearchParams(location.search).get('chat') === '1',
  chatBusy = false,
  chatMessages = [];
let chatGeometry = null;
let SESSION = null;
// The signed-in account decides what may be changed; ``state.role`` is only the
// view being rendered (a teacher may preview the student view of one learner).
const isStudentAccount = () => SESSION?.role === 'student';
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
  profileTab: 'analysis',
  chatMode: 'concise',
  studentSort: 'id',
  allHeatmap: false
};
const $ = s => document.querySelector(s);
const viewLabel = id => navItems().find(x => x[0] === id)?.[1] || (id === 'reviews' ? '存疑证据' : id === 'settings' ? '设置' : '工作台');
const nameFor = id => kb.knowledge.find(k => k.knowledge_id === id)?.name || id;
const objectiveFor = id => kb.objectives.find(o => o.objective_id === id);
const materialFor = id => kb.materials.find(m => m.material_id === id);
const node = () => D.nodes.find(n => n.node_id === state.node);
const currentProfile = () => D.profiles[state.node]?.[state.student];
const currentClass = () => D.classes[state.node]?.[state.group];
const profiles = () => Object.values(D.profiles[state.node]).filter(p => state.group === 'ALL' || p.group_id === state.group);
const groups = () => [...new Set(D.students.map(s => s.group_id))].sort();
const groupName = id => id === 'ALL' ? '全部班级' : `班级 ${id}`;
const note = text => `<details class="method-details"><summary>统计说明</summary><p>${text}</p></details>`;
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
  if (isStudentAccount() && SESSION?.student_id) {
    state.role = 'student';
    state.student = SESSION.student_id;
    state.group = 'ALL';
  }
  if (!D.nodes.some(n => n.node_id === state.node)) state.node = D.nodes.at(-1).node_id;
  if (!D.students.some(s => s.student_id === state.student)) state.student = D.students[0].student_id;
  if (!['ALL', ...groups()].includes(state.group)) state.group = 'ALL';
  const allowedViews = [...navItems().map(x => x[0]), ...(isStudentAccount() ? [] : ['settings'])];
  if (state.role === 'teacher') allowedViews.push('reviews');
  if (!allowedViews.includes(state.view)) state.view = 'overview';
}

function navItems() {
  return state.role === 'teacher' ? [
    ['overview', '班级学情', 'overview'],
    ['course', '课程知识地图', 'map'],
    ['students', '学生明细', 'students'],
    ['quality', '数据与证据', 'shield']
  ] : [
    ['overview', '学习总览', 'overview'],
    ['course', '我的知识地图', 'map'],
    ['plan', '练习与建议', 'book'],
    ['explore', '跨域探索', 'spark']
  ];
}

function shell() {
  const active = navItems().find(n => n[0] === state.view) || (state.view === 'reviews' ? ['reviews', '存疑证据', 'shield'] : ['settings', '设置', 'settings']);
  return `<div class="app-shell"><aside class="sidebar"><a class="brand" href="${routeURL(state.role)}"><img src="/favicon.svg" alt=""><div><strong>KnowFlow</strong><small>智慧学伴</small></div></a><div class="sidebar-label">${state.role==='teacher'?'教师工作台':'我的学习'}</div><nav class="nav" aria-label="主要导航">${navItems().map(([id,label,ico])=>`<button data-view="${id}" class="${state.view===id?'active':''}" aria-label="${label}" ${state.view===id?'aria-current="page"':''} title="${label}">${icon(ico)}<span>${label}</span></button>`).join('')}</nav><div class="sidebar-tools">${isStudentAccount()?'':`<button class="settings-link ${state.view==='settings'?'active':''}" data-view="settings" aria-label="设置" title="设置" ${state.view==='settings'?'aria-current="page"':''}>${icon('settings',16)}<span>设置</span></button>`}</div><div class="side-story"><div class="eyebrow">当前课程</div><h3>七年级 · 数学</h3><p>${kb.objectives.length} 个主题 · ${kb.knowledge.length} 项观察指标</p><div class="steps"><span></span><span></span><span></span></div></div><div class="sidebar-footer"><strong><i class="live-dot"></i> 本机数据已就绪</strong><p>赛事模拟数据 · 校验通过</p></div></aside><div class="workspace"><header class="topbar"><div class="breadcrumb"><span>工作空间</span><span>/</span><b>${active[1]}</b></div><div class="top-actions"><span class="viewer-chip" title="${isStudentAccount()?'学生账号':'教师账号'}">${icon(SESSION?.role==='teacher'?'shield':'students',14)}<strong>${esc(SESSION?.display_name||'')}</strong><small>${SESSION?.role==='teacher'?'教师':'学生'}</small></span><button class="text-button logout-button" data-logout>${icon('close',13)}退出登录</button><div class="avatar" title="${esc(SESSION?.display_name||'')}">${state.role==='teacher'?'KF':'S'}</div></div></header><main id="main" tabindex="-1" class="fade-in">${content()}<footer class="page-footer"><strong>KnowFlow · 智慧学伴</strong><span>赛事模拟数据 · ${esc(D.meta.dataset_id)} · ${esc(D.meta.recommendation_mode)}</span></footer></main></div>${chatWidget()}`;
}

function hero(eyebrow, title, desc) {
  return `<section class="hero"><div class="hero-copy"><div class="eyebrow">${state.role==='teacher'?'教师工作台':'学生工作台'}</div><h1>${title}</h1>${desc?`<p>${desc}</p>`:''}</div><div class="node-card"><div class="eyebrow">当前测验</div><strong>${esc(state.node)}<span> · ${esc(node().date)}</span></strong><p>${node().taught_objective_ids.length} 个已教主题</p></div></section>`;
}

function filters(student = false) {
  return `<div class="toolbar"><div class="filters"><label class="filter">测验<select id="node-select">${D.nodes.map(n=>`<option value="${esc(n.node_id)}" ${n.node_id===state.node?'selected':''}>${esc(n.node_id)} · ${esc(n.date)}</option>`).join('')}</select></label>${state.role==='teacher'?`<label class="filter">班级范围<select id="group-select">${['ALL',...groups()].map(g=>`<option value="${esc(g)}" ${g===state.group?'selected':''}>${groupName(g)}</option>`).join('')}</select></label>`:''}${student && !isStudentAccount()?`<form id="student-form" class="search-field">${icon('search',16)}<input id="student-id" aria-label="输入学生 ID" list="student-ids" placeholder="输入学生 ID" value="${esc(state.student)}" autocomplete="off"><button class="text-button" type="submit">查看</button><datalist id="student-ids">${D.students.map(s=>`<option value="${esc(s.student_id)}">${esc(s.group_id)}</option>`).join('')}</datalist></form>`:''}</div></div>`;
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

function trendSeries() {
  return groups().filter(g=>state.group==='ALL'||g===state.group).map((g,i)=>({
    label:groupName(g),color:['#438a74','#d4a16f'][i%2],
    points:D.nodes.map(n=>({label:n.node_id,date:n.date,value:D.students.filter(s=>s.group_id===g).reduce((sum,s)=>sum+D.stats[n.node_id][s.student_id].graded,0)})),
  }));
}

function trend() {
  return `<div class="trend-block">${lineChart(trendSeries())}</div>`;
}

function fitTrend() {
  const chart=$('.trend-block');
  if(chart)chart.innerHTML=lineChart(trendSeries(),Math.max(220,Math.round(chart.clientWidth)));
}
let chartResizeTimer;
window.addEventListener('resize',()=>{
  clearTimeout(chartResizeTimer);
  chartResizeTimer=setTimeout(fitTrend,80);
});

function commonIssues() {
  const rows = currentClass().rubric_patterns.slice(0, 4);
  return rows.length ? `<div class="issue-list">${rows.map((r,i)=>`<div class="issue-row"><div class="issue-number">0${i+1}</div><div class="issue-body"><h3><button class="text-button" data-knowledge="${esc(r.knowledge_id)}">${esc(r.knowledge_id)} · ${esc(r.criterion)}</button></h3><p>${esc(nameFor(r.knowledge_id))}</p><div class="issue-meter"><i style="width:${r.prevalence*100}%"></i></div></div><div class="issue-rate">${pct(r.prevalence)}<small>${r.affected_student_count} / ${r.observed_student_count} 人</small></div></div>`).join('')}</div>` : empty('当前范围没有可汇总的评分点失分证据。');
}

function overview() {
  const c=currentClass(), s=cohortStats(), list=profiles();
  const scores=list.map(p=>D.stats[state.node][p.student_id].score_ratio);
  const scoreStats=describe(scores), scoreBins=distribution(scores);
  const coverageBins=distribution(list.map(p=>p.coverage.scope_known?p.coverage.ratio:null));
  return `${hero('', '班级学情', `${groupName(state.group)} · 七年级数学`)}${filters()}
  <section class="stats-grid">
    ${stat('班级人数',s.students,'人',`${scoreStats.count} 人有评分 · ${s.students-scoreStats.count} 人暂无评分`,'students')}
    ${stat('平均得分率',pct(scoreStats.mean),'',`按 ${scoreStats.count} 名有评分学生计算`,'trend')}
    ${stat('平均评分覆盖',pct(c.coverage_summary.mean_ratio),'',`${s.known} 人的测验范围已确认`,'target','#9a9a6c','#f2f3e9')}
    ${stat('建议巩固',s.needs,'人',`至少一个知识点需要巩固`,'book','#c89160','#fbf1e8')}
  </section>
  <div class="grid-main overview-primary">
    <section class="panel">${panelHead('学生得分率分布','每人按已评分题目计算','<span class="pill">直方图 · 人数</span>')}
      ${histogram(scoreBins)}
      <div class="distribution-summary"><span>最低<strong>${pct(scoreStats.min)}</strong></span><span>中位数<strong>${pct(scoreStats.median)}</strong></span><span>最高<strong>${pct(scoreStats.max)}</strong></span><span>暂无评分<strong>${scoreBins.missing} 人</strong></span></div>
      ${note('得分率 = 已得分 / 已评分题目满分。平均值按学生等权计算。区间左闭右开，最后一组含 100%；没有评分的学生不计为零分。不同学生的作答题目可能不同，分布不等于统一试卷成绩排名。')}
    </section>
    <section class="panel">${panelHead('作答情况','已布置记录，不含没有记录的题目')}${donut(historicalItems(),s.assigned,'条已布置记录')}
      <div class="inline-stat"><span>作答完成率</span><strong>${pct(s.assigned?s.attempted/s.assigned:null)}</strong><small>${s.attempted} / ${s.assigned}</small></div>
      ${note('完成率 = 有作答记录 / 已布置记录。待评分表示已经作答，不等于零分。')}
    </section>
  </div>
  <div class="grid-main">
    <section class="panel">${panelHead('知识点状态','点击知识点查看学生差异','<span class="pill">人数</span>')}${stateBars(c.knowledge_distribution,nameFor)}${legend()}
      ${note('每行分母是所选班级全体学生。“掌握倾向”和“偏弱倾向”汇总较可能与已确认状态，个人详情保留原判断。待观察表示证据不足，不适用表示此节点没有对应可测内容。')}
    </section>
    <section class="panel">${panelHead('主题表现','按主题汇总已评分题目')}${topicComparison()}
      ${note('主题得分率 = 本主题已得分总和 / 已评分题目满分总和。同一道题不会因关联多个知识点而重复计分。暂无评分显示“—”。')}
    </section>
  </div>
  <div class="grid-half">
    <section class="panel">${panelHead('各次测验的评分记录','不同班级的已评分记录数量','<span class="pill">折线图 · 条数</span>')}${trend()}
      ${note('两次测验的教学范围和题目不同。连线用于对照已评分记录量，不表示成绩或能力增长。')}
    </section>
    <section class="panel">${panelHead('评分覆盖率分布','已评分题目占本节点可测题目的比例','<span class="pill">直方图 · 人数</span>')}${histogram(coverageBins,'#a69ac2')}
      <div class="distribution-summary"><span>范围已确认<strong>${coverageBins.count} 人</strong></span><span>范围待确认<strong>${coverageBins.missing} 人</strong></span><span>覆盖不足一半<strong>${c.coverage_summary.students_below_0_5} 人</strong></span></div>
      ${note('仅统计范围已确认的学生。0% 表示范围已知但暂无评分；范围未知的学生单独列出，不按 0% 处理。')}
    </section>
  </div>
  <div class="grid-half">
    <section class="panel">${panelHead('常见失分点','依据评分点统计','<span class="pill warm">TOP 4</span>')}${commonIssues()}${note('失分比例 = 出现该评分点失分的学生 / 该知识点有观测的学生。评分点只能提供线索，具体原因需核对原始作答。')}</section>
    <section class="panel">${panelHead('班级对照',`本次测验 · 全部 ${groups().length} 个班级`)}${groupComparison()}${note('班级得分率按已评分题目总分汇总；覆盖率按范围已确认的学生平均计算。不同班级材料覆盖可能不同，不据此推断能力高低。')}</section>
  </div>${heatmap()}`;
}

function topicComparison(owner=null) {
  const ids=owner?[owner]:profiles().map(p=>p.student_id);
  const rows=topics(D,state.node,ids);
  const peerIds=owner?D.students.filter(s=>s.group_id===D.profiles[state.node][owner].group_id).map(s=>s.student_id):[];
  const peers=owner?topics(D,state.node,peerIds):[];
  return comparisonBars(rows.map((row,i)=>({label:row.theme,detail:owner?`个人 ${row.graded} 条 / 班级 ${peers[i].graded} 条评分`:`${row.observedStudents} 人 · ${row.graded} 条评分`,values:{own:row.rate,peers:peers[i]?.rate}})),owner?[{key:'own',label:'个人得分率',color:'#3e8c78'},{key:'peers',label:'本班得分率',color:'#c9b691'}]:[{key:'own',label:'已评分得分率',color:'#4f9680'}]);
}

function groupComparison() {
  return comparisonBars(groups().map(g=>{
    const rows=D.students.filter(s=>s.group_id===g).map(s=>D.stats[state.node][s.student_id]);
    const earned=rows.reduce((sum,s)=>sum+s.earned_score,0), possible=rows.reduce((sum,s)=>sum+s.possible_score,0);
    return {label:groupName(g),detail:`${rows.length} 人 · ${rows.reduce((sum,s)=>sum+s.graded,0)} 条评分`,values:{score:possible?earned/possible:null,coverage:D.classes[state.node][g].coverage_summary.mean_ratio}};
  }),[{key:'score',label:'已评分得分率',color:'#4f9680'},{key:'coverage',label:'平均评分覆盖',color:'#a79abf'}]);
}

function heatmap() {
  const list = profiles(),
    visible = state.allHeatmap ? list : list.slice(0, 12);
  return `<section class="panel heatmap-panel">${panelHead('学生知识热力图','点击色块查看个人证据',`<button class="text-button" data-view="students">查看学生明细 ${icon('arrow',14)}</button>`)}<div class="table-scroll"><table class="data-table heatmap"><thead><tr><th>学生 / 知识点</th>${kb.knowledge.map(k=>`<th><button data-knowledge="${esc(k.knowledge_id)}" title="${esc(k.name)}">${esc(k.knowledge_id)}</button></th>`).join('')}</tr></thead><tbody>${visible.map(p=>`<tr><td><button class="text-button mono" data-student="${esc(p.student_id)}">${esc(p.student_id)}</button> <small class="muted">${esc(p.group_id)}</small></td>${kb.knowledge.map(k=>{const s=p.knowledge_states.find(x=>x.knowledge_id===k.knowledge_id);return `<td><button class="cell cell-${statusGroup(s.status)}" data-person-knowledge="${esc(k.knowledge_id)}" data-person="${esc(p.student_id)}" style="background:${states[s.status].color}" aria-label="${esc(p.student_id+' '+k.name+' '+states[s.status].label+'，'+s.evidence_count+'条有效评分')}" title="${esc(states[s.status].label+' · '+s.evidence_count+'条有效评分')}">${states[s.status].short}</button></td>`;}).join('')}</tr>`).join('')}</tbody></table></div><div class="table-footer"><span>显示 ${visible.length} / ${list.length} 人 · ${kb.knowledge.length} 个知识点</span><button class="text-button" data-toggle-heatmap>${state.allHeatmap?'收起列表':'展开全部学生'} ${icon('arrow',14)}</button></div>${legend()}</section>`;
}

function studentsPage() {
  let list=profiles().filter(p=>p.student_id.toLowerCase().includes(state.search.toLowerCase()));
  if(state.studentFilter==='needs')list=list.filter(p=>p.lists.needs_consolidation.length);
  if(state.studentFilter==='unknown')list=list.filter(p=>!p.coverage.scope_known);
  if(state.studentFilter==='submitted')list=list.filter(p=>planProgress(p.student_id).done);
  if(state.studentSort==='score')list.sort((a,b)=>(D.stats[state.node][b.student_id].score_ratio??-1)-(D.stats[state.node][a.student_id].score_ratio??-1));
  if(state.studentSort==='coverage')list.sort((a,b)=>(a.coverage.scope_known?a.coverage.ratio:2)-(b.coverage.scope_known?b.coverage.ratio:2));
  return `${hero('','学生明细','选择学生，查看个人画像、作答与学习建议。')}${filters()}
  <section class="panel roster-panel">${panelHead('学生列表','',`<span class="pill">${list.length} 人</span>`)}
    <div class="toolbar"><label class="search-field">${icon('search',15)}<input id="student-search" placeholder="搜索学生 ID" aria-label="搜索学生 ID" value="${esc(state.search)}"></label><div class="filters">
    <label class="filter">筛选<select id="student-filter"><option value="all" ${state.studentFilter==='all'?'selected':''}>全部学生</option><option value="needs" ${state.studentFilter==='needs'?'selected':''}>建议巩固</option><option value="unknown" ${state.studentFilter==='unknown'?'selected':''}>范围待确认</option><option value="submitted" ${state.studentFilter==='submitted'?'selected':''}>有练习提交</option></select></label>
    <label class="filter">排序<select id="student-sort"><option value="id" ${state.studentSort==='id'?'selected':''}>学生 ID</option><option value="score" ${state.studentSort==='score'?'selected':''}>得分率从高到低</option><option value="coverage" ${state.studentSort==='coverage'?'selected':''}>覆盖率从低到高</option></select></label></div></div>
    <div class="table-scroll roster-scroll" tabindex="0" aria-label="学生列表，可滚动"><table class="data-table"><thead><tr><th>学生</th><th>得分率</th><th>评分覆盖</th><th>已作答 / 已布置</th><th>巩固 / 待观察</th><th>新练习提交</th><th></th></tr></thead><tbody>${list.map(p=>{
      const s=D.stats[state.node][p.student_id],pr=planProgress(p.student_id);
      return `<tr class="${p.student_id===state.student?'selected':''}"><td><button class="text-button mono" data-student="${esc(p.student_id)}">${esc(p.student_id)}</button> <small class="muted">${esc(p.group_id)}</small></td><td><span class="table-score">${pct(s.score_ratio)}</span><small class="muted"> · ${s.graded} 条评分</small></td><td>${p.coverage.scope_known?pct(p.coverage.ratio):'范围待确认'}</td><td>${s.assigned?`${s.attempted} / ${s.assigned}`:'未记录'}</td><td>${p.lists.needs_consolidation.length} / ${p.lists.needs_observation.length}</td><td>${pr.done?`${pr.done} / ${pr.total} · 待评阅`:pr.total?'未记录':'无新计划'}</td><td><button class="text-button" data-student="${esc(p.student_id)}" aria-label="查看 ${esc(p.student_id)} 详情">查看 ${icon('arrow',13)}</button></td></tr>`;
    }).join('')}</tbody></table>${!list.length?empty('没有符合筛选条件的学生。'):''}</div>
    ${note('得分率仅反映已评分题目，不是统一试卷排名。新练习提交仅统计此浏览器的记录，等待评阅后才可更新画像。')}
  </section><div id="student-detail">${profileDetail(currentProfile(),true)}</div>`;
}

function profileDetail(p, teacher=false) {
  const s=D.stats[state.node][p.student_id];
  const metrics=`<section class="stats-grid profile-metrics">
    ${stat('已评分得分率',pct(s.score_ratio),'',`${s.earned_score} / ${s.possible_score} 分`,'trend')}
    ${stat('评分覆盖',p.coverage.scope_known?pct(p.coverage.ratio):'—','',p.coverage.scope_known?`${p.coverage.observed_items} / ${p.coverage.applicable_items} 道可测题目`:'测验参与范围待确认','target','#9a9a6c','#f2f3e9')}
    ${stat('已评分记录',s.graded,'条',`${s.pending} 条待评分`,'book','#c89160','#fbf1e8')}
    ${stat('作答完成率',pct(s.completion),'',`${s.attempted} / ${s.assigned} 条已布置记录`,'check','#9a87ae','#f2eef6')}
  </section>`;
  return `<section class="profile-banner"><div class="student-identity"><div class="student-avatar">${esc(p.student_id.slice(-3))}</div><div><h2>${esc(p.student_id)} <span class="pill">${esc(p.group_id)}</span></h2><p>${esc(state.node)} · ${p.coverage.scope_known?'范围已确认':'参与范围待确认'}</p></div></div><div class="profile-actions">${teacher?`<a class="button light" href="${routeURL('student')}">学生视角 ${icon('arrow',14)}</a>`:''}<button class="button" data-export>${icon('download',14)}导出摘要</button></div></section>
  ${teacher?metrics:''}
  <div class="profile-tabs" aria-label="个人画像内容">${[['analysis','表现分析','overview'],['records','作答记录','book'],['plans','学习建议','target']].map(([id,label,ico])=>`<button data-profile-tab="${id}" aria-pressed="${state.profileTab===id}" class="${state.profileTab===id?'active':''}">${icon(ico,15)}${label}${id==='plans'?`<span>${D.recommendations[state.node][p.student_id].plan.length}</span>`:''}</button>`).join('')}</div>
  <div class="profile-content">${state.profileTab==='records'?recordTable(p):state.profileTab==='plans'?`<section class="panel">${panelHead('学习建议',`${p.student_id} · ${state.node}`)}${plans(p.student_id,teacher)}</section>`:profileAnalysis(p)}</div>${teacher?feedbackPanel(p.student_id):''}`;
}

function profileAnalysis(p) {
  const needs=p.lists.needs_consolidation, strengths=p.lists.strengths, watching=p.lists.needs_observation;
  const focusCard=(title,list,color,emptyText)=>`<article class="focus-summary" style="--focus-color:${color}"><div><span>${title}</span><strong>${list.length}<small> 个</small></strong></div>${list.length?`<button class="text-button" data-knowledge="${esc(listIds(list)[0])}">${esc(nameFor(listIds(list)[0]))}${list.length>1?` <small>等 ${list.length} 项</small>`:''}${icon('arrow',12)}</button>`:`<p>${emptyText}</p>`}</article>`;
  return `<div class="focus-summary-grid">${focusCard('建议巩固',needs,'#c99365','当前没有巩固项')}${focusCard('掌握较好',strengths,'#579883','暂未确认优势知识点')}${focusCard('需要更多观察',watching,'#a596b9','当前没有待观察项')}</div>
  <div class="grid-main personal-charts"><section class="panel">${panelHead('主题表现对比','个人与所在班级的已评分题目')}${topicComparison(p.student_id)}${note('个人与班级均按已评分题目总分计算。本人包含在班级统计中；作答材料和数量可能不同，因此只作描述性对照。')}</section>
  <section class="panel">${panelHead('知识状态','每个知识点归入一种状态')}${donut(statusCount(p),p.knowledge_states.length,'个知识点')}${note('较可能与已确认状态在图中合并，明细表保留原判断。证据不足不等于未掌握。')}</section></div>
  <section class="panel">${panelHead('知识点明细','点击名称查看评分依据、课程要求和练习')}
    <div class="table-scroll"><table class="data-table knowledge-detail-table"><thead><tr><th>知识点</th><th>状态</th><th>平均得分率</th><th>满分 / 部分分 / 零分</th><th>有效评分 / 可测题</th></tr></thead><tbody>${p.knowledge_states.map(k=>`<tr><td><button class="knowledge-link" data-knowledge="${esc(k.knowledge_id)}"><small>${esc(k.knowledge_id)}</small><span>${esc(nameFor(k.knowledge_id))}</span></button></td><td>${badge(k.status)}</td><td>${pct(k.performance.mean_score_ratio)}</td><td><span class="score-breakdown"><i>${k.performance.full_credit}</i><i>${k.performance.partial_credit}</i><i>${k.performance.zero_credit}</i></span></td><td>${k.evidence_count} / ${k.applicable_items??'—'}</td></tr>`).join('')}</tbody></table></div>
    ${note('本表得分率是该知识点各条已评分记录得分比例的平均值。题目可关联多个知识点，跨知识点相加可能重复；主题与班级总分不会重复计入。')}
    <details class="method-details model-details"><summary>查看模型估计与置信区间</summary>${masteryBars(p.knowledge_states,nameFor)}</details>
  </section>`;
}

function recordTable(p) {
  const records=D.records.filter(r=>r.student_id===p.student_id&&r.node_id===state.node);
  const totals=aggregateRecords(records);
  return `<div class="grid-main"><section class="panel">${panelHead('本次作答','按已布置记录统计')}${donut(historicalItems(p.student_id),totals.assigned,'条已布置记录')}</section>
  <section class="panel">${panelHead('各次测验记录','保留不同测验的范围与评分状态')}
    <div class="node-history">${D.nodes.map(n=>{const s=D.stats[n.node_id][p.student_id],coverage=D.profiles[n.node_id][p.student_id].coverage;return `<div><span class="node-history-dot"></span><header><strong>${esc(n.node_id)}</strong><span>${esc(n.date)}</span></header><dl><div><dt>得分率</dt><dd>${pct(s.score_ratio)}</dd></div><div><dt>已评分</dt><dd>${s.graded} 条</dd></div><div><dt>覆盖率</dt><dd>${coverage.scope_known?pct(coverage.ratio):'—'}</dd></div><div><dt>待评分</dt><dd>${s.pending} 条</dd></div></dl></div>`;}).join('')}</div>${note('测验的教学与材料范围不同，这些记录不直接代表成绩增长。')}</section></div>
  <section class="panel">${panelHead('作答明细',`${records.length} 条记录`)}<div class="table-scroll"><table class="data-table"><thead><tr><th>题目</th><th>状态</th><th>得分 / 满分</th><th>记录</th><th></th></tr></thead><tbody>${records.map(r=>`<tr><td><button class="text-button" data-material="${esc(r.material_id)}">${esc(materialFor(r.material_id)?.title||r.material_id)}</button></td><td>${!r.assigned?'未布置':!r.attempted?'未作答':r.score==null?'待评分':r.score===r.max_score?'满分':r.score===0?'零分':'部分得分'}</td><td>${r.score??'—'} / ${r.max_score}</td><td class="mono">${esc(r.record_id)}</td><td><button class="text-button" data-evidence="${esc(r.record_id)}">查看作答 ${icon('arrow',12)}</button></td></tr>`).join('')}</tbody></table>${records.length?'':empty('本次测验没有作答记录。')}</div></section>`;
}

function knowledgeList(list, fallback) {
  return list.length ? `<div class="path-list">${list.map((v,i)=>{const id=typeof v==='string'?v:v.knowledge_id;return `<div class="path-row"><span class="path-marker">${i+1}</span><div><button class="text-button" data-knowledge="${esc(id)}"><strong>${esc(nameFor(id))}</strong></button>${v.reason?`<p>${esc(v.reason)}</p>`:''}</div></div>`;}).join('')}</div>` : empty(fallback);
}

function plans(sid, teacher = false) {
  const r = D.recommendations[state.node][sid];
  if (!r.plan.length) return empty('此节点没有生成新计划。若参与范围不明，请先确认范围；表现较好时也不强行加练。');
  const history = r.history || [];
  return `<div class="plan-list">${history.length?`<div class="notice">已完成 ${history.length} 项，保留在历史记录中；本轮只重排未开始项。</div>`:''}${r.plan.map(p=>{const done=p.material_ids.filter(m=>submission(sid,p.seq,m)).length;return `<article class="plan-card ${p.activity_type==='probe'?'probe':''}"><div class="plan-top"><div class="plan-heading"><span class="plan-index">${String(p.seq).padStart(2,'0')}</span><div><h3>${esc(p.activity)}</h3>${p.status==='in_progress'?'<span class="pill warm">进行中</span>':''}<div class="plan-meta"><span>${esc(p.issue_id)}</span><span>${esc(p.knowledge_ids.join(' / '))}</span><span>约 ${p.est_minutes} 分钟</span></div></div></div><span class="pill ${p.activity_type==='probe'?'purple':'warm'}">${p.activity_type==='probe'?'先补充观察':'巩固与验证'}</span></div><details class="method-details recommendation-reason"><summary>推荐依据</summary><p>${esc(p.reason)}</p></details><div class="check-line">${icon('check',15)}<span><strong>完成标准：</strong>${esc(p.check)}</span></div>${p.teacher_locked?`<div class="notice warm">教师已锁定：重新规划时保留此安排。</div>`:''}${(p.adjustments||[]).map(a=>`<div class="notice">教师调整（${ADJUST_LABEL[a.action]||a.action}）：${esc(a.reason||'')}</div>`).join('')}${(p.teacher_comments||[]).map(c=>`<div class="notice">教师评语：${esc(c.text)}</div>`).join('')}${!teacher?`<div class="feedback-row">${[['difficulty','太难'],['confusion','没看懂'],['request','需要更多例题']].map(([kind,label])=>`<button type="button" class="text-button" data-feedback-kind="${kind}" data-feedback-item="${esc(p.plan_item_id)}">${label}</button>`).join('')}</div>`:''}<div class="material-buttons">${p.material_ids.map(m=>`<button class="material-chip" data-material="${esc(m)}" data-plan="${p.seq}" data-owner="${esc(sid)}">${icon(materialFor(m)?.material_type==='assessment'?'target':'book',13)}${esc(m)} · ${materialFor(m)?.material_type==='assessment'?'练习':'阅读'}${submission(sid,p.seq,m)?' ✓':''}</button>`).join('')}</div><div class="progress-strip"><span>${done?`本机已提交 ${done} / ${p.material_ids.length} 项 · 待评阅`:'新练习：未记录'}</span><div class="progress-track"><i style="width:${done/p.material_ids.length*100}%"></i></div><span>${teacher?'待评阅':'点击材料开始'}</span></div></article>`;}).join('')}</div><div class="notice">${storageOK?'练习保存在此浏览器，教师页可查看。':'当前浏览器不允许本地存储，暂时无法保存新练习。'}提交后待评阅，历史画像不变。</div>`;
}

function feedbackPanel(sid) {
  const r = D.recommendations[state.node][sid];
  const items = r.plan || [];
  if (!items.length) return '';
  return `<section class="panel section-gap" id="teacher-feedback">${panelHead('教学调整与反馈闭环','调整只改计划，不改分数或掌握度；提交后立即重建本机快照。')}<form id="feedback-form" class="feedback-form"><label class="filter">计划项<select id="fb-item">${items.map(p=>`<option value="${esc(p.plan_item_id)}">${p.seq}. ${esc(p.knowledge_ids.join('/'))} · ${esc(p.activity_type)}</option>`).join('')}</select></label><label class="filter">动作<select id="fb-action"><option value="lock">锁定</option><option value="unlock">解除锁定</option><option value="remove">移除</option><option value="restore">恢复</option><option value="replace_materials">更换材料</option><option value="set_time">调整用时</option><option value="set_difficulty">调整难度</option><option value="comment">写评语</option></select></label><input id="fb-value" placeholder="材料 ID（逗号）/ 分钟 / 难度 / 评语"><input id="fb-reason" placeholder="调整理由（调整必填）"><button class="button" type="submit">提交调整</button></form><div id="fb-result" class="muted"></div>${note('事件追加到本机 data/feedback；教师调整不进入诊断，补充作答才作为派生证据参与重新诊断。')}</section>`;
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
  const p=currentProfile(), s=D.stats[state.node][state.student], progress=planProgress(state.student);
  return `<section class="student-hero">${hero('',`${esc(state.student)} 的学习概览`,`${esc(p.group_id)} · 七年级数学`)}</section>${filters(true)}
  <section class="stats-grid">
    ${stat('已评分得分率',pct(s.score_ratio),'',`${s.earned_score} / ${s.possible_score} 分 · ${s.graded} 条评分`,'trend')}
    ${stat('评分覆盖',p.coverage.scope_known?pct(p.coverage.ratio):'—','',p.coverage.scope_known?`${p.coverage.observed_items} / ${p.coverage.applicable_items} 道可测题目`:'测验参与范围待确认','map','#9a9a6c','#f2f3e9')}
    ${stat('作答完成率',pct(s.completion),'',`${s.attempted} / ${s.assigned} 条已布置记录`,'check','#c89160','#fbf1e8')}
    ${stat('新练习提交',progress.done?`${progress.done} / ${progress.total}`:'未记录','',progress.done?'已提交，等待评阅':progress.total?`当前有 ${progress.total} 项学习活动`:'当前没有新计划','book','#9a87ae','#f2eef6')}
  </section>${profileDetail(p)}
  <section class="panel section-gap">${panelHead('课程知识地图','选择知识点，查看学习要求与材料',`<button class="text-button" data-view="course">课程要求 ${icon('arrow',14)}</button>`)}${knowledgeMap(p)}${D.meta.dataset_id==='official-v1'?'':legend()}</section>`;
}

function studentPlans() {
  return `${hero('LEARNING INTO ACTION / 04','练习与建议','查看练习、完成标准与提交情况。')}${filters(true)}<section class="panel">${panelHead(`${esc(state.student)} 的学习建议`,`${esc(state.node)} · 预计用时供参考`,'<span class="pill">学习计划</span>')}${plans(state.student)}</section><section class="panel section-gap">${panelHead('想把学会的知识用起来？','试试自编互动实验，把抽象关系变成可观察的变化。')}<p class="panel-sub">先用数轴理解负数乘法的方向变化，再用预算方案练习建立数量关系。探索结果不计入正式评分。</p><button class="button light section-gap" data-view="explore">进入跨域探索 ${icon('arrow',15)}</button></section>`;
}

function collapsePanel(title, body, extraClass = '') {
  return `<details class="panel collapsible-panel ${extraClass}"><summary class="collapse-summary"><div class="panel-title"><h2>${title}</h2></div><span class="collapse-toggle"><span class="when-closed">展开</span><span class="when-open">收起</span>${icon('arrow',14)}</span></summary><div class="collapse-body">${body}</div></details>`;
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
  const audit = `<p class="panel-sub">此页为整个数据集的质量审计，跨两个节点；不受班级筛选影响。</p><div class="audit-flow">${[[q.input_records,'输入逻辑记录','CSV 解析后的记录数'],[q.duplicates_removed,'修订 / 重复淘汰','按数据层规则保留版本'],[q.rejected_records,'不纳入记录','保留拒绝原因'],[q.total_records,'最终保留记录','进入画像与复算']].map(([v,t,d],i)=>`<div class="audit-step"><small>STEP ${String(i+1).padStart(2,'0')}</small><strong>${v}</strong><span>${t}<br>${d}</span></div>`).join('')}</div><div class="notice">核对关系：输入 ${q.input_records} = 保留 ${q.total_records} + 修订 / 重复淘汰 ${q.duplicates_removed} + 不纳入 ${q.rejected_records}。保留中包含 ${q.partial_credit_records} 条部分得分记录，未按“全错”抹掉。</div><div class="audit-status">${['知识底座结构与引用','个人 / 班级画像复算','学习建议约束与复算'].map(t=>`<span>${icon('shield',15)}${t} · 通过</span>`).join('')}</div>${note(`数据生成时间：${esc(D.meta.generated_at)}。成果保存在被 Git 忽略的本机目录；页面没有调用外部模型。`)}`;
  const states = `<p class="panel-sub">按数据层整理结果统计。</p>${donut(Object.entries(q.records_by_state).map(([k,v],i)=>({label:labels[k]||k,value:v,color:['#398575','#d6a16f','#ab98be','#cad6d0','#e6ece7'][i]})),q.total_records,'条保留记录')}${note('“无观测”的学生—材料组合不一定有实体记录，因此不能只看此处计数判断知识覆盖。')}`;
  const boundaries = `<p class="panel-sub">缺失、待评分、未作答和部分得分分别处理。</p><ul class="rule-list">${q.handling_rules.map(r=>`<li>${esc(r)}</li>`).join('')}</ul><div class="notice warm">评分点失分是学习线索，不自动等于具体误概念。教师可以从知识点抽屉继续回查原始作答。</div>`;
  const sources = `<p class="panel-sub">保留材料出处，支持本机核对版本。</p><div class="table-scroll"><table class="data-table"><thead><tr><th>输入文件</th><th>逻辑记录数</th><th>SHA-256 指纹</th></tr></thead><tbody>${q.input_files.map(f=>`<tr><td>${esc(f.path)}</td><td>${f.rows??'—'}</td><td class="mono" title="${esc(f.sha256)}">${esc(f.sha256.slice(0,16))}…</td></tr>`).join('')}</tbody></table></div>`;
  const findings = `<p class="panel-sub">规则和处理动作来自任务 2 输出。</p><div class="table-scroll"><table class="data-table"><thead><tr><th>字段 / 记录</th><th>问题</th><th>数量 / 处理</th></tr></thead><tbody>${q.field_quality.map(f=>`<tr><td>${esc(f.field)}</td><td>${esc(f.issue)}</td><td>${f.count}</td></tr>`).join('')}${q.anomalies.slice(0,25).map(a=>`<tr><td>${esc(a.record_id||'—')}</td><td>${esc(a.reason)}</td><td>${esc(a.action)}</td></tr>`).join('')}</tbody></table></div>${!q.anomalies.length&&!q.field_quality.length?empty('当前没有记录到质量异常。'):''}${q.anomalies.length>25?note(`异常共有 ${q.anomalies.length} 项，页面展示前 25 项；全部保留在本机质量报告中。`):''}`;
  return `${hero('TRUST & TRACEABILITY / 05','数据与证据','查看数据质量与校验结果。')}
  ${collapsePanel('从原始记录到可用证据', audit)}
  <div class="grid-half section-gap">${collapsePanel('五态记录分布', states)}${collapsePanel('清洗与诊断的判断边界', boundaries)}</div>
  ${collapsePanel('源文件与数据指纹', sources, 'section-gap')}
  ${collapsePanel('质量检查发现', findings, 'section-gap')}
  <section class="panel section-gap review-entry-card" id="review-entry">
    <div><div class="eyebrow">存疑数据</div><h2>评分复核与证据隔离</h2><p>检查作答与参考答案、评分点合计之间的可疑记录；人工结论作为独立事件追加，不修改官方分数。</p></div>
    <button class="button light" data-review-entry>进入存疑证据 ${icon('arrow',14)}</button>
  </section>`;
}

const ADJUST_LABEL = {
  lock: '锁定',
  unlock: '解除锁定',
  remove: '移除',
  restore: '恢复',
  replace_materials: '更换材料',
  set_time: '调整用时',
  set_difficulty: '调整难度'
};

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
  const back = `<div class="toolbar"><button class="text-button" data-view="quality">${icon('arrow',13)}返回数据与证据</button></div>`;
  if (!r) {
    return `${back}${hero('DISPUTED EVIDENCE / 06', '先核对评分，再谈掌握。', '本机存疑评分审查产物未随快照生成。')}<section class="panel">${empty('本次快照没有存疑审查报告；请用 --refresh 重新生成本机展示数据。')}</section>`;
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
  return `${back}${hero('DISPUTED EVIDENCE / 06', '先核对评分，再谈掌握。', '规则只提出复核线索；官方分数原样保留，人工结论作为独立事件追加。')}
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
  return `${hero('EXPLORE & MAKE / 06','跨域探索','两个自编互动实验，不计入正式评分。')}${filters(true)}<div class="lab-tabs"><button data-lab="axis" class="${state.lab==='axis'?'active':''}"><strong>01 / 数轴 × 镜像变换</strong><small>理解负数乘法为什么改变不等号方向</small></button><button data-lab="budget" class="${state.lab==='budget'?'active':''}"><strong>02 / 代数 × 活动预算</strong><small>找出两种方案的交点与适用范围</small></button></div><section class="panel">${state.lab==='axis'?axisLab():budgetLab()}</section>`;
}

function axisLab() {
  return `${panelHead('当数轴发生镜像，大小关系会怎样？','关联 K-07 · 从几何变换的角度理解代数运算。','<span class="pill purple">自编互动 · 非官方评分</span>')}<div class="grid-half"><div><div class="lab-stage"><div class="lab-label"><span>原关系：3 ＜ 5</span><strong id="factor-label">同乘 −2</strong></div><svg id="number-line" class="number-line" viewBox="0 0 500 100" role="img" aria-label="数轴上变换后的两个数"></svg><div class="lab-equation" id="axis-equation">−6 ＞ −10</div><label class="lab-label" for="factor"><span>拖动乘数 a</span><span>−3 至 3</span></label><input class="lab-range" type="range" id="factor" min="-3" max="3" step="0.5" value="-2"></div><div class="lab-output" id="axis-rule"></div></div><div><div class="eyebrow">概念联系</div><h2>放大、镜像与压缩到一点</h2><p class="panel-sub">正数相乘像沿数轴缩放，左右顺序保留。负数相乘除了缩放，还相当于关于原点镜像，因此左右顺序反转。乘以 0 会让两个数都落在原点，不能继续保留原来的严格大小关系。</p><div class="notice">类比的边界：这个演示解释的是数的顺序变化，不替代解不等式时的完整等价变形论证。</div><h3>小检验：−2x ＜ 6 的解是？</h3><div class="lab-quiz"><button class="button" data-quiz="wrong">x ＜ −3</button><button class="button" data-quiz="correct">x ＞ −3</button></div><div id="quiz-feedback" aria-live="polite" class="panel-sub">选择后查看解释。此练习不改变历史画像。</div><button class="text-button section-gap" data-knowledge="K-07">回到知识点与正式学习建议 ${icon('arrow',14)}</button></div></div>`;
}

function budgetLab() {
  return `${panelHead('策划一次社团活动，选哪个方案？','关联代数式、方程与不等式 · 一个自编的小型建模项目。','<span class="pill purple">自编拓展 · 非官方推荐</span>')}<div class="grid-half"><div><div class="lab-stage"><div class="lab-label"><span>方案 A：9 + 2n 元</span><span>方案 B：3 + 4n 元</span></div><div class="budget-bars"><div class="budget-row"><span>方案 A</span><div class="budget-track"><i id="budget-a-bar"></i></div><strong id="budget-a"></strong></div><div class="budget-row"><span>方案 B</span><div class="budget-track"><i id="budget-b-bar"></i></div><strong id="budget-b"></strong></div></div><label class="lab-label" for="people"><span>参与人数 n</span><strong id="people-label">3 人</strong></label><input id="people" class="lab-range" type="range" min="1" max="12" value="3" step="1"></div><div class="lab-output" id="budget-result" aria-live="polite"></div></div><div><div class="eyebrow">动手实践</div><h2>从公式到一个“方案选择器”</h2><ol class="rule-list"><li>解释两条公式中的固定费用与每人费用。</li><li>解方程 9 + 2n = 3 + 4n，找到费用相同的人数。</li><li>用不等式判断何时 A 更划算，并考虑人数必须为正整数。</li><li>试着用电子表格或几行代码，做一个可输入人数的选择器。</li></ol><div class="notice">项目验收：输入 2、3、4 人，分别给出方案 B、费用相同、方案 A，并解释原因。费用为自编示例。</div><button class="text-button" data-knowledge="K-09">回看范围约束知识点 ${icon('arrow',14)}</button></div></div>`;
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
  if (r.status === 401) {
    location.replace('/login');
    throw new Error('登录状态已失效，请重新登录。');
  }
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
  fitTrend();
  const map = $('#app [data-interactive-map]');
  unmountMap = map ? mountMap(map, kb, openKnowledge) : null;
  document.title = `${viewLabel(state.view)} · KnowFlow`;
  if (chatOpen) bindChatChrome();
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
    return `<div class="chat-welcome"><strong>可以这样问</strong><p>回答只基于当前这份学情成果；没有依据时会直说。简洁模式少列数字，证据模式按“结论 / 依据”展开。</p><div class="chat-prompts"><button type="button" data-chat-prompt="${esc(`${state.student} 现在最需要补什么？`)}">${esc(`${state.student} 现在最需要补什么？`)}</button><button type="button" data-chat-prompt="这个班最薄弱的三个知识点？">这个班最薄弱的三个知识点？</button><button type="button" data-chat-prompt="K-07 的课程要求是什么？">K-07 的课程要求是什么？</button></div></div>`;
  }
  return chatMessages.map(message => {
    const trace = message.trace;
    const modeLabel = message.mode === 'evidence' ? '证据' : '简洁';
    return `<div class="chat-msg ${message.role} ${message.error ? 'error' : ''}"><div class="chat-bubble">${esc(message.text)}</div>${message.citations?.length?`<div class="chat-cites">${message.citations.map(citeChip).join('')}</div>`:''}${trace?`<details class="chat-trace"><summary>查看推理依据</summary><div class="chat-trace-steps">${trace.steps.map((step,index)=>`<div class="chat-trace-step"><span>${index+1}</span><div><strong>${esc(step.label)}</strong><p>${esc(step.detail)}</p></div></div>`).join('')}</div>${trace.evidence?.length?`<div class="chat-trace-evidence"><strong>用到的证据</strong><div class="chat-evidence-list">${trace.evidence.map(item=>`<span class="chat-evidence">${item.id?citeChip(item.id):''}<span>${esc(item.text)}</span></span>`).join('')}</div></div>`:''}<p class="chat-trace-note">${esc(trace.note||'展示事实卡与规则步骤，不含模型隐藏思维链。')}</p></details>`:''}${message.source?`<small class="chat-source">${modeLabel}模式 · ${message.source === 'llm' ? 'LLM 生成 · 已核对' : '本地规则回答'}</small>`:''}${message.note?`<small class="chat-note">${esc(message.note)}</small>`:''}</div>`;
  }).join('');
}

function chatPanel() {
  const resizeHandles = ['n','s','e','w','ne','nw','se','sw'].map(dir=>`<span class="chat-resize" data-resize="${dir}" aria-hidden="true"></span>`).join('');
  return `<section class="chat-panel" role="dialog" aria-label="与 AI 对话">${resizeHandles}<header class="chat-head" data-chat-drag><div><strong>AI 学伴</strong><small>${esc(chatContextLabel())}</small></div><button type="button" class="icon-button" data-chat-close aria-label="关闭对话">${icon('close')}</button></header><div class="chat-log" id="chat-log" aria-live="polite">${chatLog()}</div>${chatBusy?'<div class="chat-typing">正在查阅本机证据…</div>':''}<form class="chat-form" id="chat-form"><div class="chat-input-row"><select id="chat-mode" class="chat-mode-select" aria-label="回答方式" ${chatBusy?'disabled':''}><option value="concise" ${state.chatMode==='concise'?'selected':''}>简洁</option><option value="evidence" ${state.chatMode==='evidence'?'selected':''}>证据</option></select><textarea id="chat-input" rows="2" maxlength="500" placeholder="问当前班级、学生或知识点…" ${chatBusy?'disabled':''}></textarea><button class="button primary" type="submit" ${chatBusy?'disabled':''}>发送</button></div></form><div class="chat-foot">基于当前学情 · 简洁 / 证据两种回答 · 每条回答下方可展开依据</div></section>`;
}

function clampChatRect(rect) {
  const margin = 8;
  const width = Math.max(340, Math.min(rect.width, window.innerWidth - margin * 2));
  const height = Math.max(300, Math.min(rect.height, window.innerHeight - margin * 2));
  return {
    width,
    height,
    left: Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin)),
    top: Math.max(margin, Math.min(rect.top, window.innerHeight - height - margin))
  };
}

function applyChatGeometry() {
  const panel = document.querySelector('.chat-panel');
  if (!panel) return;
  if (!chatGeometry || window.innerWidth <= 900) {
    ['left','top','width','height','bottom','right'].forEach(prop => panel.style.removeProperty(prop));
    return;
  }
  panel.style.left = `${chatGeometry.left}px`;
  panel.style.top = `${chatGeometry.top}px`;
  panel.style.width = `${chatGeometry.width}px`;
  panel.style.height = `${chatGeometry.height}px`;
  panel.style.bottom = 'auto';
  panel.style.right = 'auto';
}

function resetChatGeometry() {
  chatGeometry = null;
  applyChatGeometry();
}

function beginChatGesture(event, kind, direction = '') {
  const panel = document.querySelector('.chat-panel');
  if (!panel || window.innerWidth <= 900) return;
  event.preventDefault();
  const rect = panel.getBoundingClientRect();
  chatGeometry = { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
  const start = { ...chatGeometry, x: event.clientX, y: event.clientY };
  const onMove = move => {
    const dx = move.clientX - start.x;
    const dy = move.clientY - start.y;
    const next = { ...start };
    if (kind === 'drag') {
      next.left = start.left + dx;
      next.top = start.top + dy;
    } else {
      if (direction.includes('e')) next.width = start.width + dx;
      if (direction.includes('s')) next.height = start.height + dy;
      if (direction.includes('w')) {
        next.width = start.width - dx;
        next.left = start.left + dx;
      }
      if (direction.includes('n')) {
        next.height = start.height - dy;
        next.top = start.top + dy;
      }
    }
    chatGeometry = clampChatRect(next);
    applyChatGeometry();
  };
  const onUp = () => {
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onUp);
  };
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onUp);
}

function bindChatChrome() {
  const panel = document.querySelector('.chat-panel');
  if (!panel || panel.dataset.chatBound) return;
  panel.dataset.chatBound = '1';
  const head = panel.querySelector('.chat-head');
  head?.addEventListener('pointerdown', event => {
    if (event.target.closest('button')) return;
    beginChatGesture(event, 'drag');
  });
  head?.addEventListener('dblclick', resetChatGeometry);
  panel.querySelectorAll('.chat-resize').forEach(handle => {
    handle.addEventListener('pointerdown', event => beginChatGesture(event, 'resize', handle.dataset.resize));
  });
  applyChatGeometry();
}

window.addEventListener('resize', () => {
  if (!chatGeometry) return;
  chatGeometry = clampChatRect(chatGeometry);
  applyChatGeometry();
});

function chatWidget() {
  return `<div id="chat-host">${chatOpen ? chatPanel() : ''}</div><button type="button" class="chat-fab ${chatOpen?'open':''}" id="chat-fab" aria-label="与 AI 对话" aria-expanded="${chatOpen}" title="与 AI 对话">${icon('chat',22)}<span>AI 学伴</span></button>`;
}

function scrollChat() {
  const log = document.querySelector('#chat-log');
  if (log) log.scrollTop = log.scrollHeight;
}

function renderChat() {
  const host = document.querySelector('#chat-host');
  if (host) {
    host.innerHTML = chatOpen ? chatPanel() : '';
    if (chatOpen) bindChatChrome();
  }
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
      mode: state.chatMode,
      context: {
        node_id: state.node,
        group_id: state.group,
        student_id: state.student
      }
    }, 'X-KnowFlow-Chat');
    const staleMode = !data.trace || data.trace.mode !== state.chatMode;
    chatMessages.push({
      role: 'assistant',
      text: data.answer,
      citations: data.citations || [],
      source: data.source,
      trace: data.trace,
      mode: data.trace?.mode || state.chatMode,
      note: data.note || (staleMode ? '当前后端进程未加载所选回答方式（旧版本）；请关闭并重启 dashboard 后重试。' : undefined)
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
  if (b.hasAttribute('data-logout')) {
    logout();
    return;
  }
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
  if (b.dataset.feedbackKind) {
    postJSON('/api/feedback', {
      event_type: 'student_feedback',
      student_id: state.student,
      node_id: state.node,
      plan_item_id: b.dataset.feedbackItem,
      kind: b.dataset.feedbackKind
    }, 'X-KnowFlow-Feedback').then(() => {
      toast('反馈已记录，正在重建快照…');
      location.reload();
    }).catch(error => toast(error.message));
    return;
  }
  if (b.hasAttribute('data-review-entry')) {
    state.view = 'reviews';
    render();
    window.scrollTo(0, 0);
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
  if (b.dataset.profileTab) {
    const y=window.scrollY;
    state.profileTab=b.dataset.profileTab;
    render();
    window.scrollTo(0,y);
    return;
  }
  if (b.dataset.student) {
    state.profileTab='analysis';
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
  if (event.target.id === 'chat-mode') {
    state.chatMode = event.target.value;
    return;
  }
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
  if (event.target.id === 'student-sort') {
    state.studentSort=event.target.value;
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
  if (event.target.id === 'feedback-form') {
    event.preventDefault();
    const action = document.querySelector('#fb-action').value;
    const value = document.querySelector('#fb-value').value.trim();
    const reason = document.querySelector('#fb-reason').value.trim();
    const payload = {
      event_type: 'teacher_adjustment',
      student_id: state.student,
      node_id: state.node,
      plan_item_id: document.querySelector('#fb-item').value,
      action,
      reason
    };
    if (action === 'comment') {
      payload.event_type = 'teacher_comment';
      payload.text = value;
      if (!payload.text) {
        toast('评语不能为空');
        return;
      }
    } else {
      if (!reason) {
        toast('请填写调整理由');
        return;
      }
      if (action === 'replace_materials') payload.materials = value;
      if (action === 'set_time') payload.est_minutes = Number(value);
      if (action === 'set_difficulty') payload.difficulty = Number(value);
    }
    const result = document.querySelector('#fb-result');
    if (result) result.textContent = '正在保存并重建快照…';
    try {
      await postJSON('/api/feedback', payload, 'X-KnowFlow-Feedback');
      location.reload();
    } catch (error) {
      if (result) result.textContent = error.message;
      toast(error.message);
    }
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
async function logout() {
  try {
    await fetch('/api/logout', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-KnowFlow-Logout': '1'},
      body: '{}'
    });
  } catch {}
  location.replace('/login');
}

async function init() {
  try {
    SESSION = await getJSON('/api/session');
    if (!SESSION.authenticated) {
      location.replace('/login');
      return;
    }
    D = await getJSON('/api/snapshot');
    kb = D.knowledge_base;
    if (isStudentAccount()) {
      state.role = 'student';
      state.student = SESSION.student_id;
    }
    readWork();
    render();
  } catch (e) {
    $('#app').innerHTML = `<div class="loading"><span class="brand-symbol">K</span><h1>暂时无法连接本机成果</h1><p>${esc(e.message)}</p><p>请检查启动窗口是否仍在运行，然后刷新页面。</p></div>`;
  }
}
init();
