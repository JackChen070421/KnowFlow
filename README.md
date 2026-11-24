# KnowFlow

[![ci](https://github.com/JackChen070421/KnowFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/JackChen070421/KnowFlow/actions/workflows/ci.yml)

> **学情诊断与个性化学习智能体** · “智慧学伴”赛道
> 第二届北京市大学生“人工智能+”创新大赛

KnowFlow 把课程材料、题目、学生作答记录，变成三样可核对的东西：

1. **知识底座**：课标 → 知识点 → 材料 → Q-matrix → 先修/易混关系；
2. **学情画像**：五态证据（含 `pending`）、覆盖度、Beta-Binomial 掌握度、问题清单；
3. **学习建议**：`issue_id` → `material_id` → `reason` → `check` → `seq`。

> 当前状态：**任务1/2/3 的基础流程都已实现**。可在本机完成 canonical 数据适配、知识底座生成、按节点的个人/班级画像、规则版学习建议，以及三层的复算与证据回查；LLM 文字层已接入但**默认关闭**，只改写 `reason`/`check` 的文字，关闭或调用失败时自动回退模板。
> 入口：[`AGENT.md`](AGENT.md) · 数据契约：[`schemas/CONTRACT.md`](schemas/CONTRACT.md) · Git 操作：[`shortcuts.md`](shortcuts.md)

---

## 本机教师页与学生页

已增加独立展示层 `src/knowflow/web/`，复用任务 1/2/3，不修改公共 schema。**Windows 上双击根目录 `start-dashboard.cmd`**，等待启动窗口出现地址后，浏览器会自动打开**登录页** `/login`。运行时保留启动窗口；结束后按 `Ctrl+C`。

登录采用本机账号：首次启动会生成 `data/auth/users.json`（Git 忽略，密码为 scrypt 哈希）。默认账号为教师 `teacher` 与学生 `S001`，初始密码都是 `123456`；登录成功后，教师进入 `/teacher`，学生进入 `/student` 并锁定为本人数据。会话保存在进程内存中（HttpOnly + SameSite 严格），关闭启动窗口即失效；学生快照在服务端裁剪，只下发本人画像、作答与建议以及班级聚合，原始作答证据与教师设置接口对学生账号返回 403。忘记账号时删除 `data/auth/users.json` 后重新启动即可重建。

```powershell
Set-Location 'D:\桌面\KnowFlow'
.\.venv\Scripts\python.exe -m knowflow.web --open
```

- 登录页：`http://127.0.0.1:8765/login`；教师页：`/teacher`；学生页：`/student`（教师打开 `/student?student=S003` 可预览单个学生）。
- 班级学情按统计用途拆为六个子页面：**成绩分布、作答与覆盖、知识诊断、主题与班级、测验记录、学生热力图**。点击顶部入口切换，测验和班级筛选保持一致；统计说明通过弹窗阅读。支持直接链接（例如 `/teacher?report=history`）、刷新和浏览器后退。
- 统计页面按常用电脑视口安排为一屏；热力图与知识明细使用分页，每页数量随窗口高度调整。窄屏一次展示一张图，使用图表名称按钮切换，长表保留分页与横向阅读；极窄或低于 720px 高的窗口允许自然滚动，避免压小文字或截断内容。
- 「数据与证据」页卡片默认收起，只显示标题；点击展开审计流程、五态分布、判断边界、源文件指纹与质量发现。
- 学生列表支持分页、ID 搜索、得分率 / 覆盖率排序；点击学生进入独立画像，可返回原列表。画像分为“表现分析、知识明细、作答明细、作答与历史、学习建议”，教师另有“教学反馈”。知识与作答明细分页保留全部记录，模型估计与置信区间单独查看；学习建议与反馈表单随内容自然展开。
- 教师画像可比较个人与本班主题表现；学生账号只展示本人的主题得分率，不以裁剪后的个人明细冒充班级统计。图表仍使用原有确定性统计口径，未修改公共契约与诊断算法。
- 教师端「数据与证据」页底部「存疑数据」入口：列出复核线索、官方分与评分点、审查状态与复核备注，可回查原始作答并下载审核清单（清单不含原始作答）。
- 计划卡显示学习路径状态：进行中的项标“进行中”，已完成的项保留在历史中，并在建议上方提示“已完成 N 项，本轮只重排未开始项”。
- 教师端“教学调整与反馈闭环”：锁定/移除/换材料/调用时/调难度/写评语；学生端计划卡可直接反馈“太难/没看懂/需要更多例题”。调整不改分数与掌握度。
- 课程地图支持点击知识点查看课程要求、材料出处、评分依据和对应建议；切换“课程要求清单”可阅读目标与课标定位。课程地图直接读正式图谱 `knowledge/curriculum_graph.json`（经知识底座进入快照），未人工核对的关系标“待核验”，不补造。
- 学生账号登录后查看本人的知识状态、练习与学习建议；教师可从学生列表查看任意学生，或用 `/student?student=S003` 预览单个学生。另有数轴镜像、活动预算两个明确标识的自编互动实验。
- 侧栏底部齿轮「设置」（教师与学生都有）按顺序分四个分区：**个人信息**（用户名可改、姓名、头像、身份、当前学期如 `2026-2027秋`、任教班级与科目、弹窗修改密码需再次输入用户名）、**教学与 AI 偏好**（学习建议语气、报告长度、数据不足时直接提示或自动摸底，含 LLM 文字层配置）、**显示**（白天 / 黑夜 / 护眼三套主题 + 默认首页）、**数据分析**（覆盖度与掌握度阈值；保存后按新阈值重建诊断，覆盖缺失线同时作为最小证据数）。学生账号只看到个人信息与显示。账号资料与偏好保存在本机 `data/auth/users.json`（Git 忽略）；头像与主题存在浏览器本地。保存即写入本机 `.env`，等同于手工改后端配置；Key 不回显、不进入页面快照。保存后对之后生成的建议生效，已有成果需重建。
- 左下角「AI 学伴」：对话窗口按当前节点 / 班级 / 学生回答，只发送聚合摘要。配置了 LLM 时回答要过数字与 ID 锁，未配置或连续校验失败会回退本地规则回答；回答里的 `S001` / `K-07` / `M-021` 可点开对应依据。`?chat=1` 可直接展开。
- AI 学伴窗口可拖动标题栏移动、拖拽边缘 / 四角缩放；输入框旁可选「简洁 / 证据」：简洁少列数字、聚焦现状与下一步，证据按“结论 / 依据”分点。每条回答下方「查看推理依据」可展开事实卡步骤与证据（展示可核对依据，不暴露模型隐藏思维链）。
- 新练习提交保存在同一浏览器的 `localStorage`，教师页可查看，标记为“待评阅”。没有新提交时显示“未记录”，不会自动改写历史成绩或画像。练习记录仍属于当前浏览器，尚未跨设备同步。
- 图表口径：已评分得分率保留部分分；观测覆盖以节点可测题为分母；历史作答完成以有明确布置记录的题为分母。两个节点题目范围不同，折线只比较已评分记录量，不表示成绩增长。
- 分布口径：直方图区间左闭右开，最后一组包含 100%；无评分与范围未知的学生单列，不按零处理。首页平均得分率 / 中位数以学生为单位；主题和班级对比按已评分题目总分加权，题目关联多个知识点时不重复计分。个人与班级题目范围可能不同，不能据此作能力排名。折线标签自动避让，图表按卡片宽度绘制，窄屏不缩小文字。

首次启动需要已安装项目依赖、并已按数据说明放入 `data/raw/official-v1`。程序在 **Git 忽略的 `artifacts/web/<时间>/`** 中独立生成 canonical、知识底座、两个节点的画像与建议，经过校验后展示；不会覆盖原有 `data/interim` 和其他成果。后续启动复用缓存；数据或 Python/schema 变化会重建。**启动窗口必须保持打开**：关闭它等于停掉后端，页面保存设置或读取证据都会失败。强制刷新用 `python -m knowflow.web --refresh`，端口占用时用 `--port 8766`；**同一端口只允许一个启动进程**，重复双击会直接报“端口已被占用”，不会让旧进程随机接管请求。想让页面里的建议文字走 LLM，用 `python -m knowflow.web --refresh --llm`（之后普通启动沿用该模式，要关掉用 `--no-llm --refresh`；未配置 Key 或调用失败会自动回退模板，页面照常显示）。也可用 `--run artifacts/web/<时间>` 复用某次已生成成果；该目录中的知识底座、画像和建议必须是同一版本，启动时会复核。

新电脑安装：`python -m venv .venv`，然后 `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`。默认只连接本机，不需要 Node/npm、云服务器或模型密钥；只有 `--llm` 才需要 Key。官方数据不会随 Git 下载；请先按下面的数据落地步骤准备。

新增代码入口：`web/data.py` 连接三项任务并整理图表数据，`web/server.py` 提供本机页面与受限资料接口，`web/static/app.js` 实现双视角交互，`web/static/charts.js` 绘制图表，`web/static/styles.css` 保留基础视图样式，`web/static/workspace.css` 统一配色、文字层级、组件和统计子页面布局。`scripts/start_dashboard.ps1` 是 Windows 启动脚本。回归测试位于 `tests/diagnosis/test_web.py`，只用合成数据。

展示层统计与标签布局位于 `web/static/analytics.mjs`，不改公共契约和诊断算法。可选前端回归检查：`node --test tests/web/dashboard.test.mjs`（开发测试使用 Node，不影响页面启动，无需 npm 安装）。覆盖区间边界、缺失排除、均值 / 中位数、题目去重与标签避让。

答辩建议顺序：班级学情 → 点击 K-07 → 选择学生查看原始证据 → 查看学习材料与验证标准 → 切换学生页演示一次提交 → 跨域探索 → 数据与证据页。截图或下载的本机摘要含模拟学情成果，请勿加入公开 Git 仓库。

---

## 一句话原则

**数字由代码算，语言由模型写；所有结论必须能追到 ID。**

- 掌握度、正确率、覆盖度、排名：确定性代码计算，可复算。
- LLM：只做措辞/错因归类，不碰分数；原始数据不进模型。
- 缺失：`unobserved` / `insufficient_evidence`，不推断成“未掌握”。

---

## 三项任务

| 任务 | 产物 | 关键点 |
|---|---|---|
| **任务 1** 知识底座 | `knowledge_base.json` | 课标原文 + 出处；知识点树；Q-matrix；先修/易混图 |
| **任务 2** 学情画像 | `student_profile.json` / `class_profile.json` | 五态、覆盖度、Beta 后验、问题识别 |
| **任务 3** 学习建议 | `recommendation.json` | 材料真实、理由可追、顺序合理、检查可验证 |

完整字段/枚举见 [`schemas/CONTRACT.md`](schemas/CONTRACT.md)。

---

## 分层架构（8 层）

| 层 | 目录/模块 | 作用 | 现状 |
|---|---|---|---|
| **1 契约层** | `schemas/` | 定义输入 CSV、输出 JSON、LLM 边界；多人协作的接口 | ✅ 22 schemas |
| **2 数据层** | `data/`、`src/knowflow/io/` | `raw → canonical → interim`；隔离官方格式，原始数据不出本机 | ✅ 适配层 + 10 张 canonical 表 |
| **3 知识层** | `src/knowflow/knowledge/` | 课标/知识点/材料/Q-matrix/先修与易混图 → `knowledge_base.json` | ✅ 生成与校验、本机课标/关系标注接入；教学内容需人工复核 |
| **3b 图谱层** | `knowledge/`、`src/knowflow/knowledge/graph.py` | 教材细目图谱：稳定边 ID、类型、来源、审核状态；前端与建议共用 | ✅ 方向二；18 条关系待人工复核 |
| **4 诊断层** | `src/knowflow/cleaning/`、`src/knowflow/diagnosis/` | 五态、覆盖度、Beta-Binomial、问题识别、个体/班级画像 | ✅ 任务2基础版；只读 canonical，不写数据 |
| **4b 审查层** | `src/knowflow/review/` | 只读 canonical 提出存疑评分线索；本机追加式复核账本；双口径隔离 | ✅ 方向一 |
| **4c 反馈层** | `src/knowflow/feedback/` | 教学调整、学生反馈、补充证据、重新诊断差异 | ✅ 方向五（本机事件账本） |
| **5 建议层** | `src/knowflow/recommend/` | 材料检索、先修约束、学习路径、完成条件、可解释 probe 评分、validator | ✅ 规则版（模板生成、可复算；`--llm` 只润色 `reason`/`check`） |
| **6 LLM 边缘层** | `src/knowflow/llm/`、`schemas/llm/` | 只读 `llm_summary`，写 `reason`/`check`/摘要；数字锁、ID 锁、重试 2 次降级模板 | ✅ 可选，默认关闭 |
| **7 验证层** | `scripts/`、`tests/`、`src/knowflow/diagnosis/validation.py`、`src/knowflow/recommend/validation.py`、`src/knowflow/llm/guard.py` | 格式检查 + 数据复检 + 契约测试 + 诊断/建议复算 → `validation_report` | ✅ 核心检查脚本 + 242 tests |
| **8 协作层** | `AGENT.md`、`README.md`、`shortcuts.md`、`.github/` | 准则、分工、分支/PR、CI、事故处理 | ✅ |

**数据流**：

```text
data/raw → 适配层(io) → data/interim → knowledge → diagnosis → recommend → 输出 JSON
                                                              ↘ LLM 只写文字，不改数字
```

**三条边界**：

- **数据边界**：`raw → canonical → summary` 单向；LLM 只能看 summary。
- **计算边界**：数值只由代码计算，LLM 不改数字。
- **语言边界**：LLM 只填 `reason`/`check`/摘要；ID 与数字来自白名单。

当前已实现第 1、2、3、4、5、6、7、8 层：契约、canonical 数据层、知识底座、任务2诊断（按节点的五态/覆盖/Beta、个人与班级画像、复算与证据回查）、任务3建议（`issue_id → material_id → reason/check → seq`），以及可选的 LLM 文字层。第 5 层默认用规则+模板保证可复算；第 6 层只在显式 `--llm` 时改写 `reason`/`check`，数字与 ID 仍来自白名单，校验失败或调用失败会回退规则文本并记录在 `run_manifest.json` 的 `llm` 块里。

三个格式检查：`check_contracts`（结构/契约/隐私）、`check_examples`（10 张合成 CSV）、`validate_outputs`（单份 JSON 对 schema）。数据层另有四个脚本：`ingest_raw`（官方包原样落地 + 指纹，**不是** IO 适配层）、`build_canonical`（官方 CSV → 10 张 canonical 表 + 质量报告）、`validate_canonical`（canonical 复检）、`export_digest`（产物指纹互证）；知识底座走 CLI 的 `knowledge`；诊断走 CLI 的 `run` / `verify-run` / `evidence`；建议走 CLI 的 `recommend` / `verify-recommend`。自然语言映射见 [`shortcuts.md`](shortcuts.md)。

| 脚本 | 作用 | 成功标志 |
|---|---|---|
| `scripts/check_contracts.py` | 必需目录/文件、schema 解析与 `$id` 唯一、`data/raw` 与 `data/interim` 下的文件**必须被 Git 忽略**、`.gitignore` 规则 | `OK (18 schemas)` |
| `scripts/check_examples.py` | `examples/synthetic/input/` 10 张 CSV 的表头、必填、类型、主键、逐行 schema | `OK (10 tables)` |
| `scripts/validate_outputs.py` | 一份 JSON 对一份 schema | `OK (0 errors)` |
| `scripts/ingest_raw.py` | 官方材料落地 + `sha256`/行数指纹；`--check` 对照入库的 `data/manifests/*.structure.json` 自检；`--export-structure` 重新钉指纹 | `INGEST OK` / `CHECK OK` |
| `scripts/build_canonical.py` | 官方 CSV → `data/interim/<dataset_id>/` 10 张表 + `data_quality_report.json` | `ADAPT OK` + 10 表行数 |
| `scripts/validate_canonical.py` | G2 引用 + G3 一致性，并与磁盘产物逐字节比对 | `VALIDATE OK` |
| `scripts/export_digest.py` | 产物指纹（每张表行数 + sha256 + 聚合计数，不含内容）；`--check` 证明多人构建一致 | `DIGEST OK` |

---

## 仓库结构

```text
KnowFlow/
├─ AGENT.md / README.md / shortcuts.md / CHANGELOG.md
├─ schemas/                 # input / output / llm + CONTRACT.md
├─ examples/synthetic/      # 10 张合成 CSV，可公开、可回归
├─ src/knowflow/            # cli / contracts / config / io / cleaning / knowledge / diagnosis / recommend / review
├─ knowledge/               # 正式课程图谱（可入库的教学资产，不含学生数据）
├─ tests/                   # contract + io + diagnosis + review + fixtures
├─ scripts/                 # check_contracts / check_examples / validate_outputs / ingest_raw / build_canonical / validate_canonical / export_digest
├─ data/raw/<dataset_id>/   # 官方原始数据，原样放，gitignore
├─ data/manifests/          # 纯指纹（路径/哈希/行数），可入库
├─ data/interim/<dataset_id>/ # 适配后 canonical，gitignore
├─ data/reviews/<dataset_id>/ # 本机人工复核账本，gitignore
├─ data/progress/<dataset_id>/ # 本机学习路径进度事件，gitignore
├─ data/feedback/<dataset_id>/ # 本机教学反馈与补充证据，gitignore
└─ .github/                 # CI + PR 模板
```

**仓库不放**：设计方案、PDF、PPT、视频、真实结果包、真实学情数据、模型权重、密钥。
这些放仓库外的团队网盘或赛方提交渠道；仓库保持干净，避免污染和误传。

---

## 快速开始

要求：Python 3.11+、Git。

推荐用 [uv](https://docs.astral.sh/uv/)：它按 `uv.lock` 装出与其他人**完全一致**的依赖树，并自动使用 `.python-version` 指定的解释器。

```powershell
cd KnowFlow
uv sync --extra dev
uv run python scripts/check_contracts.py
uv run python scripts/check_examples.py
uv run python -m pytest
```

不用 uv 也可以用 pip，但装到的是当天最新版本，可能与 `uv.lock` 有差异：

```powershell
cd KnowFlow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

python scripts/check_contracts.py
python scripts/check_examples.py
python -m pytest

# 数据处理（先按「数据集放哪里」落地官方数据）
python scripts/build_canonical.py --dataset-id official-v1
python scripts/validate_canonical.py --dataset-id official-v1
python scripts/export_digest.py --check   # 与仓库里的产物指纹比对，证明"我和你算的一样"

# 任务2：canonical → 个人/班级画像 + 复算（输出只进 artifacts/，gitignore）
python -m knowflow.cli run --dataset official-v1
python -m knowflow.cli verify-run --run artifacts/run/<目录>
python -m knowflow.cli evidence --run artifacts/run/<目录> --record R-0001
```

任务2不需要 scipy：Beta 分布的分位数与尾概率在 `src/knowflow/diagnosis/beta.py` 里用纯 Python 实现，CI 与本地 `uv sync --extra dev` 即可跑全量测试。

### 跑任务1（知识底座）

```powershell
uv run python -m knowflow.cli knowledge --dataset official-v1 `
  --graph knowledge/curriculum_graph.json
# 无本机数据时，用合成样例验证：
uv run python -m knowflow.cli knowledge --dataset synthetic --input examples/synthetic/input
```

读取 canonical 的 objectives / knowledge / materials / qmatrix / edges 五张表，输出到
`artifacts/knowledge/<dataset>-<时间戳>/knowledge_base.json`；可用 `--output` 指定新 JSON 文件。
保留课标原文、出处、知识点父子关系、Q-matrix 与已有先修/易混边，不更改输入表。
写出前验证 schema、主键、引用、计数、测评覆盖及包含/先修图无环；已有输出文件不会覆盖。
`--graph` 把正式课程图谱（`knowledge/curriculum_graph.json`）合并进知识底座，前端与建议层读同一份。
可通过 `--curation <本机标注.json>` 接入经核对的课标原文、知识点说明和补充关系；图谱复核补丁写在
`curriculum_graph.edges`（只改审核状态/出处/理由/证据等级/版本，不能改端点或类型）。
标注包含 `dataset_id`、五张 CSV 的 `source_sha256`、`objectives`/`knowledge` 补丁数组和 `edges` 新增数组；
只允许更新课标原文/出处/备注、知识点 description 和有依据说明的边，禁止改变诊断 ID 或 Q-matrix。
输入哈希变化时拒绝套用旧标注，需重新复核；真实标注与成果不进 Git。
先修与易混关系来自 `edges.csv` 或正式图谱，没有证据时不自动生成；原始课标解析由已有 IO 适配层负责，
课标出处的真实性与关系的教学合理性仍需人工核对。输出仅在本机，默认目录不进 Git。

### 跑任务2（学情画像）

前置：`data/interim/official-v1/` 已有 10 张 canonical 表（先跑 `build_canonical`，见上一段）。

```powershell
# 1) 生成：默认跑全部节点；也可 --node latest 或 --node N02
uv run python -m knowflow.cli run --dataset official-v1
#    输出目录形如 artifacts/run/official-v1-<时间戳>/

# 2) 复核：重算五态/覆盖/Beta/班级汇总，并比对产物 sha256
#    不写 --run 就是"最近一次"；也可 --run artifacts/run/<实际目录名>
uv run python -m knowflow.cli verify-run

# 3) 证据回查：把某条记录的原始作答导出到本机（默认 gitignore）
uv run python -m knowflow.cli evidence --record R-0001
```

> `<目录>` 是占位符，要替换成 `dir artifacts/run` 里看到的真实名字（Windows 文件名不能含 `<` `>`）；`--run` 省略或写 `latest` 时自动用最新一次运行。

期望结果：`run` 打印 `student_profiles 80 / class_profiles 6 / gate pass`；`verify-run` 打印 `gate pass`；`evidence` 打印 `LOCAL EVIDENCE …/evidence/R-0001.json`。

产物（都在 `artifacts/`，gitignore）：

```text
artifacts/run/<目录>/
├─ nodes/<节点>/students/Sxxx.json    # 个人画像
├─ nodes/<节点>/classes/G1|G2|ALL.json # 班级画像
├─ diagnosis_input.json               # 本 run 的输入快照（不含原文）
├─ data_quality_report.json           # 逐行清洗决策 + 五态记账
├─ coverage_matrix.csv                # 学生×知识点的覆盖/掌握度总表
├─ case_candidates.json               # 规则选出的展示候选（需人工核对）
├─ run_manifest.json                  # 产物与源文件哈希、配置
├─ validation_report.json             # 复算门结果
└─ 运行说明.md                        # 一页纸说明，可直接贴进报告
```

失败时先看 `validation_report.json` 的 `checks[]`；`gate=fail` 表示复算与产物不一致，不要照样品提交。

### 跑任务3（学习建议）

前置：已有任务1的 `knowledge_base.json`（推荐用冻结版 `artifacts/knowledge/official-v1-frozen/`）和一次完成的任务2 run。

```powershell
# 1) 生成：默认只给最新节点（N02）出建议；--node all 可两次考试各出一份
uv run python -m knowflow.cli recommend `
  --run latest `
  --knowledge artifacts/knowledge/official-v1-frozen/knowledge_base.json `
  --node latest
#    输出目录形如 artifacts/recommend/official-v1-<时间戳>/

# 2) 复核：schema、issue/材料引用、数字锁、probe 未作答、产物 sha256
uv run python -m knowflow.cli verify-recommend
```

官方 `official-v1` 的期望结果：`students 40 / plan_items 99 / probe_needed_students 39 / gate pass`（数字随任务2 run 与阈值变化，不是写死值）。

产物（都在 `artifacts/`，gitignore）：

```text
artifacts/recommend/<目录>/
├─ nodes/<节点>/students/Sxxx.json    # 个人建议
├─ index.json                          # 学生/计划索引
├─ knowledge_base.json                 # 本次使用的任务1知识底座
├─ inputs/                             # 画像与诊断输入快照（用于复核）
├─ validation_report.json              # 门禁结果
├─ run_manifest.json                   # 哈希与策略
└─ 运行说明.md                         # 一页纸说明
```

规则版的三条硬约束：

- 每个学生最多 3 条计划；先处理薄弱/评分点失分，再处理证据不足；表现较好不强行加练。
- `probe_plan.items` 只用该生在该节点**未作答、未评分、非 pending、非存疑**的测评题；`needed` 必须等于 `items` 非空。
- 每个计划项带 `plan_item_id`、`plan_version`、`status`、`prerequisite_item_ids` 与结构化 `completion_condition`；`probe_plan.scoring` 给出候选题的分量、权重和总分，可逐项复算。
- `difficulty`/`est_minutes` 是**规则推算值**：官方材料没有这两个字段，按题型/认知类型估算，运行说明里已声明，不能当作官方难度或精确用时。

### 跑方向一：存疑评分审查

目标：把「有官方分数」和「评分可信」分开。规则只提出**复核线索**，人工结论作为**独立事件**追加，官方分数永远不改。

```powershell
# 1) 扫描：只读 canonical，产出复核线索（不改官方分数、不含原始作答）
uv run python -m knowflow.cli review-scan --dataset official-v1
#    输出目录形如 artifacts/review/official-v1-<时间戳>/

# 2) 人工复核：每个结论追加一行到本机账本 data/reviews/（Git 忽略）
uv run python -m knowflow.cli review-decide --record R-0685 `
  --status dismissed --note "核对原始作答与参考答案：评分无误" `
  --source "原始 CSV 第 686 行 + 评分点记录"

# 3) 诊断与建议带上审查口径
uv run python -m knowflow.cli run --review artifacts/review/<目录> --review-policy official
uv run python -m knowflow.cli recommend --run latest --node all
```

- `--review-policy official`（默认）保留官方账本做顶层数字，同时在画像里给出 `review.usable_*`（剔除存疑后的口径）；`exclude_flagged` 让顶层数字也改用剔除后的口径。两套口径都可复算，`run_manifest.review` 记录策略、报告哈希与计数。
- 被标记记录不进入 `issues[].rubric_evidence`，改列 `disputed_rubric_evidence`；建议项只列 `basis_records`，并在 `review_required` 中交回人工，不据此安排巩固。
- 账本绑定三张 canonical 表的 SHA-256：数据重建后旧结论会被拒绝套用，必须重新扫描复核。
- 规则（`review-rules-1`）：作答与参考答案字面一致却未满分（单值题；解答题仅限 0 分）、官方得分与评分点合计不一致；「得分超满分已截断」只作审计线索；「作答≠参考答案却满分」默认关闭（写法差异会全线误报）。

官方 `official-v1` 的实测：799 条保留记录中 4 条线索（R-0685、R-0133 参与隔离；R-0361、R-0535 仅审计），排除后 2 个「学生 × 知识点」的数值变化、**没有状态翻转**。

产物（都在 `artifacts/`，gitignore）：

```text
artifacts/review/<目录>/
├─ review_report.json   # 候选、官方分快照、回查行号、人工结论历史
├─ run_manifest.json    # 源表哈希、规则版本、账本哈希
└─ 运行说明.md
```

### 跑方向二：正式课程图谱

目标：前端、诊断、建议读**同一份**受 Schema 约束的图谱；每条关系有稳定 `edge_id`、类型、来源、理由和审核状态；只有 `reviewed` 的先修关系参与排序。

```powershell
# 1) 带图谱构建知识底座（前端与建议都读这一份）
uv run python -m knowflow.cli knowledge --dataset official-v1 `
  --graph knowledge/curriculum_graph.json

# 2) 复核关系：用本机标注文件把某条边标为 reviewed，必须给出可核对出处
#    详见 knowledge/README.md 的 curation 示例
uv run python -m knowflow.cli knowledge --dataset official-v1 `
  --graph knowledge/curriculum_graph.json --curation <本机标注.json>

# 3) 重新出建议并复核
uv run python -m knowflow.cli recommend --run latest --node all
uv run python -m knowflow.cli verify-recommend
```

- 图谱：21 个教材细目、18 条关系（16 先修 + 1 易混 + 1 相关），**当前全部是 `draft`**，逐条带 `source_reference` 与 `rationale`。
- 关系语义：`prerequisite` 有向；`confusable_with` / `related_to` 对称，按 `source_node_id < target_node_id` 存储一次；`related_to` 不是先修。
- 建议层：`prerequisite_check` 输出 `reviewed_edges` / `draft_edges` / `pending_knowledge_ids`；未审核关系只提示“关系待核验”，不排序、不阻断。
- 易混：只有 reviewed 且有同时映射两个知识点的材料时才加对比练习；否则只给教师补充观察提示，不虚构对比题，也不据此判定学生混淆。
- 超出 3 项预算的 issue 写入 `deferred[]` 并给理由（先修优先 / 无可用材料）。
- 官方底座目前没有任何 **K 级** 先修边，所以正式数据的计划顺序不会因图谱改变；排序逻辑由合成数据测试覆盖（`tests/diagnosis/test_graph_planning.py`），人工复核并补 K 级边后即生效。

### 跑方向三：学习路径与主动补充观测

目标：把平面建议升级为有依赖、有完成条件、可调整版本的学习路径，并把 probe 从“按材料编号取前 3”改为可解释的启发式评分。

```powershell
# 1) 生成带路径的计划（每个学生一份）
uv run python -m knowflow.cli recommend --run latest --node all
#    每条计划项含 plan_item_id / prerequisite_item_ids / completion_condition / status

# 2) 记录一次“开始/完成”（本机事件，不改诊断、不代表答对）
uv run python -m knowflow.cli path-event --student S001 --node N01 --seq 1 `
  --event completed --plan artifacts/recommend/<目录>
#    默认写入 data/progress/official-v1/events.jsonl（Git 忽略）

# 3) 基于进度重新规划：保留已完成项，只重排未开始项
uv run python -m knowflow.cli recommend --run latest --node N01 `
  --progress data/progress/official-v1/events.jsonl `
  --previous artifacts/recommend/<上一版目录>
uv run python -m knowflow.cli verify-recommend
```

- 计划项：`plan_item_id`（`PL-<学生>-<节点>-v<版本>-<知识点>`）、`prerequisite_item_ids`（只能指向更早项）、`prerequisite_knowledge_ids`、`completion_condition`（`probe_evidence` / `full_credit`）。
- 版本：`plan_id` / `plan_version`；`history[]` 永久保留已完成项（不计入本轮 3 项预算）；`plan_diff` 记录上一版、本版的新增/删除/保留/完成与原因。
- Probe：候选必须是本节点未作答、未评分、非 pending、非存疑的测评题；分量 `issue_relevance / coverage_gain / prerequisite_value / material_quality / redundancy_penalty`，`total = Σ 权重×分量`，权重写入 `probe_plan.scoring.weights` 与 `run_manifest.policy.probe_weights`。
- 权重可用 `--probe-weights weights.json` 覆盖（五个分量名），实际权重同时写入 `probe_plan.scoring.weights` 与 `run_manifest.policy.probe_weights`。
- **边界**：官方没有题目难度/区分度/响应模型，这里给的是规则启发式，不是 IRT 信息量；进度事件不携带分数、不改诊断。“新证据→重新诊断”的完整闭环见方向五。

### 跑方向五：教学反馈与补充证据闭环

目标：把教师调整、学生反馈和补充作答串成可追溯闭环；**官方分数与 canonical 不改**。

```powershell
# 1) 录入一次补充作答（派生证据 EV-...，不写 canonical）
uv run python -m knowflow.cli feedback-attempt --student S001 --node N01 `
  --material M-003 --score 1.0 --max-score 1.0

# 2) 重新诊断，并与上一版对比
uv run python -m knowflow.cli run --dataset official-v1 --node N01 `
  --supplemental data/feedback/official-v1/events.jsonl `
  --previous artifacts/run/<上一版> --output artifacts/run/<新版>
uv run python -m knowflow.cli verify-run --run artifacts/run/<新版>
#    diagnosis_diff.json：逐学生状态/掌握度/issue 变化

# 3) 教师调整计划（锁定/移除/换材料/调时间/调难度）
uv run python -m knowflow.cli feedback-adjust --student S001 --node N01 `
  --plan artifacts/recommend/<目录> --seq 1 --action lock `
  --reason "课堂统一讲" 
uv run python -m knowflow.cli recommend --run artifacts/run/<新版> --node N01 `
  --previous artifacts/recommend/<上一版>
uv run python -m knowflow.cli verify-recommend

# 4) 界面：教师端“教学调整与反馈闭环”；学生端计划卡反馈按钮
uv run python -m knowflow.web
```

- 账本：`data/feedback/<dataset>/events.jsonl`（追加式、Git 忽略）；事件类型 `supplemental_attempt` / `teacher_adjustment` / `teacher_comment` / `student_feedback`。
- 补充证据：转成 `EV-...` 记录，仅进入派生 run 的 `supplemental_input.json`；`diagnosis_input.json` 仍是 canonical。
- 教师调整：只改计划；锁定项重排时保留，移除项进入 `deferred`，`restore` 可逆；按 `issue_id` 跨版本回退匹配。
- **边界**：本机单用户演示，无账号/权限；补充证据未经人工复核，不能当官方成绩；教师调整不改诊断与分数。

### 可选：接入 LLM 文字层

默认关闭。打开后只改写任务3的 `reason`/`check`，不碰任何数字、ID 或诊断结论。两种打开方式等价：

- **网页**：左下角齿轮「设置」→ 打开「LLM 模式」→ 选厂商、填 API Key → 保存（写入本机 `.env`）。
- **命令行**：编辑 `.env`，或使用下面的命令。

```powershell
# 1) 安装可选依赖，并在 .env 填写 KEY（.env 已被 Git 忽略）
uv sync --extra llm
#    开发者同时要保留测试工具：uv sync --extra dev --extra llm
#    KNOWFLOW_LLM_ENABLED=true
#    KNOWFLOW_LLM_API_KEY=...

# 2) 批量：任务3 生成时润色，逐条失败自动回退模板
uv run python -m knowflow.cli recommend --knowledge artifacts/knowledge/official-v1-frozen/knowledge_base.json --llm

# 3) 单题解释：只发一份聚合摘要，同时落盘输入与输出
uv run python -m knowflow.cli explain --student S001 --knowledge-id K-07
```

- 输入只有 `llm_summary`（计数、比率、状态、错误模式 + 数字/ID 白名单），不含原始作答、姓名或自由文本。
- 输出必须通过 `schemas/llm/llm_response.schema.json` 与 `src/knowflow/llm/guard.py`：schema、数字锁、ID 锁、必须引用 `issue_id` 与至少一个材料。
- 每项最多 3 次（首次 + 重试 2 次），仍不合格就回退模板；`run_manifest.json` 的 `llm` 块记录 `items_used` / `items_fallback` / `attempts` / `errors`。
- `explain` 把 `llm_summary.json` 与 `explain.json` 写到 `artifacts/explain/`（Git 忽略），可直接作为答辩证据。

按层装可选依赖（core 只有校验与配置，其余按需）：

| extra | 内容 | 何时需要 |
|---|---|---|
| `io` | pandas | 可选：当前 io 层用标准库 `csv`，不依赖 pandas |
| `stats` | numpy, scipy | 可选统计库；**当前诊断不依赖**（Beta 用纯 Python 实现） |
| `llm` | openai | 任务3 的 LLM 文字层（默认关闭；`--llm` / `explain` 才需要） |
| `app` | streamlit, plotly | 演示界面 |
| `dev` | pytest, ruff, mypy, pre-commit | 开发与 CI |

Linux / macOS：

```bash
source .venv/bin/activate
python scripts/check_contracts.py
python scripts/check_examples.py
pytest
```

校验一个产物：

```powershell
python scripts/validate_outputs.py `
  --schema schemas/output/student_profile.schema.json `
  --data tests/fixtures/student_profile.min.json
```

> 任务2 的业务入口是 `knowflow run` / `verify-run` / `evidence`；任务3 是 `knowflow recommend` / `verify-recommend`（见上）；`check` / `validate` / `config` / `version` 仍在。数据处理仍由脚本完成（`build_canonical` / `validate_canonical` / `export_digest`）。

---

## 数据集放哪里（必读）

真实数据只放本机，不进 Git。第一次接数据的组员照下面做：

```text
KnowFlow/data/
├─ raw/<dataset_id>/          # 官方原始文件，原样放，不改名
│  ├─ 原始 CSV / Excel / JSON
│  ├─ 数据字典 / 说明
│  └─ manifest.json           # 文件名、哈希、行数、来源
└─ interim/<dataset_id>/      # 适配后的 canonical，下游只读这里
```

| 数据类型 | 放哪 | 进 Git？ |
|---|---|---|
| 官方原始数据 | `data/raw/<dataset_id>/` | ❌ |
| 适配后 canonical | `data/interim/<dataset_id>/` | ❌ |
| 合成样例 | `examples/synthetic/`、`tests/fixtures/` | ✅ 仅合成 |
| 数据字典 / 本机 manifest | 跟原始数据放一起 | ❌ |
| **纯指纹清单** | `data/manifests/<dataset_id>.structure.json` | ✅ 只有路径/哈希/行数，无数据内容 |

`<dataset_id>` 用短英文/数字，例如 `dev-2026-11`、`eval-holdout`。

当前赛题数据集已落地为 **`official-v1`**：`data/raw/official-v1/`（21 文件 / 73 MB，目录结构与文件名原样保留），指纹清单入库为 `data/manifests/official-v1.structure.json`，组员一条 `--check` 就能确认自己那份是否字节一致。`data/raw` 仍全封闭，`check_contracts` 会用 `git check-ignore` 复核。详见 [`data/README.md`](data/README.md) §0 与 [`AGENT.md`](AGENT.md) §4。

**接数据 5 步**：

1. 原样放：`python scripts/ingest_raw.py --source "<赛题资料包路径>"`，一步完成复制 + 指纹，不改列名。
2. 留字典：数据字典/字段说明随包一起放（脚本按原结构复制，`字段说明.csv` 已在包内）。
3. 记 manifest：脚本自动写 `data/raw/<dataset_id>/manifest.json`（`sha256` + 行数 + 字节数）。
4. 写适配：在 `src/knowflow/io/` 把官方列名映射到 canonical，输出到 `data/interim/<dataset_id>/`。
5. 跑检查：`ingest_raw --check` + `check_contracts` + `check_examples` + `validate_outputs` + `pytest`。

> ⚠️ **`git pull` 不会带来任何数据。** 新组员必须自己跑第 1 步，否则 `data/raw/` 是空的——这是有意设计，不是故障。

**三条硬规则**：

- `examples/synthetic/` 和 `tests/fixtures/` 是**合成样例**，永远不要放真实数据。
- `data/raw/` 和 `data/interim/` 被 `.gitignore` 忽略；公开仓库里没有真实数据。
- 下游只读 `data/interim/`，不直接读官方列名；原始数据不出本机、不进 LLM。

确认文件没被 Git 跟踪：

```powershell
git check-ignore -v data/raw/<dataset_id>/records.csv
```

详细的数据分级、manifest、赛后删除规则见 [`data/README.md`](data/README.md)。

---

## 数据与隐私

- `data/raw/`、`data/interim/` 被 `.gitignore` 忽略；真实 CSV/模型权重/密钥永不提交。
- 网页设置写入的 API Key 只在仓库根目录 `.env`（`.gitignore` 第 8 行）；不要 `git add -f .env`，也不要直接打包整个项目目录提交（`.gitignore` 不会作用于 zip）。录屏/截图前把 Key 输入框留空或先关闭 LLM。
- 公开仓只放 `examples/` 下的**合成样例**；真实数据只在本地处理。
- 送进 LLM 的只有 `llm_summary`（计数/比率/状态/错误模式），不含原始作答、姓名、自由文本。
- 赛后按要求删除数据，保留 manifest（文件名/哈希/行数）与删除记录，不保留数据副本。

---

## 协作

- 角色：R1 知识/契约、R2 数据/诊断、R3 建议/LLM、R4 质量/交付；一人可兼多角。
- 流程：Issue → 分支 → 先契约/测试 → 实现 → 跑检查 → PR → 非作者 review → 合并。
- 提交前跑：`check_contracts` + `check_examples` + `validate_outputs`（有产物时）+ `pytest`，全绿再提 PR；自然语言映射见 `shortcuts.md`。
- 分支：`feat/r2-diagnosis-beta`、`fix/r1-qmatrix-ref`、`docs/r4-shortcuts`、`test/r4-validator`。
- **Git/GitHub 的具体命令与自然语言映射**：见 [`shortcuts.md`](shortcuts.md)。
- 一任务一 PR；不直接 push `main`；不 force-push；合约变更需 R1 + R4 双审。

---

## 路线图

| 阶段 | 内容 | 状态 |
|---|---|---|
| **M0 地基** | 最小目录、契约、合成样例、契约检查 | ✅ |
| **M1 知识底座** | 适配器、knowledge/Q-matrix/图 | 🟡 生成/校验入口与本机标注已接入；先修/易混关系待人工复核，官方内容成果本机保存 |
| **M2 诊断** | 五态、覆盖度、Beta、画像 | ✅ 基础版（按节点、可复算、证据可回查） |
| **M3 建议** | 检索、约束、规则理由、validator；可选 LLM 润色 | ✅ 规则版 + 可选 LLM 文字层 |
| **M4 交付** | 演示与提交（仓库外） | ⬜ |

每步只加当前需要的模块；不预先铺空目录。

---

## 文档

| 想知道 | 读 |
|---|---|
| 协作准则、角色、质量门 | [`AGENT.md`](AGENT.md) |
| **最近改了什么、怎么验证、怎么回退** | [`CHANGELOG.md`](CHANGELOG.md) |
| 字段、ID、枚举、CSV/JSON 结构 | [`schemas/CONTRACT.md`](schemas/CONTRACT.md) |
| Schema 怎么用/怎么改 | [`schemas/README.md`](schemas/README.md) |
| Git/GitHub 操作 | [`shortcuts.md`](shortcuts.md) |
| 合成样例 | [`examples/synthetic/README.md`](examples/synthetic/README.md) |
| 数据存放与删除 | [`data/README.md`](data/README.md) |

---

## 声明

- 代码许可证待团队确认；第三方组件/课程材料的来源与许可证在仓库外登记。
- 赛题数据、课程材料、学生记录不随本仓库分发；`examples/` 均为自行构造的合成样例。
