import {esc} from './charts.js';

export async function learningRequest(action, context, values = {}, signal) {
  const response = await fetch('/api/learning/' + action, {
    method: 'POST', headers: {'Content-Type':'application/json','X-KnowFlow-Learning':'1'},
    body: JSON.stringify({student_id:context.student, node_id:context.node, ...values}), signal
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作未完成，请重试。');
  return data;
}

export function mountLearning(host, context) {
  const controller = new AbortController();
  let data, lesson = null, tab = 'cards', phase = 'overview', index = 0, page = 0;
  let busy = false, busyText = '', error = '', selected = null, disposed = false;
  const drafts = new Map();
  const key = `knowflow.lesson.${context.student}.${context.node}`;
  const request = (action, values) => learningRequest(action, context, values, controller.signal);
  const activeQuestion = () => selected || (phase === 'probe' ? lesson?.probe_questions[index] : phase === 'bank' ? lesson?.bank_questions[index] : lesson?.ai_questions[index]);
  const tasks = () => phase === 'probe' ? lesson.probe_questions : phase === 'bank' ? lesson.bank_questions : lesson.ai_questions;
  const pageSize = () => tab !== 'cards' ? (innerHeight < 900 ? 4 : 6) : innerWidth < 700 ? 1 : innerWidth < 1150 ? (innerHeight >= 950 ? 4 : 2) : (innerHeight >= 1050 ? 6 : 3);
  const title = () => data?.names[lesson?.knowledge_id] || '学习卡';
  const button = (action, label, kind='light', extra='') => `<button type="button" class="button ${kind}" data-learn="${action}" ${extra} ${busy?'disabled':''}>${label}</button>`;
  const bookmark = q => button('favorite', q.favorite ? '★ 已收藏' : '☆ 收藏', 'light learn-save', `aria-pressed="${q.favorite}" aria-label="${q.favorite?'取消收藏':'收藏题目'}"`);
  function remember() { try {lesson ? sessionStorage.setItem(key,lesson.knowledge_id) : sessionStorage.removeItem(key);} catch {} }
  function rememberDraft() {
    const q=activeQuestion(), field=host.querySelector('[name="learning-answer"]:checked') || host.querySelector('textarea[name="learning-answer"]');
    if(q && field) drafts.set(q.question_id,field.value);
  }
  async function refresh() {
    const response=await fetch('/api/learning?'+new URLSearchParams({student_id:context.student,node_id:context.node}),{signal:controller.signal});
    const value=await response.json();
    if(!response.ok) throw new Error(value.error||'学习空间加载失败。');
    data=value;
  }
  async function run(work, caption='正在保存…') {
    if (busy) return;
    rememberDraft(); busy=true; busyText=caption; error=''; render();
    try { await work(); }
    catch(e) {if(e.name!=='AbortError') error=e.message||'操作失败，请重试。';}
    finally {busy=false;if(!disposed)render();}
  }
  function label(card) {
    if(card.mode==='probe')return ['待补测','probe'];
    if(card.status==='needs_practice')return ['补测：掌握不足','weak'];
    if(card.status==='ready')return ['补测通过','ready'];
    if(['confirmed_mastered','likely_mastered'].includes(card.status))return ['巩固进阶','ready'];
    return ['重点巩固','weak'];
  }
  function tabs() {
    return `<nav class="learn-tabs" aria-label="学习空间分区">${[['cards','学习卡',data.cards.length],['mistakes','错题集',data.mistakes.length],['favorites','收藏夹',data.favorites.length]].map(([id,text,count])=>button('tab',`${text}<span>${count}</span>`,tab===id?'primary':'light',`data-tab="${id}" aria-current="${tab===id?'page':'false'}"`)).join('')}</nav>`;
  }
  function pager(length) {
    const max=Math.max(1,Math.ceil(length/pageSize()));page=Math.min(page,max-1);
    return max>1?`<div class="learn-pagination">${button('prev-page','上一页','light',page===0?'disabled':'')}<span>${page+1} / ${max}</span>${button('next-page','下一页','light',page===max-1?'disabled':'')}</div>`:'';
  }
  function cards() {
    const navigation=pager(data.cards.length);
    return `<div class="learn-section-heading"><div><h2>从一个知识点开始</h2><p>先补齐观察，再把薄弱处练扎实。</p></div><span class="learn-count">${data.cards.filter(c=>c.completed).length} / ${data.cards.length} 已完成</span></div>
    <div class="learn-card-grid">${data.cards.slice(page*pageSize(),page*pageSize()+pageSize()).map(c=>{
      const [text,tone]=label(c);
      return `<article class="learn-card ${tone}"><div class="learn-card-meta"><span class="learn-tag ${tone}">${esc(text)}</span><span>${esc(c.knowledge_id)}</span></div><h3>${esc(c.name)}</h3><p>${c.mode==='probe'?'两道基础题，确认从哪里开始。':c.completed?'已完成本轮学习，可以继续练习。':'知识概要 · 题库练习 · AI 变式'}</p><div class="learn-card-bottom"><span>${c.probe_result?`本次答对 ${c.probe_result.correct}/2 题`:c.mode==='probe'?'约 2 道题':c.read?'已完成阅读':'按自己的节奏'}</span>${button('start',c.completed?'继续练习':c.started?'继续学习':c.mode==='probe'?'开始补测':'进入学习','primary',`data-kid="${esc(c.knowledge_id)}"`)}</div></article>`;
    }).join('')}</div>${navigation}`;
  }
  function collection() {
    const rows=data[tab], navigation=pager(rows.length);
    return `<div class="learn-section-heading"><div><h2>${tab==='mistakes'?'把错题变成会做的题':'留住值得再练的题'}</h2><p>${tab==='mistakes'?'包含历史失分题与新练习错题，订正后保留记录。':'收藏保存在你的账号下，随时回来重做。'}</p></div></div>
      ${rows.length?`<div class="learn-library">${rows.slice(page*pageSize(),page*pageSize()+pageSize()).map(q=>`<button class="learn-library-row" data-learn="open-question" data-qid="${esc(q.question_id)}" ${busy?'disabled':''}><span class="learn-library-icon" aria-hidden="true">${tab==='favorites'?'☆':q.resolved?'✓':'·'}</span><span class="learn-library-copy"><strong>${esc(q.prompt)}</strong><small>${esc(data.names[q.knowledge_id]||q.knowledge_id)} · ${esc(q.source_label)}${q.origin==='history'?` · 原得分 ${q.score}/${q.max_score}`:''}</small></span><span class="learn-tag ${q.resolved?'ready':'neutral'}">${tab==='favorites'?'重做':q.resolved?'已订正':'待巩固'}</span></button>`).join('')}</div>`:`<div class="learn-empty"><span aria-hidden="true">${tab==='favorites'?'☆':'✓'}</span><h3>${tab==='favorites'?'还没有收藏':'暂时没有错题'}</h3><p>${tab==='favorites'?'题目右上角的收藏按钮，会把题目保存在这里。':'完成练习后，需要回看的题目会出现在这里。'}</p>${button('back','去学习','primary')}</div>`}${navigation}`;
  }
  function stepper() {
    const stage=phase==='overview'?0:phase==='bank'?1:phase==='ai'?2:3;
    return `<ol class="learn-steps" aria-label="学习步骤">${['理解知识','题库练习','AI 变式'].map((name,i)=>`<li class="${i===stage?'current':i<stage?'done':''}" ${i===stage?'aria-current="step"':''}><span>${i<stage?'✓':i+1}</span><button type="button" data-learn="stage" data-stage="${['overview','bank','ai'][i]}" ${busy || (i>0&&!lesson.read) || (i===2&&lesson.bank_questions.some(q=>!q.attempt))?'disabled':''}>${name}</button></li>`).join('')}</ol>`;
  }
  function overview() {
    const nodes=context.knowledge.curriculum_graph?.nodes||[];
    const adjacent=new Set();
    for(const edge of lesson.overview.edges) {adjacent.add(edge.source_node_id);adjacent.add(edge.target_node_id);}
    const neighbors=nodes.filter(n=>adjacent.has(n.node_id) && !n.knowledge_ids.includes(lesson.knowledge_id)).slice(0,3);
    return `<div class="learn-reading"><div class="learn-reading-main"><span class="learn-kicker">知识概要</span><h2>${esc(title())}</h2><div class="learn-concepts">${lesson.overview.sections.map(s=>`<section class="learn-concept"><h3>${esc(s.title)}</h3><p>${esc(s.text)}</p></section>`).join('')}</div></div><aside class="learn-map-card"><span class="learn-kicker">关联知识</span><h3>关联知识地图</h3><p>定位当前节点，查看上下游关系。</p><div class="learn-map-focus">${esc(title())}</div><div class="learn-neighbors">${neighbors.map(n=>button('map',esc(n.title),'light',`data-focus="${esc(n.node_id)}"`)).join('')}</div>${button('map','打开知识图谱','light',`data-focus="${esc(lesson.overview.focus)}"`)}<details class="learn-textbooks"><summary>查看教材章节</summary>${lesson.overview.sections.map(s=>s.document_url?`<a href="${esc(s.document_url)}#page=${Number(s.pdf_page)||1}" target="_blank" rel="noopener">${esc(s.title)}<small>${esc(s.source_locator||'对应教材章节')}</small></a>`:'').join('')||'<p>本机尚未载入教材。</p>'}</details></aside></div><div class="learn-footer"><span>读完概要，再用练习检验理解。</span>${button('read','已阅读，开始练习','primary')}</div>`;
  }
  function feedback(q) {
    const a=q.attempt, solution=a?{answer:a.reference_answer,explanation:a.explanation}:q.solution;
    return `${a?`<div class="learn-feedback ${a.correct===true?'correct':a.correct===false?'incorrect':'pending'}" role="status"><strong>${a.correct===true?'回答正确':a.correct===false?'这道题还需要巩固':'这份答案需要进一步核对'}</strong><p>${a.correct===true?(a.independent?'继续挑战下一道题。':'本次重做已完成，原作答记录仍保留。'):a.correct===false?'已加入错题集。查看解析后，可以重新尝试。':'暂未可靠自动判分，不计为答错；可对照解析或请教师确认。'}</p></div>`:''}
      ${solution?`<details class="learn-solution"><summary>查看答案与解析</summary><p><strong>参考答案：</strong>${esc(solution.answer)}</p><p>${esc(solution.explanation||'请结合教材中的解题方法核对。')}</p></details>`:''}`;
  }
  function questionView(q, library=false) {
    if(!q)return `<div class="learn-empty"><h3>当前没有可用题目</h3>${button('next','下一步','primary')}</div>`;
    const count=library?'重做练习':`${phase==='probe'?'补测':phase==='bank'?'题库练习':'AI 变式'} · ${index+1} / ${tasks().length}`;
    const answer=drafts.get(q.question_id)??q.attempt?.answer??'';
    return `<article class="learn-question"><div class="learn-question-top"><span class="learn-kicker">${count}</span>${bookmark(q)}</div><span class="learn-tag neutral">${esc(q.source_label)}${q.source==='ai'?' · 已自动复核':''}</span><h2>${esc(q.prompt)}</h2><form id="learning-answer-form"><fieldset ${q.attempt||busy?'disabled':''}><legend class="sr-only">填写答案</legend>${q.options?.length?`<div class="learn-options">${q.options.map((o,i)=>{const letter='ABCD'[i];return `<label class="learn-option"><input type="radio" name="learning-answer" value="${letter}" ${answer===letter?'checked':''} required><span class="learn-option-letter">${letter}</span><span>${esc(o)}</span></label>`;}).join('')}</div>`:`<label class="learn-answer-label" for="learning-answer">你的答案</label><textarea id="learning-answer" name="learning-answer" rows="2" maxlength="1000" placeholder="输入最终答案，如 x=3、2x+1 或 x≤5。" required>${esc(answer)}</textarea>`}</fieldset>${!q.attempt?`<div class="learn-answer-actions"><button class="button primary" type="submit" ${busy?'disabled':''}>提交答案</button><span>${q.source==='ai'?'如对题目有疑问，可向教师反馈。':q.options?.length?'选择一个答案。':'无法可靠判分的答案会保留待核对。'}</span></div>`:''}</form>${feedback(q)}${q.attempt?`<div class="learn-footer"><div>${button('retry','重新作答')}${!library&&index>0?button('previous','上一题'):''}</div>${library?button('library-back','返回列表','primary'):button('next',index+1<tasks().length?'下一题':phase==='probe'?'查看补测结果':phase==='bank'?'进入 AI 变式':'完成本轮','primary')}</div>`:''}</article>`;
  }
  function probeResult() {
    const p=lesson.probe_result;
    return `<div class="learn-result"><span class="learn-kicker">本次补测</span><div class="learn-result-number">${p.correct}<span> / 2</span></div><h2>${p.status==='needs_practice'?'先把这个知识点练扎实':'基础检查通过'}</h2><p>${p.status==='needs_practice'?'已为你准备对应学习卡，从知识概要开始，再做针对性练习。':'可以进入学习卡，巩固方法并挑战新的变式。'}</p><small>两道题反映本次表现，不代表长期掌握结论。</small>${button('overview','打开学习卡','primary')}</div>`;
  }
  function aiIntro() {
    return `<div class="learn-empty learn-ai"><span aria-hidden="true">✧</span><span class="learn-kicker">AI 变式练习</span><h2>换一种问法，看看是否真正理解</h2><p>围绕「${esc(title())}」生成两道新题，出题后自动复核答案。</p>${button('generate',busy?'正在生成并复核…':'生成两道练习','primary')}<small>${data.ai_ready?'按需调用模型，生成的题目会保存。':'需要教师先在设置中连接 AI。'}</small></div>`;
  }
  function complete() {
    const questions=[...lesson.bank_questions,...lesson.ai_questions], correct=questions.filter(q=>q.attempt?.correct===true).length;
    return `<div class="learn-result"><span class="learn-result-check" aria-hidden="true">✓</span><h2>完成这一轮，继续向前</h2><p>已阅读知识概要，练习 ${questions.filter(q=>q.attempt).length} 道，其中 ${correct} 道当前作答正确。</p><p class="learn-result-note">需要巩固的题目已收进错题集，收藏的题目也可以随时重做。</p><div class="learn-result-actions">${button('back','回到学习卡')}${button('generate','再生成两道','primary')}</div></div>`;
  }
  function render() {
    if(disposed)return;
    if(!data){host.innerHTML=`<div class="learn-loading" role="status">${error?esc(error):'正在读取学习空间…'}${error?button('reload','重新加载'):''}</div>`;return;}
    const hasLesson=!!lesson;
    host.innerHTML=`<section class="learning-workspace ${hasLesson||selected?'in-lesson':''}"><div class="learn-page-heading"><div><span class="learn-kicker">MY LEARNING</span><h1>我的学习空间</h1></div><span class="learn-account">${esc(context.student)} · ${esc(context.node)}</span></div>${tabs()}
      ${error?`<div class="learn-error" role="alert">${esc(error)}</div>`:''}${busy?`<div class="learn-busy" role="status"><i></i>${esc(busyText)}</div>`:''}
      ${selected?`<div class="learn-back">${button('library-back','返回列表')}</div>${questionView(selected,true)}`:hasLesson?`<div class="learn-lesson-heading">${button('back','返回学习卡')}<span>${esc(title())}</span></div><div class="learn-book ${phase==='probe'||phase==='probe-result'?'probe-book':''}">${!['probe','probe-result'].includes(phase)?stepper():''}<div class="learn-book-page">${phase==='overview'?overview():phase==='probe-result'?probeResult():phase==='complete'?complete():phase==='ai'&&!lesson.ai_questions.length?aiIntro():questionView(activeQuestion())}</div></div>`:tab==='cards'?cards():collection()}
    </section>`;
  }
  async function open(kid) {
    lesson=await request('start',{knowledge_id:kid});selected=null;tab='cards';remember();
    if(lesson.probe_questions.length&&!lesson.probe_result){phase='probe';index=Math.max(0,lesson.probe_questions.findIndex(q=>!q.attempt));}
    else if(!lesson.read){phase='overview';index=0;}
    else if(lesson.bank_questions.some(q=>!q.attempt)){phase='bank';index=lesson.bank_questions.findIndex(q=>!q.attempt);}
    else if(lesson.ai_questions.some(q=>!q.attempt)){phase='ai';index=lesson.ai_questions.findIndex(q=>!q.attempt);}
    else {phase=lesson.ai_questions.length?'complete':'ai';index=0;}
  }
  async function onClick(event) {
    const b=event.target.closest('[data-learn]');if(!b||busy)return;
    const action=b.dataset.learn;
    rememberDraft(); error='';
    if(action==='map'){context.onMap(b.dataset.focus);return;}
    if(action==='tab'){tab=b.dataset.tab;lesson=null;selected=null;page=0;remember();render();return;}
    if(action==='back'){lesson=null;selected=null;tab='cards';remember();await run(refresh,'正在更新学习卡…');return;}
    if(action==='library-back'){selected=null;await run(refresh,'正在更新列表…');return;}
    if(action==='prev-page'||action==='next-page'){page+=action==='prev-page'?-1:1;render();return;}
    if(action==='start'){await run(()=>open(b.dataset.kid),'正在准备学习卡…');return;}
    if(action==='reload'){await run(refresh,'正在重新加载…');return;}
    if(action==='open-question'){await run(async()=>{selected=await request('question',{question_id:b.dataset.qid});selected.attempt=null;drafts.delete(selected.question_id);},'正在打开题目…');return;}
    if(action==='favorite'){const q=activeQuestion();await run(async()=>{const r=await request('favorite',{question_id:q.question_id,favorite:!q.favorite});q.favorite=r.favorite;await refresh();},'正在保存收藏…');return;}
    if(action==='read'){await run(async()=>{lesson=await request('read',{knowledge_id:lesson.knowledge_id});phase='bank';index=0;},'正在保存阅读进度…');return;}
    if(action==='stage'){phase=b.dataset.stage;index=0;if(phase==='bank')index=Math.max(0,lesson.bank_questions.findIndex(q=>!q.attempt));if(phase==='ai')index=Math.max(0,lesson.ai_questions.findIndex(q=>!q.attempt));render();return;}
    if(action==='overview'){phase='overview';render();return;}
    if(action==='retry'){const q=activeQuestion();q.solution={answer:q.attempt.reference_answer,explanation:q.attempt.explanation};q.attempt=null;drafts.delete(q.question_id);render();return;}
    if(action==='previous'){index=Math.max(0,index-1);render();return;}
    if(action==='next'){
      if(index+1<tasks().length)index++;
      else {phase=phase==='probe'?'probe-result':phase==='bank'?'ai':'complete';index=0;}
      render();return;
    }
    if(action==='generate'){
      await run(async()=>{const count=lesson.ai_questions.length;lesson=await request('generate',{knowledge_id:lesson.knowledge_id});phase='ai';index=count;await refresh();},'AI 正在出题并独立复核答案，请稍候…');return;
    }
  }
  async function onSubmit(event) {
    if(event.target.id!=='learning-answer-form')return;
    event.preventDefault();if(busy)return;
    const q=activeQuestion(), answer=new FormData(event.target).get('learning-answer');
    await run(async()=>{
      const result=await request('answer',{question_id:q.question_id,answer,request_id:crypto.randomUUID()});
      q.attempt=result;
      if(lesson)lesson.probe_result=result.probe_result||lesson.probe_result;
      await refresh();
    },'正在核对答案…');
  }
  host.addEventListener('click',onClick);host.addEventListener('submit',onSubmit);
  render();
  run(async()=>{await refresh();let saved;try{saved=sessionStorage.getItem(key);}catch{}if(saved&&data.cards.some(c=>c.knowledge_id===saved))await open(saved);},'正在读取学习进度…');
  return ()=>{disposed=true;controller.abort();host.removeEventListener('click',onClick);host.removeEventListener('submit',onSubmit);};
}
