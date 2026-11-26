// Stable visual identities keep each mathematical object continuous across steps.
const green='#23836d',blue='#517ead',orange='#bb783b';
const definitions={
 'C-001':[['每本 3 元','先用 n 表示本数。'],['单价乘数量','n 本的书本费是 3n 元。'],['加上固定费用','再加 5 元运费，得到 3n + 5。']],
 'C-002':[['找到字母的位置','计算 x = −2 时，3x + 5 的值。'],['把数放进字母的位置','用 (−2) 替换 x。'],['先乘法','3 × (−2) = −6。'],['再加法','−6 + 5 = −1。']],
 'C-003':[['分开每一项','3x²、−2x、7，符号跟着项一起移动。'],['分开系数和字母','数字因数是系数，7 是常数项。'],['观察指数','3x² 的次数是 2，−2x 的次数是 1，常数项次数是 0。']],
 'C-004':[['两组同类项','3x 是三个 x，2x 是两个 x。'],['把同类项放在一起','五个 x 移到同一组。'],['合成一个框','3x + 2x = (3 + 2)x。'],['系数相加','字母 x 保持不变，得到 5x。']],
 'C-005':[['括号内是一组','一组含 x 和 3。'],['整组复制一次','乘 2，就是取两组 x + 3。'],['按同类项归组','两个 x 一组，两个 3 一组。'],['分别合并','2(x + 3) = 2x + 6。']],
 'C-007':[['两组奇数','3 个点与 5 个点，各剩一个单点。'],['先把已有的点配对','每组先两两配对。'],['两个单点组成一对','原来的 8 个点重新组成 4 对，和是偶数。'],['用字母说明规律','相邻奇数的和为 (2n + 1) + (2n + 3) = 4(n + 1)。']],
 'C-008':[['把候选数移到字母处','检验 n = 4 是否满足 3n + 5 = 17。'],['代入计算','3 × 4 + 5 = 12 + 5。'],['比较两边','左边也是 17，所以 n = 4 是解。']],
 'C-009':[['两边相等','3x + 5 = 17，把 17 拆成 12 + 5。'],['两边同时拿走 5','相同的 5 一起移走，留下 3x = 12。'],['两边各分成三份','三个 x 对应三个 4。'],['取出对应的一份','每一份都是 x = 4。']],
 'C-010':[['展开左边','2(x + 3) − x = x + 3 + x + 3 − x。'],['同类项合并','x + x − x = x，3 + 3 = 6。'],['两边同时减 6','x + 6 = 10，两边一起拿走 6。'],['留下未知数','x = 4。']],
 'C-011':[['从总价找数量关系','书本费加运费等于付款总额。'],['把数量换成式子','每本 3 元，n 本的书本费是 3n。'],['两边减去运费','3n + 5 = 17，两边减 5 得 3n = 12。'],['按单价分组','12 ÷ 3 = 4，因此买了 4 本。']],
 'C-012':[['先满足一个条件','x + y = 10 的数对有很多组。'],['再检查另一个条件','(7, 3) 满足第一式，但 2 × 7 + 3 × 3 = 23。'],['同一数对同时成立','(4, 6) 让两式分别得到 10 和 26，是方程组的解。']],
 'C-013':[['先用 y 表示 x','x + y = 10，所以 x = 10 − y。'],['移到另一方程的 x 处','把 10 − y 放进 2x + 3y = 26。'],['展开并合并','20 − 2y + 3y = 26，整理为 20 + y = 26。'],['求出并回代','y = 6，x = 10 − 6 = 4。']],
 'C-014':[['对应项上下对齐','2x + 3y = 26，2x + 2y = 20。'],['每一列分别相减','(2x − 2x) + (3y − 2y) = 26 − 20。'],['相同项抵消','x 项抵消，留下 y = 6。'],['回代得到另一个未知数','x + 6 = 10，所以 x = 4。']],
 'C-015':[['先按张数归组','两类票共 10 张：x + y = 10。'],['再按各自票价计算','2 元票收入 2x，3 元票收入 3y，共 26 元。'],['让两个条件同时成立','x = 4，y = 6：张数为 4 + 6，收入为 8 + 18。']],
 'C-016':[['先看一个解','x = 2 时，x + 2 = 4 ≤ 5。'],['再找更多解','1、0、−1 也满足条件，3 恰好取到边界。'],['连成全部范围','全部解为 x ≤ 3，向左一直延伸。']],
 'C-018':[['两边同时减 5','3x + 5 ≤ 17。'],['留下 3x ≤ 12','两边各减去 5，大小关系不变。'],['两边除以正数 3','x ≤ 4，不等号方向保持不变。'],['把解集放到数轴上','4 处实心点，向左延伸。']],
 'C-019':[['先看方向','x < 4：4 左边的数符合条件。'],['再看是否包含端点','x ≤ 4：把空心点填实，加入 4。'],['换成大于','x > 4：端点空心，范围转到右边。']],
 'C-021':[['预算分成两部分','16 元中先扣除 5 元固定费用。'],['剩下的钱可以买几份','11 元，每份 3 元，3n ≤ 11。'],['只取整份','3 份花 9 元，4 份花 12 元，超过剩余预算。'],['回到总费用核对','3 份共 14 元，4 份共 17 元，所以最多买 3 份。']]
};
const semanticVisuals=Object.fromEntries(Object.entries(definitions).map(([id,steps])=>[id,{kind:'semantic',steps}]));
export function drawSemanticScene(svg,id,s,se){
 const add=(tag,key,attrs={},value)=>{const e=se(tag,{'data-motion-key':key,...attrs});if(value!==undefined)e.textContent=value;svg.append(e);return e};
 const text=(key,x,y,value,color=green,size=18,opacity=1)=>add('text',key,{x,y,fill:color,'font-size':size,'text-anchor':'middle',opacity},value);
 const tile=(key,x,y,value,color=green,w=90,h=42,opacity=1)=>{add('rect',key+'-box',{x,y,width:w,height:h,rx:9,fill:color,'fill-opacity':.1,stroke:color,'stroke-width':2,opacity});text(key+'-label',x+w/2,y+h/2+6,value,color,value.length>14?13:value.length>10?15:18,opacity)};
 const line=(key,x1,y1,x2,y2,color=green,opacity=1)=>add('line',key,{x1,y1,x2,y2,stroke:color,'stroke-width':3,opacity});
 const dot=(key,x,y,color=green,r=8,opacity=1,open=false)=>add('circle',key,{cx:x,cy:y,r,fill:open?'var(--surface,white)':color,stroke:color,'stroke-width':2,opacity});
 const equation=(a,b,sign='=')=>{tile('left',20,64,a,green,164,52);text('sign',200,98,sign);tile('right',218,64,b,blue,164,52)};
 const footer=v=>text('footer',200,205,v,green,18);
 if(id==='C-001'||id==='C-002'){
  const sub=id==='C-002';
  tile('input',sub?(s?135:20):20,sub?(s?65:10):65,sub?'−2':'n',green,64);
  tile('multiply',sub?20:115,65,sub?'3 ×':'× 3',blue,80);
  tile('add',220,65,'+ 5',orange,70);
  tile('result',sub?115:310,s>=2?130:65,sub?(s>=3?'−1':s>=2?'−6':'x'):(s>=2?'3n + 5':s?'3n':'?'),green,sub?170:84,42,sub?(s>=2?1:0):1);
  if(sub)footer(['3x + 5','3 × (−2) + 5','−6 + 5','−1'][s]);else footer(['n 本，每本 3 元','书本费：3n','总费用：3n + 5'][s]);
 }else if(id==='C-003'){
  ['3','−2','7'].forEach((n,i)=>{tile('co'+i,30+i*125,s?50:75,n,i===2?blue:orange,48);tile('var'+i,78+i*125,s?110:75,['x²','x',''][i],green,48,42,i===2?0:1);text('degree'+i,65+i*125,176,s===2?['次数 2','次数 1','次数 0'][i]:s?['系数 3','系数 −2','常数 7'][i]:'',blue,16)});footer(s===2?'最高次数为 2':'3x² − 2x + 7');
 }else if(id==='C-004'){
  for(let i=0;i<5;i++){const x=s===0?(i<3?24+i*55:236+(i-3)*55):s===1?65+i*54:105;tile('x'+i,x,s<2?78:72,s>=2&&i===0?(s===2?'(3 + 2)x':'5x'):'x',green,s>=2?190:48,52,s>=2&&i?0:1)}
  text('a',95,40,s===0?'3x':'');text('b',290,40,s===0?'2x':'');footer(s<2?'3 个 x + 2 个 x':s===2?'只合并系数，保留 x':'5x');
 }else if(id==='C-005'){
  ['x','3','x','3'].forEach((v,i)=>{const letter=i%2===0;const x=s<2?20+i*95:s===2?(letter?80:250):(letter?65:245);const y=s<2?80:s===2?45+Math.floor(i/2)*70:80;tile('term'+i,x,y,s===3&&i<2?(letter?'2x':'6'):v,letter?green:blue,s===3?100:70,44,(s===0&&i>1)||(s===3&&i>1)?0:1)});footer(s===0?'2 × (x + 3)':s<3?'(x + 3) + (x + 3)':'2x + 6');
 }else if(id==='C-007'){
  for(let i=0;i<8;i++){let x=i<3?60+i*30:60+(i-3)*30,y=i<3?55:115;if(s>=1){const order=[0,1,6,2,3,4,5,7][i],pair=Math.floor(order/2);x=52+pair*90+(order%2)*24;y=95;if(s===1&&(i===2||i===7)){x=i===2?150:330;y=155}}dot('point'+i,x,y,i<3?green:orange)}footer(s===3?'(2n + 1) + (2n + 3) = 4(n + 1)':s===2?'8 个点组成 4 对':'3 + 5');
 }else if(id==='C-008'){
  equation(s===0?'3n + 5':s===1?'3 × 4 + 5':'17','17');tile('candidate',s?85:30,s?130:10,'n = 4',orange,110);footer(s===2?'17 = 17，检验通过':'把同一个数代入 n');
 }else if(id==='C-009'){
  text('eq',200,104,'=');
  for(let i=0;i<3;i++){tile('x'+i,s<2?28:25+i*50,s<2?65:65,s<2?'3x':'x',green,s<2?105:44,48,(s<2&&i>0)||(s===3&&i>0)?0:1);tile('v'+i,s<2?225:225+i*50,65,s<2?'12':'4',blue,s<2?80:44,48,(s<2&&i>0)||(s===3&&i>0)?0:1)}
  tile('fiveL',138,s?155:65,'+ 5',orange,50,48,s?0:1);tile('fiveR',315,s?155:65,'+ 5',orange,60,48,s?0:1);footer(['3x + 5 = 12 + 5','两边同时减 5','两边同时分成 3 份','x = 4'][s]);
 }else if(id==='C-010'||id==='C-011'){
  const model=id==='C-011';const left=model?['书本费 + 运费','3n + 5','3n','n']:['x + 3 + x + 3 − x','x + 6','x','x'];
  equation(left[s],s>=2?(model?'12':'4'):(model?'17':'10'));
  tile('feeL',40,s>=2?154:125,model?'+ 5':s?'+ 6':'',orange,110,40,0);
  text('operation',300,150,s===2?(model?'− 5':'− 6'):s===3&&model?'÷ 3':'',orange);
  if(model&&s===3){svg.querySelector('[data-motion-key="right-label"]').textContent='4'}
  footer(model?['书本费 + 运费 = 总价','3n + 5 = 17','3n = 12','n = 4 本'][s]:['先展开括号','x + 6 = 10','两边同时减 6','x = 4'][s]);
 }else if(id==='C-012'){
  tile('candidate',s===0?20:130,10,s===1?'(7, 3)':'(4, 6)',orange,140);
  tile('first',25,75,s===0?'x + y = 10':s===1?'7 + 3 = 10':'4 + 6 = 10',green,350);
  tile('second',25,135,s===0?'2x + 3y = 26':s===1?'14 + 9 = 23 ≠ 26':'8 + 18 = 26',s===1?orange:blue,350);
  footer(s===2?'同一数对，同时满足两式':'两个条件都要检查');
 }else if(id==='C-013'){
  tile('replacement',s===0?30:65,s===0?10:72,s===3?'x = 4':s===2?'20':'10 − y',green,105);
  text('coefficient',40,99,s<2?'2 ×':'');text('tail',265,99,s<2?'+ 3y = 26':s===2?'+ y = 26':'y = 6',blue);
  text('source',200,170,s===0?'x = 10 − y':s===1?'2(10 − y) + 3y = 26':s===2?'20 − 2y + 3y = 26':'x = 10 − 6 = 4');footer(s===3?'x = 4，y = 6':'用等价表达替换 x');
 }else if(id==='C-014'){
  const top=s===0?['2x','3y','26']:s===1?['2x − 2x','3y − 2y','26 − 20']:s===2?['0','y','6']:['x','6','10'];
  for(let i=0;i<3;i++){tile('top'+i,20+i*130,s?80:40,top[i],i===0?green:i===1?blue:orange,100,48,s===2&&i===0?0:1);tile('bottom'+i,20+i*130,s?80:115,['2x','2y','20'][i],i===0?green:i===1?blue:orange,100,48,s?0:1)}
  text('plus',135,s?112:72,s===2?'':'+');text('equals',265,s?112:72,'=');footer(['上下两式，对应项对齐','整条等式逐项相减','y = 6','x + 6 = 10 → x = 4'][s]);
 }else if(id==='C-015'){
  tile('ticketA',30,35,s===2?'4 张 × 2 元':'x 张 × 2 元',green,150);tile('ticketB',220,35,s===2?'6 张 × 3 元':'y 张 × 3 元',blue,150);
  tile('sum',45,110,s===0?'x + y = 10':s===1?'2x + 3y = 26':'4 + 6 = 10',green,310);text('verify',200,180,s===2?'2 × 4 + 3 × 6 = 26':'',blue);footer(s===0?'数量相加':s===1?'各自乘单价，再相加':'两个条件同时成立');
 }else if(['C-016','C-018','C-019'].includes(id)){
  const x=n=>40+(n+2)*36,b=id==='C-016'?3:4;
  const show=id!=='C-018'||s===3;
  line('axis',25,130,380,130,blue,show?1:0);
  for(let n=-2;n<=7;n++){text('tick'+n,x(n),160,String(n),blue,13,show?1:0)}
  const right=id==='C-019'&&s===2,range=id==='C-016'?s===2:show;
  line('range',right?x(b):25,130,right?380:x(b),130,green,range?1:0);
  dot('end',x(b),130,green,7,show&&(id!=='C-016'||s>0)?1:0,id==='C-019'&&s!==1);
  for(let i=0;i<5;i++)dot('sample'+i,x(2-i),130,orange,6,id==='C-016'&&(s===1||s===0&&i===0)?1:0);
  text('direction',right?375:30,119,right?'→':'←',green,22,range?1:0);
  text('formula',200,55,id==='C-018'?['3x + 5 ≤ 17','3x ≤ 12','x ≤ 4','x ≤ 4'][s]:id==='C-019'?['x < 4','x ≤ 4','x > 4'][s]:s===0?'2 + 2 ≤ 5':'x ≤ 3');
  if(id==='C-018'){tile('opLeft',65,s?90:82,s===0?'− 5':s===1?'÷ 3':'',orange,85,38,s<2?1:0);tile('opRight',250,s?90:82,s===0?'− 5':s===1?'÷ 3':'',orange,85,38,s<2?1:0)}
  footer(id==='C-019'?(s===1?'填实端点，包含 4':s===2?'换到右侧，不含 4':'左侧，不含 4'):id==='C-016'?'从一个解到全部解':'乘除正数，方向不变');
 }else if(id==='C-021'){
  tile('budget',25,25,s===0?'预算 16 元':'可用 11 元',blue,170);tile('fee',235,s?0:25,'固定费 5 元',orange,140,42,s?0:1);
  for(let i=0;i<4;i++)tile('item'+i,25+i*92,100,'3 元',i===3?orange:green,80,45,s>=2||s===1&&i<3?1:0);
  text('warning',200,177,s>=2?'3 份：9 元 ≤ 11；4 份：12 元 > 11':'16 − 5 = 11',green,17);footer(s===3?'总费用：14 元可买；17 元超预算':'最多取 3 个整份');
 }
}

// Authored exploration layer. IDs continue to resolve to the official graph;
// narrative links never enter diagnostic prerequisites or mastery calculations.
export const storyPaths=[
 {title:'表达规律',question:'许多个具体例子，能否用一句数学语言说清？',ids:['C-001','C-002','C-003','C-004','C-005','C-006','C-007'],bridge:'表达式描述关系；给出一个目标，就产生了方程。'},
 {title:'寻找未知',question:'知道结果，怎样倒推隐藏的数量？',ids:['C-008','C-009','C-010','C-011'],bridge:'一个条件不够时，让多个条件共同确定答案。'},
 {title:'联立条件',question:'两条线索，怎样合成一个确定的答案？',ids:['C-012','C-013','C-014','C-015'],bridge:'条件也可以限定范围，由“是多少”走向“有哪些可能”。'},
 {title:'选择范围',question:'所有限制同时成立时，还剩下哪些选择？',ids:['C-016','C-017','C-018','C-019','C-020','C-021'],bridge:'回到真实问题：表达条件、求出范围，再检验选择。'}
];
const authoredNodes=[
 ['C-001','用一个式子描述变化','买的数量一直变，怎样只写一次总价？','用字母表示数量，再按数量关系列式。','每本 3 元，运费 5 元，买 n 本共需 3n + 5 元。','3n 是随数量变化的部分，5 是固定费用；这里 n 是正整数。','买 4 本需要多少元？','3 × 4 + 5 = 17 元。', [['C-002','给字母一个具体值'],['C-008','反过来问：费用已知怎么办？']],['函数的第一眼','给定一本数，就得到一个费用；这种输入与输出的对应，将在函数中系统研究。']],
 ['C-002','让符号落到具体数值','同一个表达式，换一个输入会怎样？','把字母换成给定的数，按顺序计算；代入负数时加括号。','x = −2 时，3x + 5 = 3 × (−2) + 5 = −1。','负数代入先加括号；−x² 与 (−x)² 通常不同。','当 x = −2 时，−x² 是多少？','−x² = −4；先乘方再取相反数。',[['C-008','用代入验证一个答案'],['C-007','从几个数走向一般规律']],['程序里的变量','表达式也像一段小程序：输入改变，输出随规则改变。试几个输入能发现错误，但不能代替一般证明。']],
 ['C-003','读懂式子的组成','式子里的哪些部分决定能否合并？','项包含前面的符号；系数是数字因数，单项式次数是字母指数之和。','−4xy² 的系数为 −4，次数为 1 + 2 = 3。','项要连同前面的符号一起读；多项式次数不是各项次数相加。','−4xy² 的系数与次数分别是什么？','系数 −4，次数 1 + 2 = 3。',[['C-004','相同结构才能合并']],['按结构分类','把项按字母结构分类，就像整理同规格的零件。分类标准比表面数字更重要。']],
 ['C-004','同一种量，合在一起','为什么 3x + 2x 能变成 5x，而 3x + 2 不能？','同类项的系数相加，字母和指数保持不变。','3x + 2x = 5x；2ab − 5ab = −3ab。','数值恰好相等不代表是同类项；判断要看结构。','2ab 与 −5ba 能合并吗？','能。乘法交换律说明 ab = ba，结果为 −3ab。',[['C-006','组合化简工具'],['C-010','用化简帮助求解']],['压缩表达','合并同类项缩短了表达，却保留了对所有允许输入的取值。这是一种保持意义的改写。']],
 ['C-005','拆开括号，保留关系','括号外的数，为什么要作用到每一项？','括号外的数乘到每一项；括号前是负号，各项变号。','2(x + 3) = 2x + 6；−(x − 3) = −x + 3。','不能只乘第一项。用矩形面积解释分配律时，边长需非负；代数法则不限于非负数。','−2(x − 4) 等于什么？','−2x + 8。',[['C-006','把拆分与合并连起来'],['C-009','区分改写式子与变换等式']],['面积里的分配律','长为 x + 3、宽为 2 的矩形可拆成两个小矩形；比较总面积，就能看见分配律。']],
 ['C-006','换一种写法，看见结构','复杂表达式能否整理成容易理解的形式？','先去括号，再合并同类项。','2(x + 3) − x = 2x + 6 − x = x + 6。','化简不等于求出 x；没有额外条件，就不应凭空得到一个确定的 x。','3(x + 2) − 2(x + 1) 化简后是什么？','x + 4。',[['C-007','用化简解释规律'],['C-010','用化简整理方程']],['符号计算','计算机代数也会改写表达式。判断改写是否正确，需要检查等价性与适用条件。']],
 ['C-007','从“试过都对”到“说明总对”','连续奇数相加，为什么总得到偶数？','用字母写出一类数，再通过化简找规律。','相邻奇数的和为 (2n + 1) + (2n + 3) = 4(n + 1)，n 为整数，所以和是 4 的倍数。','这里 n 是整数；举例可以启发猜想，不能证明所有情形。','三个连续整数的和为什么是 3 的倍数？','设为 n、n + 1、n + 2，和为 3(n + 1)，其中 n 为整数。',[['C-001','重新选择恰当的表达'],['C-011','把数量规律用于建模']],['不变量与数字魔术','“想一个数、加 3、乘 2、再减去原数的两倍”，结果恒为 6。把步骤写成式子，就能揭开魔术。']],
 ['C-008','把目标变成一个条件','费用是 17 元，能反推出买了几本吗？','使方程左右两边相等的未知数取值，就是方程的解。','3n + 5 = 17，代入 n = 4，两边都等于 17。','表达式没有提出相等条件；方程的解需要代回原方程检验。','n = 3 是这个方程的解吗？','不是，左边为 14，与右边 17 不相等。',[['C-009','怎样改变方程而保留解？'],['C-016','如果目标改成“不超过”呢？']],['交点的语言','两个费用表达式相等时，对应图像的交点。把“相等”画出来，可为之后学习函数做准备。'],'cost'],
 ['C-009','变换过程，守住相等','为什么可以移项，却不能随意删掉一项？','两边同加、同减一个数，或同乘、同除一个非零数，方程的解不变。','3x + 5 = 17 → 3x = 12 → x = 4。','同乘 0 后等式仍成立，但所有信息变成 0 = 0，不能据此等价求解；除数不能为 0。','把 x = 2 两边乘 0 后，能否再由 0 = 0 推回 x = 2？','不能。0 = 0 对任何 x 都成立，原来的限制已经丢失。',[['C-010','把等价变换组织成步骤'],['C-017','比较大小时规则会变化吗？']],['可逆操作','求解时要关心每一步能否反向还原。可逆性解释了为什么某些看似合法的操作会丢失信息。']],
 ['C-010','一步步让未知数显露','怎样选择步骤，让方程越来越简单？','去括号、合并同类项，再移项、把未知数系数化为 1。','2(x + 3) − x = 10 → x + 6 = 10 → x = 4。','步骤不必机械固定；去分母时必须处理等式两边的每一项。','3(x − 1) = 6 的解是什么？','x = 3。先除以 3 得 x − 1 = 2，再加 1。',[['C-011','把求解放回现实'],['C-013','两个未知数如何化成一个？']],['算法与策略','不同求解顺序可能都正确。可以比较哪条路径中间项更少、更不容易出现符号错误。']],
 ['C-011','从故事中找出等量','应用题里，哪一句话提供了等号？','设未知数，找等量关系，列方程求解，再核对数量和单位。','每本 3 元，运费 5 元，共付 17 元：3n + 5 = 17，买了 4 本。','数学解还要满足情境：本数应为非负整数，费用单位必须一致。','若总费用改为 16 元，这个模型有可行的整数本数吗？','没有。方程解 n = 11/3，不符合整本购买条件。',[['C-015','需要同时定义两个未知量时'],['C-021','预算只是上限时']],['模型有假设','固定单价、没有折扣、运费不变都是假设。规则改变时，应该修改模型，而不是继续套用原式。']],
 ['C-012','让两条线索同时成立','只知道一共 10 张票，能确定两类票各几张吗？','方程组的解是一组同时满足所有方程的数。','x + y = 10，2x + 3y = 26，解为 x = 4，y = 6。','只满足其中一个方程还不是方程组的解；不能从两组不同的候选值各取一个。','(7, 3) 能否满足上述方程组？','不能。虽然 7 + 3 = 10，但 2 × 7 + 3 × 3 = 23。',[['C-013','用替换减少未知量'],['C-014','用相减消去未知量']],['交汇、平行与重合','在二维图形中，两个一次方程对应两条直线。它们可能相交、平行或重合，因此方程组不总有唯一解。']],
 ['C-013','用一种表达替换另一种','知道 x = 10 − y，为什么还要保留两个未知数？','用一个未知数表示另一个，代入另一方程；求出一个后再回代。','把 x = 10 − y 代入 2x + 3y = 26，得 y = 6，再得 x = 4。','应代入另一条独立条件；代回同一方程通常只得到恒等式。','得到 y = 6 后，求解是否已经结束？','还需要回代求 x，并用原来的两个方程核验数对。',[['C-014','看看另一种消元方式'],['C-010','回到熟悉的一元求解']],['替换的思想','把一个对象换成等价表达，可让复杂关系变得简单。消元的核心是减少需要同时处理的未知量。']],
 ['C-014','让共同部分抵消','两条等式相减，能不能直接露出一个未知量？','把一个未知数的系数配成相同或相反，再相减或相加消元，最后回代。','2x + 3y = 26 减去 2x + 2y = 20，得 y = 6；代回 x + y = 10，得 x = 4。','做减法时整条等式逐项相减；消元后仍要保留一个原方程用于回代。','如果 x 的系数分别为 2 和 −2，哪种操作更直接？','把两个方程相加，x 项会抵消。',[['C-015','根据问题选择消元方法'],['C-013','对照替换与抵消']],['通向线性代数','把消元按步骤记录下来，可以推广到更多未知数的线性方程组。这里的两元问题是一个小型起点。']],
 ['C-015','让数量与总量互相验证','知道票数和总收入，怎样确定两类票的数量？','设两个未知数，按数量和费用等关系列出两个方程。','2 元票与 3 元票共 10 张，收入 26 元：x + y = 10，2x + 3y = 26，得 4 张与 6 张。','两个条件要提供有效的新信息；数量为整数且非负，还应核对单价与总额的单位。','如果第二个条件只是 2x + 2y = 20，能确定各买几张吗？','不能，它只是第一个条件的两倍，没有增加新限制。',[['C-012','判断信息是否足够'],['C-021','把等量条件改成资源上限']],['信息是否独立','方程条数多，不一定信息多。辨认重复条件，比简单地数等号更重要。']],
 ['C-016','答案可以是一整段范围','“不超过预算”为什么通常不只有一个答案？','满足不等式的数是它的解，所有解组成解集。','x + 2 ≤ 5 的解集是 x ≤ 3，2 是其中一个解。','给出几个例子不等于找到了全部解；现实中的人数还要限定为整数。','x = −10 是否满足 x + 2 ≤ 5？','满足。若 x 表示人数，则还需加上非负整数限制。',[['C-017','怎样保持大小关系？'],['C-019','把全部可能画出来']],['从一个值到一个集合','“找到答案”也可以是描述所有可能。集合的视角帮助区分一个成员与全部成员。']],
 ['C-017','镜像之后，顺序反过来','为什么同乘负数，不等号必须变向？','两边同加、同减一个数，方向不变；同乘、同除正数方向不变，负数则变向。','2 < 5，两边同乘 −1，得到 −2 > −5。','同乘正数保持方向；乘以 0 会让两边相等，不能保留严格不等式。','−2x < 6，两边除以 −2 后得到什么？','x > −3；除以负数要改变不等号方向。',[['C-018','用这个规则求范围'],['C-009','对照等式的变换']],['顺序与变换','平移保持左右顺序，镜像反转顺序。观察变换如何影响关系，比单记口诀更可靠。'],'mirror'],
 ['C-018','求出分界点，再确定方向','解不等式时，怎样知道答案朝哪边延伸？','移项、合并，再将未知数系数化为 1；乘除负数时改变不等号方向。','3x + 5 ≤ 17 → 3x ≤ 12 → x ≤ 4。','检验一个数可以发现方向错误，但完整解集仍需由等价推导得到。','5 − 2x ≥ 11 的解集是什么？','−2x ≥ 6，除以 −2 后得 x ≤ −3。',[['C-019','把方向与端点画出来'],['C-021','解释哪些现实选择可行']],['临界值的意义','比较两种费用时，相等的位置是分界点。分界点左右分别对应不同的优劣关系。'],'cost'],
 ['C-019','把可能性画在数轴上','一个空心点，为什么会改变答案？','实心点表示包含端点，空心点表示不包含；大于向右，小于向左。','x ≤ 4：在 4 画实心点，向左延伸。','数轴上的连续线段描述实数范围；整数解应另外筛选。','x < 3 与 x ≤ 3 只差在哪里？','只差是否包含 3 这个边界值。',[['C-020','把多个范围叠加'],['C-016','再看一个解与全部解']],['图形也是一种语言','数轴把符号中的“方向”和“是否包含”直接展示出来。读图与读式应能互相翻译。']],
 ['C-020','只保留共同允许的部分','每条限制都合理，放在一起还可能无解吗？','分别求出各个不等式的解集，再取公共部分。','x ≥ 2 且 x ≤ 6，公共解集为 2 ≤ x ≤ 6。','“且”取交集，“或”取并集；端点能否保留要看每一条条件。','x > 2 且 x ≤ 2，有解吗？','无解，数 2 不满足第一条，其余数也无法同时满足两条。',[['C-021','将共同范围用于决策'],['C-012','比较方程组的“同时满足”']],['通向优化问题','约束先划出可行选择；再加入“费用最低”等目标，才成为寻找最优选择的问题。可行不等于最优。'],'intersection'],
 ['C-021','从可行范围作出选择','预算有限时，最多能购买多少份？','把“至少”“至多”写成不等式，求出范围，再按实际数量取值。','每份 3 元，另付运费 5 元，预算 17 元：3n + 5 ≤ 17，所以最多买 4 份。','求出实数范围后要按情境筛选整数；若不购买就不收费，需单独修改 n = 0 的模型。','预算改成 16 元，最多能购买几份？','n ≤ 11/3，取非负整数，最多 3 份。',[['C-001','回头检验表达的假设'],['C-020','资源不止一种时']],['决策需要目标','“都买得起”只说明可行。若还关心数量、质量或时间，需要明确优先目标，才能比较不同方案。'],'cost']
];
const lifeExamples={
 "C-001": "点外卖时，每份餐 12 元、配送费 3 元，买 n 份共付 12n + 3 元。",
 "C-002": "按每小时 4 元计算停车费，停 3 小时：把 t = 3 代入 4t，得到 12 元。",
 "C-003": "制作长方形展板，面积写成 3x² 时，3 是系数，2 是次数；尺寸翻倍时，面积会变成原来的 4 倍。",
 "C-004": "上午买 3 本同款笔记本，下午又买 2 本，每本 x 元，总价就是 3x + 2x = 5x 元。",
 "C-005": "买两套文具，每套含一支 x 元的笔和一本 3 元的本子，总价为 2(x + 3) = 2x + 6 元。",
 "C-006": "买两套“笔＋本”，再退掉一支笔：2(x + 3) − x = x + 6，剩下一支笔和两本本子的钱。",
 "C-007": "用小棒并排摆正方形，相邻两个共用一条边。摆 n 个需要 4 + 3(n − 1) = 3n + 1 根。",
 "C-008": "买几本每本 3 元的本子，加上 5 元运费共付 17 元？3n + 5 = 17，买了 4 本。",
 "C-009": "天平两边同时拿走同样重的物品，仍然平衡；这就像等式两边同时减去同一个数。",
 "C-010": "两份套餐共 26 元，每份含一个汉堡和一杯 3 元饮料：2(x + 3) = 26，汉堡每个 10 元。",
 "C-011": "打车起步价 10 元含 3 千米，之后每千米 2 元。行程超过 3 千米且共付 24 元，可列 10 + 2(x − 3) = 24，得 10 千米。",
 "C-012": "买两种饮料共 10 瓶，单价分别为 2 元、3 元，总价 26 元。4 瓶与 6 瓶同时满足瓶数和总价两个条件。",
 "C-013": "两组共 10 人，第一组有 x 人，第二组就是 10 − x 人。代入另一条条件，就能只用一个未知数计算。",
 "C-014": "两支笔加三本本子共 26 元，两支笔加两本本子共 20 元。相减后，一本本子的价格是 6 元。",
 "C-015": "成人票 20 元、儿童票 10 元，共买 8 张花了 130 元。列 x + y = 8、20x + 10y = 130，得成人票 5 张、儿童票 3 张。",
 "C-016": "电梯限载 800 千克，总质量 m 要满足 m ≤ 800；600、700、800 都是允许的取值。",
 "C-017": "气温从 2℃ 降到 −2℃，从 5℃ 降到 −5℃。两个数都乘 −1 后，原来较大的数反而较小。",
 "C-018": "有 17 元预算，先付 5 元包装费，每份点心 3 元。3n + 5 ≤ 17，最多买 4 份。",
 "C-019": "游乐设施要求身高至少 1.2 米：h ≥ 1.2。在数轴的 1.2 处画实心点，向右表示符合要求的身高。",
 "C-020": "两位同学分别在 14—17 点、15—18 点有空，能一起活动的时间是共同的 15—17 点。",
 "C-021": "班级有 100 元活动经费，材料费 20 元，每份奖品 6 元。6n + 20 ≤ 100，最多买 13 份奖品。"
};
export const storyContent=Object.fromEntries(authoredNodes.map(([id,title,question,idea,example,caution,check,answer,next,extra,lab])=>[id,{title,question,idea,example,caution,check,answer,next,extra,lab,life:lifeExamples[id]}]));

export function storyExperiment(kind,value){
 if(kind==='mirror'){const a=2*value,b=5*value;return {a,b,text:`2 × ${value} = ${a} ${a<b?'＜':a>b?'＞':'＝'} ${b} = 5 × ${value}；${value<0?'负数使顺序反转':value>0?'正数保持顺序':'乘零后两点重合，严格大小关系消失'}`}}
 if(kind==='cost'){const a=3*value+5,b=5*value;return {a,b,text:`${value} 份：A = 3n + 5 = ${a} 元，B = 5n = ${b} 元。${a<b?'A 更便宜':a>b?'B 更便宜':'费用相等'}。两方案在 n = 2.5 相等；整份购买时，1～2 份选 B，3 份及以上选 A。`}}
 return {low:value,high:6,text:value>6?`没有公共解：x 要大于或等于 ${value}，同时小于或等于 6。`:value===6?'公共解只剩 x = 6。':`公共解集：${value} ≤ x ≤ 6。紫色部分同时满足两条不等式。`};
}

// Each visual is an authored explanation, keyed to an existing curriculum node.
export const nodeVisuals={
 'C-001':{kind:'machine',steps:[['数量进入规则','n 本 → 每本 3 元 → 加运费 5 元'],['用一个式子概括','总费用 = 3n + 5']]},
 'C-002':{kind:'machine',steps:[['先替换字母','x = −2，把负数放进括号'],['再按顺序计算','3 × (−2) + 5 = −1']]},
 'C-003':{kind:'tiles',steps:[['拆成带符号的项','3x² − 2x + 7'],['读出结构','系数：3、−2；常数项：7；最高次数：2']],tiles:[['3x²','−2x','7'],['3x²','−2x','7']]},
 'C-004':{kind:'tiles',steps:[['同一种字母结构','3x + 2x'],['合并的是系数','(3 + 2)x = 5x']],tiles:[['x','x','x','x','x'],['5x']]},
 'C-005':{kind:'tiles',steps:[['括号表示一个整体','2(x + 3)：相同的一组取两次'],['分配到每一项','2x + 6']],tiles:[['x','3','x','3'],['2x','6']]},
 'C-006':{kind:'combine',steps:[['展开括号','2(x + 3) − x = x + 3 + x + 3 − x'],['同类项放在一起','把 x、x、−x 叠在一组，把 3、3 放在另一组。'],['分别合成一个式子','字母项合成 x + x − x，常数项合成 3 + 3。'],['合并系数，得到结果','(1 + 1 − 1)x = x，3 + 3 = 6，所以结果是 x + 6。']]},
 'C-007':{kind:'pattern',steps:[['先看一个例子','3 + 5 = 8：两组奇数合在一起'],['把剩下的单点配成一对','每组奇数都剩 1 个单点，它们恰好配对'],['推广到任意相邻奇数','(2n + 1) + (2n + 3) = 4(n + 1)，n 为整数']]},
 'C-008':{kind:'balance',steps:[['把候选数放回去','3n + 5 = 17'],['检验 n = 4','3 × 4 + 5 = 17，两边相等']],sides:[['3n + 5','17'],['3 × 4 + 5','17']]},
 'C-009':{kind:'balance',steps:[['两边保持相等','3x + 5 = 17'],['两边同时减去 5','3x = 12'],['两边同时除以 3','x = 4']],sides:[['3x + 5','17'],['3x','12'],['x','4']]},
 'C-010':{kind:'balance',steps:[['先化简左边','2(x + 3) − x = 10'],['拆括号、合并同类项','x + 6 = 10'],['两边同时减去 6','x = 4']],sides:[['2(x + 3) − x','10'],['x + 6','10'],['x','4']]},
 'C-011':{kind:'balance',steps:[['用两种方式表示总费用','每本 3 元 × 本数 + 运费 = 17 元'],['列出等量条件','3n + 5 = 17'],['解释答案','n = 4：买 4 本，费用恰好 17 元']],sides:[['书本费 + 运费','总费用'],['3n + 5','17'],['3 × 4 + 5','17']]},
 'C-012':{kind:'intersection2d',steps:[['每条线代表一个条件','绿色：x + y = 10；橙色：2x + 3y = 26'],['共同解在交点','交点 (4, 6) 同时满足两个方程']]},
 'C-013':{kind:'system',steps:[['先表达一个未知数','x + y = 10 → x = 10 − y'],['把 x 换成等价表达','2(10 − y) + 3y = 26'],['只剩一个未知数','20 + y = 26 → y = 6，回代得 x = 4']],rows:[['x','+ y','= 10'],['2(10 − y)','+ 3y','= 26'],['20','+ y','= 26']]},
 'C-014':{kind:'system',steps:[['先把 x 的系数配齐','第一式乘 2：2x + 2y = 20'],['两式相减','(2x + 3y) − (2x + 2y) = 26 − 20'],['相同的 x 项抵消','y = 6，回代得 x = 4']],rows:[['2x','+ 3y','= 26'],['2x','+ 2y','= 20'],['0x','+ y','= 6']]},
 'C-015':{kind:'system',steps:[['数量提供一条线索','两类票合计 10 张：x + y = 10'],['收入提供另一条线索','2 元票与 3 元票：2x + 3y = 26'],['答案需要同时核验','4 + 6 = 10；2 × 4 + 3 × 6 = 26']],rows:[['x','+ y','= 10'],['2x','+ 3y','= 26'],['8','+ 18','= 26']]},
 'C-016':{kind:'interval',steps:[['一个数只是一个解','x + 2 ≤ 5：例如 x = 2 满足条件'],['画出全部解','全部实数解是 x ≤ 3，包含 3 并向左延伸']],bound:3},
 'C-017':{kind:'mirror'},
 'C-018':{kind:'interval',steps:[['先找等价条件','3x + 5 ≤ 17'],['两边同时减去 5','3x ≤ 12'],['除以正数 3，方向不变','x ≤ 4；用数轴表示全部解']],bound:4},
 'C-019':{kind:'endpoint',steps:[['包含边界','x ≤ 4：实心点，向左延伸'],['排除边界','x > 4：空心点，向右延伸']],bound:4},
 'C-020':{kind:'intersection'},
 'C-021':{kind:'budget',steps:[['连续范围','3n + 5 ≤ 16 → n ≤ 11/3'],['筛选整数份数','n ∈ {0, 1, 2, 3}，最多 3 份（固定费始终收取）']]}
};

Object.assign(nodeVisuals,semanticVisuals);

// Allow reading time for prose, equations, and the transition itself.
export function visualReadingDelay(text,finalStep=false){
 const compact=text.replace(/\s/g,'');
 const operations=(compact.match(/[=<>≤≥+−×÷→]/g)||[]).length;
 return Math.min(12000,Math.max(4200,1600+compact.length*75+operations*150))+(finalStep?1000:0);
}

// Morph matching SVG shapes between teaching steps; fade changed labels.
function visualTransition(svg,render,reduced){
 const before=[...svg.children].map(node=>({tag:node.tagName,text:node.textContent,attrs:Object.fromEntries([...node.attributes].map(a=>[a.name,a.value]))}));
 render();
 if(reduced)return()=>{};
 const tweens=[],animations=[];
 [...svg.children].forEach((node,i)=>{
  const key=node.getAttribute('data-motion-key');
  const old=key?before.find(v=>v.attrs['data-motion-key']===key):before[i];
  if(!old||old.tag!==node.tagName){animations.push(node.animate([{opacity:0},{opacity:1}],{duration:450}));return}
  for(const name of ['x','y','x1','y1','x2','y2','cx','cy','r','width','height','opacity']){
   if(old.attrs[name]===undefined||!node.hasAttribute(name))continue;
   const from=Number(old.attrs[name]),to=Number(node.getAttribute(name));
   if(Number.isFinite(from)&&Number.isFinite(to)&&from!==to)tweens.push({node,name,from,to});
  }
  if(old.text!==node.textContent)animations.push(node.animate([{opacity:.15,transform:'translateY(6px)'},{opacity:1,transform:'translateY(0)'}],{duration:450,easing:'ease-out'}));
 });
 let frame=0,start=performance.now();
 function tick(now){const t=Math.min(1,(now-start)/650),ease=t*t*(3-2*t);for(const v of tweens)v.node.setAttribute(v.name,String(v.from+(v.to-v.from)*ease));if(t<1)frame=requestAnimationFrame(tick)}
 if(tweens.length)tick(start);
 return()=>{cancelAnimationFrame(frame);animations.forEach(a=>a.cancel())};
}

export function mountNodeVisual(host,id,el,se){
 const config=nodeVisuals[id];if(!config)return;
 if(['mirror','intersection'].includes(config.kind))return mountStoryLab(host,config.kind,el,se);
 const box=el('section','','node-visual'),heading=el('h3','看图理解'),svg=se('svg',{viewBox:'0 0 400 220',role:'img'}),caption=el('p','','visual-caption'),controls=el('div','','visual-controls');
 const previous=el('button','上一步'),next=el('button','下一步'),count=el('span');previous.type=next.type='button';caption.setAttribute('aria-live','polite');const play=el('button','暂停');play.type='button';controls.append(previous,play,count,next);box.append(heading,svg,caption,controls);host.append(box);let step=0;
 const green='#23836d',orange='#bb783b',blue='#517ead';
 function text(x,y,value,size=17,color='currentColor'){const t=se('text',{x,y,'text-anchor':'middle','font-size':size,fill:color});t.textContent=value;svg.append(t)}
 function line(x1,y1,x2,y2,color=green,w=3){svg.append(se('line',{x1,y1,x2,y2,stroke:color,'stroke-width':w}))}
 function rect(x,y,w,h,color){svg.append(se('rect',{x,y,width:w,height:h,rx:10,fill:color,'fill-opacity':.12,stroke:color,'stroke-width':2}))}
 function circle(x,y,r,color,empty=false){svg.append(se('circle',{cx:x,cy:y,r,fill:empty?'var(--surface,white)':color,stroke:color,'stroke-width':2}))}
 function tiles(items,y){const w=Math.min(96,330/items.length),start=200-items.length*w/2;items.forEach((v,i)=>{const color=v.includes('−')?orange:/[xy]/.test(v)?green:blue;rect(start+i*w+3,y,w-6,50,color);text(start+(i+.5)*w,y+32,v,Math.min(20,w/2.5),color)})}
 function axis(bound,direction=-1,open=false){const x=n=>45+(n+2)*34;line(28,120,375,120,'#8a9b95',2);for(let i=-2;i<=7;i++){line(x(i),116,x(i),124,'#8a9b95',1);text(x(i),146,String(i),13)}line(direction<0?28:x(bound),120,direction<0?x(bound):375,120,green,6);circle(x(bound),120,7,green,open);text(direction<0?28:375,126,direction<0?'◀':'▶',18,green)}
 function draw(){svg.replaceChildren();const [title,explanation]=config.steps[step];heading.textContent=title;caption.textContent=explanation;svg.setAttribute('aria-label',title+'：'+explanation);count.textContent=(step+1)+' / '+config.steps.length;previous.disabled=step===0;next.disabled=step===config.steps.length-1;
  if(config.kind==='semantic'){drawSemanticScene(svg,id,step,se)}
  else if(config.kind==='combine'){
   const terms=['x','3','x','3','−x'];
   terms.forEach((value,i)=>{
    const isLetter=i%2===0,leader=i===0||i===1;
    let x=24+i*70,y=82,w=60,h=44,opacity=1,label=value;
    if(step===1){x=isLetter?68:270;y=isLetter?30+(i/2)*52:56+((i-1)/2)*58}
    if(step>=2){x=isLetter?(step===2?34:64):254;y=76;w=isLetter?(step===2?180:120):112;h=64;opacity=leader?1:0;label=leader?(isLetter?(step===2?'x + x − x':'x'):(step===2?'3 + 3':'6')):value}
    const color=isLetter?(step<2&&i===4?orange:green):blue;
    const tile=se('rect',{x,y,width:w,height:h,rx:10,fill:color,'fill-opacity':.12,stroke:color,'stroke-width':2,opacity});
    const labelNode=se('text',{x:x+w/2,y:y+h/2+7,'text-anchor':'middle','font-size':step===3?26:20,fill:color,opacity});labelNode.textContent=label;
    svg.append(tile,labelNode);
   });
   text(200,20,step===0?'先展开':step===1?'字母项一组，常数项一组':step===2?'同类项各自合成一个框':'系数相加，字母不变',16);
   text(220,116,step>=2?'+':'',24);
   text(200,210,step===3?'x + 6':step===2?'(1 + 1 − 1)x + (3 + 3)':'2(x + 3) − x',22,green);
  }
  else if(config.kind==='tiles'){tiles(config.tiles[step],80);text(200,45,step===0?'把每一项看成一块带符号的积木':'改变组合，保持表达式的值',16);text(200,176,'色块代表代数项，大小不代表数值或面积',13);if(id==='C-006'&&step===1){text(200,207,'x + (−x) = 0',20,orange)}}
  else if(config.kind==='machine'){const negative=id==='C-002';const values=negative?(step?['−2','× 3 + 5','−1']:['x = −2','3x + 5','?']):(step?['n','× 3 + 5','3n + 5']:['n 本','每本 3 元','加 5 元']);values.forEach((v,i)=>{rect(14+i*132,72,108,70,i===1?orange:green);text(68+i*132,114,v,17);if(i<2)text(134+i*132,113,'→',20)});text(200,182,negative?'先替换，再计算':'输入数量 → 应用规则 → 输出费用',16)}
  else if(config.kind==='balance'){const [a,b]=config.sides[step];line(65,114,335,114,blue,5);svg.append(se('path',{d:'M200 116 L175 179 L225 179 Z',fill:blue,'fill-opacity':.2,stroke:blue}));line(90,115,90,139);line(310,115,310,139);line(38,140,142,140,green,4);line(258,140,362,140,green,4);rect(18,58,164,48,green);rect(218,58,164,48,orange);text(100,88,a,a.length>10?15:19);text(300,88,b,19);text(200,88,'=',23);text(200,207,'同一等式的两边，始终保持相等',15)}
  else if(config.kind==='pattern'){for(let i=0;i<3;i++)circle(64+i*28,68,9,green);for(let i=0;i<5;i++)circle(64+i*28,118,9,orange);text(270,74,'3 = 2 + 1',18);text(270,124,'5 = 4 + 1',18);if(step>0){for(let i=0;i<4;i++){line(65+i*74,170,87+i*74,170,blue,4);circle(65+i*74,170,8,green);circle(87+i*74,170,8,orange)}text(200,208,step===2?'一般式：4(n + 1)':'合起来 8 个点，可以全部两两配对',16)}}
  else if(config.kind==='intersection2d'){const x=n=>45+n*27,y=n=>190-n*14;line(45,190,335,190,'#8a9b95',2);line(45,190,45,36,'#8a9b95',2);line(x(0),y(10),x(10),y(0),green);line(x(0),y(26/3),x(10),y(2),orange);text(350,195,'x',15);text(42,24,'y',15);text(32,205,'0',13);if(step){circle(x(4),y(6),7,blue);text(x(4)+62,y(6)-10,'(4, 6)',18,blue);line(x(4),y(6),x(4),190,blue,1);line(45,y(6),x(4),y(6),blue,1);text(x(4),208,'4',13);text(30,y(6)+5,'6',13)}}
  else if(config.kind==='system'){if(id==='C-014'){tiles(['2x','+ 3y','= 26'],35);tiles(['2x','+ 2y','= 20'],105);text(200,24,'上式 − 下式',16);if(step>0){line(47,38,122,80,orange,3);line(47,108,122,150,orange,3)}if(step===2)text(200,204,'相同部分抵消 → y = 6',21,green)}else{tiles(config.rows[step],85);text(200,46,id==='C-013'?'用等价表达替换同一个未知量':'每条条件都必须成立',16);text(200,185,step===2?'再回到原方程组检验 (4, 6)':'同一行的三块，组成一条等量关系',14)}}
  else if(config.kind==='interval'){axis(config.bound);text(200,62,'x ≤ '+config.bound,23,green);if(id==='C-016'&&step===0){circle(45+4*34,120,9,orange);text(45+4*34,92,'一个解：2',16,orange)}else text(200,190,'所有绿色位置，都满足条件',16)}
  else if(config.kind==='endpoint'){axis(config.bound,step===0?-1:1,step===1);text(200,62,step===0?'x ≤ 4':'x > 4',24,green);text(200,192,step===0?'实心点：边界值 4 也在解集中':'空心点：边界值 4 不在解集中',16)}
  else if(config.kind==='budget'){const x=n=>45+n*58;line(x(0),105,x(5),105,'#8a9b95',2);line(x(0),105,x(11/3),105,green,6);for(let i=0;i<=5;i++){text(x(i),136,String(i),15);if(step===1)circle(x(i),105,7,i<=3?green:orange,true)}circle(x(11/3),105,6,green);text(x(11/3),76,'11/3',17);text(200,178,step===0?'可行实数范围：0 ≤ n ≤ 11/3':'整数选择：0、1、2、3；4 已超出范围',16);text(200,207,'数量只能取整数，边界值不能直接当份数',13)}
 }
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 let playing=!reduced,timer=0,stopTransition=()=>{},disposed=false;
 function update(){stopTransition();stopTransition=visualTransition(svg,draw,reduced)}
 function syncPlay(){play.textContent=playing?'暂停':'播放';play.setAttribute('aria-label',playing?'暂停动画':'播放动画');play.setAttribute('aria-pressed',String(playing))}
 function schedule(){clearTimeout(timer);if(!playing||disposed)return;timer=setTimeout(()=>{if(!box.isConnected)return;if(!document.hidden){step=(step+1)%config.steps.length;update()}schedule()},visualReadingDelay(heading.textContent+' '+svg.textContent+' '+caption.textContent,step===config.steps.length-1))}
 function pause(){playing=false;clearTimeout(timer);syncPlay()}
 previous.onclick=()=>{pause();if(step>0){step--;update()}};
 next.onclick=()=>{pause();if(step<config.steps.length-1){step++;update()}};
 play.onclick=()=>{playing=!playing;syncPlay();schedule()};
 draw();syncPlay();schedule();
 return()=>{disposed=true;clearTimeout(timer);stopTransition()};
}
export function mountStoryLab(host,kind,el,svgEl){
 const box=el('section','','story-lab'),label=el('label',''),input=el('input',''),output=el('p','','lab-output');
 const config={mirror:['数轴实验 · 同时缩放两个数','先预测：滑过 0 时，左右顺序会怎样？','共同乘数',-2,2,.5,-1],cost:['方案实验 · 找到费用分界','自编比较：A 有 5 元固定费、每份 3 元；B 无固定费、每份 5 元。','购买份数',1,8,1,2],intersection:['条件实验 · 寻找公共范围','x 要同时满足绿色和橙色两条不等式。拖动滑块改变绿色条件，紫色显示共同满足的数。','绿色条件中的数',0,8,1,2]}[kind];
 const [title,prompt,name,min,max,step,value]=config;box.append(el('h3',title),el('p',prompt));input.type='range';Object.assign(input,{min,max,step,value});input.setAttribute('aria-label',name);label.append(el('span',name),input);const svg=svgEl('svg',{viewBox:kind==='intersection'?'0 0 440 180':'0 0 440 150',role:'img','aria-label':title});output.setAttribute('aria-live','polite');box.append(label,svg,output);host.append(box);
 function line(x1,y1,x2,y2,color,width=3){svg.append(svgEl('line',{x1,y1,x2,y2,stroke:color,'stroke-width':width}))}
 function text(x,y,t){const e=svgEl('text',{x,y,'text-anchor':'middle',fill:'currentColor','font-size':13});e.textContent=t;svg.append(e)}
 function dot(x,y,color){svg.append(svgEl('circle',{cx:x,cy:y,r:6,fill:color}))}
 function draw(){svg.replaceChildren();const v=Number(input.value),r=storyExperiment(kind,v);output.textContent=r.text;svg.setAttribute('aria-label',r.text);label.firstChild.textContent=kind==='intersection'?'绿色条件：x ≥ '+v:name+'：'+v;
  if(kind==='mirror'){const x=n=>220+n*18;line(35,78,405,78,'#8a9b95',2);for(const n of [-10,-5,0,5,10]){line(x(n),73,x(n),83,'#8a9b95',1);text(x(n),105,String(n))}dot(x(r.a),78,'#16836e');dot(x(r.b),78,'#b97132');text(x(r.a),45,'2k = '+r.a);text(x(r.b),125,'5k = '+r.b)}
  else if(kind==='cost'){text(40,48,'A');text(40,102,'B');line(65,43,65+r.a*8,43,'#16836e',18);line(65,97,65+r.b*8,97,'#b97132',18);text(90+r.a*8,48,String(r.a));text(90+r.b*8,102,String(r.b));text(220,140,'横条长度表示费用（元）')}
  else{const x=n=>45+n*42;line(x(0),138,x(8),138,'#8a9b95',1);line(x(v),36,x(8),36,'#16836e',5);line(x(0),86,x(6),86,'#b97132',5);dot(x(v),36,'#16836e');dot(x(6),86,'#b97132');text(x(8)+9,41,'→');text(x(0)-9,91,'←');if(v<=6){line(x(v),138,x(6),138,'#7062a5',7);dot(x(v),138,'#7062a5');dot(x(6),138,'#7062a5')}for(let i=0;i<=8;i++)text(x(i),164,String(i));text(220,20,'绿色：x ≥ '+v);text(220,70,'橙色：x ≤ 6');text(220,120,v>6?'紫色：没有公共解':v===6?'紫色：x = 6':'紫色：'+v+' ≤ x ≤ 6')}
 }
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const controls=el('div','','visual-controls'),play=el('button','暂停');play.type='button';controls.append(play);box.append(controls);
 let playing=!reduced,timer=0,direction=1,disposed=false,stopTransition=()=>{};
 function syncPlay(){play.textContent=playing?'暂停':'播放';play.setAttribute('aria-label',playing?'暂停动画':'播放动画');play.setAttribute('aria-pressed',String(playing))}
 function update(){stopTransition();stopTransition=visualTransition(svg,draw,reduced)}
 function schedule(){clearTimeout(timer);if(!playing||disposed)return;timer=setTimeout(()=>{if(!box.isConnected)return;if(!document.hidden){let v=Number(input.value)+direction*Number(step);if(v>max||v<min){direction*=-1;v=Number(input.value)+direction*Number(step)}input.value=String(v);update()}schedule()},visualReadingDelay(prompt+' '+svg.textContent+' '+output.textContent))}
 input.oninput=()=>{playing=false;clearTimeout(timer);syncPlay();update()};
 play.onclick=()=>{playing=!playing;syncPlay();schedule()};
 draw();syncPlay();schedule();
 return()=>{disposed=true;clearTimeout(timer);stopTransition()};
}
