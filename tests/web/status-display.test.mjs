import test from 'node:test';
import assert from 'node:assert/strict';
import {states, legend, stateBars} from '../../src/knowflow/web/static/charts.js';

test('four levels share names and colors across confirmed and likely states',()=>{
  for(const key of ['mastered','confirmed_mastered','likely_mastered']) {
    assert.equal(states[key].label,'掌握');
    assert.equal(states[key].color,'#d78b51');
  }
  for(const key of ['weak','confirmed_weak','likely_weak']) {
    assert.equal(states[key].label,'薄弱');
    assert.equal(states[key].short,'弱');
    assert.equal(states[key].color,'#238778');
  }
  assert.equal(states.sparse_good.color,'#edb985');
  assert.equal(states.sparse_poor.color,'#81b9a5');
  assert.doesNotMatch(legend(),/表现不稳定|知识点表现不一|待观察/);
  assert.match(legend(true),/知识点表现不一/);
});

test('class bars retain all four separate counts with correct population widths',()=>{
  const html=stateBars([{knowledge_id:'K-01',student_count:10,mastered_count:1,sparse_good_count:2,sparse_poor_count:3,weak_count:4}],()=> '方程');
  for(const [label,count] of [['掌握',1],['较好',2],['较差',3],['薄弱',4]])assert.ok(html.includes(`${label} ${count} 人`));
  for(const width of [10,20,30,40])assert.ok(html.includes(`width:${width}%`));
});
