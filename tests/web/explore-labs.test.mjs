import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
  exploreLabs, labById, mirrorModel, budgetModel, rentalModel, windowModel, labModel,
  exploreKey, emptyExploreRecord, parseExploreStore, labProgress, exploreSummary, EXPLORE_VERSION
} from '../../src/knowflow/web/static/explore-labs.mjs';

const graph = JSON.parse(readFileSync(new URL('../../knowledge/curriculum_graph.json', import.meta.url), 'utf8'));

test('every lab carries the fields the page renders', () => {
  assert.equal(exploreLabs.length, 4);
  assert.deepEqual(exploreLabs.map(lab => lab.index), ['01', '02', '03', '04']);
  assert.equal(new Set(exploreLabs.map(lab => lab.id)).size, 4);
  for (const lab of exploreLabs) {
    for (const key of ['field', 'title', 'hook', 'subtitle', 'question', 'context', 'model', 'boundary', 'transfer', 'stageLabel', 'takeaway']) {
      assert.ok(typeof lab[key] === 'string' && lab[key].trim(), `${lab.id}.${key}`);
    }
    assert.ok(Number.isInteger(lab.minutes) && lab.minutes > 0, `${lab.id}.minutes`);
    assert.equal(lab.steps.length, 3, `${lab.id}.steps`);
    assert.ok(lab.checks.length >= 3, `${lab.id}.checks`);
    assert.ok(lab.presets.length >= 3, `${lab.id}.presets`);
    assert.equal(lab.quiz.length, 2, `${lab.id}.quiz`);
    for (const item of lab.quiz) {
      assert.ok(item.q.trim());
      assert.equal(item.options.filter(option => option.correct).length, 1, `${lab.id} needs exactly one answer`);
      for (const option of item.options) assert.ok(option.text.trim() && option.why.trim(), `${lab.id} option copy`);
    }
  }
});

test('lab references resolve to existing curriculum nodes and knowledge points', () => {
  const nodes = new Map(graph.nodes.map(node => [node.node_id, node]));
  const knowledge = new Set(graph.nodes.flatMap(node => node.knowledge_ids));
  for (const lab of exploreLabs) {
    assert.ok(lab.nodes.length, `${lab.id}.nodes`);
    for (const node of lab.nodes) assert.ok(nodes.has(node), `${lab.id} -> ${node}`);
    for (const id of lab.knowledge) assert.ok(knowledge.has(id), `${lab.id} -> ${id}`);
    const covered = new Set(lab.nodes.flatMap(node => nodes.get(node).knowledge_ids));
    assert.ok(lab.knowledge.some(id => covered.has(id)), `${lab.id} knowledge not covered by its nodes`);
  }
});

test('mirroring keeps, reverses or collapses the order', () => {
  const positive = mirrorModel(2);
  assert.equal(positive.order, 'keep');
  assert.ok(positive.x < positive.y);
  assert.equal(positive.relation, '<');
  const negative = mirrorModel(-2);
  assert.equal(negative.order, 'reverse');
  assert.ok(negative.x > negative.y);
  assert.equal(negative.relation, '>');
  const zero = mirrorModel(0);
  assert.equal(zero.order, 'collapse');
  assert.equal(zero.x, 0);
  assert.equal(zero.y, 0);
  assert.equal(zero.relation, '=');
  assert.match(zero.text, /严格的大小关系消失/);
  assert.equal(labModel('mirror', -0.5).x, -1.5);
});

test('budget crosses over at three items and respects the cap', () => {
  const tie = budgetModel(3);
  assert.equal(tie.cheaper, 'tie');
  assert.equal(tie.a, 15);
  assert.equal(tie.b, 15);
  assert.equal(tie.tieAt, 3);
  assert.equal(tie.affordableA, 10);
  assert.equal(tie.affordableB, 6);
  const small = budgetModel(2);
  assert.equal(small.cheaper, 'B');
  assert.equal(small.diff, 2);
  const large = budgetModel(4);
  assert.equal(large.cheaper, 'A');
  assert.equal(large.diff, 2);
  assert.match(budgetModel(12).text, /方案 A 便宜/);
});

test('rental plan hits equality at one hour and keeps the segment break at two', () => {
  const short = rentalModel(0.5);
  assert.equal(short.cheaper, 'B');
  assert.equal(short.a, 6);
  assert.equal(short.b, 4);
  const tie = rentalModel(1);
  assert.equal(tie.cheaper, 'tie');
  assert.equal(tie.a, 6);
  assert.equal(tie.b, 6);
  assert.equal(tie.tieAt, 1);
  assert.equal(tie.breakAt, 2);
  const four = rentalModel(4);
  assert.equal(four.cheaper, 'A');
  assert.equal(four.a, 12);
  assert.equal(four.b, 18);
  assert.equal(four.diff, 6);
  assert.equal(rentalModel(2).a, 6);
  assert.equal(rentalModel(3).a, 9);
});

test('shared free time is an interval, a single moment or empty', () => {
  const interval = windowModel(15, 17);
  assert.equal(interval.kind, 'interval');
  assert.equal(interval.low, 15);
  assert.equal(interval.high, 17);
  assert.match(interval.text, /15 — 17/);
  const point = windowModel(18, 18);
  assert.equal(point.kind, 'point');
  assert.equal(point.low, 18);
  assert.equal(point.high, 18);
  assert.match(point.text, /单点/);
  const empty = windowModel(18, 16);
  assert.equal(empty.kind, 'empty');
  assert.match(empty.text, /没有公共时间/);
  const wide = windowModel(12, 20);
  assert.equal(wide.low, 14);
  assert.equal(wide.high, 18);
  assert.equal(labModel('window', {s: 13, e: 15}).high, 15);
});

test('storage keys are deterministic and scoped per learner', () => {
  assert.equal(exploreKey('official-v1', 'S001', 'mirror'), 'official-v1|S001|mirror');
  assert.notEqual(exploreKey('official-v1', 'S001', 'mirror'), exploreKey('official-v1', 'S002', 'mirror'));
  assert.deepEqual(emptyExploreRecord(), {checks: [], answers: {}, transfer: '', updated_at: ''});
});

test('a broken or foreign local store degrades to empty instead of throwing', () => {
  assert.deepEqual(parseExploreStore(null), {version: EXPLORE_VERSION, records: {}});
  assert.deepEqual(parseExploreStore('{not json'), {version: EXPLORE_VERSION, records: {}});
  assert.deepEqual(parseExploreStore('[]'), {version: EXPLORE_VERSION, records: {}});
  assert.deepEqual(parseExploreStore({version: 99, records: {}}), {version: EXPLORE_VERSION, records: {}});
  const parsed = parseExploreStore({
    version: EXPLORE_VERSION,
    records: {
      'official-v1|S001|mirror': {checks: ['keep', 'keep', 3], answers: {'0': 1, '1': 99, bad: 2}, transfer: 'x'.repeat(2500), updated_at: 'now'},
      broken: 'nope'
    }
  });
  assert.deepEqual(Object.keys(parsed.records), ['official-v1|S001|mirror']);
  assert.deepEqual(parsed.records['official-v1|S001|mirror'].checks, ['keep']);
  assert.deepEqual(parsed.records['official-v1|S001|mirror'].answers, {'0': 1});
  assert.equal(parsed.records['official-v1|S001|mirror'].transfer.length, 2000);
});

test('a lab counts as done once both self-check answers are right', () => {
  const lab = labById('mirror');
  const record = emptyExploreRecord();
  assert.deepEqual(labProgress(record, lab), {checks: 0, checksTotal: 3, correct: 0, quizTotal: 2, done: false});
  record.checks = ['keep', 'reverse'];
  record.answers = {'0': 1};
  assert.deepEqual(labProgress(record, lab), {checks: 2, checksTotal: 3, correct: 1, quizTotal: 2, done: false});
  record.answers = {'0': 1, '1': 1};
  assert.equal(labProgress(record, lab).done, true);
  record.checks = ['keep', 'reverse', 'collapse', 'stale'];
  assert.equal(labProgress(record, lab).checks, 3);
  assert.equal(labProgress(record, lab).done, true);
  record.answers = {'0': 0, '1': 1};
  assert.equal(labProgress(record, lab).done, false);
  assert.equal(exploreSummary({version: EXPLORE_VERSION, records: {}}, 'official-v1', 'S001').done, 0);
});
