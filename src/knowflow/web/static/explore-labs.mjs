// Student-side cross-domain exploration: authored content plus pure models.
// Every lab is a self-authored example, not an official textbook task; nothing
// here reads diagnostics or writes evidence. Numbers stay in the browser only.

const minus = v => String(v).replace('-', '−');
const num = v => (Math.round(v * 100) / 100).toString().replace('-', '−');

export const EXPLORE_KEY = 'knowflow.explore.v1';
export const EXPLORE_VERSION = 1;

export const exploreLabs = [
  {
    id: 'mirror',
    index: '01',
    field: '物理 · 地理',
    title: '数轴上的镜像',
    hook: '气温从 2℃ 降到 −2℃，为什么"更冷"的数反而更小？',
    subtitle: '同乘一个数，数轴上的左右顺序会怎样？',
    minutes: 6,
    knowledge: ['K-07'],
    nodes: ['C-017'],
    question: '为什么同乘负数，不等号必须变向？',
    context:
      '温度、海拔、楼层盈亏都用同一条数轴表示：0℃ 以下、海平面以下、地下一层都是负数。把 "3 ＜ 5" 看成数轴上的两个点，再让它们同乘一个数 a，点的位置会怎样移动？',
    model:
      '两个点分别是 3a 和 5a，它们的差是 3a − 5a = −2a。a 为正时差为负（顺序不变），a 为负时差为正（顺序反转），a 为 0 时两点落在一起。',
    steps: [
      '把滑块拖到正数区（如 2），记下两点的左右顺序。',
      '再拖到负数区（如 −2），观察两点是否交换了位置。',
      '停在 0 上，说明为什么这时不能再说"谁大于谁"。'
    ],
    checks: [
      { id: 'keep', text: 'a ＞ 0 时，3a 仍在 5a 左侧，顺序保留。' },
      { id: 'reverse', text: 'a ＜ 0 时，两点交换左右位置，顺序反转。' },
      { id: 'collapse', text: 'a = 0 时两点重合，严格的大小关系消失。' }
    ],
    boundary:
      '类比的边界：数轴只解释"数的顺序怎样随乘法改变"，不替代不等式两边同乘或同除一个负数时的等价变形论证；除以 0 没有意义，也不能靠镜像类比补上。',
    transfer: '找一周里最高气温有正有负的五天，把它们同乘 −1 后重新排序，说说"最冷的一天"排到了哪里。',
    quiz: [
      {
        q: '−2x ＜ 6 的解集是？',
        options: [
          { text: 'x ＜ −3', why: '不对：两边同除以 −2，不等号方向必须反过来。' },
          { text: 'x ＞ −3', why: '正确：两边同除以 −2，6 ÷ (−2) = −3，不等号反向。', correct: true },
          { text: 'x ＞ 3', why: '不对：6 ÷ (−2) = −3，不是 3。' }
        ]
      },
      {
        q: '若 a ＜ b 且 c ＜ 0，则 ac 与 bc 的大小关系是？',
        options: [
          { text: 'ac ＜ bc', why: '不对：乘负数时顺序反转，这个选项对应 c ＞ 0。' },
          { text: 'ac ＞ bc', why: '正确：两边同乘负数，大小关系反转。', correct: true },
          { text: '无法确定', why: '不对：c 的符号已经给定，方向是确定的。' }
        ]
      }
    ],
    presets: [
      { label: 'a = 2', value: 2 },
      { label: 'a = −0.5', value: -0.5 },
      { label: 'a = −2', value: -2 },
      { label: 'a = 0', value: 0 }
    ],
    stageLabel: '原关系：3 ＜ 5',
    control: { min: -3, max: 3, step: 0.5, value: -2, label: '拖动乘数 a', hint: '−3 至 3' },
    takeaway: '乘正数只是缩放，乘负数会镜像：顺序反转不是口诀，是数轴翻了个面。'
  },
  {
    id: 'budget',
    index: '02',
    field: '经济 · 班务',
    title: '活动预算的两个方案',
    hook: '同样的活动，A 店收 9 元固定费 + 每份 2 元，B 店收 3 元固定费 + 每份 4 元，怎么选？',
    subtitle: '两个一次式比大小，交点就是分界点。',
    minutes: 7,
    knowledge: ['K-09'],
    nodes: ['C-021'],
    question: '参与人数变化时，哪个方案更省钱？分界点在哪里？',
    context:
      '班级要订做活动材料。A 店报价 9 + 2n 元，B 店报价 3 + 4n 元（n 为份数）。固定费不同、单价也不同，所以"哪家便宜"取决于你订多少份——这正是两个一次式的比大小。',
    model:
      '令 9 + 2n = 3 + 4n，解得 n = 3，这是费用相同的分界点；n ＞ 3 时 A 更便宜，n ＜ 3 时 B 更便宜。若再加一条"总预算不超过 30 元"，则 A 最多 10 份（n ≤ 10.5），B 最多 6 份（n ≤ 6.75），份数还要取整数。',
    steps: [
      '把人数依次调到 2、3、4，读出两条方案的费用。',
      '在第 3 人处停住，确认两种方案费用相同。',
      '加上 30 元预算的限制，算算两种方案各自最多能订几份。'
    ],
    checks: [
      { id: 'tie', text: 'n = 3 时两种方案费用相同（都是 15 元）。' },
      { id: 'left', text: 'n ＜ 3 时方案 B 更便宜。' },
      { id: 'right', text: 'n ＞ 3 时方案 A 更便宜。' },
      { id: 'cap', text: '预算 30 元时，A 最多 10 份、B 最多 6 份（取整数）。' }
    ],
    boundary:
      '模型的边界：真实报价常有阶梯价、满减或最低消费，一旦规则变化就要重算；人数、份数在现实中必须是整数，"n = 2.5 元"这种答案要回到情境里筛选。',
    transfer: '挑一件你班真实要买的东西，问两家报价，写出两个一次式，算出它们的交点并说明你选哪家。',
    quiz: [
      {
        q: '两个方案费用相同的份数是几份？',
        options: [
          { text: '2 份', why: '不对：代入得 A = 13 元、B = 11 元，并不相等。' },
          { text: '3 份', why: '正确：9 + 2 × 3 = 15，3 + 4 × 3 = 15。', correct: true },
          { text: '4 份', why: '不对：代入得 A = 17 元、B = 19 元，A 已经更便宜。' }
        ]
      },
      {
        q: '总预算 30 元时，按方案 A 最多能订几份？',
        options: [
          { text: '9 份', why: '不对：9 + 2 × 9 = 27 元，第 10 份仍只要 29 元。' },
          { text: '10 份', why: '正确：9 + 2 × 10 = 29 ≤ 30；11 份要 31 元。', correct: true },
          { text: '11 份', why: '不对：11 份需要 31 元，超过预算。' }
        ]
      }
    ],
    presets: [
      { label: 'n = 2', value: 2 },
      { label: 'n = 3', value: 3 },
      { label: 'n = 4', value: 4 },
      { label: 'n = 10', value: 10 }
    ],
    stageLabel: '方案 A：9 + 2n 元 · 方案 B：3 + 4n 元',
    control: { min: 1, max: 12, step: 1, value: 3, label: '拖动参与人数 n', hint: '1 至 12 份' },
    takeaway: '两个一次式谁大谁小，分界点就是它们的交点；把它写成不等式，才回答得了"最多能买几份"。'
  },
  {
    id: 'rental',
    index: '03',
    field: '生活消费 · 计算机',
    title: '共享充电宝的计费拐点',
    hook: 'A 柜机 2 小时内 6 元、之后每小时 3 元；B 柜机起步 2 元、每小时 4 元。借多久选哪个？',
    subtitle: '先用方程找等费点，再用分段函数读整段关系。',
    minutes: 8,
    knowledge: ['K-04', 'K-06'],
    nodes: ['C-011'],
    question: '两种计费方式在什么时候一样贵？什么时候该换一家？',
    context:
      '手机没电时，两排柜机就在眼前：A 柜机 2 小时内一律 6 元，超过 2 小时后每小时再加 3 元；B 柜机起步 2 元，之后每小时 4 元。这不是"哪家更贵"，而是"借多久才算得出来"。',
    model:
      'A(h) = 6（h ≤ 2），A(h) = 6 + 3(h − 2)（h ＞ 2）；B(h) = 2 + 4h。令 6 = 2 + 4h，得 h = 1：借 1 小时两家都是 6 元；不到 1 小时选 B，超过 1 小时选 A。超过 2 小时后 A(h) = 3h，始终比 B 便宜。',
    steps: [
      '把时长调到 1 小时，确认两种计费显示相同金额。',
      '调到 0.5 小时和 4 小时，分别记下哪家更便宜、差多少。',
      '找到 A 的"跳档点"（2 小时），说明为什么这里是分段点。'
    ],
    checks: [
      { id: 'tie', text: 'h = 1 时两种计费相等，都是 6 元。' },
      { id: 'short', text: 'h ＜ 1 时 B 更便宜。' },
      { id: 'long', text: 'h ＞ 1 时 A 更便宜，差额随时长扩大。' },
      { id: 'break', text: 'h = 2 是 A 的分段点：2 小时以内是固定价。' }
    ],
    boundary:
      '模型的边界：真实计费常以 30 分钟或整小时为单位向上取整，还可能收押金或芝麻信用免押；"更便宜"不等于"更划算"，归还点远近、可借数量都影响选择。',
    transfer: '记录一次真实的借用时长，用两个模型各算一遍，写出你下次会选哪家、为什么。',
    quiz: [
      {
        q: '两种计费相等时，借用时长是多少？',
        options: [
          { text: '0.5 小时', why: '不对：此时 A = 6 元、B = 4 元，B 便宜。' },
          { text: '1 小时', why: '正确：6 = 2 + 4 × 1，两边都是 6 元。', correct: true },
          { text: '2 小时', why: '不对：此时 A = 6 元、B = 10 元，A 更便宜。' }
        ]
      },
      {
        q: '借 4 小时，哪家更便宜？',
        options: [
          { text: 'A 便宜 6 元', why: '正确：A = 6 + 3 × 2 = 12 元，B = 2 + 4 × 4 = 18 元。', correct: true },
          { text: 'B 便宜 6 元', why: '不对：4 小时已经超过等费点，A 更便宜。' },
          { text: '两家一样', why: '不对：只有 1 小时时两家才相同。' }
        ]
      }
    ],
    presets: [
      { label: 'h = 0.5', value: 0.5 },
      { label: 'h = 1', value: 1 },
      { label: 'h = 2', value: 2 },
      { label: 'h = 4', value: 4 }
    ],
    stageLabel: 'A：2 小时内 6 元，之后 3 元/时 · B：2 元 + 4 元/时',
    control: { min: 0, max: 6, step: 0.5, value: 2, label: '拖动借用时长 h', hint: '0 至 6 小时' },
    takeaway: '分段计费先找等费点，再看每一段里谁增长得快——这就是"先列方程，再读函数"的思路。'
  },
  {
    id: 'window',
    index: '04',
    field: '时间管理 · 体育',
    title: '两个人的共同空闲',
    hook: '甲说"我 15 点后到 18 点有空"，乙说"我 14 点到 17 点有空"，他们能约上吗？',
    subtitle: '两个时间范围取交集，可能是一段、一点，也可能没有。',
    minutes: 6,
    knowledge: ['K-08'],
    nodes: ['C-020'],
    question: '两个"有空"的范围放在一起，还剩下哪些时段？',
    context:
      '约训练、约讨论、约还书，都要先看两个人的空闲能不能对上。甲的空闲是从某个时刻到 18 点，乙的空闲是从 14 点到某个时刻；把它们画在同一根时间轴上，重叠的部分才是"都能到"的时间。',
    model:
      '甲的空闲是 [s, 18]，乙的是 [14, e]。共同时间是 [max(s, 14), min(18, e)]：起点取晚的那个，终点取早的那个。两个端点相等时只剩一个时刻，起点超过终点时没有公共时间。',
    steps: [
      '把甲的开始时间调到 15 点、乙的结束时间调到 17 点，读出交集。',
      '把甲的起点推到 18 点，观察交集缩成一个时刻。',
      '再让乙在 18 点前结束，观察交集变成空集。'
    ],
    checks: [
      { id: 'interval', text: '两个区间有重叠时，交集仍是一段区间。' },
      { id: 'point', text: '端点刚好相接时，交集只剩下一个时刻。' },
      { id: 'empty', text: '起点晚于终点时，交集为空，约不上。' }
    ],
    boundary:
      '模型的边界：时间按整点近似，真实约见还要留出路程与缓冲；"有空"不等于"愿意"，也不等于"场地可用"。交集只回答"时间上有没有可能"。',
    transfer: '收集三位同学的空闲区间，找出三个人都能到的时段；如果没有，说明最少要改动谁的时间。',
    quiz: [
      {
        q: '交集为空说明什么？',
        options: [
          { text: '两个人都没空', why: '不对：各自都有一段时间，只是没有重叠。' },
          { text: '没有共同可用的时段', why: '正确：空集表示两条范围没有公共部分，需要有人改时间。', correct: true },
          { text: '一定有一方记错了时间', why: '不对：时间都可能正确，只是刚好错开。' }
        ]
      },
      {
        q: '甲的起点是 18 点、乙的结束时间是 18 点，交集是什么？',
        options: [
          { text: '一整段 18 点到 18 点', why: '不对：起点与终点相同，长度为零。' },
          { text: '只剩 18 点这一刻', why: '正确：两个范围只在 18 点相接，交集是一个单点。', correct: true },
          { text: '空集', why: '不对：18 点同时落在两个范围里。' }
        ]
      }
    ],
    presets: [
      { label: '15—17', value: { s: 15, e: 17 } },
      { label: '18—18', value: { s: 18, e: 18 } },
      { label: '18—16', value: { s: 18, e: 16 } },
      { label: '12—20', value: { s: 12, e: 20 } }
    ],
    stageLabel: '甲：从起点到 18 点 · 乙：从 14 点到终点',
    control: { min: 12, max: 18, step: 1, value: 15, label: '甲的起点', hint: '12 至 18 点' },
    control2: { min: 14, max: 20, step: 1, value: 17, label: '乙的终点', hint: '14 至 20 点' },
    takeaway: '两个范围求交集：起点取晚的、终点取早的；一旦起点晚于终点，就只剩"约不上"这一个结论。'
  }
];

export const labById = id => exploreLabs.find(lab => lab.id === id);

export function mirrorModel(a) {
  const x = 3 * a, y = 5 * a;
  const order = a > 0 ? 'keep' : a < 0 ? 'reverse' : 'collapse';
  const text = a > 0
    ? `乘以正数 ${num(a)} 只是缩放：${num(x)} ＜ ${num(y)}，顺序保留。`
    : a < 0
      ? `乘以负数 ${num(a)} 相当于关于原点镜像：${num(x)} ＞ ${num(y)}，顺序反转。`
      : '乘以 0 后两个点都落在原点，严格的大小关系消失，也不能用除以 0 逆推。';
  return { a, x, y, order, relation: a > 0 ? '<' : a < 0 ? '>' : '=', text };
}

export function budgetModel(n) {
  const a = 9 + 2 * n, b = 3 + 4 * n;
  const cheaper = a < b ? 'A' : a > b ? 'B' : 'tie';
  const text = a === b
    ? `${n} 份时两种方案同为 ${a} 元；交点满足 9 + 2n = 3 + 4n，即 n = 3。`
    : `${n} 份时方案 ${cheaper} 便宜 ${Math.abs(a - b)} 元；n ＞ 3 选 A，n ＜ 3 选 B。`;
  return {
    n, a, b, cheaper, diff: Math.abs(a - b),
    tieAt: 3, cap: 30,
    affordableA: Math.floor((30 - 9) / 2),
    affordableB: Math.floor((30 - 3) / 4),
    text
  };
}

export function rentalModel(h) {
  const a = h <= 2 ? 6 : 6 + 3 * (h - 2);
  const b = 2 + 4 * h;
  const cheaper = a < b ? 'A' : a > b ? 'B' : 'tie';
  const text = a === b
    ? `借 ${num(h)} 小时：两种计费都是 ${num(a)} 元；等费点满足 6 = 2 + 4h，即 h = 1。`
    : `借 ${num(h)} 小时：A 收 ${num(a)} 元，B 收 ${num(b)} 元，${cheaper} 便宜 ${num(Math.abs(a - b))} 元。`;
  return { h, a, b, cheaper, diff: Math.abs(a - b), tieAt: 1, breakAt: 2, text };
}

export function windowModel(s, e) {
  const low = Math.max(s, 14), high = Math.min(18, e);
  const kind = low > high ? 'empty' : low === high ? 'point' : 'interval';
  const text = kind === 'empty'
    ? `甲最早 ${s} 点才有空，而乙 ${e} 点前必须结束：起点晚于终点，没有公共时间。`
    : kind === 'point'
      ? `两个范围只在 ${low} 点相接，交集是一个单点：只能约在 ${low} 点这一刻。`
      : `公共时间是 ${low} — ${high} 点，共 ${high - low} 小时；起点取较晚的 ${low}，终点取较早的 ${high}。`;
  return { s, e, low, high, kind, text };
}

export function labModel(id, params) {
  if (id === 'mirror') return mirrorModel(Number(params));
  if (id === 'budget') return budgetModel(Number(params));
  if (id === 'rental') return rentalModel(Number(params));
  if (id === 'window') return windowModel(Number(params.s), Number(params.e));
  throw new Error(`unknown lab: ${id}`);
}

export function exploreKey(datasetId, studentId, labId) {
  return `${datasetId}|${studentId}|${labId}`;
}

export function emptyExploreRecord() {
  return { checks: [], answers: {}, transfer: '', updated_at: '' };
}

function cleanRecord(value) {
  const base = emptyExploreRecord();
  if (!value || typeof value !== 'object' || Array.isArray(value)) return base;
  const checks = Array.isArray(value.checks)
    ? value.checks.filter(id => typeof id === 'string')
    : [];
  const answers = {};
  if (value.answers && typeof value.answers === 'object' && !Array.isArray(value.answers)) {
    for (const [key, choice] of Object.entries(value.answers)) {
      const index = Number(choice);
      if (Number.isInteger(index) && index >= 0 && index < 8 && /^\d+$/.test(key)) answers[key] = index;
    }
  }
  const transfer = typeof value.transfer === 'string' ? value.transfer.slice(0, 2000) : '';
  const updated = typeof value.updated_at === 'string' ? value.updated_at : '';
  return { checks: [...new Set(checks)], answers, transfer, updated_at: updated };
}

export function parseExploreStore(raw) {
  const empty = { version: EXPLORE_VERSION, records: {} };
  let parsed = raw;
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return empty;
    }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return empty;
  if (Number(parsed.version) !== EXPLORE_VERSION) return empty;
  const source = parsed.records;
  if (!source || typeof source !== 'object' || Array.isArray(source)) return empty;
  const records = {};
  for (const [key, value] of Object.entries(source)) {
    if (typeof key !== 'string' || !key.includes('|')) continue;
    records[key] = cleanRecord(value);
  }
  return { version: EXPLORE_VERSION, records };
}

export function labProgress(record, lab) {
  const checksTotal = lab.checks.length;
  const known = new Set(lab.checks.map(item => item.id));
  const checks = (record?.checks || []).filter(id => known.has(id)).length;
  const quizTotal = lab.quiz.length;
  const answers = record?.answers || {};
  const correct = lab.quiz.filter((item, index) => {
    const choice = answers[String(index)];
    return Number.isInteger(choice) && !!item.options[choice]?.correct;
  }).length;
  return {
    checks, checksTotal, correct, quizTotal,
    // The checklist is a reading aid; only the self-check decides completion.
    done: correct === quizTotal
  };
}

export function exploreSummary(store, datasetId, studentId) {
  const labs = exploreLabs.map(lab => {
    const record = store.records[exploreKey(datasetId, studentId, lab.id)] || emptyExploreRecord();
    return { lab, record, progress: labProgress(record, lab) };
  });
  return { labs, done: labs.filter(item => item.progress.done).length, total: labs.length };
}
