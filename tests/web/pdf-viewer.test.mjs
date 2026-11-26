import test from 'node:test';
import assert from 'node:assert/strict';
import {loadPDFPages} from '../../src/knowflow/web/static/pdf-viewer.js';

async function preview(t,papers,answers=false,ok=true){
 const calls=[];
 t.mock.method(globalThis,'fetch',async url=>{calls.push(url);return {ok,json:async()=>({papers,error:ok?undefined:'访问被拒绝'})}});
 const prior=globalThis.document;
 globalThis.document={fonts:{ready:Promise.resolve()}};
 const container={innerHTML:''};
 try{const meta=await loadPDFPages(container,'paper-1',answers);return {html:container.innerHTML,meta,calls}}
 finally{if(prior===undefined)delete globalThis.document;else globalThis.document=prior}
}
const paper={id:'paper-1',title:'<img src=x onerror=alert(1)>',status:'draft',questions:[{question_id:'Q-1',knowledge_id:'K-01',prompt:'<script>unsafe</script> & 2',answer:'SECRET_ANSWER',explanation:'SECRET_EXPLANATION'}]};
test('question preview escapes content and excludes answers without calling PDF endpoints',async t=>{
 const result=await preview(t,[paper]);
 assert.deepEqual(result.calls,['/api/training']);
 assert.ok(result.html.includes('&lt;script&gt;unsafe&lt;/script&gt; &amp; 2'));
 assert.ok(result.html.includes('&lt;img src=x onerror=alert(1)&gt;'));
 assert.ok(!result.html.includes('<script>'));
 assert.ok(!result.html.includes('SECRET_ANSWER'));
 assert.ok(!result.html.includes('SECRET_EXPLANATION'));
 assert.ok(result.html.includes('作答区域'));
});
test('authorized answer preview includes answers and no writing area',async t=>{
 const result=await preview(t,[paper],true);
 assert.ok(result.html.includes('SECRET_ANSWER'));
 assert.ok(result.html.includes('SECRET_EXPLANATION'));
 assert.ok(!result.html.includes('作答区域'));
});
test('student-filtered payload cannot render an answer sheet',async t=>{
 const {answer,explanation,...question}=paper.questions[0];
 await assert.rejects(preview(t,[{...paper,questions:[question]}],true),/无权查看参考答案/);
});
test('missing papers and failed requests show errors instead of a sheet',async t=>{
 await assert.rejects(preview(t,[]),/不存在或无权访问/);
 await assert.rejects(preview(t,[],false,false),/访问被拒绝/);
});
