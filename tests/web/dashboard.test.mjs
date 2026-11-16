// No package install: node --test tests/web/dashboard.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {describe, distribution, aggregateRecords, topics, placeLabels} from '../../src/knowflow/web/static/analytics.mjs';

test('ungraded students are excluded; real zero and full marks remain in the histogram', () => {
  const result=distribution([null,undefined,NaN,0,.19999,.2,.4,.6,.8,1]);
  assert.deepEqual(result.bins.map(b=>b.value),[2,1,1,1,2]);
  assert.equal(result.missing,3);
  assert.equal(result.count,7);
});
test('mean, median and endpoints use only finite observations', () => {
  assert.deepEqual(describe([null,0,.25,.75,1]),{count:4,mean:.5,median:.5,min:0,max:1});
  assert.equal(describe([.9,.1,.2]).median,.2);
  assert.deepEqual(describe([null]),{count:0,mean:null,median:null,min:null,max:null});
});
const record=(score,max_score=2,extras={})=>({student_id:'S001',node_id:'N01',material_id:'M-001',assigned:true,attempted:true,score,max_score,...extras});
test('completion, pending and partial credit keep separate denominators', () => {
  const sum=aggregateRecords([record(1),record(0),record(2),record(null),record(null,2,{attempted:false}),record(2,2,{assigned:false})]);
  assert.equal(sum.assigned,5);
  assert.equal(sum.attempted,4);
  assert.equal(sum.graded,3);
  assert.equal(sum.rate,.5);
  assert.equal(sum.completion,.8);
  assert.deepEqual([sum.full,sum.partial,sum.zero,sum.pending,sum.unattempted],[1,1,1,1,1]);
  assert.equal(aggregateRecords([]).rate,null);
});
test('theme totals do not duplicate multi-knowledge questions and obey node/student scope', () => {
  const data={knowledge_base:{objectives:[{objective_id:'O1',theme:'one'},{objective_id:'O2',theme:'two'}],materials:[{material_id:'M-001',objective_id:'O1'}],qmatrix:[{material_id:'M-001',knowledge_id:'K1'},{material_id:'M-001',knowledge_id:'K2'}]},records:[record(1),record(2,2,{student_id:'S002'}),record(2,2,{node_id:'N02'})]};
  const own=topics(data,'N01',['S001']);
  assert.equal(own[0].earned,1);
  assert.equal(own[0].possible,2);
  assert.equal(own[0].graded,1);
  assert.equal(own[1].rate,null);
  assert.equal(topics(data,'N01',['S001','S002'])[0].rate,.75);
});
test('close, identical and boundary line labels never overlap or leave the chart', () => {
  for(const positions of [[16,19],[60,60],[189,188],[10,11,12,13],[-10,20,400]]){
    const result=placeLabels(positions,14,180,24), sorted=[...result].sort((a,b)=>a-b);
    assert.ok(result.every(y=>y>=14&&y<=180));
    assert.ok(sorted.slice(1).every((y,i)=>y-sorted[i]>=24));
  }
  assert.deepEqual(placeLabels([25,80],14,180),[25,80]);
  assert.deepEqual(placeLabels([],14,180),[]);
});
