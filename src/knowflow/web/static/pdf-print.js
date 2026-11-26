import {loadPDFPages} from './pdf-viewer.js';
const params=new URLSearchParams(location.search),paper=params.get('paper'),answers=params.get('answers')==='1';
const status=document.querySelector('#status'),button=document.querySelector('#print');
button.onclick=()=>window.print();
try{
 const meta=await loadPDFPages(document.querySelector('#pages'),paper,answers);
 status.textContent='A4 试卷 · 在打印窗口选择“另存为 PDF”，建议关闭页眉页脚';
 document.title=meta.title;button.disabled=false;
}catch(error){status.textContent=error.message;status.setAttribute('role','alert')}
