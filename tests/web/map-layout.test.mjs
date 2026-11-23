import test from 'node:test';
import assert from 'node:assert/strict';
import {relax} from '../../src/knowflow/web/static/map-layout.mjs';
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
