export async function loadPDFPages(container, paperId, answers=false) {
  const query='?answers='+(answers?'1':'0');
  const response=await fetch('/api/training/pdf-preview/'+encodeURIComponent(paperId)+query);
  const metadata=await response.json();
  if(!response.ok)throw Error(metadata.error||'PDF 生成失败');
  container.replaceChildren();
  const loads=[];
  for(let i=0;i<metadata.pages;i++){
    const page=document.createElement('img');page.alt=`第 ${i+1} 页，共 ${metadata.pages} 页`;
    loads.push(new Promise((resolve,reject)=>{page.onload=resolve;page.onerror=()=>reject(Error('PDF 页面加载失败，请重试。'))}));
    page.src='/api/training/pdf-page/'+encodeURIComponent(paperId)+query+'&page='+i;
    container.append(page);
  }
  await Promise.all(loads);return metadata;
}

export async function openPDF(paperId, answers=false) {
  const dialog=document.createElement('dialog');dialog.className='pdf-dialog';
  dialog.setAttribute('aria-label','PDF 预览与输出');
  dialog.innerHTML='<header class="pdf-toolbar"><h2>正在生成 PDF…</h2><a class="button light" data-download>下载 PDF</a><a class="button" data-print target="_blank" rel="noopener">打印</a><button class="button light" data-close>关闭预览</button></header><div class="pdf-pages" role="region" aria-label="PDF 分页预览"><p role="status">正在排版并加载页面…</p></div>';
  const query='?answers='+(answers?'1':'0');
  dialog.querySelector('[data-download]').href='/api/training/pdf/'+encodeURIComponent(paperId)+query;
  dialog.querySelector('[data-print]').href='/training-print?paper='+encodeURIComponent(paperId)+'&answers='+(answers?'1':'0');
  dialog.querySelector('[data-close]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
  try{
    const metadata=await loadPDFPages(dialog.querySelector('.pdf-pages'),paperId,answers);
    dialog.querySelector('h2').textContent=metadata.title+' · '+metadata.pages+' 页';
  }catch(error){dialog.querySelector('.pdf-pages').textContent=error.message;dialog.querySelector('h2').textContent='PDF 预览失败'}
}
