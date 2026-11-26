import {states as statusStyles} from './charts.js';
import {radialLayout,relaxCategory,interpolateCamera,resizeCamera} from './map-layout.mjs';
import {storyContent,mountNodeVisual} from './course-stories.mjs';

export function mountMap(host,{materials,knowledge,curriculum_graph:graph},openKnowledge,profile=null,training=null){
 const nodes=(graph?.nodes||[]).map(n=>({id:n.node_id,name:n.title,topic:n.theme_index,summary:n.summary,loc:n.source_locator,page:n.pdf_page,indicators:n.knowledge_ids,material:n.material_id}));
 if(!nodes.length){host.textContent='本次快照未包含课程图谱，请刷新展示数据。';return()=>{}}
 const themes=['代数式与整式运算','方程与方程组','不等式与不等式组'];
 const colors=['#268a72','#4a83bd','#bc7d42'];
 const states=new Map((profile?.knowledge_states||[]).map(s=>[s.knowledge_id,s]));
 const palette=Object.fromEntries(Object.entries(statusStyles).map(([status,style])=>[status,[style.label,style.color]]));
 const byId=new Map(nodes.map(n=>[n.id,n])),edges=graph.edges||[];
 const root=host.attachShadow({mode:'open'});
 root.innerHTML=`<link rel="stylesheet" href="/knowledge-map.css"><div class="tools" ${host.hasAttribute('workspace')?'hidden':''}><input id="query" type="search" aria-label="查找知识点" placeholder="查知识点、问题或教材章节"><select id="topic" aria-label="知识类别"><option value="">全部类别</option></select><button id="overviewMode" class="mode" aria-pressed="true">知识图谱</button><button id="listMode" class="mode" aria-pressed="false">一览表</button></div><section id="overview" class="canvas"><div class="explorer"><div class="stage"><div class="legend" id="legend" role="group" aria-label="知识类别图例"></div><svg id="atlas" role="group" aria-label="按类别辐射的数学知识图谱"><g id="world"><g id="branches"></g><g id="hubs"></g><g id="dots"></g></g></svg><div class="maptools"><button id="home">查看全图</button><button id="minus" aria-label="缩小">−</button><button id="plus" aria-label="放大">＋</button></div></div><article id="detail" class="story-reader" aria-label="知识点形象化讲解" hidden></article></div></section><div id="nodata" class="none" hidden>没有匹配的知识点，请更换关键词或类别。</div><div id="list" class="tablebox" hidden><table><thead><tr><th>知识点</th><th>学习要求</th><th>教材位置</th></tr></thead><tbody id="rows"></tbody></table></div>`;
 const $=id=>root.getElementById(id),svg=$('atlas'),world=$('world');
 function el(tag,text='',cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e}
 function se(tag,attrs={}){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e}
 function svgText(parent,text,x,y,cls){const t=se('text',{x,y,'text-anchor':'middle',class:cls});t.textContent=text;parent.append(t)}
 function action(group,fn){group.setAttribute('role','button');group.setAttribute('tabindex','0');group.onclick=()=>{if(!suppressClick)fn()};group.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();fn()}}}
 function nodeState(n){const ss=n.indicators.map(id=>states.get(id)).filter(Boolean);return ss.find(s=>['weak','confirmed_weak','likely_weak'].includes(s.status))||ss.find(s=>s.status==='sparse_poor')||ss.find(s=>s.status==='insufficient_evidence')||ss.find(s=>s.status==='unobserved')||ss.find(s=>s.status==='mixed_performance')||ss[0]}
 const layout=radialLayout(nodes);
 const chapterSpeed=(Math.random()<.5?-1:1)*Math.PI*2/(480000+Math.random()*180000);
 const chapterOrbits=new Map([...layout.hubs.keys()].map(topic=>[topic,{time:0,phase:Math.random()*Math.PI*2,period:45000+Math.random()*30000,amplitude:.035+Math.random()*.025,radial:5+Math.random()*5}]));
 const categoryOrbits=new Map([...layout.hubs.keys()].map(topic=>[topic,{speed:(Math.random()<.5?-1:1)*Math.PI*2/(300000+Math.random()*180000)}]));
 const nodeOrbits=new Map(nodes.map(n=>[n.id,{time:0,phase:Math.random()*Math.PI*2,period:18000+Math.random()*24000,amplitude:.012+Math.random()*.018}]));
 const points=new Map([['course',layout.center],...[...layout.hubs].map(([id,p])=>['category-'+id,p]),...layout.positions]);
 const homes=new Map([...points].map(([id,p])=>[id,{...p}]));
 const springs=[...[...layout.hubs.keys()].map(id=>({from:'course',to:'category-'+id})),...nodes.map(n=>({from:'category-'+n.topic,to:n.id}))];
 const segments=[],hubGroups=new Map();
 let drawKey=null,renderPoints=[],lastCamera='',paintFrame=0,geometryDirty=false;
 // ?motion=1 时即使系统关闭动画也按“可动”启动：theme-boot.js 已把 html.kf-force-motion
 // 写好，这里再把同一个标记放到 shadow host 上，供 knowledge-map.css 的 @media 使用
 // （shadow root 里的选择器碰不到 <html>）。
 const forcedMotion=document.documentElement.classList.contains('kf-force-motion');
 if(forcedMotion)host.classList.add('force-motion');
 const motionOK=window.kfMotionAllowed?window.kfMotionAllowed():!matchMedia('(prefers-reduced-motion: reduce)').matches;
 let physicsFrame=0,energy=0,pinned=null,dynamic=motionOK;
 let orbitFrame=0,orbitLast=0,orbitHover=false;
 let cameraFrame=0,cameraReady=false,animateNext=false;
 let mode='overview',active=null,shown=nodes,groups=new Map(),camera={x:0,y:0,k:1},width=900,height=650,gesture=null,suppressClick=false,frame=0,disposed=false;
 themes.forEach((name,i)=>{$('topic').add(new Option(name,String(i)));if(!profile){const item=el('span',name),dot=el('i');dot.style.background=colors[i];item.prepend(dot);$('legend').append(item)}});
 if(profile){
  $('legend').setAttribute('aria-label','个人掌握程度图例');
  $('legend').classList.add('personal-legend');
  $('legend').append(el('strong','节点颜色 · 掌握程度'));
  const entries=el('div','','status-legend-items');
  const keys=['mastered','sparse_good','sparse_poor','weak','insufficient_evidence','unobserved','not_applicable'];
  if(nodes.some(n=>nodeState(n)?.status==='mixed_performance'))keys.push('mixed');
  keys.forEach(key=>{const style=statusStyles[key],item=el('span',style.label),dot=el('i');dot.style.background=style.color;item.prepend(dot);entries.append(item)});
  $('legend').append(entries,el('small','连线与外圈表示章节类别'));
 }
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
   g.append(se('rect',{x:-120,y:-34,width:240,height:68,rx:22}));svgText(g,themes[topic],0,-2,'category-title');svgText(g,category.length+' 个知识点',0,22,'category-count');action(g,()=>{stopCamera();animateNext=true;pinned=null;$('topic').value=String(topic);render()});$('hubs').append(g);
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
  for(const item of renderPoints){const p=item.point;if(p.x===item.x&&p.y===item.y)continue;item.element.setAttribute('transform',`translate(${p.x} ${p.y})`);item.x=p.x;item.y=p.y;const n=byId.get(item.element.dataset.id);if(n){const hub=layout.hubs.get(n.topic),labels=item.element.querySelectorAll('.node-label');labels.forEach((label,i)=>label.setAttribute('y',String((p.y<hub.y-20?-37-(labels.length-1)*25:49)+i*25)))}}
  for(const segment of segments){const {a,b,path}=segment;const d=`M ${a.x} ${a.y} Q ${a.x} ${b.y} ${b.x} ${b.y}`;if(d!==segment.d){path.setAttribute('d',d);segment.d=d}}
 }
 function requestPaint(geometry=false){geometryDirty=geometryDirty||geometry;if(paintFrame)return;paintFrame=requestAnimationFrame(()=>{paintFrame=0;if(disposed)return;const dirty=geometryDirty;geometryDirty=false;paint(dirty)})}
 // Slow, varied category orbits with bounded individual drift to preserve spacing.
 // Random parameters stay fixed for this mount; never add per-frame jitter.
 function orbit(now){
  if(disposed)return;
  orbitFrame=requestAnimationFrame(orbit);
  if(!orbitLast){orbitLast=now;return}
  const elapsed=now-orbitLast;if(elapsed<33)return;orbitLast=now;
  if(!dynamic||document.hidden||mode!=='overview'||active||gesture||orbitHover||physicsFrame||cameraFrame||frame||svg.querySelector(':focus'))return;
  const dt=Math.min(elapsed,70);
  // Keep chapters spaced around the course while adding gentle, independent drift.
  // Move every child with its hub; pause this outer orbit in filtered views.
  if(shown.length===nodes.length){
   for(const [topic,hub] of layout.hubs){
    const motion=chapterOrbits.get(topic),before=motion.phase+motion.time/motion.period*Math.PI*2;
    motion.time+=dt;
    const after=motion.phase+motion.time/motion.period*Math.PI*2;
    const angle=chapterSpeed*dt+motion.amplitude*(Math.sin(after)-Math.sin(before));
    const dx=hub.x-layout.center.x,dy=hub.y-layout.center.y,radius=Math.hypot(dx,dy);
    const radial=motion.radial*(Math.sin(after*.73)-Math.sin(before*.73));
    const scale=radius>1?Math.max(1,radius+radial)/radius:1,c=Math.cos(angle),s=Math.sin(angle);
    const x=layout.center.x+(dx*c-dy*s)*scale,y=layout.center.y+(dx*s+dy*c)*scale;
    for(const n of nodes){if(n.topic!==topic)continue;const p=layout.positions.get(n.id);p.x+=x-hub.x;p.y+=y-hub.y}
    hub.x=x;hub.y=y;
   }
  }
  for(const n of shown){
   const motion=nodeOrbits.get(n.id),before=motion.phase+motion.time/motion.period*Math.PI*2;
   motion.time+=dt;
   const after=motion.phase+motion.time/motion.period*Math.PI*2;
   const angle=categoryOrbits.get(n.topic).speed*dt+motion.amplitude*(Math.sin(after)-Math.sin(before)),c=Math.cos(angle),s=Math.sin(angle);
   const p=layout.positions.get(n.id),hub=layout.hubs.get(n.topic),dx=p.x-hub.x,dy=p.y-hub.y;p.x=hub.x+dx*c-dy*s;p.y=hub.y+dx*s+dy*c;
  }
  requestPaint(true);
 }
 svg.addEventListener('pointerover',e=>{orbitHover=!!e.target.closest('[data-drag-id]')});
 svg.addEventListener('pointerout',e=>{orbitHover=!!e.relatedTarget?.closest?.('[data-drag-id]')});
 svg.addEventListener('pointerleave',()=>{orbitHover=false});
 function wake(){
  // 拖动模块/知识点时，挂在上面的节点要跟着被弹簧带走。这是对直接操作的反馈，
  // 不是装饰性动画，所以不再受 dynamic（系统“减少动效”）约束：即使系统关闭动画，
  // 拖拽联动照样生效；被关掉的只是空闲漂移（orbit）与环境光。
  if(disposed||mode!=='overview'||!shown.length)return;energy=1;if(physicsFrame)return;
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
   if((energy>.025&&quiet<3)||gesture?.node)physicsFrame=requestAnimationFrame(tick);else{physicsFrame=0}
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
  if(!active){for(const [topic,hub] of layout.hubs){const visible=shown.filter(n=>n.topic===topic);if(!visible.length)continue;const radius=Math.max(...visible.map(n=>{const p=layout.positions.get(n.id);return Math.hypot(p.x-hub.x,p.y-hub.y)}));points.push({x:hub.x-radius,y:hub.y-radius},{x:hub.x+radius,y:hub.y+radius})}}
  if(!active&&shown.length===nodes.length){
   const radius=Math.max(...nodes.map(n=>{const hub=layout.hubs.get(n.topic),p=layout.positions.get(n.id);return Math.hypot(hub.x-layout.center.x,hub.y-layout.center.y)+Math.hypot(p.x-hub.x,p.y-hub.y)+20}));
   points.push({x:layout.center.x-radius,y:layout.center.y-radius},{x:layout.center.x+radius,y:layout.center.y+radius});
  }
  const left=Math.min(...points.map(p=>p.x))-130,right=Math.max(...points.map(p=>p.x))+130,top=Math.min(...points.map(p=>p.y))-85,bottom=Math.max(...points.map(p=>p.y))+95;
  const selected=active?layout.positions.get(active):null;
  const target=selected?{x:selected.x,y:selected.y,k:Math.max(.75,Math.min(1.25,width/480,height/440))}:{x:(left+right)/2,y:(top+bottom)/2,k:Math.min((width-28)/(right-left),(height-70)/(bottom-top),1.4)};
  if(!active&&shown.length===nodes.length)target.k*=1.12;
  const animate=cameraReady&&(animateNext||cameraFrame!==0)&&motionOK;animateNext=false;cameraReady=true;cancelAnimationFrame(cameraFrame);cameraFrame=0;
  if(!animate){camera=target;paint();return}
  const start={...camera},t0=performance.now();
  function step(now){if(disposed)return;const progress=Math.min(1,(now-t0)/420);camera=interpolateCamera(start,target,progress);paint();if(progress<1)cameraFrame=requestAnimationFrame(step);else cameraFrame=0}
  cameraFrame=requestAnimationFrame(step);
 }
 function scheduleFit(){cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{frame=0;fit()})}
 function pdf(n){const url=materials.find(m=>m.material_id===n.material)?.document_url;if(!url)return el('small','本机未载入该教材 PDF');const a=el('a','打开教材 · PDF 第 '+n.page+' 页 ↗','pdf');a.href=url+'#page='+n.page;a.target='_blank';a.rel='noopener';return a}
 let disposeVisual=()=>{};
 function showDetail(){
  disposeVisual();disposeVisual=()=>{};
  const d=$('detail');d.replaceChildren();d.hidden=!active;root.querySelector('.explorer').classList.toggle('has-detail',!!active);if(!active)return;
  const n=byId.get(active),c=storyContent[n.id];d.scrollTop=0;
  const close=el('button','收起讲解','detail-close');close.onclick=()=>{animateNext=true;active=null;pinned=null;showDetail();syncViewport();highlight();paint();scheduleFit()};d.append(close,el('div',themes[n.topic]+' · '+n.id,'meta'),el('h2',n.name));
  if(c){
   d.append(el('p',c.question,'story-question'));disposeVisual=mountNodeVisual(d,n.id,el,se)||(()=>{});d.append(el('h3','要点'),el('p',c.idea),el('div',c.example,'story-example'));
   if(c.life)d.append(el('h3','联系生活'),el('p',c.life));
   d.append(el('h3','相关知识'));
   for(const [target] of c.next){if(byId.has(target)){const b=el('button',byId.get(target).name,'story-link');b.onclick=()=>choose(target);d.append(b)}}
  }else d.append(el('p',n.summary));
  const source=el('details','','story-sources');source.append(el('summary','教材与学情'),pdf(n));
  for(const id of n.indicators){const k=knowledge.find(v=>v.knowledge_id===id);if(!k)continue;
   if(profile){const s=states.get(id);source.append(el('p',k.name+'：'+(palette[s?.status]||palette.insufficient_evidence)[0]+' · '+(s?.evidence_count||0)+' 条评分证据'));
    const scores=[];for(const scan of training?.scans||[]){if(scan.status!=='reviewed'||scan.student_id!==profile.student_id||scan.node_id!==profile.node_id)continue;const paper=training?.papers?.find(p=>p.id===scan.paper_id);for(const q of paper?.questions||[]){const score=scan.scores?.[q.question_id];if(q.knowledge_id===id&&Number.isFinite(score))scores.push(score)}}
    if(scores.length)source.append(el('p','补充训练：'+scores.length+' 题 · 平均得分 '+Math.round(scores.reduce((a,b)=>a+b,0)/scores.length*100)+'%'));
   }
   const b=el('button',k.name+' · 学情与材料','story-link');b.onclick=()=>openKnowledge(id);source.append(b);
  }d.append(source);
 }
 function choose(id){if(!byId.has(id))return;stopCamera();animateNext=true;pinned=id;if(!shown.some(n=>n.id===id)){$('query').value='';$('topic').value='';shown=nodes}mode='overview';active=id;render(false)}
 function full(){stopCamera();animateNext=true;pinned=null;$('query').value='';$('topic').value='';active=null;mode='overview';render()}
 function render(clear=true){
  if(clear)active=null;const q=$('query').value.trim().toLowerCase();shown=nodes.filter(n=>($('topic').value===''||String(n.topic)===$('topic').value)&&[n.name,n.id,n.summary,n.loc,...Object.values(storyContent[n.id]||{}).flat(2)].join(' ').toLowerCase().includes(q));
  $('nodata').hidden=!!shown.length;$('overview').hidden=mode!=='overview'||!shown.length;$('list').hidden=mode!=='list'||!shown.length;$('overviewMode').setAttribute('aria-pressed',String(mode==='overview'));$('listMode').setAttribute('aria-pressed',String(mode==='list'));
  motion.hidden=reset.hidden=mode!=='overview';cancelAnimationFrame(physicsFrame);physicsFrame=0;if(mode!=='overview')stopCamera();
  if(mode==='list'){$('rows').replaceChildren();for(const n of shown){const tr=el('tr'),name=el('td'),b=el('button',n.name),loc=el('td',n.loc);b.onclick=()=>choose(n.id);name.append(b);loc.append(el('br'),pdf(n));tr.append(name,el('td',n.summary),loc);$('rows').append(tr)}}else{showDetail();draw();scheduleFit()}
 }
 function stopCamera(){cancelAnimationFrame(frame);frame=0;cancelAnimationFrame(cameraFrame);cameraFrame=0;animateNext=false}
 function zoom(f){stopCamera();camera.k=Math.max(.15,Math.min(3,camera.k*f));requestPaint()}
 $('query').oninput=$('topic').onchange=()=>render();$('overviewMode').onclick=()=>{mode='overview';render()};$('listMode').onclick=()=>{mode='list';render()};$('home').onclick=full;$('plus').onclick=()=>zoom(1.25);$('minus').onclick=()=>zoom(.8);
 svg.onwheel=e=>{e.preventDefault();zoom(Math.exp(-Math.sign(e.deltaY)*.14))};
 svg.onpointerdown=e=>{if(e.button!==0)return;stopCamera();suppressClick=false;const node=e.target.closest('[data-drag-id]')?.dataset.dragId;gesture={id:e.pointerId,node,start:node?{...points.get(node)}:null,x:e.clientX,y:e.clientY,camera:{...camera},moved:false}};
 svg.onpointermove=e=>{if(!gesture||gesture.id!==e.pointerId)return;const dx=e.clientX-gesture.x,dy=e.clientY-gesture.y;if(!gesture.moved&&Math.hypot(dx,dy)>4){gesture.moved=true;svg.setPointerCapture(e.pointerId);svg.classList.add('dragging')}if(!gesture.moved)return;if(gesture.node){pinned=gesture.node;Object.assign(points.get(gesture.node),{x:gesture.start.x+dx/camera.k,y:gesture.start.y+dy/camera.k});wake()}else{camera.x=gesture.camera.x-dx/camera.k;camera.y=gesture.camera.y-dy/camera.k}requestPaint(!!gesture.node)};
 function end(e){if(gesture?.id!==e.pointerId)return;const movedNode=gesture.moved&&gesture.node,blankClick=!gesture.moved&&!gesture.node&&e.type==='pointerup';suppressClick=gesture.moved||e.type==='pointercancel';gesture=null;svg.classList.remove('dragging');if(blankClick)full();else if(movedNode)wake();setTimeout(()=>suppressClick=false,0)}svg.onpointerup=svg.onpointercancel=end;
 const motion=el('button','动态布局：'+(dynamic?'开':'关'));motion.id='motion';motion.setAttribute('aria-pressed',String(dynamic));motion.onclick=()=>{dynamic=!dynamic;motion.textContent='动态布局：'+(dynamic?'开':'关');motion.setAttribute('aria-pressed',String(dynamic));if(dynamic)wake();else{cancelAnimationFrame(physicsFrame);physicsFrame=0}};
 const reset=el('button','重置布局');reset.id='resetLayout';reset.onclick=()=>{cancelAnimationFrame(physicsFrame);physicsFrame=0;pinned=null;for(const [id,p] of points)Object.assign(p,homes.get(id));full()};root.querySelector('.tools').append(motion,reset);
 const observer=new ResizeObserver(()=>{const box=svg.getBoundingClientRect();if(box.width&&box.height&&(Math.abs(box.width-width)>.1||Math.abs(box.height-height)>.1))scheduleFit()});observer.observe(svg);render();
 // 学习卡「定位图谱」用 host.dataset.focus 指定要聚焦的节点或其观察指标（PR #38）。
 if(host.dataset.focus){const target=nodes.find(n=>n.id===host.dataset.focus||n.indicators.includes(host.dataset.focus));if(target)choose(target.id)}
 orbitFrame=requestAnimationFrame(orbit);return()=>{disposed=true;cancelAnimationFrame(orbitFrame);disposeVisual();observer.disconnect();stopCamera();cancelAnimationFrame(physicsFrame);cancelAnimationFrame(paintFrame)};
}
