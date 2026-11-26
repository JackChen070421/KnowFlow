import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
  taskWall, subjectLinks, historyReads, moreSections, taskById,
  rubricProgress, moreKey, emptyMoreRecord, parseMoreStore, moreRecord, moreSummary,
  MORE_VERSION
} from '../../src/knowflow/web/static/explore-more.mjs';

const graph = JSON.parse(readFileSync(new URL('../../knowledge/curriculum_graph.json', import.meta.url), 'utf8'));

test('the three entries carry complete, unique content', () => {
  assert.deepEqual(moreSections.map(section => section.id), ['tasks', 'links', 'reads']);
  assert.equal(taskWall.length, 6);
  assert.equal(subjectLinks.length, 8);
  assert.equal(historyReads.length, 3);
  assert.equal(new Set(taskWall.map(task => task.id)).size, 6);
  assert.equal(new Set(subjectLinks.map(item => item.id)).size, 8);
  assert.equal(new Set(historyReads.map(item => item.id)).size, 3);

  for (const task of taskWall) {
    for (const key of ['subject', 'role', 'title', 'brief', 'given', 'ask', 'deliverable', 'hint']) {
      assert.ok(typeof task[key] === 'string' && task[key].trim(), `${task.id}.${key}`);
    }
    assert.equal(task.rubric.length, 3, `${task.id}.rubric`);
    for (const item of task.rubric) assert.ok(item.id && item.text.trim(), `${task.id} rubric copy`);
  }

  for (const link of subjectLinks) {
    for (const key of ['subject', 'title', 'inClass', 'math', 'example', 'careful']) {
      assert.ok(typeof link[key] === 'string' && link[key].trim(), `${link.id}.${key}`);
    }
    assert.ok(link.knowledge.length >= 1, `${link.id}.knowledge`);
  }
  assert.equal(new Set(subjectLinks.map(item => item.subject)).size, 8, 'one link per subject');

  for (const read of historyReads) {
    assert.ok(read.title.trim() && read.takeaway.trim() && read.question.trim(), read.id);
    assert.ok(Number.isInteger(read.minutes) && read.minutes > 0, `${read.id}.minutes`);
    assert.ok(read.paragraphs.length >= 3, `${read.id}.paragraphs`);
    for (const paragraph of read.paragraphs) assert.ok(paragraph.trim(), `${read.id} paragraph`);
  }
});

test('every referenced knowledge point exists in the curriculum graph', () => {
  const known = new Set(graph.nodes.flatMap(node => node.knowledge_ids));
  for (const task of taskWall) {
    assert.ok(task.knowledge.length >= 1, `${task.id}.knowledge`);
    for (const id of task.knowledge) assert.ok(known.has(id), `${task.id} -> ${id}`);
  }
  for (const link of subjectLinks) {
    for (const id of link.knowledge) assert.ok(known.has(id), `${link.id} -> ${id}`);
  }
});

test('rubric progress counts only known rubric ids', () => {
  const task = taskById('books');
  const ids = task.rubric.map(item => item.id);
  assert.deepEqual(rubricProgress(task, []), {done: 0, total: 3, ratio: 0});
  assert.deepEqual(rubricProgress(task, [ids[0], 'stale']), {done: 1, total: 3, ratio: 1 / 3});
  assert.deepEqual(rubricProgress(task, ids), {done: 3, total: 3, ratio: 1});
});

test('storage keys are scoped per learner and degrade safely', () => {
  assert.equal(moreKey('official-v1', 'S001'), 'official-v1|S001');
  assert.notEqual(moreKey('official-v1', 'S001'), moreKey('official-v1', 'S002'));
  assert.deepEqual(emptyMoreRecord(), {tasks: {}});
  const empty = {version: MORE_VERSION, records: {}};
  assert.deepEqual(parseMoreStore(null), empty);
  assert.deepEqual(parseMoreStore('{not json'), empty);
  assert.deepEqual(parseMoreStore('[]'), empty);
  assert.deepEqual(parseMoreStore({version: 99, records: {}}), empty);
});

test('stored plans are validated and clipped, unknown ids dropped', () => {
  const parsed = parseMoreStore({
    version: MORE_VERSION,
    records: {
      'official-v1|S001': {
        tasks: {
          books: {plan: 'x'.repeat(2500), rubric: ['formula', 'formula', 'unknown'], updated_at: 'now'},
          unknown: {plan: 'nope'}
        },
        cases: {flip: {step: 2, reason: 0}}
      },
      broken: 'nope'
    }
  });
  assert.deepEqual(Object.keys(parsed.records), ['official-v1|S001']);
  const record = parsed.records['official-v1|S001'];
  assert.equal(record.tasks.books.plan.length, 2000);
  assert.deepEqual(record.tasks.books.rubric, ['formula']);
  assert.equal(record.tasks.unknown, undefined);
  assert.deepEqual(Object.keys(record), ['tasks']);
});

test('summary counts written plans only', () => {
  const store = parseMoreStore(null);
  const record = moreRecord(store, 'official-v1', 'S001');
  record.tasks.books = {plan: '18n + 12 ≤ 200', rubric: ['formula'], updated_at: 'now'};
  record.tasks.transit = {plan: '   ', rubric: [], updated_at: 'now'};
  const summary = moreSummary(store, 'official-v1', 'S001');
  assert.equal(summary.tasksWritten, 1);
  assert.equal(summary.taskTotal, 6);
  assert.equal(summary.linkTotal, 8);
  assert.equal(summary.readTotal, 3);
  assert.equal(moreSummary(store, 'official-v1', 'S002').tasksWritten, 0);
});
