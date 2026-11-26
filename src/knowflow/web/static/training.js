import {openPDF} from './pdf-viewer.js';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(action,payload){
 const r=await fetch('/api/training'+(action?'/'+action:''),payload?{method:'POST',headers:{'Content-Type':'application/json','X-KnowFlow-Training':'1'},body:JSON.stringify(payload)}:{});
 const data=await r.json();if(!r.ok)throw Error(data.error||'请求失败');return data;
}
export async function openTraining({student,node,teacher,students,onClose}){
 const dialog=document.createElement('dialog');dialog.className='training-workspace';
 document.body.append(dialog);dialog.showModal();
 dialog.addEventListener('close',()=>{dialog.remove();onClose?.()});
 let data;
 let activeSection='试卷管理';
 async function load(){data=await api();draw()}
 function draw(){
  dialog.innerHTML=`<header class="training-header"><div><span class="training-eyebrow">教学工具 · ${esc(node)}</span><h2>变式训练</h2><p>生成试卷、核对发布，再打印与扫描回录。</p></div><button id="tr-close" class="button light">关闭</button></header><div id="tr-message" role="status"></div>
  ${teacher?`<h3 data-training-section>生成试卷</h3><form id="tr-generate" class="panel"><label>范围 <select name="mode"><option value="personal">个人针对性训练</option><option value="unified">统一知识点训练</option></select></label> <label>学生 <select name="student_id">${students.map(s=>`<option ${s.student_id===student?'selected':''}>${esc(s.student_id)}</option>`).join('')}</select></label> <label>题数 <input name="count" type="number" value="12" min="1" max="12" style="width:70px"></label> <button class="button" value="api">通过 API 生成</button> <button class="button light" value="demo">生成全体 Demo 卷</button><p>基于 ${esc(node)} 学情摘要出题。<br>API 生成需配置接口；Demo 面向全体学生，无需配置。</p></form>`:''}
  <h3 data-training-section>我的试卷 <span class="training-count">${data.papers.length} 份</span></h3><div>${data.papers.slice().reverse().map(p=>`<details class="panel training-paper"><summary><span class="paper-card-title">${esc(p.student_id?p.student_id+' · 针对性训练':'全体学生 · 统一训练')}</span><span class="paper-status ${p.status==='approved'?'published':''}">${p.status==='approved'?'已发布':'待复核'}</span><span class="paper-card-meta">${esc(p.node_id)} · ${p.questions.length} 道题 · ${p.generator==='local_demo'?'模拟 Demo':'API 生成'} · ${esc(p.id.slice(0,8))}</span></summary>${p.note?`<p>${esc(p.note)}</p>`:''}${p.basis?`<details><summary>查看全体学情出题依据</summary>${p.basis.map(b=>`<p>${esc(b.name)}：${esc(b.focus_label||'旧口径：薄弱／表现混合')} ${b.focus_count} 人，安排 ${b.question_count} 题</p>`).join('')}</details>`:''}<div class="paper-questions">${p.questions.map(q=>`<article><p><b>${esc(q.question_id)} · ${esc(q.knowledge_id)}</b><br>${esc(q.prompt)}</p>${teacher?`<details><summary>参考答案与解析</summary><p>${esc(q.answer)}</p><p>${esc(q.explanation)}</p></details>`:''}</article>`).join('')}</div><p><button class="button" data-pdf="${p.id}">预览题卷</button> ${teacher?`<button class="button light" data-pdf="${p.id}" data-answers="1">答案与解析</button>`:''}</p>${teacher?`<button class="button light danger" data-delete="${p.id}">删除试卷</button>`:''}${teacher&&p.status==='draft'?`<button class="button" data-approve="${p.id}">已核对题目答案，发布</button>`:''}</details>`).join('')||'<p>还没有试卷。</p>'}</div>
  <h3 data-training-section>上传已作答扫描件</h3><form id="tr-upload" class="panel"><label>试卷 <select name="paper_id" required>${data.papers.filter(p=>p.status==='approved').map(p=>`<option value="${p.id}">${esc(p.student_id||'统一')} · ${esc(p.id.slice(0,8))}</option>`).join('')}</select></label> <label>学生 <select name="student_id">${students.map(s=>`<option ${s.student_id===student?'selected':''}>${esc(s.student_id)}</option>`).join('')}</select></label><p><input name="file" type="file" accept="image/png,image/jpeg,application/pdf" capture="environment" required></p><button class="button">上传扫描件</button><p>支持拍照、PNG/JPEG 或扫描 PDF，最大 12 MB。请核对纸面试卷编号与所选试卷一致。原件仅保存在本机。</p></form>
  <h3 data-training-section>扫描与复核记录</h3>${data.scans.slice().reverse().map(s=>{const p=data.papers.find(p=>p.id===s.paper_id);return `<details class="panel" style="margin:12px 0"><summary>${esc(s.student_id)} · ${esc(s.paper_id.slice(0,8))} · ${s.status==='reviewed'?'已入库':'待复核'}</summary><p>扫描预览 · 共 ${s.pages} 页</p>${Array.from({length:s.pages},(_,i)=>`<a href="/api/training/scan/${s.id}?page=${i}" target="_blank"><img src="/api/training/scan/${s.id}?page=${i}" style="max-width:100%;max-height:650px;object-fit:contain" alt="扫描第 ${i+1} 页"></a>`).join('')}${teacher&&s.status==='pending'?`<form data-review="${s.id}">${(p?.questions||[]).map(q=>`<p><label>${esc(q.question_id)} · ${esc(q.prompt)}<br>得分比例 <input type="number" name="${q.question_id}" min="0" max="1" step="0.01" required></label><br>参考答案：${esc(q.answer)}</p>`).join('')}<button class="button">确认逐题评分并入库</button></form>`:s.status==='reviewed'?`<p>得分：${Object.entries(s.scores).map(([k,v])=>`${esc(k)} ${Math.round(v*100)}%`).join(' · ')}</p>`:''}</details>`}).join('')||'<p>暂无扫描记录。</p>'}`;
  const headings=[...dialog.querySelectorAll('[data-training-section]')];
  const nav=document.createElement('nav');nav.className='tabs module-tabs';nav.setAttribute('aria-label','训练模块');
  const body=document.createElement('div');body.className='training-body';
  const rawSections=headings.map(h=>{const panel=document.createElement('section');let next=h.nextSibling;panel.append(h);while(next&&!headings.includes(next)){const n=next.nextSibling;panel.append(next);next=n}body.append(panel);return panel});
  const sections=[],labels=['试卷管理','扫描与复核'];
  const manage=document.createElement('section');manage.className='training-columns';
  const review=document.createElement('section');review.className='training-columns';
  if(teacher)manage.append(rawSections[0],rawSections[1]);else manage.append(rawSections[0]);
  review.append(...rawSections.slice(teacher?2:1));body.replaceChildren(manage,review);sections.push(manage,review);
  dialog.append(nav,body);dialog.classList.add('training-workspace');
  function select(label){activeSection=label;sections.forEach((p,i)=>{p.hidden=labels[i]!==label;nav.children[i].classList.toggle('active',!p.hidden);nav.children[i].setAttribute('aria-pressed',String(!p.hidden))})}
  labels.forEach(label=>{const b=document.createElement('button');b.textContent=label;b.onclick=()=>select(label);nav.append(b)});select(activeSection);
  dialog.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>{if(confirm('删除这份试卷？试卷及关联扫描记录将从列表移除，本地历史记录保留。'))work(b,()=>api('delete',{paper_id:b.dataset.delete}))});
  dialog.querySelectorAll('.paper-questions').forEach(box=>{
    const questions=[...box.children];let index=0;
    const pager=document.createElement('div');pager.className='table-pager';
    const prev=document.createElement('button'),next=document.createElement('button'),label=document.createElement('span');
    prev.textContent='上一题';next.textContent='下一题';prev.className=next.className='button light';pager.append(prev,label,next);box.before(pager);
    function show(){questions.forEach((q,i)=>q.hidden=i!==index);label.textContent=`第 ${index+1} / ${questions.length} 题`;prev.disabled=index===0;next.disabled=index===questions.length-1}
    prev.onclick=()=>{index--;show()};next.onclick=()=>{index++;show()};show();
    const paper=box.closest('details');const actions=document.createElement('div');actions.className='paper-actions';
    paper.querySelectorAll('[data-pdf],[data-delete],[data-approve]').forEach(b=>actions.append(b));paper.querySelector('summary').after(actions);
  });
  dialog.querySelector('#tr-close').onclick=()=>dialog.close();
  const mode=dialog.querySelector('[name="mode"]');
  if(mode){const studentSelect=dialog.querySelector('#tr-generate [name="student_id"]');const syncMode=()=>{studentSelect.disabled=mode.value==='unified'};mode.onchange=syncMode;syncMode()}
  dialog.querySelectorAll('[data-pdf]').forEach(b=>b.onclick=()=>openPDF(b.dataset.pdf,b.dataset.answers==='1'));
  async function work(button,fn){button.disabled=true;const msg=dialog.querySelector('#tr-message');msg.textContent='正在处理，请稍候…';try{await fn();await load();dialog.querySelector('#tr-message').textContent='已保存。'}catch(e){msg.textContent=e.message;button.disabled=false}}
  dialog.querySelector('#tr-generate')?.addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);work(e.submitter,()=>api('generate',{mode:f.get('mode'),student_id:f.get('student_id'),count:Number(f.get('count')),node_id:node,generator:e.submitter.value==='demo'?'demo':'api',...(e.submitter.value==='demo'?{mode:'unified'}:{})}))});
  dialog.querySelectorAll('[data-approve]').forEach(b=>b.onclick=()=>work(b,()=>api('approve',{paper_id:b.dataset.approve})));
  dialog.querySelector('#tr-upload').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target),file=f.get('file');work(e.submitter,async()=>{if(file.size>12*1024*1024)throw Error('文件超过 12 MB。');const encoded=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('文件读取失败'));r.readAsDataURL(file)});await api('scan',{paper_id:f.get('paper_id'),student_id:f.get('student_id'),data:encoded})})};
  dialog.querySelectorAll('[data-review]').forEach(f=>f.onsubmit=e=>{e.preventDefault();work(e.submitter,()=>api('review',{scan_id:f.dataset.review,scores:Object.fromEntries([...new FormData(f)].map(([k,v])=>[k,Number(v)]))}))});
 }
 try{await load()}catch(e){dialog.textContent=e.message;const close=document.createElement('button');close.textContent='关闭';close.onclick=()=>dialog.close();dialog.append(close)}
}
