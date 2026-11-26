import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {logicLayout,logicNeighborhood,logicRelationLabel} from '../../src/knowflow/web/static/map-layout.mjs';
import {relax,relaxCategory,interpolateCamera,resizeCamera} from '../../src/knowflow/web/static/map-layout.mjs';

const graph=JSON.parse(readFileSync(new URL('../../knowledge/curriculum_graph.json',import.meta.url),'utf8'));
const nodes=graph.nodes.map(n=>({id:n.node_id,topic:n.theme_index}));
test('logic view preserves graph evidence and places prerequisites above successors',()=>{
 const before=JSON.stringify(graph),layout=logicLayout(nodes,graph.edges);
 assert.equal(layout.positions.size,nodes.length);
 assert.equal(new Set([...layout.positions.values()].map(p=>`${p.x},${p.y}`)).size,nodes.length);
 assert.deepEqual(layout.links,graph.edges);
 for(const e of graph.edges.filter(e=>e.relation_type==='prerequisite'))assert.ok(layout.positions.get(e.source_node_id).y<layout.positions.get(e.target_node_id).y);
 assert.equal(JSON.stringify(graph),before);
});
test('focus includes only immediate neighbors and preserves relative relationship direction',()=>{
 const near=logicNeighborhood('C-010',graph.edges);
 assert.deepEqual([...near.ids].sort(),['C-004','C-005','C-010','C-013','C-014']);
 assert.equal(near.links.filter(e=>logicRelationLabel(e,'C-010')==='前置知识').length,2);
 assert.equal(near.links.filter(e=>logicRelationLabel(e,'C-010')==='后续知识').length,2);
 const methods=logicNeighborhood('C-013',graph.edges);
 assert.ok(methods.links.some(e=>logicRelationLabel(e,'C-013')==='不同方法'));
 assert.deepEqual([...logicNeighborhood('C-007',graph.edges).ids],['C-007']);
});
test('empty and cyclic display graphs terminate with finite positions and omit dangling links',()=>{
 assert.equal(logicLayout([],[]).positions.size,0);
 const cycle=[{source_node_id:'a',target_node_id:'b',relation_type:'prerequisite'},{source_node_id:'b',target_node_id:'a',relation_type:'prerequisite'},{source_node_id:'a',target_node_id:'missing'}];
 const result=logicLayout([{id:'a',topic:0},{id:'b',topic:0}],cycle);
 assert.equal(result.links.length,2);
 assert.ok([...result.positions.values()].every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
});

test('panel resize preserves the on-screen position before focus starts',()=>{
 const a={x:40,y:-30,k:.7},b=resizeCamera(a,900,600,500,600),point={x:-200,y:130};
 assert.ok(Math.abs(450+(point.x-a.x)*a.k-(250+(point.x-b.x)*b.k))<1e-9);
 assert.equal(a.k,b.k);
});
test('selected node follows a straight screen path without overshoot',()=>{
 const a={x:150,y:100,k:.5},p={x:-200,y:300},b={...p,k:1.1};
 const start={x:(p.x-a.x)*a.k,y:(p.y-a.y)*a.k};let previous=Math.hypot(start.x,start.y);
 for(let i=1;i<=40;i++){const c=interpolateCamera(a,b,i/40),x=(p.x-c.x)*c.k,y=(p.y-c.y)*c.k;
  assert.ok(Math.abs(x*start.y-y*start.x)<1e-8);const distance=Math.hypot(x,y);assert.ok(distance<=previous+1e-9);previous=distance;
 }assert.equal(previous,0);
});

test('camera transition has exact endpoints and monotonic intermediate zoom',()=>{
 const a={x:0,y:10,k:.5},b={x:200,y:-50,k:1.2};
 assert.deepEqual(interpolateCamera(a,b,0),a);assert.deepEqual(interpolateCamera(a,b,1),b);
 let previous=a.k;for(let i=1;i<=20;i++){const c=interpolateCamera(a,b,i/20);assert.ok(c.k>=previous&&c.k<=b.k);previous=c.k}
 assert.ok(interpolateCamera(a,b,.25).k>a.k);assert.ok(interpolateCamera(a,b,.75).k<b.k);
});

test('category spring keeps dragged node fixed and pulls its neighbor',()=>{
 const points=[{id:'hub',x:0,y:0,homeX:0,homeY:0},{id:'leaf',x:500,y:0,homeX:250,homeY:0}];
 relaxCategory(points,[{from:'hub',to:'leaf'}],'leaf');
 assert.equal(points[1].x,500);assert.ok(points[0].x>0);
 for(let i=0;i<300;i++)relaxCategory(points,[{from:'hub',to:'leaf'}],'leaf',.5);
 assert.ok(points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
});
test('dragged node stays pinned while linked neighbor follows',()=>{
 const points=[{id:'a',x:0,y:0},{id:'b',x:600,y:0}];
 relax(points,[{from:'a',to:'b'}],'a');
 assert.equal(points[0].x,0);assert.equal(points[0].y,0);assert.ok(points[1].x<600);
});
test('overlapping nodes separate and remain finite across repeated relaxation',()=>{
 const points=[{id:'a',x:0,y:0},{id:'b',x:0,y:0},{id:'c',x:0,y:0}];
 for(let i=0;i<300;i++)relax(points,[{from:'a',to:'b'}]);
 assert.ok(points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)));
 assert.ok(Math.hypot(points[0].x-points[1].x,points[0].y-points[1].y)>80);
});
