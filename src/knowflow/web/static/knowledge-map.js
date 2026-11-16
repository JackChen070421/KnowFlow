export function mountMap(host, {materials, knowledge, curriculum_graph: graph}, openKnowledge) {
const nodes = (graph?.nodes || []).map(n => ({
 id: n.node_id, name: n.title, topic: n.theme_index, summary: n.summary,
 loc: n.source_locator, book: n.textbook, page: n.pdf_page,
 indicators: n.knowledge_ids, material: n.material_id
}));
const edges = (graph?.edges || []).map(e => ({
 id: e.edge_id, from: e.source_node_id, to: e.target_node_id,
 kind: e.relation_type, status: e.review_status
}));
if (!nodes.length) {
 host.innerHTML = '<div class="none">本次快照未包含正式课程图谱。请先构建 knowledge/curriculum_graph.json，或使用 --refresh 重新生成展示数据。</div>';
 return () => {};
}
const root=host.attachShadow({mode:"open"});
root.innerHTML=`<link rel="stylesheet" href="/knowledge-map.css"><div class="tools"><input type="search" id="query" aria-label="查找知识点" placeholder="查知识点、教材章节或编号，如「消元」"><select id="topic" aria-label="主题"><option value="">全部主题</option></select><button class="mode" id="overviewMode" aria-pressed="true">知识总览</button><button class="mode" id="listMode" aria-pressed="false">一览表</button></div>
<section class="canvas" id="overview"><h2>七年级数学知识网络</h2><p class="hint">拖动圆点调整位置，拖动空白处平移。点击圆点聚焦，滚轮缩放。共 ${nodes.length} 个教材细目、${edges.length} 条关系，其中 ${edges.filter(e=>e.status!=='reviewed').length} 条待人工核验。</p><div class="legend" id="legend"></div>
<div class="explorer"><div class="stage"><svg id="atlas" role="group" aria-label="可拖动的数学知识图谱"><defs><marker id="tip" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#bacebb"/></marker></defs><g id="world"><g id="lines"></g><g id="dots"></g></g></svg><div class="maptools"><button id="home">查看全图</button><button id="minus" aria-label="缩小">−</button><button id="plus" aria-label="放大">＋</button></div></div><article id="detail" aria-live="polite"></article></div></section>
<div id="nodata" class="none" hidden>没有匹配的知识点。请更换关键词或选择其他主题。</div>
<div id="list" class="tablebox" hidden><table><thead><tr><th>知识点</th><th>简要内容与学习要求</th><th>教材位置</th></tr></thead><tbody id="rows"></tbody></table></div>`;
const themes=['代数式与整式运算','方程与方程组','不等式与不等式组'];
const $=id=>root.getElementById(id);
const byId=new Map(nodes.map(n=>[n.id,n]));
let active=null,mode='overview';
function el(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e}
themes.forEach((t,i)=>$('topic').add(new Option(t,String(i))));
function hits(){const q=$('query').value.trim().toLowerCase();return nodes.filter(n=>($('topic').value===''||String(n.topic)===$('topic').value)&&[n.name,n.id,n.summary,n.loc,themes[n.topic]].join(' ').toLowerCase().includes(q))}

function btn(n,cls){let b=el('button',n.name,cls);b.onclick=()=>choose(n.id);return b}
function pdf(n){
 const url=materials.find(m=>m.material_id===n.material)?.document_url;
 if(!url)return el('small','本机未载入该教材 PDF');
 const a=el('a','打开教材 · PDF 第 '+n.page+' 页 ↗','pdf');
 a.href=url+'#page='+n.page;a.target='_blank';a.rel='noopener';return a;
}
const colors=['#7fd4b0','#86bde8','#edb786'];
themes.forEach((name,i)=>{const tag=el('span',name),dot=el('i','');dot.style.background=colors[i];tag.prepend(dot);$('legend').append(tag)});
const uniqueEdges=edges.filter((e,i)=>e.kind==='prerequisite'||!edges.slice(0,i).some(p=>p.kind===e.kind&&p.from===e.to&&p.to===e.from));
// Fixed positions keep each connected component stable while highlighting and filtering.
const globalPositions=[
 [150,148],[820,156],[348,55],[364,175],[595,185],[485,92],[92,444],
 [743,77],[755,333],[484,215],[65,65],[905,76],[403,305],[568,308],[66,248],
 [887,446],[901,316],[485,398],[734,455],[602,470],[236,237]
];
function svgEl(tag,attrs){
 const e=document.createElementNS('http://www.w3.org/2000/svg',tag);
 for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);
 return e;
}
const svg=$('atlas'), positions=new Map(), homes=new Map(), groups=new Map(), segments=[];
let camera={x:495,y:267,k:1}, width=990,height=534, frame=0, gesture=null, suppressClick=false;
let shown=new Set(nodes.map(n=>n.id));
for(const edge of uniqueEdges){
 const line=svgEl('line',{class:'edge',stroke:'#a8c5b6','stroke-width':1.5});
 if(edge.kind==='prerequisite')line.setAttribute('marker-end','url(#tip)');else line.setAttribute('stroke-dasharray','4 4');
 $('lines').append(line);segments.push({edge,line});
}
for(const [i,n] of nodes.entries()){
 const [x,y]=globalPositions[i];homes.set(n.id,{x,y});positions.set(n.id,{x,y});
 const g=svgEl('g',{class:'point','data-id':n.id,tabindex:0,role:'button','aria-label':n.name+'，'+n.loc});
 const title=svgEl('title',{});title.textContent=n.name+' · '+n.loc;
 const label=svgEl('text',{'text-anchor':'middle',y:31});label.textContent=n.name;
 g.append(title,svgEl('circle',{r:22,fill:'transparent',style:'stroke:none'}),svgEl('circle',{r:10,fill:colors[n.topic]}),label);
 g.onclick=()=>{if(!suppressClick)selectNode(n.id)};
 g.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();selectNode(n.id)}};
 $('dots').append(g);groups.set(n.id,g);
}
function neighbors(id){return uniqueEdges.filter(e=>e.from===id||e.to===id).map(e=>({id:e.from===id?e.to:e.from,status:e.status,role:e.kind==='prerequisite'?(e.to===id?'基础知识':'后续应用'):(e.kind==='related_to'?'相关方法':'易混对照')}))}
function paint(){
 $('world').setAttribute('transform','translate('+width/2+' '+height/2+') scale('+camera.k+') translate('+(-camera.x)+' '+(-camera.y)+')');
 for(const [id,g] of groups){const p=positions.get(id);g.setAttribute('transform','translate('+p.x+' '+p.y+')')}
 for(const {edge,line} of segments){
  const a=positions.get(edge.from),b=positions.get(edge.to),dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;
  const r=Math.min(13,d/2);
  for(const [key,val] of Object.entries({x1:a.x+r*dx/d,y1:a.y+r*dy/d,x2:b.x-r*dx/d,y2:b.y-r*dy/d}))line.setAttribute(key,val);
 }
}
function layoutTo(targets,end){
 cancelAnimationFrame(frame);
 const from=new Map(positions),start={...camera},t0=performance.now(),duration=matchMedia('(prefers-reduced-motion: reduce)').matches?0:390;
 function step(t){
  const u=duration?Math.min(1,(t-t0)/duration):1,m=1-Math.pow(1-u,3);
  for(const [id,p] of targets){const a=from.get(id);positions.set(id,{x:a.x+(p.x-a.x)*m,y:a.y+(p.y-a.y)*m})}
  for(const key of ['x','y','k'])camera[key]=start[key]+(end[key]-start[key])*m;
  paint();if(u<1)frame=requestAnimationFrame(step)
 }
 frame=requestAnimationFrame(step);
}
function styleMap(){
 const near=new Set(active?[active,...neighbors(active).map(n=>n.id)]:[]);
 for(const [id,g] of groups){
  g.style.display=shown.has(id)?'':'none';g.classList.toggle('dim',!!active&&!near.has(id));
  g.classList.toggle('selected',id===active);g.setAttribute('aria-pressed',id===active);
 }
 for(const {edge,line} of segments){
  line.style.display=shown.has(edge.from)&&shown.has(edge.to)?'':'none';
  line.classList.toggle('dim',!!active&&edge.from!==active&&edge.to!==active);
 }
}
function showDetail(){
 const d=$('detail');d.replaceChildren();
 if(!active){d.append(el('div','知识点索引','meta'),el('h2',shown.size+' 个知识点'),el('p','选择圆点，查看学习要求、教材位置和直接联系。'),el('h3','关系线'),el('p','实线箭头从基础指向应用。虚线连接易混性质或相关方法；标“待核验”的关系尚未人工确认，不参与学习顺序。'));return}
 const n=byId.get(active);
 d.append(el('div',themes[n.topic]+' · '+n.id,'meta'),el('h2',n.name),el('h3','学习要求'),el('p',n.summary),el('h3','教材位置'),el('p',n.loc),pdf(n));
 d.append(el('h3','对应观察指标'));
 for(const id of n.indicators){
  const k=knowledge.find(item=>item.knowledge_id===id);
  if(k){const b=el('button',k.name+' · 学情与材料');b.onclick=()=>openKnowledge(id);d.append(b)}
 }
 const ns=neighbors(active);d.append(el('h3','直接联系 · '+ns.length));
 for(const other of ns){const b=el('button',other.role+(other.status==='reviewed'?' · 已核对':' · 待核验')+' · '+byId.get(other.id).name);b.onclick=()=>choose(other.id);d.append(b)}
}
function selectNode(id){
 active=id;styleMap();showDetail();
 const p=positions.get(id),near=neighbors(id).filter(n=>shown.has(n.id));
 const k=Math.min(1.35,Math.max(.74,width/630)),rx=Math.max(60,(width/2-75)/k*.78),ry=(height/2-63)/k*.82;
 const targets=new Map(homes);targets.set(id,p);
 near.forEach((n,i)=>{const angle=near.length===2?Math.PI/2+i*Math.PI:-Math.PI/2+i*2*Math.PI/near.length;
  targets.set(n.id,{x:p.x+rx*Math.cos(angle),y:p.y+ry*Math.sin(angle)})});
 // Foreground nodes stay selectable even when unrelated regions overlap.
 for(const n of [...near,{id}])$('dots').append(groups.get(n.id));
 layoutTo(targets,{x:p.x,y:p.y,k});
}
function full(){
 active=null;styleMap();showDetail();
 const ps=[...shown].map(id=>homes.get(id));if(!ps.length)return;
 const xs=ps.map(p=>p.x),ys=ps.map(p=>p.y),left=Math.min(...xs)-83,right=Math.max(...xs)+83,top=Math.min(...ys)-40,bottom=Math.max(...ys)+76;
 layoutTo(homes,{x:(left+right)/2,y:(top+bottom)/2,k:Math.min(width/(right-left),height/(bottom-top),1.45)});
}
function local(e){const b=svg.getBoundingClientRect();return {x:e.clientX-b.left,y:e.clientY-b.top}}
function zoom(f,p={x:width/2,y:height/2}){
 cancelAnimationFrame(frame);const k=Math.min(4,Math.max(.18,camera.k*f));
 camera.x+=(p.x-width/2)*(1/camera.k-1/k);camera.y+=(p.y-height/2)*(1/camera.k-1/k);camera.k=k;paint()
}
svg.onwheel=e=>{e.preventDefault();zoom(Math.exp(-Math.sign(e.deltaY)*.14),local(e))};
svg.onpointerdown=e=>{
 if(e.button!==0||gesture)return;
 cancelAnimationFrame(frame);suppressClick=false;
 const id=e.target.closest('.point')?.dataset.id;
 const target=id?groups.get(id):svg;
 gesture={pointer:e.pointerId,id,origin:local(e),start:id?{...positions.get(id)}:{...camera},moved:false};
 if(svg.hasPointerCapture(e.pointerId)||e.isTrusted)target.setPointerCapture(e.pointerId);
};
svg.onpointermove=e=>{
 if(!gesture||gesture.pointer!==e.pointerId)return;
 const p=local(e),dx=p.x-gesture.origin.x,dy=p.y-gesture.origin.y;
 if(!gesture.moved&&Math.hypot(dx,dy)<4)return;
 gesture.moved=true;svg.classList.add('dragging');
 const {id,start}=gesture;
 if(id){const pos={x:start.x+dx/camera.k,y:start.y+dy/camera.k};positions.set(id,pos);homes.set(id,pos)}
 else{camera.x=start.x-dx/camera.k;camera.y=start.y-dy/camera.k}
 paint();
};
function endGesture(e){if(gesture?.pointer!==e.pointerId)return;suppressClick=gesture.moved||e.type==='pointercancel';gesture=null;svg.classList.remove('dragging');setTimeout(()=>suppressClick=false,0)}
svg.onpointerup=svg.onpointercancel=endGesture;
function choose(id){if(!shown.has(id)){$('query').value='';$('topic').value=''}if(mode==='list'||!shown.has(id)){mode='overview';render()}selectNode(id)}
function measure(){const b=svg.getBoundingClientRect();if(!b.width||!b.height)return false;width=b.width;height=b.height;svg.setAttribute('viewBox','0 0 '+width+' '+height);return true}
function render(){
 const results=hits();shown=new Set(results.map(n=>n.id));
 $('nodata').hidden=!!results.length;$('overview').hidden=mode==='list'||!results.length;$('list').hidden=mode!=='list'||!results.length;
 $('overviewMode').setAttribute('aria-pressed',mode==='overview');$('listMode').setAttribute('aria-pressed',mode==='list');
 if(mode==='list'){const body=$('rows');body.replaceChildren();for(const n of results){const tr=el('tr',''),name=el('td',''),loc=el('td',n.loc);name.append(btn(n,''));loc.append(el('br',''),pdf(n));tr.append(name,el('td',n.summary),loc);body.append(tr)}}else if(measure())full();
}
$('query').oninput=$('topic').onchange=render;
$('overviewMode').onclick=()=>{mode='overview';render()};$('listMode').onclick=()=>{mode='list';render()};
$('home').onclick=full;$('plus').onclick=()=>zoom(1.25);$('minus').onclick=()=>zoom(.8);
const observer=new ResizeObserver(()=>{const oldW=width,oldH=height;if(measure()&&(width!==oldW||height!==oldH)){if(active)selectNode(active);else full()}});observer.observe(svg);
render();
return ()=>{observer.disconnect();cancelAnimationFrame(frame)};
}
