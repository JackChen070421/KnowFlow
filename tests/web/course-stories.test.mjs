import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {storyContent,storyPaths,storyExperiment,nodeVisuals,drawSemanticScene,visualReadingDelay} from '../../src/knowflow/web/static/course-stories.mjs';
import {radialLayout} from '../../src/knowflow/web/static/map-layout.mjs';

test('exploration covers every official node exactly once and links resolve',()=>{
 const graph=JSON.parse(readFileSync(new URL('../../knowledge/curriculum_graph.json',import.meta.url),'utf8'));
 const ids=graph.nodes.map(n=>n.node_id).sort();
 assert.deepEqual(storyPaths.flatMap(p=>p.ids).sort(),ids);
 assert.deepEqual(Object.keys(storyContent).sort(),ids);
 assert.deepEqual(Object.keys(nodeVisuals).sort(),ids);
 for(const c of Object.values(storyContent)){
  for(const key of ['title','question','idea','example','caution','check','answer'])assert.ok(c[key]);
  for(const [id,reason] of c.next){assert.ok(storyContent[id]);assert.ok(reason)}
  assert.equal(c.extra.length,2);
 }
});

test('category hierarchy places circular nodes with equal angular spacing',()=>{
 const graph=JSON.parse(readFileSync(new URL('../../knowledge/curriculum_graph.json',import.meta.url),'utf8'));
 const nodes=graph.nodes.map(n=>({id:n.node_id,topic:n.theme_index}));
 const {positions,hubs,links}=radialLayout(nodes);
 assert.equal(hubs.size,3);assert.equal(links.length,nodes.length);
 for(const n of nodes){assert.equal(links.find(l=>l.id===n.id).topic,n.topic);assert.ok(positions.has(n.id))}
 const points=[...positions.values()];
 for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){
  assert.ok(Math.hypot(points[i].x-points[j].x,points[i].y-points[j].y)>90,'circular nodes overlap');
 }
 for(const [topic,hub] of hubs){const angles=nodes.filter(n=>n.topic===topic).map(n=>{const p=positions.get(n.id);assert.ok(Math.abs(Math.hypot(p.x-hub.x,p.y-hub.y)-180)<.001);return (Math.atan2(p.y-hub.y,p.x-hub.x)+2*Math.PI)%(2*Math.PI)}).sort((a,b)=>a-b);for(let i=0;i<angles.length;i++){const gap=(angles[(i+1)%angles.length]-angles[i]+2*Math.PI)%(2*Math.PI);assert.ok(Math.abs(gap-2*Math.PI/angles.length)<.001)}}
});
test('multiplication preserves, reverses or collapses order',()=>{
 for(const k of [-2,-1,-.5,0,.5,1,2]){
  const r=storyExperiment('mirror',k);
  assert.equal(Math.sign(r.b-r.a),Math.sign(k));
 }
 assert.match(storyExperiment('mirror',0).text,/严格大小关系消失/);
});
test('cost comparison switches at the real-valued boundary',()=>{
 assert.equal(storyExperiment('cost',2).a,11);
 assert.equal(storyExperiment('cost',2).b,10);
 assert.equal(storyExperiment('cost',2.5).a,storyExperiment('cost',2.5).b);
 assert.ok(storyExperiment('cost',3).a<storyExperiment('cost',3).b);
});
test('intersection distinguishes an interval, a singleton and the empty set',()=>{
 assert.match(storyExperiment('intersection',2).text,/2 ≤ x ≤ 6/);
 assert.match(storyExperiment('intersection',6).text,/只剩 x = 6/);
 assert.match(storyExperiment('intersection',7).text,/没有公共解/);
});


test('all semantic animation steps render finite geometry with stable object identities',()=>{
 const makeNode=(tag,attrs={})=>({tagName:tag,attrs:{...attrs},textContent:'',setAttribute(k,v){this.attrs[k]=v}});
 for(const [id,config] of Object.entries(nodeVisuals)){
  if(config.kind!=='semantic')continue;
  for(let step=0;step<config.steps.length;step++){
   const children=[];
   const svg={append(node){children.push(node)},querySelector(selector){const key=selector.match(/"([^"\]]+)"/)[1];return children.find(n=>n.attrs['data-motion-key']===key)}};
   drawSemanticScene(svg,id,step,makeNode);
   assert.ok(children.length>0,id);
   const keys=children.map(n=>n.attrs['data-motion-key']);
   assert.equal(new Set(keys).size,keys.length,id+' duplicate visual identity');
   for(const n of children)for(const key of ['x','y','x1','x2','y1','y2','cx','cy','width','height','r']){
    if(key in n.attrs)assert.ok(Number.isFinite(Number(n.attrs[key])),id+' '+key);
   }
  }
 }
});

test('animation gives dense equations more reading time and holds the final result',()=>{
 assert.ok(visualReadingDelay('x = 4')>=4200);
 assert.ok(visualReadingDelay('先展开括号，再合并同类项：2(x + 3) − x = x + 3 + x + 3 − x = x + 6')>visualReadingDelay('x = 4'));
 assert.equal(visualReadingDelay('x = 4',true)-visualReadingDelay('x = 4'),1000);
});
