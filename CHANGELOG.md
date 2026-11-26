# 变更记录

记录**会影响他人**的改动：改了什么、为什么、怎么验证、怎么回退。
`git log` 是逐提交流水；这里只记「一个可交付的最小单元」，供回溯、交接，以及答辩时讲"我们是怎么迭代的"。

- **方向**：最新在最上（第一条 `---` 之后）；同日"后发生在前"。
- **粒度**：一个 PR / 一组相关改动一条；纯措辞、格式化不必记。
- **长度**：每条 ≤ 15 行。论证细节放 PR 正文，这里只留结论与证据。
- **没验证就写"未验证"**，不要留空。

---

## 2026-11-26 — 动画默认开启，不再由系统「减少动效」拦截

- 根因：原实现把系统设置当总开关——Windows 关闭「动画效果」→ 浏览器上报 `prefers-reduced-motion: reduce` → 三处各自关闭：`knowledge-map.js` 的 `dynamic`（空闲漂移/相机补间/拖拽物理）、`styles.css` 的全局 `animation/transition: none !important`、`motion.css` 整份包在 `@media (no-preference)` 里。演示机上因此整页静态，且界面上没有任何入口能打开。
- 口径改为「默认播放，按需关闭」：`theme-boot.js` 默认给 `<html>` 挂 `kf-force-motion`，只有本机显式关闭时才不挂；`kfMotionAllowed()` 成为脚本侧唯一判定（`app.js` 主题切换、`knowledge-map.js`、`course-stories.mjs` 共用）。关闭入口：设置 → 显示 →「关闭」（存 `localStorage['knowflow.motion']='off'`）或 `?motion=0`；`?motion=1` 恢复默认。
- 拖拽联动与动效开关解耦：`knowledge-map.js` 的 `wake()` 不再受 `dynamic` 约束——拖动模块/知识点时子节点被弹簧带走属于直接操作反馈，任何设置下都生效。
- 样式：`styles.css` / `theme.css` / `login.css` 的 reduce 守卫加 `html:not(.kf-force-motion)`；`knowledge-map.css` 在 shadow root 内改用 `:host(:not(.force-motion))`；`motion.css` 去掉 `@media (no-preference)` 包裹，默认关闭改由上述 blanket 守卫负责（登录页不加载 styles.css，故自带一份）。
- 无障碍代价：偏好「减少动效」的用户现在也会看到动画，需要自己关一次（本机记住）。这是为演示可见性做的取舍，不是遗漏。
- 验证：`node --test tests/web/*.test.mjs` 29 项通过（含 9 项动效策略）；`pytest` 454 项、`ruff` 通过。真实浏览器（Edge headless，系统动画关闭、`reduce=true`）实测：全新环境不登录直接进导图即 `kf-force-motion`、`::before` 为 `map-ambient-glow`、节点 2.5s 位移约 14px；设置点「关闭」后 `transform` 两次采样完全相同、动画名 `none`、`localStorage=off`；再点「始终开启（默认）」恢复移动并清空存储。
- 回退：还原 6 个静态文件、`server.py` 的登录跳转与 `tests/web/motion-override.test.mjs`。

---

## 2026-11-26 — 事实审计与多轮隔离

**本机未提交** · 建议分支 `feat/chat-fact-audit`

- ① 中文数字进审计（A）：`audit.py` 新增 `parse_chinese_number` / `chinese_number_tokens`，解析后复用同一个 `classify_number` 判语境。支持四十三 / 一百零五 / 两千零二十六 / 百分之二十三 / 三分之二；模糊数量（十几 / 几十 / 百余）与解析失败的"一两"不得作为精确事实；序数、一方面、建议十人一组不误报。
- ② 历史隔离（D）：删除"上一轮回答里的数字进白名单"；system 增加 `HISTORY_RULE`，真实 `complete_messages` 与单轮兜底两条路径同时生效；事实卡新增 `dialogue`（指代 / 冲突 / 用户补充 / clarify）。用户数字只在带"你说的、你补充的"归属时放行，用户补充不算数据库更新。
- ③ 零记录缺口（G）：`_knowledge_rows` 增 `unknown = insufficient + unobserved`（已核对状态桶互斥，`not_applicable` 不计入）；新增 `no_record` 与 `_gap_sentence`，兜底不再漏掉"完全没有作答记录"的知识点，仍只给一个判断、一个动作。
- ④ 结构化验收（F）：`tests/diagnosis/test_acceptance.py` 分五类（数据提取 7 / 统计口径 6 / 表达 4 / 数字审计 4 / 实体引用 3），`acceptance_support.py` 是 B 的原型检查器，`scripts/check_acceptance.py` 按类输出通过数。
- ⑤ 顺带收紧两处旧漏洞：百分比换算只在数字确实写成百分数时生效（否则 0.17 会放行"17 人"）；白名单不再预置 1/2/3/5（"有 3 人薄弱"不再无条件通过）。
- 验证：`pytest` 440 passed + 1 xfailed、`ruff`、`check_contracts`、`check_examples` 通过；`scripts/check_acceptance.py` 五类全 PASS；真实快照六条验收 0/6（规则与真实模型各跑一遍）。
- 未验证 / 已知缺口：B 只做设计，运行时仍放行"K-06 有 19 人薄弱"（以 xfail 记录）；中文数字只到"万"，"千万"按语气词处理；用户补充与数据库记录的合并口径未定义。
- 回退：还原 `llm/audit.py`、`llm/chat.py`、新增测试与脚本，以及 CHANGELOG/AGENT/README 三处文档。

---

## 2026-11-26 — 学情对话：意图识别、信号区分与兜底重写

**本机未提交** · 建议分支 `feat/chat-teaching-analysis`

- ① 意图识别：新增 `llm/intent.py`（7 类意图 + 复合意图 + 提问形式 + 学科问题标记）。只给**主意图**的分析重点，避免"班级分层指南"叠到单个学生问题上；数据查询类显式要求"只回答数据本身"。
- ② 事实卡改结构：`weak_signal` 与 `evidence_gap` 分开（旧的 `weak+insufficient` 合并排序把 K-06 排在 K-05 前面）；补 `tiers`（注明"不是能力分层"）、`groups`（描述性差异）、`timeline`（注明跨节点不等于进步）、`focus`、`lookup`；知识点带组成计数与短名。
- ③ 数字审计重构为 `llm/audit.py`：按语境分「学情数字 / 教学数字 / 建议数量 / 待核」；数据词判定从整句收到数字附近。修复真实误杀——"开场用 10 分钟做小测…36 名证据不足"里的 10 分钟曾被判为编造数据（该次回答被弃用后重写更差）。反向收紧三处：`约/不到` 只对邻近数字放宽（`41 人` 不再借用同句的"不到"）；"×100" 百分比换算只对 0<x≤1 的比率生效（此前事实卡里有个 10，`999 人` 就能按"999% of 10"过关）；新增绝对化结论检查——事实卡还有证据缺口时拒收"全班都没掌握/都掌握"，带"不能说……"限定语的说法放行。
- ④ 兜底重写：按意图组合作答（查询一问一答、是/否正面回答、策略分"先补证据/直接巩固"），不再输出 `ALL` 与 `M-` 编号；证据模式的"结论/依据"保留。
- ⑤ 失败可分类：`trace.guard` 增 `intent`/`failure_kind`/`problems`/`attempts`，`note` 区分模型不可达、数字、编号、越界结论与格式，重写提示按类型给。
- ⑥ 冲突修正：证据模式给数据查询硬套"依据"（"全班 40 人 / 依据：当前数据只有课程映射"）→ 单事实回答不再套两段；"有多少人掌握"没指明知识点时按班级人数作答 → 改为回"这个数查不到，请指明知识点或学生"；学科问题（"K-07 怎么算"）复用知识点分析指南 → 改用独立 `TEACH_GUIDE`；生源无适用知识点时输出"已观察到 0/0" → 改为"这个节点还没有可判断的记录"。
- 验证：`pytest` 372 项、`ruff`、`check_contracts`、`check_examples` 通过；真实快照上 `scripts/chat_acceptance.py --path rules` 与 `--path live` 均 0/6 未通过。规则路径由"六条问题同一段模板"变为六种回答；模型路径 E 从"40 人 + 整段分析"变为一句，C 从误判回退变为直接作答。
- 未验证：① 白名单只能证明数字“在事实卡里存在”，不能证明它被挂在了正确的对象上；本轮六条验收未出现错挂，但机制上不保证。② 模型偶尔仍用“证据不足”统称“有评分但太少”和“一条记录都没有”两种缺口（如“用整式解释具体问题 40 人全部证据不足”，实际是 11 人证据不足 + 29 人无记录），提示词已要求分开说，但不保证。③ 学生视角与多轮下的真实模型未逐条复核。
- 回退：删除 `llm/intent.py`、`llm/audit.py`、`scripts/chat_acceptance.py` 与新增测试，恢复 `llm/chat.py`；事实卡与前端协议不变。

---

## 2026-11-26 — 学生知识地图图例对应掌握程度

- 仅个人学情导图将章节色图例替换为节点状态图例，共用节点色表，说明连线与外圈代表章节。
- 教师端继续显示原有三类章节图例；新增布局样式限定在个人图例内。
- 验证：JavaScript 语法、差异检查通过，浏览器核对学生端图例文字、颜色及布局。
- 回退：还原 knowledge-map.js 的个人图例分支和 knowledge-map.css 的个人图例样式。

---

## 2026-11-26 — 作答统计同步橙绿语义配色

- 个人与班级作答图统一满分橙色、部分得分浅绿、零分深绿；待评分和未作答使用中性色。
- 数据质量的观测状态图共用同一色表，按状态名取色，避免对象字段顺序影响颜色。
- 验证：JavaScript 语法和差异检查通过；浏览器刷新核对学生“本次作答”图表及图例。
- 回退：还原 app.js 的作答色表及引用即可，不涉及统计计算与数据变更。

---

## 2026-11-26 — 统一掌握程度的下游展示与建议

- 班级诊断、个人画像、知识地图、状态徽章和统计说明统一掌握／较好／较差／薄弱名称与深浅橙绿配色。
- 建议、AI 事实摘要及训练选题纳入较差；较好不再一律解释为全对，待评分／核验与未覆盖分别处理。
- 设置页读取真实分类计数，保存后重建；主题汇总分开未覆盖和待评分，历史混合状态保留兼容。
- 同步接口说明、生成产物说明和旧训练卷口径，补充下游分类、训练排序及图表回归用例。
- 验证：307 项 Python 测试通过、4 项跳过；20 项前端测试、Ruff、契约及合成样例检查通过；本地数据重建并核对班级诊断、个人画像和设置页面。
- 回退：还原本条下游逻辑、展示与主题状态契约改动，重新生成本地诊断及建议。

---

## 2026-11-26 — 混合答题结果按对错数量分类

- 达到证据门槛后，保留掌握／薄弱判定；其余按对数≥错数判较好、错数更多判较差，部分得分仍计入错误或扣分。
- 覆盖 2 对 1 错、1 对 1 错为好及 1 对 2 错为差；保留实际失分点的巩固建议。
- 交换较好／较差颜色：较好橙色、较差绿色；同步热力图、知识地图和状态徽章。
- 验证：300 项 Python 测试通过、4 项跳过，契约、样例、Ruff 与 JavaScript 语法检查通过；本地数据重建校验通过。
- 回退：还原本条分类、配色及合约说明并重建本地数据。

---

## 2026-11-26 — 稀疏评分按错误数显示较好／较差

- 0<n<证据门槛时，全对为 sparse_good（较好），有错误或扣分为 sparse_poor（较差）；门槛以上保留原诊断规则，未评分不判好坏。
- 同步画像、班级分布、先修排序、学习建议、LLM 摘要和图表；图例改为掌握／薄弱，较好与较差单列计数。
- 更新状态枚举、班级计数合约与 fixtures；已有输出需重建，原始评分不改动。
- 验证：297 项 Python 测试通过、4 项跳过；18 项前端测试、契约、样例与 Ruff 通过；本机数据重建校验通过，并在浏览器检查热力图及一次答对详情。
- 回退：还原本条代码和合约变更后重建本机画像与建议。

---

## 2026-11-26 — 完善知识地图与分步教学动画

- 为知识点提供连续的 SVG 分步图解、播放控制和按内容密度调整的阅读时间；补充语义图形与阅读时长测试。
- 增加缓慢轨道运动、空白处返回全图及动画清理，整理课程导航和知识详情中的学生列表滚动区域。
- 验证：18 项前端测试、Python 全套测试（4 项跳过）、契约/样例检查与 Ruff 通过；本轮未进行浏览器视觉复验。
- 回退：还原本条前端及测试变更，课程数据与诊断产物不变。

---

## 2026-11-25 — 减少地图动画重复更新

- 相同节点集合下复用 SVG 元素；镜头运动仅更新整体变换，几何更新只处理实际变化的节点与路径。
- 合并高频拖拽/滚轮事件；弹性计算复用当前节点集合，最多约 30 次/秒，稳定后停止。切换节点不再重新激活弹性计算，镜头运动期间暂停物理更新。
- 镜头过渡缩短为 420ms，保留居中、连续切换、拖拽与重置。
- 离线 Edge 受控帧对比：同一次节点切换 SVG 属性变更 4813 → 52，子节点列表变更 52 → 0，节点元素得到复用；该指标不是在线 FPS。
- 验证：16 项前端测试、21 项图谱测试、契约/样例通过；离线浏览器检查居中、快速切换、100 次拖拽事件合并、点击抑制与重置。未测当前在线会话真实帧率。
- 回退：还原本条地图渲染与调度改动，教学和诊断数据不变。

---

## 2026-11-25 — 修正节点居中与缩放轨迹

- 聚焦目标从类别范围改为选中节点，节点切换保持一致尺度；固定当前选中点，避免动态布局使其偏离中心。
- 面板展开时补偿画布尺寸，保留原屏幕位置；平移与缩放按屏幕变换插值，避免偏移、绕行及重复尺寸观察打断动画。
- 验证：16 项前端测试、21 项图谱测试、契约/样例检查通过。离线 Edge 受控帧检查整式加减/代入求值居中、连续切换、面板展开无瞬移及动态布局开启后的中心稳定，并核对截图；未核验在线真实帧率。
- 回退：还原本条镜头与视口补偿逻辑，课程内容和诊断不变。

---

## 2026-11-25 — 圆形知识节点与平滑聚焦

- 知识点改为圆形节点，在三类知识中心周围等角度展开；标签按方位上下排布，更新斥力间距并隔离旧矩形布局缓存。
- 点击节点、收起讲解与返回全图增加约 650ms 缓动缩放和平移；手动拖拽/缩放可中断，减弱动态偏好下直接定位。
- 验证：14 项前端测试、21 项图谱测试及契约/样例检查通过；离线 Edge 使用受控帧调度检查缩放中间态、圆节点与全部图解，核对总览截图。未核验在线会话的真实帧率。
- 回退：还原本条布局、圆节点样式和镜头动画；课程内容与学情数据不变。

---

## 2026-11-25 — 恢复知识地图动态拖拽

- 恢复节点与类别拖拽、连线实时跟随及邻居弹性移动；保留分类结构和右侧 SVG 讲解。
- 提供动态布局开关、重置及本浏览器位置保存；暂停时仍可手动拖动，减弱动态效果偏好下默认暂停。
- 区分拖动与点击，拖动松手不误开讲解；退出地图时停止动画。
- 验证：13 项前端测试、21 项图谱测试、契约及样例检查通过；离线 Edge 验证拖拽、点击抑制、暂停恢复、复位及全部 21 个图解。未核验当前在线会话。
- 回退：还原本条地图交互及分类弹性计算变更，正式数据不受影响。

---

## 2026-11-25 — 分类辐射图谱与节点图解

- 按反馈移除「探索脉络」入口，以课程中心、三大类别和 21 个知识点构成稳定辐射图；取消力导向布局与演示关系编辑。
- 点击节点在右侧展示 SVG 形象化讲解；全部节点覆盖积木、规则机器、天平、交点、消元或数轴，支持分步演示与滑杆操作。
- 教材、学情、补充训练与正式关系保留在折叠区域；分类连线不作为先修关系，图解不改写学情。
- 验证：12 项前端测试、21 项课程图谱测试、22 schemas 与 10 表样例检查通过；离线 Edge 验证 21 个图解、步骤控制、筛选、搜索、列表和复位，并核对总览与详情截图。
- 未验证：当前在线会话与真实触屏操作；本轮未重复运行上轮已确认受 WinError 10013 限制的 HTTP 测试。
- 回退：还原本条地图、样式及图解模块修改；正式图谱与诊断数据未变。

---

## 2026-11-25 — 课程知识探索脉络

- 重写 21 个节点的教学展示内容，以表达、求解、联立、决策四条主线组织；默认分层路径与节点阅读区，保留正式网络和列表。
- 每个节点含核心问题、概念解释、例子、易错边界、自测答案、跨节点联系及选读拓展；加入三个可操作 SVG 实验。
- 自编探索内容独立于正式图谱，继续按原节点关联教材、指标与学情；不改变正式关系、掌握度或诊断证据。
- 新增静态模块路由，运行中的服务需重启一次。
- 验证：11 项前端测试、契约与样例检查、JS 语法及 Python 修改文件 Ruff 通过；离线 Edge 验证全部节点、实验、搜索、筛选、视图切换与跳转。
- Python 回归 245 通过、4 跳过；7 项 HTTP 测试因环境套接字权限 WinError 10013 失败。当前页面连接与原生浏览器通道不可用，未完成在线集成核验。
- 回退：还原本条页面、静态路由与新增内容模块；正式图谱和诊断数据未变。

---

## 2026-11-26 — 待观察瘦身：把"未覆盖"从"证据不足"里拆出来

**本机未提交** · `feat/coverage-vs-evidence`

- ① 新状态 `unobserved`：有可测题但 0 条已评分且无待评分 → 进新桶 `lists.needs_coverage`；`insufficient_evidence` 只保留"有评分但不足门槛 / 已作答待评分"。
- ② 动作与状态解耦：`diagnosis/evidence.py::evidence_action` 成为六档动作的唯一出处，写进 `knowledge_states[].evidence_action`，诊断层、建议层、语言层共用；`rules._sparse_action` 改为读它。
- ③ 语言层不再被状态绑架：`llm_summary.facts` 传 `evidence_action`；prompt 第 4 条从"只能建议补充观测"改为按动作分档；`integrate._advice_conflict` 拒绝把巩固项改写成只补观测。
- ④ 班级分层：`mixed_performance` 优先于"补观测"（有失分点可查 > 题太少），新增 `cover` 档；`knowledge_distribution` 增 `unobserved_count`，`coverage_summary` 增 `students_with_coverage_gap`。
- ⑤ 设置解耦：`min_evidence` 从 `coverage_missing` 拆成独立项，改覆盖率显示阈值不再改变诊断结论。
- ⑥ 门槛 3→2：`min_evidence` 默认改为 2，`rules.MIN_EVIDENCE` 改为从 `DiagnosisConfig` 读取（此前是硬编码 3，改设置会让文案说错数字）。依据：2 条证据在任何组合下都到不了 `confirmation_probability=0.9`，只会得到 `likely_*`/`mixed_performance`，不会冒充"已确认"；1 条不作数（答错一题就给 likely_weak 站不住）。题量本身少于门槛的知识点，`status_reason` 明确写"题目本身不足"，不归因于学生。
- 效果（官方数据 80 个画像 / 521 个可测状态）：待观察 77.7%→**25.0%**、人均 5.06→**1.62**、有待观察的学生 80/80→67/80；班级"补充观测" N01 26→4、N02 31→2；建议里"补充观测"类文案 64→0，"建立基线"70。`confirmed_*` 数量未增加（仍 2 条），说明没有靠放宽确认门槛凑数。
- 验证：`pytest` 294 项、`ruff` 通过；`prepare` 重建真实快照，诊断与建议两个 gate 均 pass；`/api/snapshot` 实测服务端已返回新口径。
- 回退：还原 `diagnosis/{mastery,profiles,validation}.py`、删除 `diagnosis/evidence.py`、`recommend/rules.py`、`llm/{summary,prompt,integrate}.py`、两个 schema 与前端图例。

---

## 2026-11-25 — 稀疏观测下的建议：后验、子状态与层级先验

**本机未提交** · `feat/sparse-recommendation`

- ① 后验接进决策：`rules._sparse_action` 用 `weak_probability/mastered_probability` 把“证据不足”拆成梯度——后验 ≥60% 薄弱 → 低置信度巩固，≥40% 已掌握 → 轻量复核，中间 → 继续观测；`_priority/_reason/_check` 相应分档。
- ② 区分稀疏子状态：0 观测 / 已布置未作答 / 已作答待评分（defer）各有文案，不再统一“补 3 题”。
- ③ 层级先验：`_prior_risk` 用 reviewed 先修 + 同主题平均表现给 0 观测知识点先验风险，参与排序并写入理由。
- `allowed_numbers` 纳入后验概率（含百分比写法），否则“约 64%”会被数字锁误杀。
- 效果（真实 N02，40 人）：巩固项 34→69、补观测 65→41；“稀疏薄弱→巩固”43、“先验风险”17、“稀疏已掌握”5、“稀疏中间”4。
- 验证：`pytest` 285 项、`ruff` 通过；`recommend --node N02` 真实数据 gate=pass。
- 未验证：`audience=student` 端到端；先修先验（真实图谱无 reviewed 边，仅单测覆盖）。
- 回退：还原 `rules.py`（`_sparse_action/_prior_risk/_reason/_check/_plan_item/recommend_profile`）、`validation.py::allowed_numbers` 与相关测试。

---

## 2026-11-25 — 交互契约：行为红线同源 + 受众（第二档）

**本机未提交** · `feat/contract-behavior-audience`

- 行为红线单一来源：`MUST_NOT_INFER`（5 条）与 `BOUNDARY_NOTE` 迁到 `llm/contract.py`；`summary.py`、`prompt.py`、`chat.py` 三处经 `forbidden_text()` 同源注入，两条路径的“出门声明”收拢到一处。
- 推荐路径补受众：`build_issue_summary` / `explain_student` 增 `audience`（默认 teacher），写进 `llm_summary`（schema 增 `audience` 枚举）；prompt 按 audience 决定语气与是否给答案。
- 新增 `tests/diagnosis/test_contract.py`：红线共享、材料漂移、answer_key 权限、audience 透传。
- 验证：`pytest` 283 项、`ruff` 通过；真实 `explain` 返回 `source=llm`、`attempts=1`、summary 带 `audience=teacher`。
- 未验证：`audience=student` 的真实调用（仅单测）；`explain` 独立工具仍按“解释单题”给出全部相关材料（无计划可漂移，属预期）。
- 回退：还原 `contract.py`/`summary.py`/`prompt.py`/`chat.py`/`explain.py` 与 schema、`test_contract.py`。

---

## 2026-11-25 — 建议语言层：决策/语言边界与契约修复（第一档）

**本机未提交** · `fix/recommend-text-boundary`

- 决策/语言边界落成代码：新增 `llm/contract.py`（`material_drift`、`answer_key_visible`）；语言层只能引用计划已选材料，否则回退模板。
- `check`（完成门槛）不再交给模型改写：`integrate.py` 只改 `reason`，`check` 保持 `rules.py` 确定性文案——修掉“证据门槛 3→1”与“材料漂移 22%”两类越权。
- 教师「换材料」后 reason/check 跟着新材料重生成（`feedback/apply.py` + `rules.refresh_item_wording`）；`verify-recommend` 新增“正文引用材料 ⊆ 计划材料”闸门。
- 契约实现矛盾：`llm_response.schema.json` 去掉 `numbers_used` 必填、`check` 改可选；`guard.py` 从正文抽数字不再比对 `numbers_used`；prompt 去掉 check/numbers_used、禁用掌握度小数、reason 上限 240。
- `answer_key` 权限抽到 `contract.answer_key_visible`，`retrieval.py` 复用。
- 验证：`pytest` 278 项、`ruff` 通过；真实 deepseek-chat 复跑 N02：回退率 27%→10%（89/99 改写）、材料漂移 0、六位小数 0、check 与模板一致。
- 未验证：其余节点 / 厂商端点。
- 回退：还原 `contract.py`/`guard.py`/`prompt.py`/`service.py`/`integrate.py`/`rules.py`/`validation.py`/`feedback/apply.py`/`pipeline.py` 与 schema、`test_llm.py`。

---

## 2026-11-25 — AI 学伴 P1/P2：能讲题、能追问、数字锁按数据主张判定

**本机未提交** · `feat/chat-teaching-p1p2`

- 讲不了题的根因：事实卡只有统计（`name/title`），65 份材料的正文/解析与 `objective_text` 从未发送。新增 `llm/retrieval.py`：按知识点名/ID/课标字面重叠打分，取课标原文 + 该主题学习卡 + 至多 2 道例题（题面/解析；学生端不含 `answer_key`）写入 `facts.sources`，总数 ≤5、单条 ≤220 字。
- 边界：学习者数据仍是聚合事实；课程内容来自已校验 `knowledge_base.json`，经 `create_server` 缓存并在 `/api/rebuild` 后刷新。`/api/snapshot` 体积不变（1.69 MB）。
- 提示词：区分 A 学习者数据（只能来自 FACTS）与 B 学科知识（可讲，可引用 sources，但不得据此编造学生数据）；补受众（学生/教师）、3 条语气示例、禁 Markdown、材料用 M- 编号；`temperature 0.6`、`max_tokens 700`、`MAX_ANSWER 1200`。
- 多轮：前端带最近 6 轮 `/api/chat` 的 `history`，后端 `normalize_history` 只收 `role/text`、单条 600 字、合计 2400 字；新增 `complete_messages`，历史作为独立轮次发送，注入式假客户端仍走单轮 `complete`。
- 校验：数字锁从“整段白名单”改为“数据主张”判定——人数/比例/掌握度/覆盖等语境的数字必须对得上事实卡（列表长度也算事实），教学数字（“14 道题”“第 12 周”）放行，“约”给更宽的四舍五入带宽；证据模式的“结论/依据”只提醒一次，不再因此丢弃内容。
- 其它：点名知识点即使不在默认 6 条状态里也会补进事实卡；规则兜底多套句式；前端去掉残留的 `**`。
- 验证：`pytest` 278 项、`ruff`、`node --check` 通过；真实 deepseek-chat 6/6 由模型回答（0.85–2.2 s）：`K-07 怎么算` 讲出变号规则并引用 M-057，`分数加减法` 给出通分方法，`你好` 正常寒暄，带 2 轮上文问“那第二个呢”正确落到 K-02；HTTP 端到端 `history_turns=2`、坏 `history` 返回 400。
- 未验证：浏览器内视觉走查（无头截图未重做）；教师端 `answer_key` 的真实调用（仅单测覆盖）；弱网与其它厂商端点。
- 回退：还原 `chat.py`/`retrieval.py`/`client.py`/`server.py`/`config.py`/`app.js` 与相关测试，`.env` 去掉两个 chat 键即可回到 P0 行为。

---

## 2026-11-24 — AI 学伴：传输层不再靠 SDK，失败要说得清

**本机未提交** · `fix/chat-transport-p0`

- 现象：本机 `.venv` 未安装 `openai`，`client._sdk()` 抛 `RuntimeError`，被 `except Exception` 吞掉后统一显示“模型暂时调用不通”，实际 100% 走规则兜底且没有任何日志。
- 传输：`llm/client.py` 改为标准库 `urllib` 直连（温度、`max_tokens`、超时照传），删除 SDK 依赖；代理只读环境变量，忽略 Windows 注册表里的旧代理。
- 分类：新增 `LLMError(kind)`（auth / billing / model / request / rate_limit / server / timeout / network / empty / bad_response）；`chat.py` 记 warning 日志（密钥脱敏），气泡按 kind 给出可执行提示；只对 timeout / network / 5xx / 429 重试一次。
- 可观测：新增 `POST /api/settings/llm/test`（1 token 探测，返回 kind/延迟/错误）与设置页「测试连接」；`read_llm_settings` 增加 `timeout_seconds` 与 `transport`。
- 前端：`/api/chat` 45 s 中止并提示；规则兜底或请求失败时气泡下方出现「重试这次提问」（重试替换旧答案，不叠加重复提问）。
- 配置：`Settings` 新增 `llm_max_tokens`（`.env` 里原本就有但此前未生效）；`llm_timeout_seconds` 默认 30 → 20，本机 `.env` 同步为 20。
- 验证：`pytest` 268 项通过、`ruff check`、`node --check` 通过；真实调用 deepseek-chat 5 个问题全部由模型回答（1.2–2.1 s）；坏 URL / 坏模型名 / 坏 Key 分别分类为 model / request / auth；`--no-auth` 启动后 `POST /api/chat` 返回 `source=llm`，`/api/settings/llm/test` 返回 `ok:true, 517 ms`。
- 未验证：LLM 设置块的视觉走查（`--no-auth` 下账号相关分区不渲染，需教师登录后人工确认）；真实弱网下的超时重试；其他厂商端点。对话面板与设置页外壳已用无头截图确认无排版破损。
- 回退：还原本条涉及的 `client.py`/`chat.py`/`settings_store.py`/`server.py`/`app.js`/`styles.css` 与相关测试，并把 `.env` 的 `TIMEOUT` 改回 30；`openai` 依赖已不需要，无需回装。

---

## 2026-11-24 — 合并 #29 / 个人地图与变式训练 / 离线知识图谱

**分支整合** · `integration/2026-11-24` → `main`

- 合入 `feat/web-settings-analysis`（PR #29）：设置页四分区、阈值接入诊断与 `/api/rebuild`、改密与改名、白天/黑夜/护眼三主题。`feat/web-ui-theme`（PR #28）的提交已包含在其中，单独分支归档。
- 合入 `feat/personal-map-variant-training`：变式训练闭环（出题 → A4 题卷/答案 PDF → 站内分页预览 → 扫描回录 → 教师核分）、知识地图拖拽与个人状态、课程资料库。
- 合入 `feat/interactive-knowledge-map`：`examples/knowledge-map/` 离线"知识一查表"，与主程序零耦合。
- 口径对齐：`auth.DEFAULT_THRESHOLDS` 的已掌握/需巩固由 `85/60` 改为 `75/40`，`diagnosis_config()` 回到 `DiagnosisConfig` 默认（0.75 / 0.40 / 3），正式数据诊断数字与已提交报告保持一致。
- 未合入：`groupClassOverview` / `moduleTabs` 等按旧 DOM 重排班级页的分组层（依赖 `.heatmap-panel` / `.overview-primary`，这两个类名在 #30 之后已不存在，合并会直接抛错）；班级学情仍为 #30 的六子页结构。
- 主题 token 收敛：`theme.css` 成为调色板唯一来源（浅色沿用 #30 深绿），`workspace.css` 只留尺寸与字体；补齐统计子页面与设置页在深色/护眼下的表面映射。
- 验证：256 项 Python 测试、7 项前端测试、`ruff check` 通过；本机 `--no-auth` 与带登录两种模式启动，`/api/profile`（阈值 75/40）、`/api/training`、Demo 卷生成与 PDF 预览/分页/下载、`/training-print` 均实测；Edge 无头截图核对浅色/深色/护眼与课程页。
- 未验证：其他浏览器与触屏；真实 LLM 出题质量；Safari/Firefox 的遮罩动画回退分支。
- 回退：还原本条的提交（三个 merge 与后续两次修正），或 `git revert -m 1` 对应 merge；归档分支见 `archive/2026-11-24/*` 标签。

---

## 2026-11-23 — 统计子页面与统一视觉样式

**界面优化** · `feat/ui-statistics-pages`

- 班级学情拆为成绩分布、作答与覆盖、知识诊断、主题与班级、测验记录、学生热力图六个子页面；共享筛选，支持链接、刷新与后退。
- 学生列表与画像分开，知识/作答/热力表分页；保留证据、模型区间、建议、教学反馈、学生预览与新练习提交展示。
- 新增 `workspace.css`：统一深绿主色、文字对比、字号、卡片/按钮/导航与留白；同步登录页和图谱文字。
- 1280×720、1366×768、1440×900、1536×864 的统计页一屏展示；窄屏切换单图，低于 720px 高的窗口保留自然滚动。
- 折线图随容器宽高绘制；改变窗口大小时调整分页并保留聊天草稿。学生账号主题图仅显示本人，避免把裁剪后的个人数据误作班级对照。
- 验证：244 Python 测试、5 前端统计测试、309 项 Edge 浏览器检查；22 schemas / 10 合成表检查、修改的 Python 文件 ruff 与 JS 语法通过。
- 未验证：远程 CI、其他浏览器；未调用真实 LLM。未修改公共契约、诊断算法或正式数据。
- 回退：还原本条对应的页面/样式变更，并移除 `workspace.css` 的样式引用与静态路由；历史数据与画像成果不受影响。

---

## 2026-11-23 — 工作台分组、资料库与试卷删除

- 班级学情按整体概况、知识与薄弱项、覆盖与班级对照、学生分布分组，相关图表同屏展示。
- 学生画像合并指标与分析，建议和教学调整并排；证据页分为三组，训练页合并为试卷管理与扫描复核。
- 学习计划逐项翻页，课程材料改为带章节简介、课程关联标识、搜索和筛选的资料卡片。
- 新增教师试卷软删除；关联扫描不再展示，历史文件保留，学生操作被拒绝。
- 验证：界面切换与权限已验证；本轮提交前运行完整检查，结果见 PR。
- 回退：还原本次代码；删除状态保存在本地训练 JSON 中，不改变原始教学数据。
- **2026-11-24 合并说明**：本条的 DOM 分组层（`groupClassOverview` / `moduleTabs` / `arrangeWorkspace`）未合入——它按 #30 之前的类名重排页面，与六子页结构冲突；资料库、试卷软删除与训练入口已合入，见 11-24 条目。

---

## 2026-11-23 — 修正免登录演示的退出入口

- 免登录模式会持续返回本机教师身份，原界面仍显示退出按钮，点击后看似无法退出。会话接口现在返回 `auth_enabled`，界面仅在启用登录时显示退出入口。
- 关闭联调时占用 8767 端口的免登录进程，改为带登录模式启动；退出接口继续撤销会话并清除 Cookie。
- 验证：会话接口区分两种模式，登录/退出回归测试通过。

---

## 2026-11-22 — 个人知识地图与变式训练打印回录

- 2026-11-23 补充：地图改为不滚动的固定画布，课程要求、材料出处和关系说明移入副板块；
  训练窗口加入站内 PDF 分页预览、下载和 A4 打印页，使用 ReportLab 排版、PyMuPDF 渲染。
- 验证：浏览器确认 720px 高度下页面无纵向滚动，副板块可切换；Demo 卷站内显示 3 页并启用打印按钮；250 项 Python、7 项前端测试通过。

- 后续：地图增加弹性布局、拖拽联动、浏览器演示关系编辑与保存/重置；新增无需 API 的全体 Demo 卷，按当前全体学情汇总排序，包含题卷、答案和出题依据。
- 后续验证：249 Python、7 前端测试与契约检查通过；浏览器实测拖拽和连接增删，Demo 题卷 3 页、答案 2 页完成渲染检查。

- 地图白底、柔和状态配色、保持节点布局的平滑聚焦；支持减弱动态效果偏好。
- 学生地图接入本人当前测验的诊断状态、评分证据数与独立补充训练成绩。
- 新增统一/个人变式训练 API；只发送知识状态摘要，生成内容经教师核题后发布。
- 新增 A4 中文题卷、独立答案 PDF、多页扫描预览、教师核分和持久化；学生权限隔离、扫描去重与复核防重。
- 数据写入被忽略的 `data/training/`；不改 canonical，不自动覆盖正式掌握度。扫描采用人工核分，未包含手写 OCR。
- 验证：248 Python、5 前端测试、契约/合成数据检查；浏览器地图/训练表单与中文 PDF 渲染检查。
- 未验证：真实模型端点出题质量、实体打印与真实手写扫描。
- 回退：还原本分支代码，保留本机 `data/training/` 可留存训练档案。

---

---

## 2026-11-22 — 设置页信息层级与 LLM 折叠

**设置与体验** · `feat/web-settings-expand`

- 个人信息与账号安全拆成两个同格式面板：用户名（规则收进 `?` tooltip）与修改密码移入「账号安全」；改名后头像跟随（本地存储键随用户名迁移），不再回落默认头像。
- 设置页标题恢复右侧「当前测验」卡片，去掉 eyebrow 的「/ 06」，标题与选项卡间距保持 12px。
- LLM 文字层去掉重复的状态列表；配置区默认折叠，开启「启用 LLM 模式」后以 max-height / opacity 过渡展开，关闭时加 `inert` 防止误聚焦。
- 验证：249 Python 测试、ruff、前端 6 模块语法；无头 Chrome 实测两面板、tooltip、改名后头像键迁移、折叠/展开高度 0 → 311px。

---

## 2026-11-22 — 过渡收尾、账号字段调整与设置页留白

**设置与体验** · `feat/web-settings-expand`

- 主题切换遮罩改为在动画开始前挂载，并让实心区域越过视口最远角（`radius / 0.86`）。
- 修掉切换末尾的闪烁：WAAPI 遮罩动画补上 `fill: forwards`（否则动画结束即回退到 `mask-size: 0`，闪一帧）；动画结束后先切到 `kf-masking-done`（`mask-image: none`）保持完全可见，再隔两帧移除类；另加 2.5s 兜底清理。
- 学年 + 学期合并为单一字段 `term`（如 `2026-2027秋`）；旧的 `year` / `semester` 由后端自动迁移成 `term`。
- 用户名可修改（3–24 位字母、数字或 `_.-`，重名拒绝），改名后当前会话自动跟随新用户名；修改密码时需同时输入用户名，与当前账号不一致会被拒绝。
- 删除个人信息页“头像只保存在本机浏览器…”说明行；设置页标题与选项卡之间的留白由 38px 收到 12px。
- 验证：249 Python 测试（新增改名与改密码用例）、ruff、6 个前端模块语法解析；无头 Chrome 实测资料表单、密码弹窗、过渡末帧与留白。
- 未验证：真实触屏键盘操作；旧账号文件迁移只在单元层验证。
- 回退：还原 `auth.py` 的 `term` / 改名 / 密码校验与设置页表单即可，旧字段仍会被迁移逻辑识别。

---

## 2026-11-22 — 阈值接入诊断 + 设置页交互打磨

**设置与诊断** · `feat/web-settings-expand`

- 数据分析阈值真正驱动诊断：掌握百分比映射为 Beta 判定阈值（`weak_threshold` / `mastered_threshold`），覆盖缺失线映射为最小证据数（`min_evidence`）；`prepare()` 把阈值纳入缓存指纹，改阈值后按新口径重建诊断。
- 新增 `POST /api/rebuild`（教师）：按当前账号阈值重建快照，页面在保存阈值后提示并自动刷新。
- 阈值变化实测：`85/60` → `95/70` 后 N02 的知识点状态计数由 confirmed_weak 8 / likely_weak 12 / mixed 31 变为 16 / 20 / 15。
- 设置页交互：主题切换改为柔和渐变遮罩（`mask-image` 径向渐变 + `mask-size` 动画，1200ms；不支持时回退为圆形裁剪 + 淡入）；左侧「设置」去掉框线，与导航项一致；阈值四项改为「标签 + 输入框 + 单位」同一行、两列排布；修改密码改为按钮触发的居中弹窗。
- 快照 `meta.analysis` 新增诊断配置，设置页直接显示“当前诊断配置”。
- 验证：248 Python 测试、ruff、6 个前端模块语法解析；无头 Chrome 实测柔和渐变、行内阈值、密码弹窗、阈值保存→重建→快照状态变化。
- 未验证：真实触屏键盘操作；Safari / Firefox 的 mask 动画只验证了代码回退分支。
- 回退：`prepare()` 不再传 `thresholds`、移除 `/api/rebuild` 与前端重建调用即可恢复旧口径。

---

## 2026-11-22 — 设置页重排：个人信息、教学偏好、显示、分析阈值

**设置与账号** · `feat/web-settings-expand`

- 设置页按顺序拆成四个分区：**个人信息 / 教学与 AI 偏好 / 显示 / 数据分析**；学生账号只看到个人信息与显示。
- 个人信息：用户名（只读）、姓名、头像上传、身份、当前学年与学期、任教班级与科目（教师），以及修改密码（校验当前密码，新密码 ≥8 位）。资料写入本机 `data/auth/users.json`（Git 忽略）。
- 教学与 AI 偏好：学习建议语气（温和引导 / 简洁直接 / 严谨正式）、报告长度（简短 / 标准 / 详细）、数据不足时的默认行为（直接提示 / 自动摸底）；原 LLM 文字层配置并入此分区。语气、长度与不足行为会作为附加要求传给 AI 学伴的生成提示。
- 显示：白天 / 黑夜 / 护眼三套主题（沿用圆形铺开切换），新增「默认首页」，登录后按偏好落页。
- 数据分析阈值：覆盖充足 ≥ N 条、覆盖缺失严重 < M 条、已掌握 ≥ X%、需巩固 < Y%；保存前校验大小关系，并提供「恢复默认」。阈值用于页面上的覆盖/掌握判读预览，官方诊断输出仍按固定口径复算。
- 后端新增 `GET /api/profile`、`POST /api/profile`、`POST /api/preferences`、`POST /api/password`（均要求登录 + 自定义请求头）；账号文件写入改为临时文件替换。
- 验证：245 Python 测试（新增 1 项覆盖资料/偏好/阈值/改密码流程）、ruff、`check_contracts`、6 个前端模块语法解析；无头 Chrome 实测四个分区、学生端两个分区、默认首页、阈值预览联动、保存与改密码后旧密码失效。
- 未验证：阈值尚未参与后端诊断重算（只做页面判读预览）；真实设备上的键盘操作未逐一测试。
- 回退：还原 `web/auth.py`、`web/server.py`、`llm/chat.py` 与设置页前端，删除 `data/auth/users.json` 中的 `profile` / `preferences` / `thresholds` 字段即可（旧文件缺字段时自动取默认值）。

---

## 2026-11-21 — 外观主题、个人信息与设置页重构

**展示层体验** · `feat/web-ui-theme`

- 设置页拆为「外观 / 个人信息 / 模型配置」三个选项卡；模型配置仍只写本机 `.env`。学生账号同样可以进入设置，但只看到前两个选项卡。
- 新增白天 / 黑夜 / 护眼三套主题：只换配色，共用同一套布局与字号；切换时用 View Transitions 的圆形裁剪从点击位置铺满页面（约 1.1 秒）。偏好存 `localStorage`，`theme-boot.js` 在首屏前应用，避免闪烁。
- 新增「个人信息」：姓名、账号、身份、班级/年级或数据集规模、快照 ID、生成时间、推荐模式；支持上传/移除头像，图片在浏览器内裁成 256px 后只存本机 `localStorage`，不上传后端。
- 顶栏不再显示姓名胶囊与独立退出按钮：头像本身就是账号菜单（未上传头像时教师显示「教」、学生显示「学」）；气泡里是身份、查看个人信息、退出登录，点「查看个人信息」直接切到设置页对应选项卡。设置页与顶栏共用同一头像。
- 列表入场改为交错动画（32ms 阶梯、轻微回弹上滑）；按钮按压 `scale(.96)` + 内阴影，松开按 `cubic-bezier(.34,1.56,.64,1)` 轻微过冲回弹；`prefers-reduced-motion` 下全部关闭。
- 验证：244 Python 测试、ruff、`check_contracts`；无头 Chrome 实测三套主题、设置页三个选项卡、气泡菜单、学生页与登录页截图；CDP 断言按压矩阵 `matrix(0.96,…)` 与内阴影、入场动画名 `kf-rise`。
- 未验证：Safari / Firefox 的 View Transitions 回退分支（只测到"直接切换"路径）；真实触屏设备上的按压手感。
- 回退：删除 `theme.css` / `motion.css` / `theme-boot.js` 与设置页选项卡代码，顶栏恢复为单一退出按钮。

---

## 2026-11-21 — 本机登录与按角色的数据裁剪

**本机登录** · `feat/web-login`

- 新增 `data/auth/users.json`（Git 忽略）：首次启动生成 `teacher` 与学生 `S001` 两个账号，初始密码 `123456`，密码以 scrypt 加盐哈希存储，不存明文。
- 新增 `/login` 页面与 `/api/login`、`/api/logout`、`/api/session`；会话保存在进程内存，Cookie 为 `HttpOnly; SameSite=Strict`，关窗口即失效。未登录访问页面 302 到登录页、访问 API 返回 401。
- 学生快照在服务端裁剪：只下发本人 `profiles`/`recommendations`/`records`/`stats` 与班级聚合；`quality`、`reviews` 置空；`/api/evidence` 越权 403，`/api/settings/llm` 与教师调整类反馈对学生 403。
- 移除顶栏“教师视角/学生视角”切换，改为身份徽标 + 退出登录；学生账号锁定本人，隐藏学生搜索与设置入口；教师仍可用 `/student?student=S003` 预览单个学生。
- 验证：244 Python 测试（新增 2 项登录/越权用例）、`check_contracts`、`check_examples`、5 个前端模块语法解析；教师/学生登录、越权 403、错误密码 401、退出后会话失效均实测。
- 未验证：未在真实浏览器里点过登录表单（本机无可用浏览器自动化），仅通过 HTTP 断言页面与接口；未做密码强度/找回流程。
- 回退：`--no-auth` 启动可临时跳过登录；彻底回退需删除 `src/knowflow/web/auth.py`、`static/login.*`，并还原 `server.py`/`app.js` 的路由与顶栏。

---

## 2026-11-17 — AI 学伴：可拖拽/缩放窗口、简洁/证据模式、依据展开

- 窗口：标题栏拖动、8 个边缘/角手柄缩放；最小 340×300，限制在视口内；双击标题重置；≤900px 宽度沿用全宽布局。
- 输入框旁新增「简洁 / 证据」：简洁少列数字、聚焦现状与下一步；证据按“结论 / 依据”分点，依据逐条引用事实。
- 每条回答下方「查看推理依据」展开确定性步骤与证据 ID；明确说明展示的是事实卡与规则步骤，不是模型隐藏思维链。
- 后端：`/api/chat` 接受 `mode`；分模式 prompt；证据模式校验“结论/依据”结构；trace 由 facts/规则构建。
- 旧后端进程：前端检测响应缺少 `trace` 时提示重启，避免“简洁/证据看起来一样”。
- 验证：242 Python + 5 前端统计测试、ruff、check_contracts；拖拽/缩放/两模式/依据展开实测，LLM 与规则 fallback 均检查。
- 回退：移除 mode 参数、窗口手势与 trace 展示；默认规则回答不受影响。

---

## 2026-11-17 — WebUI 三处修正

- 侧栏「当前课程」卡片在短屏 / 中等宽度下被压缩或与 AI 学伴按钮重叠：固定 flex 收缩、短屏间距与底部留白，700 / 768 / 900 高度检查通过。
- 教师端「存疑证据」从侧栏移入「数据与证据」页底部「存疑数据」入口；保留直接路由与返回入口，学生端不可见。
- 「数据与证据」卡片默认折叠，只显示标题；点击展开正文（审计流程、五态分布、判断边界、源文件、质量发现），入口始终在页尾。
- 验证：239 Python + 5 前端统计测试、ruff、check_contracts；1366×700、1200×768、1500×900 截图检查。

---

## 2026-11-16 — 方向五：教学反馈与补充证据闭环

**本机提交** · `feat/feedback-loop`

- 新增 `data/feedback/<dataset>/events.jsonl`（追加式、Git 忽略）：补充作答、教师调整、教师评语、学生反馈；无认证，仅本机演示。
- 补充作答转 `EV-...` 派生证据，写入 `supplemental_input.json`；`diagnosis_input.json` 仍是 canonical，官方分数与质量报告不变；`verify-run` 用 canonical + 补充记录复算。
- `run --supplemental ... --previous <run>` 输出 `diagnosis_diff.json`：逐学生状态、mastery、issue 增删。
- 建议层重放教师调整：锁定项保留并占预算，移除项进入 `deferred` 且可 `restore`，换材料/调时间/调难度；按 `issue_id` 跨版本回退匹配；只改计划，不改诊断。
- 学生反馈/教师评语进入计划卡与 `recommendation.feedback`；新增 `/api/feedback`（本机、同源、`X-KnowFlow-Feedback`）与教师“教学调整与反馈闭环”面板、学生反馈按钮。
- 契约 v0.10（22 schemas），`record_id` 扩展 `EV-...`。
- 验证：`pytest 239 passed`、`ruff`、`check_contracts`、`verify-run`（含补充 evidence）、`verify-recommend`（含反馈调整）。
- 回退：移除 `feedback/` 与 `--supplemental`/`--previous`/`/api/feedback`；旧 run/建议仍可校验。

---

## 2026-11-16 — 方向三：学习路径与主动补充观测

**本机提交** · `feat/learning-path`

- 计划项：新增 `plan_item_id` / `plan_version` / `status` / `prerequisite_item_ids` / `prerequisite_knowledge_ids` / 结构化 `completion_condition`；顶层 `plan_id`、`plan_version`、`history`、`plan_diff`、`progress`。
- Probe：用可解释评分替换“按材料编号取前 3”；候选必须是本节点未作答、未评分、非 pending、非存疑的测评题；5 个分量 + 配置权重，`total = Σ 权重×分量`，权重写入产物与 manifest；明确标注为规则启发式，不是 IRT。
- 进度：`path-event` 追加 `data/progress/<dataset>/events.jsonl`（不含分数）；`started` 保留为 `in_progress`，`completed` 进入 `history`；预算只计活动项；`plan_diff` 记录版本、原因与差异，旧计划与历史不删除。
- 前端：计划卡显示“进行中”，建议上方提示已完成历史。
- 契约 v0.9（21 schemas），新增 `path_event.schema.json`。
- 官方数据：N01 98 条计划项、probe 评分可复算；完成 1 项后 N01 97 条、S001 版本 v2、历史 1 条、diff 记录完成项。
- 验证：`pytest 231 passed`、`ruff`、`check_contracts`、`verify-run` / `verify-recommend` 通过。
- 回退：移除 `path.py` / `probe.py` 与 `--progress`/`--previous`；旧建议仍可校验。

---

## 2026-11-16 — 方向二：正式课程图谱进入契约与决策

**本机提交** · `feat/curriculum-graph`

- 问题：前端硬编码 21 个教材细目、20 条边（去重 18 组），后端诊断/建议读不到，关系没有 ID、来源和审核状态，先修也不进入排序。
- 数据：新增 `knowledge/curriculum_graph.json`（21 节点 / 18 关系：16 先修 + 1 易混 + 1 相关），逐条带 `edge_id`、`source_reference`、`rationale`、`review_status=draft`、`evidence_level`；对称关系按 ID 升序只存一次。
- 契约 v0.8：新增 `curriculum_graph` schema；`knowledge_base` 加可选图谱；`recommendation` 加 `prerequisite_check.{pending_knowledge_ids,reviewed_edges,draft_edges,note}`、`plan[].relation_notes`、`deferred`。
- 校验：端点存在、重复边/反向对称边、自环、先修环（给路径）、计数；`check_contracts` 纳入 G0；知识底座与 curation 哈希绑定，`reviewed` 必须有可核对出处。
- 决策：只有 reviewed 先修参与排序；insufficient 先修先补观测、不判薄弱；已掌握不重复；易混只用共享材料做对比，缺材料只提示教师；未审核关系在建议中写“关系待核验”。
- 前端：删除硬编码图谱，改用快照里的 `knowledge_base.curriculum_graph`；节点抽屉标注“待核验/已核对”，课程页按关系类型计数，计划卡显示“关系待核验/先修待巩固/先修证据不足”。
- 官方数据实测：知识底座含 21/18 图谱；建议 98 条计划项、20 条计划项带“关系待核验”提示；`verify-recommend` pass。官方图谱无 K 级先修边，故正式数据顺序不变，排序逻辑由合成测试覆盖。
- 验证：`pytest 217 passed`、`ruff` 通过、`check_contracts`/`check_examples`/`validate_canonical`/`verify-run`/`verify-recommend` 全过。
- 回退：移除 `knowledge/`、`--graph` 与前端图谱读取即可；旧底座（无图谱）行为不变。

---

## 2026-11-16 — 方向一：存疑评分审查

**本机提交** · `feat/review-disputed-scores`

- 问题：R-0685（作答与参考答案字面一致却 0 分）与 R-0133（满分，但评分点合计 2、结果评分点为 0）都能一路进入画像与建议；旧链路只校验算术关系，从不比较作答与参考答案。
- 审查层：新增 `src/knowflow/review/`（规则 `review-rules-1`、追加式账本、报告校验）；`review-scan` 只读 canonical 产出线索，`review-decide` 把人工结论追加到 `data/reviews/`，账本用三张 canonical 表 SHA-256 绑定。
- 诊断：`knowledge_states[].review` 同时给 `official_*` 与 `usable_*`；`run --review-policy official|exclude_flagged` 决定顶层口径；存疑失分移入 `issues[].disputed_rubric_evidence`，不进 `rubric_evidence`。
- 建议：计划项加 `basis_records`/`review_flags`；只剩存疑依据的 issue 进 `review_required`，不生成巩固计划；`verify-recommend` 增加三条隔离检查。
- 教师端：新增「存疑证据」只读页与审核清单导出（清单不含原始作答）；快照新增 `reviews`。
- 契约 v0.7：新增 `review_report.json`，两个输出 schema 加可选字段；旧画像/旧建议仍可校验。
- 官方数据实测：799 条保留记录中 4 条线索（2 条参与隔离、2 条仅审计）；排除后 2 个「学生 × 知识点」数值变化，无状态翻转。
- 验证：`pytest 186 passed`、`ruff` 通过、`check_contracts` / `check_examples` / `validate_canonical` / `verify-run` / `verify-recommend` 全过；CI 增加 ruff 步骤并清掉既有 F401。
- 回退：移除 `review/`、`--review*` 参数与页面入口即可；旧 run 不读审查字段，仍能复算。
## 2026-11-16 — 学情页面精简与统计展示优化

**本机提交** · `feat/dashboard-clarity`

- 精简标题与重复说明，统计口径 / 模型估计 / 推荐依据可展开；保留知识图谱、AI 对话与证据回查。
- 班级页新增得分率与覆盖率直方图、均值 / 中位数 / 高低值、主题与班级对比；无评分 / 未知范围单列。
- 个人画像增加主题对照、知识点满分 / 部分分 / 零分明细；分析 / 作答 / 建议分标签，学生列表独立滚动并支持排序。
- 折线数值自动避让，轴刻度 / 日期留白；按卡片宽度重绘，修复手机设置按钮与环形图溢出。
- 展示统计独立放入 `analytics.mjs`；公共契约、诊断算法和原始数据不变。
- 验证：合并后 239 项 Python 测试、5 项前端统计回归、Edge 交互 / 布局检查通过；22 契约、10 表合成样例及 JS 语法检查通过。
- 回退：撤销本条对应 UI、静态资源路由、前端测试和 README 改动，三项任务的原始成果不受影响。

---

## 2026-11-15 — 工作台课程知识图谱

- 教师课程页与学生工作台接入 21 项教材细目的动态图谱，支持拖动、同画布聚焦、查页码与回查对应指标的学情。
- 已验证两个角色的图谱交互、教材 PDF 链接与学情详情，完整测试通过。

## 2026-11-15 — 放宽对话数字校验，减少误回退

**本机未提交** · `fix/chat-number-tolerance`

- 旧行为：回答里任何不在事实卡白名单的数字都会触发回退，连把 0.2422 写成“约 24%”也会被拒，导致“模型回答未通过数字/ID 校验”出现得很频繁。
- 数字：允许四舍五入/百分比换算——与事实值相差 ≤0.015 的百分数、与整数相差 ≤0.5 的整数、与百分制相差 ≤1.5 的数值；另放行 0–10 的小序数与 2000–2100 的年份。
- ID：白名单从“当前事实卡”扩展到**整个快照的真实 ID**（学生/节点/知识点/材料/问题/记录），引用其他真实知识点不再被拒。
- 重试：第一次不合格时把“具体哪几个数字/ID 不合格”作为反馈带回模型重写一次，再不合格才回退；回退文案改为“模型这次给了无法核对的数字或编号…”。
- 仍然拦截：编造人数/比例（如 999 人）、不存在的 ID、URL 与代码块；规则回答不变。
- 验证：新增“四舍五入 + 小序数通过”“首次不合格带反馈重试成功”测试；`pytest 156 passed`、`ruff`、`node --check` 通过。
- 回退：恢复严格集合比较并移除重试反馈；对话仍可用，只是回退更频繁。

---

## 2026-11-15 — 左下角 AI 对话窗口

**本机未提交** · `feat/chat-widget`

- 新增 `src/knowflow/llm/chat.py`：从已校验快照构造事实卡（计数/状态/ID/建议，不含原始作答），模型回答必须通过数字与 ID 白名单；连续两次不合格或无 Key 时回退本地规则回答。
- 新增 `POST /api/chat`：仅回环、要求 `X-KnowFlow-Chat` 头、16 KB 上限；异常返回 JSON，不重置连接。
- 前端左下角悬浮「AI 学伴」按钮 + 对话面板：欢迎问题、上下文标签（节点/班级/学生）、引用 chip 可点开知识点或材料、Enter 发送、Esc 关闭；`?chat=1` 直接展开。
- 验证：`pytest 154 passed`（新增规则兜底、数字锁拦截、模型回答、接口鉴权 5 项）；`ruff`、`node --check` 通过；实际启动后规则回答与 Edge 无头截图核对。
- 回退：移除 `chat.py`、`/api/chat` 与 `chat-fab` 相关前端/样式；其余功能不受影响。

---

## 2026-11-15 — 合并 origin/main（PR #19）并推送

**待推送** · `main` ← `origin/main`

- 远端 PR #19 改了 `.env` 契约检查（`_git_tracked` + `_git_ignored`）；本地已有同类改动，合并时保留远端实现，本地 LLM/设置页提交重放到其后。
- 冲突处理：`contracts.py` 采用远端 `.env` 分支；`AGENT.md` 版本表调整为先契约检查（v0.16）、再 LLM（v0.17）、再设置页（v0.18）；`CHANGELOG.md` 两边条目按时间合并且不丢记录。
- 验证：合并后 `pytest 149 passed`（含远端新增 `.env` 回归测试）；`ruff`、`check_contracts` 通过。
- 回退：`git revert -m 1 <merge>` 可退回合并前，本地 6 个提交仍在。

---

## 2026-11-15 — 密钥泄露审计与错误脱敏

**本机未提交** · `fix/secret-redaction`

- 审计：`.env` 被 `.gitignore:8` 忽略、从未被跟踪、从未进入任何提交；`HEAD` 中没有 `sk-` 开头的长 token（仅测试假值 `sk-test-*`）。
- 脱敏：模型/网络错误写入 `run_manifest.json`、`explain.json` 前，把 `sk-...` 形状替换为 `sk-***`，避免供应商报错回显 Key。
- 文档：补充“不要 `git add -f .env`、不要打包整个项目目录提交、录屏前清空 Key”。
- 验证：新增脱敏单测；`pytest 148 passed`、`ruff` 通过。
- 回退：移除 `redact` 调用即可，不影响正常路径。

---

## 2026-11-15 — 设置保存不再出现 Failed to fetch

**本机未提交** · `fix/web-settings-network`

- 现象：输入 Key 保存时页面报 `Failed to fetch`。原因是本机后端进程已退出（启动窗口被关闭或被回收），浏览器连接不到 8765。
- 前端：POST 遇到网络中断自动重试一次；仍失败则提示“无法连接本机后端，请确认启动窗口仍在运行”，读取设置失败也给出同样可操作提示。
- 后端：`GET/POST /api/settings/llm` 包住所有异常，返回 JSON 4xx/5xx 并打印 traceback；保存失败不再重置连接。
- 文档：明确“启动窗口必须保持打开；关闭窗口=停掉后端”。
- 验证：新增“保存失败返回 500 且同一连接仍可访问 /teacher”测试；`pytest 147 passed`、`ruff`、`node --check` 通过。
- 回退：移除前端重试与后端兜底分支即可；接口与设置页不变。

---

## 2026-11-15 — 修复重复启动导致设置页 404

**本机未提交** · `fix/web-single-instance`

- 根因：Windows 的 `SO_REUSEADDR` 允许两个 `knowflow.web` 同时绑定 8765。静态文件每次从磁盘读，所以旧进程也能显示新齿轮，但没有 `/api/settings/llm`，请求随机落到旧进程就报“找不到页面”。
- 修复：新增 `LocalHTTPServer`，Windows 上禁用地址复用，重复启动直接失败；端口占用时打印可操作中文提示。
- 前端：设置接口返回 404 时提示“后端进程还是旧版本，请关闭所有启动窗口后重跑”，不再只显示通用错误。
- 验证：清理 3 个残留进程后只保留 1 个监听；`/api/settings/llm` 与 `/teacher` 均 200；第二个实例 exit 1；`pytest 146 passed`、`ruff`、`node --check` 通过。
- 回退：恢复 `ThreadingHTTPServer` 并移除提示分支；不影响设置页本身。

---

## 2026-11-15 — 网页设置面板：LLM 开关与配置

**本机未提交** · `feat/web-llm-settings`

- 侧栏新增齿轮「设置」；页面内提供 LLM 开关、厂商（DeepSeek/OpenAI/通义千问/自定义）、API Key、模型与 Base URL。
- 新增 `src/knowflow/llm/settings_store.py`：校验后原子改写本机 `.env`，保留其他行；Key 只写不读，接口仅返回 `api_key_set`。
- 后端新增 `GET/POST /api/settings/llm`：仍只监听回环，POST 要求 `X-KnowFlow-Settings` 头（跨站预检不会通过）并限制 8 KB；请求体先读后判，避免 Windows 连接重置。
- `.env` 路径固定为仓库根目录，网页保存与后续 CLI 读取同一份配置；保存只改配置，不自动重算已有成果。
- 验证：`pytest 146 passed`（新增设置存储与接口测试）；`ruff check` 通过；实际启动后 GET 返回脱敏配置、POST 保存 200、缺头 403、Key 未出现在响应中；前端 `node --check` 通过。
- 回退：移除设置页与 `/api/settings/llm`、删除 `settings_store.py`；LLM 文字层仍可通过 `.env` + `--llm` 使用。

---

## 2026-11-15 — LLM 文字层接入与仓库清洗

**本机未提交** · `feat/llm-edge`

- 新增 `src/knowflow/llm/`：`llm_summary` 白名单构造、prompt、OpenAI 兼容客户端（懒加载）、数字/ID 锁 guard、重试 2 次回退模板。
- 新增 `knowflow explain`（单题、只发摘要、落盘输入与输出）与 `recommend --llm`（批量润色 `reason`/`check`）；`run_manifest.json` 新增 `llm` 块，`policy.llm_enabled` 反映真实请求。
- `llm_summary.status` 枚举补 `mixed_performance`；Web 在 LLM 生效时标注“规则推荐 + LLM 润色”，并新增 `knowflow.web --llm` 重建入口。
- 契约修正：`.env` 不再要求“不存在”，改为必须被 Git 忽略；本地配置 Key 时 `check_contracts` 仍全绿。
- 清洗：删除静态原型 `webui-prototype/`、缓存目录与旧 artifacts，保留当前 `knowflow.web` 与 harness 文档。
- 验证：`pytest 139 passed`；`check_contracts` / `check_examples` / 两个 fixture / `verify-run` / `verify-recommend` 全部通过；**未调用真实 API**。
- 回退：移除 `llm/` 与 `--llm`/`explain`，恢复旧 `.env` 检查；规则版不受影响。

---

## 2026-11-15 — 契约检查：本地 `.env` 允许存在，只禁止被提交

**待合并** · `fix/env-tracked-check` → `main`

- `contracts.check_repo()` 不再“磁盘上看到 `.env` 就报错”：改为问 Git——`git ls-files` 判断是否被跟踪、`git check-ignore` 判断是否被忽略；本地持有 `.env`（放 DeepSeek key）是文档允许的正常状态，风险只在提交。
- 新增 `_git_tracked()`；Git 不可用时退化为只报“未被忽略”，不把本地文件当违规。
- 影响：本地有 `.env` 的开发者跑 `pytest` 与 `check_contracts.py` 不再假红；CI（无 `.env`）行为不变。
- 验证：`pytest 132 passed`（含新增 `test_local_env_is_allowed_but_tracked_env_is_not`）；`check_contracts.py` 通过；`git add -f .env` 时报 `tracked by Git`。
- 回退：revert 本提交即恢复“存在即报错”；只影响检查逻辑，不碰 schema 与产物。

---

## 2026-11-15 — 本机教师与学生展示页

**本机未提交** · `feat/teacher-student-dashboard`

- 新增 `src/knowflow/web/`：复用任务 1/2/3、验证成果版本，提供教师/学生页面；公共契约不变。
- 展示班级条形/环形/节点记录量折线、知识热力表、个人画像、课程地图与出处、证据抽屉、规则学习建议。
- 新练习只保存浏览器，标记待评阅；自编数轴/预算实验不计入正式画像；不推断缺失或未核对先修关系。
- 新增 `start-dashboard.cmd` 与 `scripts/start_dashboard.ps1`；运行数据独立写入忽略目录 `artifacts/web/`，不覆盖原中间表。
- 验证：131 项 Python 测试通过；53 项 Edge 浏览器检查通过（含 320–1440 px、筛选、证据、本机提交）；契约与 10 表合成样例通过。
- 回退：移除 `web/`、启动脚本及对应测试/说明；原三项任务不受影响。历史成果与浏览器提交无需删除。

---

## 2026-11-14 — 七年级数学交互知识图谱（离线示例）

**示例** · `feat/interactive-knowledge-map`

- 新增 [离线知识一查表](examples/knowledge-map/README.md)：单文件页面，21 个知识点，支持节点拖动、同画布聚焦、主题筛选与教材页码查阅。
- 与主程序零耦合：教材切片由使用者本机放入 `examples/knowledge-map/教材/`；移除该示例目录即可回退。
- 未验证：真实设备上的拖拽手感；作为演示备用的离线页面未纳入自动化检查。

---

## 2026-11-14 — 任务3规则版：issue → 材料 → reason/check

**待合并** · `feat/r3-recommend` → `main`

- 新增 `src/knowflow/recommend/`：规则选材料、模板写 `reason`/`check`、`probe_plan`、validator；不接 LLM。
- CLI 加 `recommend` / `verify-recommend`；默认最新节点，`--node all` 两次都出；每生 ≤3 条计划。
- 契约 v0.6：`node_id`/`activity_type`、数字锁、probe 必须未作答；`validation_report` 加可选 `errors`/`policy_version`。
- `difficulty`/`est_minutes` 为规则推算（官方无此字段），运行说明与校验报告标注。
- 验证：`pytest 125 passed`；官方数据 40 人 / 99 计划 / 39 人需补观测 / `gate pass`；三个格式检查通过。
- 回退：revert 本提交，删 `recommend/` 与两条 CLI；契约 v0.6 向后兼容，可单独保留。

---

## 2026-11-13 — 任务1评审修订

- M1恢复为待复核状态，区分canonical可复现产物与本机内容成果；同步协作说明。
- knowledge输入目录缺失时给出build_canonical操作提示；新增默认目录及显式输入路径回归测试。
- 验证：pytest 118 passed；契约与合成表检查通过。
- 回退：撤销本次修订，恢复旧状态说明与缺目录报错。

---

## 2026-11-12 — 任务1 canonical 知识底座生成

- 新增 `knowledge` CLI 与知识层，按现有 schema 打包五张 canonical 表；不改输入或诊断逻辑。
- 校验原文出处字段、主键/引用/计数、Q-matrix 测评覆盖、父子/包含/先修无环；保留已有易混边。
- 输出默认进 `artifacts/knowledge/`，不覆盖已有文件，不推断缺失关系。
- 新增 18 项回归测试；全量 pytest 115 passed，契约/合成表/产物 schema 检查通过。
- 补充哈希绑定的本机 curation 接口：只允许课标/说明/有依据关系更新，保持诊断ID和Q-matrix不变。
- 本机在 canonical 之上完成课标/说明/关系标注与产物生成；仓库可见数据可复现 3 课标/9 知识点/65 材料/63 映射/9 条 contains 边；细化后的 21 内容细项属本机成果，不在本 PR 验收范围。
- 回退：移除知识层、CLI knowledge 入口及对应测试/说明。

---

## 2026-11-12 — `--run` 可省略：默认最近一次运行

**待合并** · 分支 `fix/r4-run-argument` → `main`

### 改了什么

- `knowflow verify-run` / `knowflow evidence` 的 `--run` 改为可选：省略或写 `latest` 时自动取 `artifacts/run/` 下最新的完整运行（按 `run_manifest.json` 存在性过滤、按 mtime 排序）。
- 目录不存在或不是完整运行时，给出可读报错（`run directory not found: …`），不再抛 `[Errno 22] Invalid argument`。
- `verify-run` 输出增加 `run` 字段，明确这次复核的是哪个目录。
- 新增 4 项测试（最新目录选择、无完整运行、占位符路径、半截目录）；README/AGENT/shortcuts/PR 模板同步为"默认最近一次"，并说明 `<目录>` 是占位符。

### 验证

```text
pytest                 97 passed
uv run python -m knowflow.cli verify-run
  gate pass（自动选中最新一次，80 份个人 / 6 份班级）
uv run python -m knowflow.cli verify-run --run "artifacts/run/<目录>"
  KnowFlow: run directory not found: artifacts\run\<目录> (…omit --run to use the newest run)
```

### 回退

revert 本提交；`--run` 恢复为必填，行为与之前一致。

---

## 2026-11-12 — 文档同步：把过期的计数与状态改回真实值

**`c344f2d`** · PR [#12](https://github.com/JackChen070421/KnowFlow/pull/12) · `docs/r4-docs-sync` → `main`（纯文档）

### 改了什么

- **计数**：脚本 6 → 7；canonical 表 9 → 10（含 `record_details.csv`，806 行）；测试 50 → 93；schema 18 保持。
- **状态**：README 里程碑 M2 由 ⬜ 改为 ✅ 基础版；"第 3–6 层"改为"第 3、5、6 层"；AGENT 的 G2/G3 说明改为"数据层 + 诊断层已覆盖，任务3 未实现"。
- **入口**：删掉"CLI 只有 check/validate/config/version"的旧说明，改为 `run`/`verify-run`/`evidence`；README 新增「跑任务2」一节（3 条命令 + 产物树 + 期望输出）。
- **样例说明**：`examples/README.md` 去掉 M0 旧话术；合成样例 README 的 "M1–M3" 改为 "任务2/3"。
- **PR 模板**：增加 `knowflow verify-run` 检查项。

### 验证

```text
md 相对链接全部可解析（脚本扫描）
check_contracts  OK (18 schemas)
check_examples   OK (10 tables)
pytest           93 passed
```

### 回退

revert 本提交；纯文档，无代码/数据影响。

---

## 2026-11-12 — 任务2诊断层：canonical → 个人/班级画像

**待合并** · 分支 `feat/r2-diagnosis-on-canonical` → `main`（含契约 v0.5 提交）

### 改了什么

- **新增** `src/knowflow/diagnosis/`：`beta.py`（纯 Python 正则不完全 Beta 与反函数）、`mastery.py`（Beta 后验与状态阈值）、`profiles.py`（个人/班级画像、评分点证据）、`pipeline.py`（读 canonical、运行、证据回查）、`validation.py`（复算门）。
- **入口**：`knowflow run` / `verify-run` / `evidence`；输出只进 `artifacts/run/`（gitignore）。
- **数据入口改写**：只读 `data/interim/<ds>/` 的 10 张 canonical 表；`score_points` 由 `rubric_scores_json` + `materials.rubric_json` 解析；逐行 `decisions` 由 `record_details.csv` 生成，不再自建适配层。
- **去重**：删除 PR #9 自带的 `io/adapters.py`、`cleaning/records.py`；复用 `cleaning/states.py` 与 io 层，`records.csv` 仍只有一个生产者。
- **依赖**：不引入 scipy（误差 <1e-14 已用测试钉住），CI 仍 `uv sync --frozen --extra dev`。

### 验证

```text
pytest                         93 passed（含 29 项诊断测试）
check_contracts                OK (18 schemas)
check_examples                 OK (10 tables)
knowflow run --dataset official-v1   80 个人画像 / 6 班级画像，gate=pass
knowflow verify-run             gate=pass（复算 + 产物哈希）
knowflow evidence --record R-0001     导出成功，源文件被改则拒绝
```

### 限制

- 未接 R1 `knowledge_base` 覆盖，仍用官方指标映射；无测验节点的数据集不适用。
- 未涉及任务3建议与 LLM。

### 回退

revert 本提交即可；契约 v0.5 提交可单独保留。无数据迁移（输入表未改）。

---

## 2026-11-12 — 输出契约 v0.5：把诊断层的字段写进合同

**待评审** · 分支 `feat/r2-diagnosis-contract-v05` → `main`（只动契约，不含实现）

### 改了什么

- **个人画像**：`node_id` 必填；`coverage.scope_known` 必填、`ratio` 可空；`knowledge_states[]` 增加 `credible_interval` / `weak_probability` / `mastered_probability` / `applicable_items` / `status_reason` / `performance`；`issues[].rubric_evidence` 必填（空数组 = 已核查无失分）。
- **群体画像**：`node_id`、五项分布计数（之和 = `student_count`）、`rubric_patterns`、`common_issues.denominator(_basis)`；`mean_ratio` 可空。
- **枚举**：`status` 加 `mixed_performance` / `not_applicable`；`issue_type` 加 `performance_gap` / `score_point_gap`。
- **ID**：`issue_id` 第二段改为知识点序号（跨节点稳定），并写死"每学生每知识点至多一条"。
- **质量报告**：加逐行 `decisions` 等**可选**字段（数据层旧产物仍有效，诊断运行必须带）。
- **边界**：输入表未动，`CANONICAL_VERSION` 仍 `0.4.0`；不加 `event_id` / `score_points`；原文不进输出；schema 总数仍 18。

### 验证

```text
check_contracts   OK (18 schemas)
check_examples    OK (10 tables)
pytest            64 passed
data/interim/official-v1/data_quality_report.json  v0.5 校验通过（向后兼容）
PR #9 代码 + v0.5 输出 schema                      30 项诊断测试通过（兼容性预演）
```

### 回退

revert 本提交即可；schema / fixtures / CONTRACT / AGENT 同批回退。无数据迁移：输入表与 `*.expected.json` 未改。

---

## 2026-11-12 — 产物指纹：多人构建互证

**待合并** · 分支 `feat/r2-record-details` → `main`

### 改了什么

- **新增** `scripts/export_digest.py` 与 `src/knowflow/io/digest.py`：把 10 张表压成"行数 + sha256 + 聚合计数"，`--check` 与仓库里的 `data/manifests/official-v1.expected.json` 比对，不一致会点出是哪张表和哪个字段。
- **入库** 产物指纹（2 KB）：只含行数、哈希、归一化后的异常分类计数（`得分 <n> 超出满分 <n>`），不含任何单元格内容；`.gitignore` 为它开例外，和 `*.structure.json` 同类。
- **契约常量** `CANONICAL_VERSION` 0.3.0 → 0.4.0，与 CONTRACT v0.4 对齐；指纹里带版本号，跨版本比对会先报版本不一致。
- **分工**：`*.structure.json` 证明"输入同一份"，`*.expected.json` 证明"产物同一份"，`validate_canonical` 证明"产物没被手改"。

### 验证

```text
export_digest --write   DIGEST WRITTEN tables=10 records=799
export_digest --check   DIGEST OK tables=10 records=799 anomalies=13
check_contracts         OK (18 schemas)
pytest                  54 passed
```

### 回退

删除 `scripts/export_digest.py`、`src/knowflow/io/digest.py`、`data/manifests/official-v1.expected.json`，并回退 `.gitignore`、`contracts.py`、`README`、`data/README`、`shortcuts.md`。

---

## 2026-11-12 — 证据层：record_details 拆分（canonical v0.4）

**待合并** · 分支 `feat/r2-record-details` → `main`

### 改了什么

- **契约**：新增 `record_details.csv`（v0.4，minor）。一行对应官方 CSV 一行，原文零加工（换行/空格/原始编号都保留），带 `csv_record_number` 可逐行回查、`kept` 标记被更高修订替代的行；`records` 字段不变，仍是分析层。
- **数据层**：`quality.build_records` 返回 `(records, details)`；`pipeline` 增加第 10 张表、明细引用校验（每条记录恰有一条 `kept` 明细、`record_details` 行数 = 原始行数）；写盘改为临时文件 + 原子替换。
- **边界**：五态记账从 `io/quality.py` 下沉到 `cleaning/states.py`（数据层只记账，判定留给诊断层）。
- **安全**：适配错误信息不再回显单元格原文（评分点解析失败只报材料和第几行）。
- **样例与文档**：合成样例补 `record_details.csv`（10 张表）；README / AGENT / shortcuts / CONTRACT / data README 同步。

### 验证

```text
check_contracts     OK (18 schemas)
check_examples      OK (10 tables)
pytest              50 passed
build_canonical     ADAPT OK records=799 record_details=806 duplicates_removed=7
validate_canonical  VALIDATE OK tables=10 records=799 anomalies=13
```

### 回退

`git revert` 本提交；本机 `data/interim/official-v1/` 删除后重跑 `build_canonical` 即可回到 v0.3 形态（少了 `record_details.csv`）。

---

## 2026-11-12 — 数据层落地：official-v1 → canonical v0.3

**`07b662f`** · PR [#5](https://github.com/JackChen070421/KnowFlow/pull/5) · `feat/r2-canonical-adapters` → `main`

### 改了什么

- **契约**：canonical `v0.2 → v0.3`（minor）。新增 `nodes.csv` 与 `records.node_id`；`records` 增 `rubric_scores_json` / `steps_json`；`materials` 增 `item_format` / `explanation` / `rubric_json` / `attachments_json`；`materials.difficulty` 与无主题教材的 `objective_id` 允许 `null`；去重口径改为「同一学生 × 材料 × 节点」；§7.1 新增官方 → canonical ID 映射表。
- **数据层**：新增 `src/knowflow/io/`（`mapping` ID、`adapters` 字段、`quality` 清洗与报告、`pipeline` 读写校验）与 `scripts/build_canonical.py`、`scripts/validate_canonical.py`；产物写 `data/interim/`，仍被 gitignore。
- **结果**：official-v1 → 9 张表（3/9/65/63/9/40/2/799/0）+ `data_quality_report.json`；五态 405/385/4/5/0，去重 7，异常 13。
- **样例与文档**：合成样例补 `nodes.csv`、`records.node_id` 接入节点（输入表 8 → 9 张）；README / AGENT / shortcuts / CONTRACT §5.3 / examples 说明同步。

### 验证

```text
check_contracts     OK (17 schemas)
check_examples      OK (9 tables)
pytest              46 passed
build_canonical     ADAPT OK records=799 duplicates_removed=7 anomalies=13
validate_canonical  VALIDATE OK tables=9 records=799 anomalies=13
```

### 回退

`git revert 07b662f`；本机 `data/interim/official-v1/` 重跑 `build_canonical` 即可重建（目录本身不入库）。

---

## 2026-11-10 — 依赖分层 + 锁文件 + 格式校验修复

**待合入** · 分支 `chore/r4-deps-lock` → `main`（已 rebase 到 #3 之后的 main）

### 改了什么

- **依赖分层**：core 从 10 个包瘦到 4 个（`jsonschema[format]`、`referencing`、`pydantic`、`pydantic-settings`）；`pandas`→`io`、`numpy`/`scipy`→`stats`、`openai`→`llm`、`streamlit`/`plotly`→`app`。移除 `httpx`（LLM 走 SDK）与尚未使用的 `PyYAML`/`Jinja2`。
- **配置**：新增 `src/knowflow/config.py`（pydantic-settings，读 `.env` + `KNOWFLOW_*`）；新增 `knowflow config` 子命令，密钥只显示 `(set)`/`(empty)`。
- **校验修复**：`validate_instance` 与 `check_examples` 补 `format_checker`——此前 8 处 `"format": "date-time"` 空转，`"昨天下午"` 也能通过。
- **可复现**：新增 `uv.lock`（84 包）与 `.python-version`（3.13）；`pyproject` 补 `license`。
- **CI**：`ci.yml` 从 `pip install -e .[dev]` 改为 `uv sync --frozen`，新增 `lock` job（`uv lock --check`）、矩阵扩到 3.11/3.12/3.13、加 `concurrency` 与 `timeout`；README 加 ci badge。

### 验证

```text
uv sync --frozen --extra dev  OK（venv 内无 httpx/pandas/numpy/scipy）
check_contracts        OK (16 schemas)
check_examples         OK (8 tables)
pytest                 14 passed
uv lock --check        OK
CI 里的每条命令已在本机逐条复跑通过
反例 generated_at="昨天下午" → validate_outputs 退出码 1（此前静默通过）
```

### 回退

`git checkout -- pyproject.toml README.md scripts src` 并删除 `uv.lock`、`.python-version`、`src/knowflow/config.py`。

---

## 2026-11-09 — M1-a：新增 pending 态 + 官方数据可复现接入

**`6a8aac9`** · PR [#2](https://github.com/JackChen070421/KnowFlow/pull/2) · `feat/r1-m1a-contract-pending` → `main`

### 改了什么

- **契约**：`evidence_state` 四态 → 五态，新增 `pending`（已作答、未评分）；`state_counts` 与 `records_by_state` 增加**必填** `pending`。canonical `v0.1 → v0.2`（minor）。
- **语义**：写明 `assigned` / `attempted` 判定；官方数据无 `assigned`，**禁止**由「测验节点可用题目」反推；新增 2 条可核对不变式。
- **数据**：新增 `scripts/ingest_raw.py`；入库纯指纹 `data/manifests/official-v1.structure.json`（21 文件，不含数据内容）；`data/raw/official-v1/` 仍被 gitignore。
- **质量门**：受限目录检查从「不得有任何文件」改为「文件必须被 Git 忽略」（`git check-ignore`）。
- **文档 / 测试**：AGENT §4 复现四步、`data/README.md` §0、README、shortcuts、schemas/README；测试 11 → 13。

### 验证

```text
check_contracts     OK (16 schemas)
check_examples      OK (8 tables)
pytest              13 passed
ingest_raw --check  CHECK OK dataset_id=official-v1 files=21 bytes=76518706
git ls-tree         data/raw 下无任何数据文件入库
```

### 回退

`git revert 6a8aac9`。本机 `data/raw/official-v1/` 不受影响（本来就不在版本库里）。

---

## 2026-11-08 — M0 地基：契约、合成样例、检查脚本

**`ed2400a`** · PR [#1](https://github.com/JackChen070421/KnowFlow/pull/1) · 55 个文件

### 改了什么

- **契约层**：16 个 JSON Schema（`schemas/input|output|llm`）+ `CONTRACT.md`（六个贯通 ID、四态、输出 JSON 结构）。
- **合成样例**：8 张 CSV（`examples/synthetic/input/`），可公开、可回归。
- **检查脚本**：`check_contracts`（结构/契约/隐私）、`check_examples`（CSV 行级）、`validate_outputs`（JSON 对 schema）。
- **协作**：`AGENT.md`（八条准则/角色/质量门）、`README.md`、`shortcuts.md`（自然语言 → 命令）、`data/README.md`、GitHub Actions。
- **测试**：11 个契约测试 + 5 份 fixtures。

### 验证

```text
check_contracts  OK (16 schemas)
check_examples   OK (8 tables)
pytest           11 passed
```

### 回退

`git revert ed2400a`；仓库回到只有占位文件的状态。

---

## 2026-11-07 — 初始化仓库

**`9520729`** · 2 个文件（空占位）

- 建仓，放入 `AGENT.md` / `README.md` 两个空文件，尚无内容。

---

## 模板（新增一条时复制）

```markdown
## YYYY-MM-DD — 一句话标题

**`<commit>`** · PR #N · `<branch>` → `main`

### 改了什么

- 按「契约 / 数据 / 代码 / 文档 / 测试」分组，只写结论。

### 验证

- 贴命令与结果；没跑就写「未验证」。

### 回退

- `git revert <commit>`，或需要人工清理的额外步骤。
```
