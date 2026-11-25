import {radialLayout,relaxCategory,interpolateCamera,resizeCamera} from './map-layout.mjs';
import {storyContent,mountNodeVisual} from './course-stories.mjs';

export function mountMap(host,{materials,knowledge,curriculum_graph:graph},openKnowledge,profile=null,training=null){
 const nodes=(graph?.nodes||[]).map(n=>({id:n.node_id,name:n.title,topic:n.theme_index,summary:n.summary,loc:n.source_locator,page:n.pdf_page,indicators:n.knowledge_ids,material:n.material_id}));
 if(!nodes.length){host.textContent='本次快照未包含课程图谱，请刷新展示数据。';return()=>{}}
 const themes=['代数式与整式运算','方程与方程组','不等式与不等式组'];
 const colors=['#268a72','#4a83bd','#bc7d42'];
 const states=new Map((profile?.knowledge_states||[]).map(s=>[s.knowledge_id,s]));
 const palette={confirmed_mastered:['已掌握','#199b79'],mastered:['已掌握','#199b79'],likely_mastered:['趋于掌握','#48ad98'],confirmed_weak:['需加强','#df785c'],weak:['需加强','#df785c'],likely_weak:['需加强','#df785c'],mixed_performance:['表现不稳定','#b58b31'],insufficient_evidence:['证据不足','#a3afbf'],not_applicable:['未覆盖','#cbd3df']};
 const byId=new Map(nodes.map(n=>[n.id,n])),edges=graph.edges||[];
 const root=host.attachShadow({mode:'open'});
 root.innerHTML=`<link rel="stylesheet" href="/knowledge-map.css"><div class="tools"><input id="query" type="search" aria-label="查找知识点" placeholder="查知识点、问题或教材章节"><select id="topic" aria-label="知识类别"><option value="">全部类别</option></select><button id="overviewMode" class="mode" aria-pressed="true">知识图谱</button><button id="listMode" class="mode" aria-pressed="false">一览表</button></div><section id="overview" class="canvas"><div class="map-caption"><strong>从整体，看见知识的分支</strong><span>中心 → 类别 → 知识点 · 点击节点打开图解</span></div><div class="legend" id="legend"></div><div class="explorer"><div class="stage"><svg id="atlas" role="group" aria-label="按类别辐射的数学知识图谱"><g id="world"><g id="branches"></g><g id="hubs"></g><g id="dots"></g></g></svg><div class="maptools"><button id="home">查看全图</button><button id="minus" aria-label="缩小">−</button><button id="plus" aria-label="放大">＋</button></div></div><article id="detail" class="story-reader" aria-label="知识点形象化讲解" hidden></article></div></section><div id="nodata" class="none" hidden>没有匹配的知识点，请更换关键词或类别。</div><div id="list" class="tablebox" hidden><table><thead><tr><th>知识点</th><th>学习要求</th><th>教材位置</th></tr></thead><tbody id="rows"></tbody></table></div>`;
 const $=id=>root.getElementById(id),svg=$('atlas'),world=$('world');
 function el(tag,text='',cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e}
 function se(tag,attrs={}){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e}
 function svgText(parent,text,x,y,cls){const t=se('text',{x,y,'text-anchor':'middle',class:cls});t.textContent=text;parent.append(t)}
 function action(group,fn){group.setAttribute('role','button');group.setAttribute('tabindex','0');group.onclick=()=>{if(!suppressClick)fn()};group.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();fn()}}}
 function nodeState(n){const ss=n.indicators.map(id=>states.get(id)).filter(Boolean);return ss.find(s=>['weak','confirmed_weak','likely_weak'].includes(s.status))||ss.find(s=>s.status==='insufficient_evidence')||ss.find(s=>s.status==='mixed_performance')||ss[0]}
 const layout=radialLayout(nodes);
 const points=new Map([['course',layout.center],...[...layout.hubs].map(([id,p])=>['category-'+id,p]),...layout.positions]);
 const homes=new Map([...points].map(([id,p])=>[id,{...p}]));
 const springs=[...[...layout.hubs.keys()].map(id=>({from:'course',to:'category-'+id})),...nodes.map(n=>({from:'category-'+n.topic,to:n.id}))];
 const storageKey='knowflow.dynamic-categories.v2.'+(profile?.student_id||'course');
 try{const saved=JSON.parse(localStorage.getItem(storageKey)||'{}');for(const [id,p] of points){const s=saved[id];if(s&&Number.isFinite(s.x)&&Number.isFinite(s.y)&&Math.abs(s.x)<10000&&Math.abs(s.y)<10000)Object.assign(p,{x:s.x,y:s.y})}}catch{}
 const segments=[],hubGroups=new Map();
 let drawKey=null,renderPoints=[],lastCamera='',paintFrame=0,geometryDirty=false;
 let physicsFrame=0,energy=0,pinned=null,dynamic=!matchMedia('(prefers-reduced-motion: reduce)').matches;
 let cameraFrame=0,cameraReady=false,animateNext=false;
 let mode='overview',active=null,shown=nodes,groups=new Map(),camera={x:0,y:0,k:1},width=900,height=650,gesture=null,suppressClick=false,frame=0,disposed=false;
 themes.forEach((name,i)=>{$('topic').add(new Option(name,String(i)));const item=el('span',name),dot=el('i');dot.style.background=colors[i];item.prepend(dot);$('legend').append(item)});
 if(profile)$('legend').append(el('span','节点圆点表示个人学情；边框表示类别'));
 function curve(a,b,color,main=false){const path=se('path',{fill:'none',stroke:color,'stroke-width':main?5:2.2,class:'category-branch'});$('branches').append(path);segments.push({a,b,path})}
 function draw(){
  const key=shown.map(n=>n.id).join('|');
  if(drawKey===key){highlight();syncViewport();paint(true);return}
  drawKey=key;
  groups=new Map();segments.length=0;hubGroups.clear();$('branches').replaceChildren();$('hubs').replaceChildren();$('dots').replaceChildren();
  const center=se('g',{class:'course-hub','aria-label':'七年级数学，查看全部类别'});
  center.append(se('circle',{r:82}));svgText(center,'七年级',0,-5,'center-title');svgText(center,'数学',0,28,'center-title');action(center,full);$('hubs').append(center);
  center.dataset.dragId='course';hubGroups.set('course',center);
  for(const [topic,hub] of layout.hubs){
   const category=shown.filter(n=>n.topic===topic);if(!category.length)continue;curve(layout.center,hub,colors[topic],true);
   const g=se('g',{transform:`translate(${hub.x} ${hub.y})`,class:'category-hub','aria-label':themes[topic]+'，聚焦本类',style:`--branch:${colors[topic]}`});
   g.append(se('rect',{x:-120,y:-34,width:240,height:68,rx:22}));svgText(g,themes[topic],0,-2,'category-title');svgText(g,category.length+' 个知识点',0,22,'category-count');action(g,()=>{$('topic').value=String(topic);render()});$('hubs').append(g);
   g.dataset.dragId='category-'+topic;hubGroups.set('category-'+topic,g);
   for(const n of category){
    const p=layout.positions.get(n.id);curve(hub,p,colors[topic]);
    const item=se('g',{transform:`translate(${p.x} ${p.y})`,class:'point radial-node','data-id':n.id,style:`--branch:${colors[topic]}`,'aria-label':n.name+'，打开图解','aria-pressed':n.id===active});
    item.append(se('circle',{r:32,class:'node-halo'}));const title=se('title');title.textContent=n.name+' · '+n.loc;item.append(title);
    const status=nodeState(n)?.status;item.append(se('circle',{r:21,class:'node-core',fill:profile?(palette[status]||palette.insufficient_evidence)[1]:colors[topic]}));
    const split=Math.ceil(n.name.length/2),chunks=n.name.length>7?[n.name.slice(0,split),n.name.slice(split)]:[n.name];chunks.forEach((chunk,i)=>svgText(item,chunk,0,(p.y<hub.y-20?-37-(chunks.length-1)*25:49)+i*25,'node-label'));action(item,()=>choose(n.id));$('dots').append(item);groups.set(n.id,item);
    item.dataset.dragId=n.id;
   }
  }renderPoints=[...groups,...hubGroups].map(([id,element])=>({point:points.get(id),element,x:NaN,y:NaN}));highlight();syncViewport();paint(true);
 }
 function highlight(){for(const [id,g] of groups){g.classList.toggle('selected',id===active);g.classList.toggle('dim',!!active&&byId.get(id).topic!==byId.get(active).topic);g.setAttribute('aria-pressed',String(id===active))}}
 function paint(geometry=false){
  const transform=`translate(${width/2} ${height/2}) scale(${camera.k}) translate(${-camera.x} ${-camera.y})`;
  if(transform!==lastCamera){world.setAttribute('transform',transform);lastCamera=transform}
  if(!geometry)return;
  for(const item of renderPoints){const p=item.point;if(p.x===item.x&&p.y===item.y)continue;item.element.setAttribute('transform',`translate(${p.x} ${p.y})`);item.x=p.x;item.y=p.y}
  for(const segment of segments){const {a,b,path}=segment;const d=`M ${a.x} ${a.y} Q ${a.x} ${b.y} ${b.x} ${b.y}`;if(d!==segment.d){path.setAttribute('d',d);segment.d=d}}
 }
 function requestPaint(geometry=false){geometryDirty=geometryDirty||geometry;if(paintFrame)return;paintFrame=requestAnimationFrame(()=>{paintFrame=0;if(disposed)return;const dirty=geometryDirty;geometryDirty=false;paint(dirty)})}
 function persist(){try{localStorage.setItem(storageKey,JSON.stringify(Object.fromEntries(points)))}catch{}}
 function wake(){
  if(!dynamic||disposed||mode!=='overview'||!shown.length)return;energy=1;if(physicsFrame)return;
  const visible=new Set(['course',...shown.map(n=>'category-'+n.topic),...shown.map(n=>n.id)]);
  const ps=[...points].filter(([id])=>visible.has(id)).map(([id,p])=>({id,...p,point:p,homeX:homes.get(id).x,homeY:homes.get(id).y}));
  const links=springs.filter(e=>visible.has(e.from)&&visible.has(e.to));let lastTick=-Infinity,quiet=0;
  function tick(now){
   if(disposed)return;
   if(now-lastTick<32){physicsFrame=requestAnimationFrame(tick);return}lastTick=now;
   for(const p of ps){p.x=p.point.x;p.y=p.point.y}
   relaxCategory(ps,links,gesture?.node||pinned,energy);let movement=0;
   for(const p of ps){movement=Math.max(movement,Math.abs(p.x-p.point.x)+Math.abs(p.y-p.point.y));p.point.x=p.x;p.point.y=p.y}
   requestPaint(true);energy*=.89;quiet=movement<.06?quiet+1:0;if(gesture?.node)energy=Math.max(.5,energy);
   if((energy>.025&&quiet<3)||gesture?.node)physicsFrame=requestAnimationFrame(tick);else{physicsFrame=0;persist()}
  }
  physicsFrame=requestAnimationFrame(tick);
 }
 function syncViewport(){
  const box=svg.getBoundingClientRect();if(!box.width||!box.height)return false;
  if(cameraReady&&(box.width!==width||box.height!==height)){camera=resizeCamera(camera,width,height,box.width,box.height);if(cameraFrame){cancelAnimationFrame(cameraFrame);cameraFrame=0;animateNext=true}}
  width=box.width;height=box.height;svg.setAttribute('viewBox',`0 0 ${width} ${height}`);return true;
 }
 function fit(){
  if(disposed||mode!=='overview'||!shown.length||!syncViewport())return;
  // Freeze geometry during camera travel: only one transform changes per frame.
  cancelAnimationFrame(physicsFrame);physicsFrame=0;
  const focus=active?byId.get(active).topic:$('topic').value===''?null:Number($('topic').value);
  const points=shown.filter(n=>focus===null||n.topic===focus).map(n=>layout.positions.get(n.id));
  if(focus===null)points.push(layout.center,...layout.hubs.values());else points.push(layout.hubs.get(focus));
  const left=Math.min(...points.map(p=>p.x))-130,right=Math.max(...points.map(p=>p.x))+130,top=Math.min(...points.map(p=>p.y))-85,bottom=Math.max(...points.map(p=>p.y))+95;
  const selected=active?layout.positions.get(active):null;
  const target=selected?{x:selected.x,y:selected.y,k:Math.max(.75,Math.min(1.25,width/480,height/440))}:{x:(left+right)/2,y:(top+bottom)/2,k:Math.min((width-28)/(right-left),(height-70)/(bottom-top),1.4)};
  const animate=cameraReady&&(animateNext||cameraFrame!==0)&&!matchMedia('(prefers-reduced-motion: reduce)').matches;animateNext=false;cameraReady=true;cancelAnimationFrame(cameraFrame);cameraFrame=0;
  if(!animate){camera=target;paint();return}
  const start={...camera},t0=performance.now();
  function step(now){if(disposed)return;const progress=Math.min(1,(now-t0)/420);camera=interpolateCamera(start,target,progress);paint();if(progress<1)cameraFrame=requestAnimationFrame(step);else cameraFrame=0}
  cameraFrame=requestAnimationFrame(step);
 }
 function scheduleFit(){cancelAnimationFrame(frame);frame=requestAnimationFrame(fit)}
 function pdf(n){const url=materials.find(m=>m.material_id===n.material)?.document_url;if(!url)return el('small','本机未载入该教材 PDF');const a=el('a','打开教材 · PDF 第 '+n.page+' 页 ↗','pdf');a.href=url+'#page='+n.page;a.target='_blank';a.rel='noopener';return a}
 function showDetail(){
  const d=$('detail');d.replaceChildren();d.hidden=!active;root.querySelector('.explorer').classList.toggle('has-detail',!!active);if(!active)return;
  const n=byId.get(active),c=storyContent[n.id];d.scrollTop=0;
  const close=el('button','收起讲解','detail-close');close.onclick=()=>{animateNext=true;active=null;pinned=null;showDetail();syncViewport();highlight();paint();scheduleFit()};d.append(close,el('div',themes[n.topic]+' · '+n.id,'meta'),el('h2',n.name));
  if(c){
   d.append(el('p',c.question,'story-question'));mountNodeVisual(d,n.id,el,se);d.append(el('h3','这样理解'),el('p',c.idea),el('div',c.example,'story-example'));
   const check=el('details','','story-challenge');check.append(el('summary','想一想 · '+c.check),el('p',c.answer));d.append(check);
   const more=el('details','','story-sources');more.append(el('summary','易错提醒与课外连接'),el('p',c.caution),el('h3',c.extra[0]),el('p',c.extra[1]));d.append(more,el('h3','接着看'));
   for(const [target,reason] of c.next){if(byId.has(target)){const b=el('button',reason+' → '+byId.get(target).name,'story-link');b.onclick=()=>choose(target);d.append(b)}}
  }else d.append(el('p',n.summary));
  const source=el('details','','story-sources');source.append(el('summary','教材、学习要求与学情'),el('p',n.summary),el('p',n.loc),pdf(n));
  for(const id of n.indicators){const k=knowledge.find(v=>v.knowledge_id===id);if(!k)continue;
   if(profile){const s=states.get(id);source.append(el('p',k.name+'：'+(palette[s?.status]||palette.insufficient_evidence)[0]+' · '+(s?.evidence_count||0)+' 条评分证据'));
    const scores=[];for(const scan of training?.scans||[]){if(scan.status!=='reviewed'||scan.student_id!==profile.student_id||scan.node_id!==profile.node_id)continue;const paper=training?.papers?.find(p=>p.id===scan.paper_id);for(const q of paper?.questions||[]){const score=scan.scores?.[q.question_id];if(q.knowledge_id===id&&Number.isFinite(score))scores.push(score)}}
    if(scores.length)source.append(el('p','补充训练：'+scores.length+' 题 · 平均得分 '+Math.round(scores.reduce((a,b)=>a+b,0)/scores.length*100)+'%（独立证据，未覆盖原始诊断）'));
   }
   const b=el('button',k.name+' · 学情与材料','story-link');b.onclick=()=>openKnowledge(id);source.append(b);
  }d.append(source);
  const related=edges.filter(e=>e.source_node_id===active||e.target_node_id===active);
  if(related.length){const section=el('details','','story-sources');section.append(el('summary','正式课程关系 · '+related.length));for(const e of related){const target=e.source_node_id===active?e.target_node_id:e.source_node_id;if(!byId.has(target))continue;const relation=e.relation_type==='prerequisite'?(e.target_node_id===active?'基础知识':'后续应用'):e.relation_type==='related_to'?'相关方法':'易混对照';const b=el('button',relation+' · '+byId.get(target).name+' · '+(e.review_status==='reviewed'?'已核对':'待核验'),'story-link');b.onclick=()=>choose(target);section.append(b)}d.append(section)}
  d.append(el('p','图解与例子为自编教学演示，待教师复核；图中的分支表示类别归属，不表示先修关系。','story-note'));
 }
 function choose(id){if(!byId.has(id))return;stopCamera();animateNext=true;pinned=id;if(!shown.some(n=>n.id===id)){$('query').value='';$('topic').value='';shown=nodes}mode='overview';active=id;render(false)}
 function full(){stopCamera();animateNext=true;$('query').value='';$('topic').value='';active=null;mode='overview';render()}
 function render(clear=true){
  if(clear)active=null;const q=$('query').value.trim().toLowerCase();shown=nodes.filter(n=>($('topic').value===''||String(n.topic)===$('topic').value)&&[n.name,n.id,n.summary,n.loc,...Object.values(storyContent[n.id]||{}).flat(2)].join(' ').toLowerCase().includes(q));
  $('nodata').hidden=!!shown.length;$('overview').hidden=mode!=='overview'||!shown.length;$('list').hidden=mode!=='list'||!shown.length;$('overviewMode').setAttribute('aria-pressed',String(mode==='overview'));$('listMode').setAttribute('aria-pressed',String(mode==='list'));
  motion.hidden=reset.hidden=mode!=='overview';cancelAnimationFrame(physicsFrame);physicsFrame=0;if(mode!=='overview')stopCamera();
  if(mode==='list'){$('rows').replaceChildren();for(const n of shown){const tr=el('tr'),name=el('td'),b=el('button',n.name),loc=el('td',n.loc);b.onclick=()=>choose(n.id);name.append(b);loc.append(el('br'),pdf(n));tr.append(name,el('td',n.summary),loc);$('rows').append(tr)}}else{showDetail();draw();scheduleFit()}
 }
 function stopCamera(){cancelAnimationFrame(frame);cancelAnimationFrame(cameraFrame);cameraFrame=0;animateNext=false}
 function zoom(f){stopCamera();camera.k=Math.max(.15,Math.min(3,camera.k*f));requestPaint()}
 $('query').oninput=$('topic').onchange=()=>render();$('overviewMode').onclick=()=>{mode='overview';render()};$('listMode').onclick=()=>{mode='list';render()};$('home').onclick=full;$('plus').onclick=()=>zoom(1.25);$('minus').onclick=()=>zoom(.8);
 svg.onwheel=e=>{e.preventDefault();zoom(Math.exp(-Math.sign(e.deltaY)*.14))};
 svg.onpointerdown=e=>{if(e.button!==0)return;stopCamera();suppressClick=false;const node=e.target.closest('[data-drag-id]')?.dataset.dragId;gesture={id:e.pointerId,node,start:node?{...points.get(node)}:null,x:e.clientX,y:e.clientY,camera:{...camera},moved:false}};
 svg.onpointermove=e=>{if(!gesture||gesture.id!==e.pointerId)return;const dx=e.clientX-gesture.x,dy=e.clientY-gesture.y;if(!gesture.moved&&Math.hypot(dx,dy)>4){gesture.moved=true;svg.setPointerCapture(e.pointerId);svg.classList.add('dragging')}if(!gesture.moved)return;if(gesture.node){pinned=gesture.node;Object.assign(points.get(gesture.node),{x:gesture.start.x+dx/camera.k,y:gesture.start.y+dy/camera.k});wake()}else{camera.x=gesture.camera.x-dx/camera.k;camera.y=gesture.camera.y-dy/camera.k}requestPaint(!!gesture.node)};
 function end(e){if(gesture?.id!==e.pointerId)return;const movedNode=gesture.moved&&gesture.node;suppressClick=gesture.moved||e.type==='pointercancel';gesture=null;svg.classList.remove('dragging');persist();if(movedNode)wake();setTimeout(()=>suppressClick=false,0)}svg.onpointerup=svg.onpointercancel=end;
 const motion=el('button','动态布局：'+(dynamic?'开':'关'));motion.id='motion';motion.setAttribute('aria-pressed',String(dynamic));motion.onclick=()=>{dynamic=!dynamic;motion.textContent='动态布局：'+(dynamic?'开':'关');motion.setAttribute('aria-pressed',String(dynamic));if(dynamic)wake();else{cancelAnimationFrame(physicsFrame);physicsFrame=0;persist()}};
 const reset=el('button','重置布局');reset.id='resetLayout';reset.onclick=()=>{cancelAnimationFrame(physicsFrame);physicsFrame=0;pinned=null;for(const [id,p] of points)Object.assign(p,homes.get(id));persist();full()};root.querySelector('.tools').append(motion,reset);
 root.querySelector('.map-caption span').textContent='拖动节点，分支弹性跟随 · 拖动空白平移 · 点击打开图解';
 const observer=new ResizeObserver(()=>{const box=svg.getBoundingClientRect();if(box.width&&box.height&&(Math.abs(box.width-width)>.1||Math.abs(box.height-height)>.1))scheduleFit()});observer.observe(svg);render();return()=>{disposed=true;persist();observer.disconnect();stopCamera();cancelAnimationFrame(physicsFrame);cancelAnimationFrame(paintFrame)};
}
