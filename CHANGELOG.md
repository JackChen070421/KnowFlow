# 变更记录

记录**会影响他人**的改动：改了什么、为什么、怎么验证、怎么回退。
`git log` 是逐提交流水；这里只记「一个可交付的最小单元」，供回溯、交接，以及答辩时讲"我们是怎么迭代的"。

- **方向**：最新在最上（第一条 `---` 之后）；同日"后发生在前"。
- **粒度**：一个 PR / 一组相关改动一条；纯措辞、格式化不必记。
- **长度**：每条 ≤ 15 行。论证细节放 PR 正文，这里只留结论与证据。
- **没验证就写"未验证"**，不要留空。

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
