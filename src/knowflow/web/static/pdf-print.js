import {loadPDFPages} from './pdf-viewer.js';
const params=new URLSearchParams(location.search),paper=params.get('paper'),answers=params.get('answers')==='1';
const status=document.querySelector('#status'),button=document.querySelector('#print');
document.querySelector('#download').href='/api/training/pdf/'+encodeURIComponent(paper||'')+'?answers='+(answers?'1':'0');
button.onclick=()=>window.print();
try{
 const meta=await loadPDFPages(document.querySelector('#pages'),paper,answers);
 status.textContent=meta.title+' · '+meta.pages+' 页 · 建议 A4、关闭页眉页脚';
 document.title=meta.title;button.disabled=false;
}catch(error){status.textContent=error.message}
