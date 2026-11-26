const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Both previews use permission-filtered JSON, never Python PDF endpoints.
export async function loadPDFPages(container,paperId,answers=false){
 const response=await fetch('/api/training');
 const data=await response.json();
 if(!response.ok)throw Error(data.error||'试卷加载失败，请重试。');
 const paper=data.papers.find(p=>p.id===paperId);
 if(!paper)throw Error('试卷不存在或无权访问。');
 if(answers&&paper.questions.some(q=>!Object.hasOwn(q,'answer')))throw Error('无权查看参考答案。');
 const title=(paper.title||'变式训练')+(answers?' · 答案与解析':' · 题卷');
 container.innerHTML=`<article class="print-paper"><div class="paper-heading"><p class="paper-kicker">KNOWFLOW · 变式训练</p><h1>${esc(title)}</h1><p>${paper.status==='approved'?'已由教师核对发布':'待教师核题草稿'}${paper.generator==='local_demo'?' · 本地模拟 Demo':''} · ${paper.questions.length} 题</p><p>学生：${esc(paper.student_id||'____________')}　日期：____________</p><p class="paper-id">试卷编号：${esc(paper.id)}</p></div>${paper.questions.map((q,i)=>`<section class="print-question"><h2>第 ${i+1} 题 <span>${esc(q.question_id)} · ${esc(q.knowledge_id)}</span></h2><p class="question-text">${esc(q.prompt)}</p>${answers?`<div class="answer-block"><strong>参考答案</strong><p>${esc(q.answer)}</p><strong>解析</strong><p>${esc(q.explanation)}</p></div>`:'<div class="writing-space" aria-label="作答区域"></div>'}</section>`).join('')}<footer class="paper-footer">${esc(paper.id)} · ${answers?'答案与解析':'请核对试卷编号后扫描回录'}</footer></article>`;
 await document.fonts.ready;
 return {title};
}
export async function openPDF(paperId,answers=false){
 const dialog=document.createElement('dialog');dialog.className='pdf-dialog';
 dialog.setAttribute('aria-label','试卷预览与输出');
 dialog.innerHTML='<header class="pdf-toolbar"><h2>试卷预览</h2><a class="button" data-print target="_blank" rel="noopener">打印 / 保存 PDF</a><button class="button light" data-close>关闭预览</button></header><div class="paper-preview-frame" role="region" aria-label="试卷预览内容"></div>';
 dialog.querySelector('[data-print]').href='/training-print?paper='+encodeURIComponent(paperId)+'&answers='+(answers?'1':'0');
 const shadow=dialog.querySelector('.paper-preview-frame').attachShadow({mode:'open'});
 const style=document.createElement('link');style.rel='stylesheet';style.href='/pdf-print.css';
 const pages=document.createElement('main');pages.textContent='正在加载试卷…';shadow.append(style,pages);
 dialog.querySelector('[data-close]').onclick=()=>dialog.close();
 dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
 try{const meta=await loadPDFPages(pages,paperId,answers);dialog.querySelector('h2').textContent=meta.title}catch(error){pages.textContent=error.message}
}
