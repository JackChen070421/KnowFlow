import test from 'node:test';
import assert from 'node:assert/strict';
import {buildAdviceSummary, renderAdviceSummary} from '../../src/knowflow/web/static/advice-summary.mjs';

const knowledge = {
  knowledge: [{knowledge_id:'K-01', name:'等式的性质'}, {knowledge_id:'K-02', name:'方程的应用'}],
  objectives: [{objective_id:'OBJ-7M-01', objective_text:'用等量关系建立模型。', source_locator:'课程要求第 1 条'}],
  materials: [{material_id:'M-001', title:'学习卡', material_type:'explain'}, {material_id:'M-002', title:'练习', material_type:'assessment'}],
};
const planItem = {
  seq:1, issue_id:'IS-001-01', knowledge_ids:['K-01'], objective_id:'OBJ-7M-01',
  activity_type:'consolidate', material_ids:['M-001','M-002'], primary_material_id:'M-002',
  reason:'需要核对等式变形步骤。', check:'原计划的完整完成标准。', est_minutes:12,
  completion_condition:{type:'full_credit', min_full_credit:1, criterion:'变形正确'},
};

test('preserves recommendation order and counts knowledge states, excluding out-of-scope points', () => {
  const profile = {knowledge_states:[
    {knowledge_id:'K-01',status:'likely_weak', evidence_count:3, performance:{full_credit:1}},
    {knowledge_id:'K-02',status:'unobserved'}, {status:'sparse_good'}, {status:'not_applicable'},
  ]};
  const recommendation = {plan:[{...planItem, seq:2}, {...planItem, seq:1}]};
  const before = JSON.stringify(recommendation);
  const summary = buildAdviceSummary(profile, recommendation, knowledge);
  assert.deepEqual(summary.items.map(i=>i.seq),[1,2]);
  assert.deepEqual([summary.weak, summary.unknown, summary.good], [1,1,1]);
  assert.equal(summary.minutes,24);
  assert.equal(JSON.stringify(recommendation),before);
});

test('missing and pending evidence are never described as wrong answers', () => {
  for (const status of ['unobserved','insufficient_evidence']) {
    const summary = buildAdviceSummary({knowledge_states:[{knowledge_id:'K-01',status,evidence_count:0}]}, {plan:[planItem]}, knowledge);
    assert.match(summary.items[0].basis,/观察|核验/);
    assert.doesNotMatch(summary.items[0].basis,/0 条满分|答错|薄弱/);
    assert.equal(summary.weak,0);
  }
});

test('uses score-point evidence without claiming an unobserved cognitive cause', () => {
  const profile = {knowledge_states:[{knowledge_id:'K-01',status:'likely_weak',evidence_count:4,performance:{full_credit:1}}],issues:[{
    issue_id:'IS-001-01', evidence:{records:['R-0001']}, rubric_evidence:[
      {criterion:'答案正确',score:0,max_score:1},
      {criterion:'两边同时变形',score:0,max_score:1},
      {criterion:'检验',score:1,max_score:1},
    ],
  }]};
  const {items:[item]} = buildAdviceSummary(profile,{plan:[planItem]},knowledge);
  assert.match(item.basis,/4 条有效评分，1 条满分/);
  assert.match(item.basis,/两边同时变形/);
  assert.doesNotMatch(item.basis,/检验|概念混淆/);
  assert.deepEqual(item.records,['R-0001']);
  assert.match(item.action,/1 份学习材料.*1 道练习/);
});

test('multiple knowledge points sharing a record are not summed into inflated evidence counts', () => {
  const profile = {knowledge_states:['K-01','K-02'].map(knowledge_id=>({knowledge_id,status:'likely_weak',evidence_count:2,evidence:['R-0001','R-0002']}))};
  const {items:[item]} = buildAdviceSummary(profile,{plan:[{...planItem,knowledge_ids:['K-01','K-02']}]},knowledge);
  assert.equal(item.basis, planItem.reason);
  assert.doesNotMatch(item.basis,/4 条/);
});

test('completion summary follows structured thresholds and retains original text for audit', () => {
  const recommendation = {plan:[{...planItem,activity_type:'probe',completion_condition:{type:'probe_evidence',min_graded:3}}]};
  const {items:[item]} = buildAdviceSummary({},recommendation,knowledge);
  assert.match(item.check,/3 道有效评分/);
  assert.equal(item.rawCheck,planItem.check);
  const html = renderAdviceSummary({},recommendation,knowledge);
  assert.ok(html.includes(planItem.check));
  assert.ok(html.includes('课程要求第 1 条'));
  assert.ok(html.includes('data-material="M-002"'));
});

test('empty, incomplete and large recommendations stay explicit and escape source content', () => {
  assert.match(renderAdviceSummary({},undefined,knowledge),/暂无待执行建议/);
  const list = Array.from({length:4},(_,i)=>({...planItem,seq:i+1,est_minutes:undefined,reason:'<img src=x onerror=alert(1)>'}));
  const html=renderAdviceSummary({}, {plan:list}, knowledge);
  assert.equal((html.match(/class="advice-card /g)||[]).length,3);
  assert.match(html,/共 4 项安排/);
  assert.doesNotMatch(html,/<img|NaN|undefined|预计/);
  assert.match(html,/&lt;img/);
});

test('teacher view reuses the student summary and points at teaching feedback', () => {
  const profile = {knowledge_states:[{knowledge_id:'K-01',status:'likely_weak',evidence_count:3,performance:{full_credit:1}}]};
  const recommendation = {plan:[{...planItem,teacher_locked:true,student_feedback:[
    {kind:'difficulty'},{kind:'request'},{kind:'difficulty'},
  ]}],history:[{seq:0}]};
  const html = renderAdviceSummary(profile, recommendation, knowledge, {teacher:true});
  assert.match(html,/教师视角/);
  assert.match(html,/data-profile-tab="feedback"/);
  assert.match(html,/查看教学反馈/);
  assert.match(html,/学生反馈/);
  assert.equal((html.match(/太难/g)||[]).length,1);
  assert.match(html,/需要更多例题/);
  assert.match(html,/已锁定/);
  assert.match(html,/另有 1 项已完成/);
  assert.doesNotMatch(html,/进入学习空间|data-view="plan"/);
});

test('teacher view without a plan stays explicit and offers the evidence view', () => {
  const html = renderAdviceSummary({}, {plan: []}, knowledge, {teacher:true});
  assert.match(html,/没有生成新计划/);
  assert.match(html,/data-profile-tab="knowledge"/);
  assert.match(html,/没有新计划不代表已经掌握/);
  assert.doesNotMatch(html,/进入学习空间|data-view="plan"/);
});

test('student view keeps the learning-space entry and hides teacher signals', () => {
  const recommendation = {plan:[{...planItem,teacher_locked:true,student_feedback:[{kind:'difficulty'}]}],history:[{seq:0}]};
  const html = renderAdviceSummary({}, recommendation, knowledge);
  assert.match(html,/进入学习空间/);
  assert.match(html,/data-view="plan"/);
  assert.doesNotMatch(html,/教师视角|学生反馈|已锁定|另有 1 项已完成/);
});
