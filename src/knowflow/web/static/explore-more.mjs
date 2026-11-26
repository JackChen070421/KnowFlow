// Cross-domain content that is not an experiment: a task wall, subject links
// and short history reads. Everything is authored here and stays offline;
// student writing is kept in the browser only and never reaches diagnostics.

export const MORE_KEY = 'knowflow.explore.more.v1';
export const MORE_VERSION = 1;

export const moreSections = [
  { id: 'tasks', title: '真实任务墙', hint: '6 个跨学科任务 · 交付物 + 量规' },
  { id: 'links', title: '学科联动', hint: '8 门学科 · 同一套数学' },
  { id: 'reads', title: '数学小史', hint: '3 篇微阅读 · 2—3 分钟' }
];

export const taskWall = [
  {
    id: 'heart-rate',
    subject: '体育',
    role: '体育老师',
    title: '给训练定一个心率区间',
    brief: '校队要开始中等强度训练。教练希望每个同学都带着手表，训练时把心率控制在合适的范围里。',
    given: '同班同学 13 岁；最大心率按 220 − 年龄估算；中等强度取最大心率的 60%—75%。',
    ask: '用不等式组写出这个同学的中等强度心率区间，并把结果取整数。',
    deliverable: '一张心率区间卡：算式 + 区间 + 一条安全提示。',
    knowledge: ['K-08', 'K-09'],
    rubric: [
      { id: 'formula', text: '写出了最大心率和两条不等式。' },
      { id: 'conclusion', text: '结论是一个带单位的区间，并说明了为什么取整数。' },
      { id: 'boundary', text: '补了一条边界或安全提示（如身体不适要停止）。' }
    ],
    hint: '先算 220 − 13，再分别乘 60% 和 75%；区间用「≤」连接，心率取整数次/分。'
  },
  {
    id: 'altitude',
    subject: '地理',
    role: '地理老师',
    title: '给登山路线标注气温',
    brief: '地理小组要带同学走一条登山路线。老师要求在每个休息点标出大致气温，提醒大家带外套。',
    given: '海拔每升高 100 米，气温大约下降 0.6℃；山脚（海拔 0 米）气温 26℃。',
    ask: '写出海拔 h 米处的气温表达式，并算出 500 米、1000 米、1500 米三个点的气温。',
    deliverable: '一张对照表 + 一句「为什么高处更冷」的解释。',
    knowledge: ['K-01', 'K-03'],
    rubric: [
      { id: 'formula', text: '把「每 100 米降 0.6℃」正确写成了式子。' },
      { id: 'conclusion', text: '三个点的气温都算对，并标了单位。' },
      { id: 'boundary', text: '说明了这是估算，实际还受天气与地形影响。' }
    ],
    hint: '0.6℃ / 100 米 就是 0.006℃ / 米，气温 = 26 − 0.006 × 海拔。'
  },
  {
    id: 'books',
    subject: '班务',
    role: '图书管理员',
    title: '图书角采购',
    brief: '班级图书角要补一批同款科普书，班费有限，采购前先算清楚最多能买几本。',
    given: '预算 200 元；每本 18 元；下单另付运费 12 元。',
    ask: '最多能买几本？用不等式表示，并说明为什么答案要取整数。',
    deliverable: '不等式 + 取整理由 + 剩余预算。',
    knowledge: ['K-04', 'K-09'],
    rubric: [
      { id: 'formula', text: '把书本费和运费一起写进了不等式。' },
      { id: 'conclusion', text: '结论是整数本数，并算出剩余预算。' },
      { id: 'boundary', text: '说明如果运费变化或涨价，结论要重算。' }
    ],
    hint: '18n + 12 ≤ 200；运费只有一笔，不随本数变化。'
  },
  {
    id: 'budget-code',
    subject: '信息技术',
    role: '程序员',
    title: '写一条预算提醒',
    brief: '班级记账小程序里，如果购物车总价超过预算，就要弹出提醒。这个判断要写进代码里。',
    given: '程序中有两个数：预算 budget 和当前总价 total。',
    ask: '用 5 行以内的伪代码写出「总价超过预算就提示」，并说明为什么这里用不等式而不是等式。',
    deliverable: '5 行伪代码 + 两句话说明。',
    knowledge: ['K-09'],
    rubric: [
      { id: 'formula', text: '条件写对了（超过 = 大于，等于预算不算超支）。' },
      { id: 'conclusion', text: '伪代码能看懂：有判断、有提示、有结束。' },
      { id: 'boundary', text: '解释了为什么用不等式而不是等式。' }
    ],
    hint: '「超过」对应「>」；如果写成「=」，只有在恰好相等时才提醒。'
  },
  {
    id: 'rehearsal',
    subject: '音乐',
    role: '乐队指挥',
    title: '排练时长够不够',
    brief: '艺术节前最后一次排练只剩 12 分钟，指挥想确认整首曲子能完整跑几遍。',
    given: '每小节 4 拍，每拍 0.5 秒；曲子共 32 小节；可用时间 12 分钟。',
    ask: '整首曲子多少秒？12 分钟能完整排几遍？还剩多少秒？',
    deliverable: '算式 + 遍数 + 剩余秒数。',
    knowledge: ['K-01', 'K-04'],
    rubric: [
      { id: 'formula', text: '先算出每小节秒数，再算出全曲秒数。' },
      { id: 'conclusion', text: '遍数取整数，余下时间算对。' },
      { id: 'boundary', text: '提到实际还要留出上下场和沟通时间。' }
    ],
    hint: '每小节 4 × 0.5 = 2 秒；12 分钟 = 720 秒。'
  },
  {
    id: 'transit',
    subject: '交通',
    role: '通勤族',
    title: '月卡什么时候更划算',
    brief: '学校到家的公交可以刷单次，也可以买月卡。先算清楚一个月坐多少次才值得办卡。',
    given: '月卡 15 元；单次 1.5 元（一个月内不限次数）。',
    ask: '一个月坐多少次以上，办月卡才比单次便宜？用不等式求解，并给一句建议。',
    deliverable: '不等式 + 结论 + 一句使用建议。',
    knowledge: ['K-09'],
    rubric: [
      { id: 'formula', text: '把两种花费写成 1.5n 与 15 两个量并比较。' },
      { id: 'conclusion', text: '结论是整数次数，并说明「以上」是否含该次数。' },
      { id: 'boundary', text: '提到月卡只在有效期内、指定线路可用等限制。' }
    ],
    hint: '令 1.5n > 15，得 n > 10；次数必须是整数。'
  }
];

export const subjectLinks = [
  {
    id: 'geo-temp',
    subject: '地理',
    title: '气温为什么随海拔下降',
    inClass: '七年级地理在学气温的垂直变化：海拔越高，气温越低。',
    math: '把「每升高 100 米降 0.6℃」写成一次式：t = 26 − 0.006h。',
    example: '海拔 1500 米处：26 − 0.006 × 1500 = 17℃。',
    careful: '这是平均估算，实际还受坡向与天气影响。',
    knowledge: ['K-01', 'K-03']
  },
  {
    id: 'bio-lens',
    subject: '生物',
    title: '显微镜的放大倍数',
    inClass: '七年级生物要用显微镜观察细胞，目镜和物镜各有倍数。',
    math: '总放大倍数 = 目镜倍数 × 物镜倍数，用乘法把两个量合起来。',
    example: '目镜 10×、物镜 40×，总放大 400 倍。',
    careful: '「放大 400 倍」指长度；面积会变成 400² 倍，这是拓展，不是课本要求。',
    knowledge: ['K-01']
  },
  {
    id: 'history-years',
    subject: '历史',
    title: '跨越公元前后的年数',
    inClass: '七年级历史按时间轴讲朝代，经常要算「距今多少年」。',
    math: '公元前 221 年到公元 2026 年，中间没有公元 0 年：221 + 2026 − 1 = 2246 年。',
    example: '同一条数轴上，左右位置和「早晚」对应。',
    careful: '公元纪年里没有 0 年，直接相减会多算一年。',
    knowledge: ['K-01']
  },
  {
    id: 'chinese-data',
    subject: '语文',
    title: '说明文里的数字',
    inClass: '七年级语文写说明文，要求数据准确、有单位、说法严谨。',
    math: '「不超过 30 分钟」就是 t ≤ 30；「约 2 倍」是估算，不能当成精确相等。',
    example: '写「每天阅读不少于 30 分钟」，比写「每天阅读 30 分钟」更准确。',
    careful: '「约」和「等于」不能混用；说范围时最好把边界写清楚。',
    knowledge: ['K-09']
  },
  {
    id: 'it-condition',
    subject: '信息科技',
    title: '变量和判断',
    inClass: '七年级信息科技开始写程序：变量存数据，if 做判断。',
    math: '变量就是字母：total 存总价，budget 存预算；条件 total > budget 就是不等式。',
    example: 'if total > budget then 提示「超支」——等于预算不算超支。',
    careful: '程序里的「超过」是严格大于；写成 ≥ 会把刚好用完预算也报成超支。',
    knowledge: ['K-09']
  },
  {
    id: 'pe-heart',
    subject: '体育',
    title: '训练强度与成绩',
    inClass: '七年级体育按强度分组训练，也会记录成绩做比较。',
    math: '心率区间用不等式组：124 ≤ h ≤ 155；成绩比较常用平均数描述整体。',
    example: '13 岁同学最大心率约 207，中等强度下限是 207 × 60% ≈ 124。',
    careful: '估算公式只作参考，身体不适要立刻停止。',
    knowledge: ['K-08']
  },
  {
    id: 'music-beat',
    subject: '音乐',
    title: '拍号与时长',
    inClass: '七年级音乐要读拍号，知道每小节有几拍、每拍多长。',
    math: '总时长 = 每小节拍数 × 每拍秒数 × 小节数。',
    example: '4 拍 × 0.5 秒 × 32 小节 = 64 秒。',
    careful: '实际演奏还有前奏、反复与停顿，算出来的是「净时长」。',
    knowledge: ['K-01', 'K-04']
  },
  {
    id: 'art-proportion',
    subject: '美术',
    title: '构图比例与对称',
    inClass: '七年级美术讲比例、构图和对称，画框要按长宽比裁切。',
    math: '长宽比 3 : 2，长 45 cm 时宽是 45 ÷ 3 × 2 = 30 cm；对称轴对应数轴上的镜像。',
    example: '把画纸对折，折痕就是对称轴，左右两个点互为镜像。',
    careful: '比例说的是长度的比，不是面积；面积比是长度比的平方。',
    knowledge: ['K-07']
  }
];

export const historyReads = [
  {
    id: 'negative',
    title: '负数曾被叫作「荒谬的数」',
    minutes: 3,
    paragraphs: [
      '今天的课本里，−3 只是一个普通的数。可在很长一段时间里，它被人叫作「假的」「荒谬的」。',
      '中国《九章算术》里已经出现负数的运算，刘徽在注释中给出了正负数加减的法则；7 世纪，印度的婆罗摩笈多也在使用负数。',
      '欧洲的情况更曲折：一些数学家把负根称为「假根」，莱布尼茨仍怀疑负数的合法性，却在计算中照常使用它。',
      '直到 17 至 19 世纪，负数才逐渐被当作真正的数接受下来。'
    ],
    takeaway: '今天随手写下的一个负号，背后是几百年的争论。',
    question: '如果学校只承认正数，温度、海拔和账单该怎么记？',
  },
  {
    id: 'signs',
    title: '不等号只有几百年',
    minutes: 2,
    paragraphs: [
      '「＜」和「＞」看上去像天生就有的符号，其实它们的形状只有几百年历史。',
      '16 世纪的文献里已经出现类似的两笔尖角记号，17 世纪随着代数书流行开来，逐渐固定成今天的样子。',
      '「≤」「≥」「≠」这些符号出现得更晚，是后来为了少写几个字才补上的。'
    ],
    takeaway: '符号是约定，不是自然规律；真正重要的是它代表的关系。',
    question: '用文字写「不超过 30 元」，和用「≤ 30」相比，各有什么好处？',
  },
  {
    id: 'letters',
    title: 'x 为什么是 x',
    minutes: 2,
    paragraphs: [
      '用字母表示数，是代数真正开始的地方：一句话就能说清「所有满足条件的数」。',
      '16 世纪的韦达开始系统用字母表示未知量与已知量；笛卡尔在《几何学》里用 x、y、z 表示未知数。',
      '字母让式子可以「先算再说」：即使不知道具体数值，也能推导出关系。'
    ],
    takeaway: '字母不是偷懒，而是把「一类数」压缩进一个符号。',
    question: '如果把未知数改叫「苹果」，3x + 5 会怎么写？读起来更清楚还是更麻烦？',
  }
];

export const taskById = id => taskWall.find(task => task.id === id);

export function rubricProgress(task, checks) {
  const list = task?.rubric || [];
  const done = list.filter(entry => checks.includes(entry.id)).length;
  return { done, total: list.length, ratio: list.length ? done / list.length : 0 };
}

export function moreKey(datasetId, studentId) {
  return `${datasetId}|${studentId}`;
}

export function emptyMoreRecord() {
  return { tasks: {} };
}

function cleanTask(taskId, value) {
  const task = taskById(taskId);
  const base = { plan: '', rubric: [], updated_at: '' };
  if (!task || !value || typeof value !== 'object' || Array.isArray(value)) return base;
  const plan = typeof value.plan === 'string' ? value.plan.slice(0, 2000) : '';
  const rubric = Array.isArray(value.rubric)
    ? [...new Set(value.rubric.filter(id => typeof id === 'string' && task.rubric.some(entry => entry.id === id)))]
    : [];
  const updated = typeof value.updated_at === 'string' ? value.updated_at : '';
  return { plan, rubric, updated_at: updated };
}

export function parseMoreStore(raw) {
  const empty = { version: MORE_VERSION, records: {} };
  let parsed = raw;
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return empty;
    }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return empty;
  if (Number(parsed.version) !== MORE_VERSION) return empty;
  const source = parsed.records;
  if (!source || typeof source !== 'object' || Array.isArray(source)) return empty;
  const records = {};
  for (const [key, value] of Object.entries(source)) {
    if (typeof key !== 'string' || !key.includes('|')) continue;
    if (!value || typeof value !== 'object' || Array.isArray(value)) continue;
    const tasks = {};
    if (value.tasks && typeof value.tasks === 'object' && !Array.isArray(value.tasks)) {
      for (const [id, entry] of Object.entries(value.tasks)) {
        if (!taskById(id)) continue;
        tasks[id] = cleanTask(id, entry);
      }
    }
    records[key] = { tasks };
  }
  return { version: MORE_VERSION, records };
}

export function moreRecord(store, datasetId, studentId) {
  const key = moreKey(datasetId, studentId);
  if (!store.records[key]) store.records[key] = emptyMoreRecord();
  return store.records[key];
}

export function moreSummary(store, datasetId, studentId) {
  const record = moreRecord(store, datasetId, studentId);
  const tasksWritten = taskWall.filter(task => (record.tasks[task.id]?.plan || '').trim().length > 0).length;
  return {
    tasksWritten,
    taskTotal: taskWall.length,
    linkTotal: subjectLinks.length,
    readTotal: historyReads.length
  };
}
