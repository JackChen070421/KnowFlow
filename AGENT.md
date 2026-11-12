# AGENT.md — KnowFlow 协作入口

> 适用：所有参与 KnowFlow 的人与 AI Agent。
> 最后更新：2026-11-12 · v0.12
> 阅读顺序：本文件 → [`README.md`](README.md) → [`CHANGELOG.md`](CHANGELOG.md)（最近改了什么）→ [`schemas/CONTRACT.md`](schemas/CONTRACT.md) → 你的任务。
> Git/GitHub 操作见 [`shortcuts.md`](shortcuts.md)；不要一上来通读全仓。

## 0. 30 秒总览

KnowFlow 是“智慧学伴”赛道的学情诊断与个性化学习智能体。输入课程材料、题目、学生作答记录，输出：

1. **知识底座**：课标 → 知识点 → 材料 → Q-matrix → 先修/易混关系；
2. **学情画像**：五态证据（含 `pending`）、覆盖度、Beta-Binomial 掌握度、问题清单；
3. **学习建议**：`issue_id` → `material_id` → `reason` → `check` → `seq`。

**一句话：数字由代码算，语言由模型写；所有结论必须能追到 ID。**

当前已实现 **任务2基础流程**：canonical 数据落盘、按节点的五态/覆盖/Beta 与个人/班级画像、`verify-run` 复算、按记录回查本机原文。课标知识底座（任务1）与学习建议/LLM（任务3）仍待接入。

## 1. 八条准则

1. **契约先行**：`schemas/` 是接口；改字段/枚举/ID 先改 schema + `CONTRACT.md`，再改代码。
2. **数字由代码算**：`mastery`、正确率、覆盖度、排名只能由确定性代码产出；LLM 不改数字。
3. **原始数据不出本机**：`data/raw`、`data/interim` 不进 Git、不进 LLM；LLM 只接收 `llm_summary`。
4. **缺失不等于未掌握**：无记录 = `unobserved`，输出 `insufficient_evidence`，不推断成 0 或“不会”。
5. **证据链闭合**：结论带 `record_id`/`material_id`/`knowledge_id`；建议带 `issue_id` 与可验证的 `check`。
6. **小步可回滚**：一任务一分支一 PR；不顺手大重构；不 force-push `main`。
7. **先验证后提交**：schema/引用/一致性/隐私检查通过才算完成；没有输出就不说“已完成”。
8. **人类签字**：对外提交物由人复核；Agent 不自行宣布可提交。

## 2. 仓库边界

**只放**：代码、schema、合成样例、契约检查、必要的协作说明（README/AGENT/shortcuts/**CHANGELOG**）。

**不放**：设计方案/PDF/PPT/视频/真实结果包/项目文档/真实学情数据/模型权重/密钥。
这些放仓库外的团队网盘或赛方提交渠道；仓库保持干净，避免污染和误传。

## 3. 分层架构（8 层）

| 层 | 目录/模块 | 作用 | 现状 |
|---|---|---|---|
| **1 契约层** | `schemas/` | 输入 CSV、输出 JSON、LLM 边界；多人接口 | ✅ |
| **2 数据层** | `data/`、`src/knowflow/io/` | `raw → canonical → interim`；隔离官方格式 | ✅ |
| **3 知识层** | 未来 `knowledge/` | 课标/知识点/材料/Q-matrix/先修与易混图 | 🟡 |
| **4 诊断层** | `src/knowflow/cleaning/`、`src/knowflow/diagnosis/` | 五态/覆盖度/Beta/问题/个体与班级画像；只读 canonical，不写数据 | ✅ 任务2基础版 |
| **5 建议层** | 未来 `recommend/` | 检索/约束/排序/理由/探测小测/validator | 🟡 |
| **6 LLM 边缘层** | `schemas/llm/`、未来 `llm/` | 只读摘要，写 `reason`/`check`；数字锁/降级 | 🟡 |
| **7 验证层** | `scripts/`、`tests/`、未来 `validation/` | 三检查脚本 + 数据落地 + 契约测试 + 校验报告 | ✅ |
| **8 协作层** | `AGENT/README/shortcuts/.github` | 准则/流程/分支/PR/CI | ✅ |

数据流：`data/raw → io → data/interim → knowledge → diagnosis → recommend → JSON`；LLM 只写文字。

**三条边界**：

- **数据边界**：`raw → canonical → summary` 单向；LLM 只能看 summary。
- **计算边界**：数值只由 `diagnosis`/`recommend` 的纯函数计算。
- **语言边界**：LLM 只填 `reason`/`check`/摘要等文字；ID 与数字来自白名单。

第 3、5、6 层先冻结 schema，逐步加代码；任务2（第 4 层）已完成基础版，任务3 与 LLM 仍待接入；暂不建 UI、报告层、交付物目录。

## 4. 目录（最小）

```text
KnowFlow/
├─ AGENT.md / README.md / shortcuts.md / CHANGELOG.md
├─ .gitignore / .gitattributes / .env.example / pyproject.toml
├─ schemas/                 # input / output / llm + CONTRACT.md
├─ examples/synthetic/      # 10 张合成 CSV，可公开、可回归
├─ src/knowflow/            # cli / contracts / config / io / cleaning / diagnosis
├─ tests/                   # contract + io + diagnosis + fixtures
├─ scripts/                 # check_contracts / check_examples / validate_outputs / ingest_raw / build_canonical / validate_canonical / export_digest
├─ data/
│  ├─ raw/<dataset_id>/     # 官方原始数据，原样放，不进 Git
│  ├─ interim/<dataset_id>/ # 适配后 canonical，不进 Git
│  └─ README.md
└─ .github/                 # CI + PR 模板
```

**数据集放置（必读）**：官方原始数据放 `data/raw/<dataset_id>/`（原样、不改名）；canonical 中间表放 `data/interim/<dataset_id>/`；两者都不进 Git。`examples/synthetic/`、`tests/fixtures/` 只放合成样例，**永远不放真实数据**；下游只读 `interim/`。

> ⚠️ **`git pull` 不会带来数据。** `data/raw/**` 与 `data/interim/**` 都在 `.gitignore` 里，新组员拉下来只有 `README.md` 和两个 `.gitkeep`。所以“数据集放哪”不是口头约定，而是一条**必须执行的命令**。

**复现当前结构（每台新机器、每个新组员都要跑一次）**：

| 步骤 | 命令 | 期望输出 |
|---|---|---|
| 1. 取材料 | 赛题组统一渠道获取 `赛题资料包`，解压到本机任意路径 | 目录内含 `1_赛题规则.pdf` |
| 2. 落地 | `python scripts/ingest_raw.py --source "<上一步路径>"` | `INGEST OK dataset_id=official-v1 files=21 bytes=76518706` |
| 3. 自检 | `python scripts/ingest_raw.py --check` | `CHECK OK ...` + `compared against .../data/manifests/official-v1.structure.json` |
| 4. 验不进库 | `python scripts/check_contracts.py` | `files under data/raw and data/interim are git-ignored` |
| 5. 处理数据 | `python scripts/build_canonical.py --dataset-id official-v1` | `ADAPT OK` + 10 表行数（3/9/65/63/9/40/2/799/806/0） |
| 6. 复检 | `python scripts/validate_canonical.py --dataset-id official-v1` | `VALIDATE OK dataset_id=official-v1 tables=10 records=799` |

- `dataset_id` 固定为 `official-v1`，**不要改名**：文档、审计报告与下游都按这个名字引用。
- **原样复制**：不改名、不改列、不删干扰项（B01–B08 全留；其中只有 B02/B05/B06 对应 T03/T01/T02）。
- **两份指纹，分工不同**：
  - `data/manifests/official-v1.structure.json` —— **入库**。纯指纹（路径 + `sha256` + 字节数 + 行数），不含任何数据内容。第 3 步默认拿它当基准，所以组员不用交换文件就能知道“我这份和主仓是否字节一致”。
  - `data/raw/official-v1/manifest.json` —— **不入库**。本机落地时生成，多带 `received_at`/来源等易变字段，只用于自己复查。
- **官方材料版本变化时**（赛方更新了包）：必须 `--export-structure` 重新钉住指纹，并在 PR 里写明变了几行、为什么。**不要**为了“让检查过”去改这份清单。
- `scripts/ingest_raw.py` **不是 IO 适配层**：它只做“复制 + 指纹”，不做任何列名/ID 映射（映射见 [`schemas/CONTRACT.md`](schemas/CONTRACT.md) §6，实现在 `src/knowflow/io/`）。
- 收尾确认：`git status --porcelain` 应为空；`git ls-files data/` 只应出现 `data/README.md`、`data/manifests/official-v1.structure.json`、`data/raw/.gitkeep`、`data/interim/.gitkeep`。

业务模块（`io/cleaning/knowledge/diagnosis/recommend/llm`）按任务逐个添加，不预先铺空目录。

## 5. 数据契约

六个贯通 ID：

| 实体 | 字段 | 示例 |
|---|---|---|
| 课标条目 | `objective_id` | `OBJ-7M-03` |
| 知识点 | `knowledge_id` | `K-07` |
| 材料/题目 | `material_id` | `M-021` |
| 作答记录 | `record_id` | `R-0031` |
| 学生 | `student_id` | `S012` |
| 问题 | `issue_id` | `IS-012-01` |

关键枚举：

| 枚举 | 取值 |
|---|---|
| `evidence_state` | `observed_correct` / `observed_wrong` / `assigned_not_attempted` / `pending` / `unobserved` |
| `status` | 原五类 + `mixed_performance`（中间表现，不是证据不足）/ `not_applicable`（本节点无该知识点可测题目） |
| `issue_type` | 原六类 + `performance_gap`（表现差距、错因未定）/ `score_point_gap`（有官方评分点依据的失分） |
| `material_type` | `reference` / `explain` / `example` / `practice` / `assessment` / `probe` |

字段、CSV 列、输出结构以 [`schemas/CONTRACT.md`](schemas/CONTRACT.md) 与 `schemas/` 为准。

## 6. 角色

| 角色 | 负责 | 主要产物 |
|---|---|---|
| **R1 知识/契约** | 课标/知识点/Q-matrix/图；守 schema | `knowledge_base.json`、schema |
| **R2 数据/诊断** | 适配、清洗、五态、覆盖度、Beta | canonical 表、`student_profile.json` |
| **R3 建议/LLM** | 材料检索、约束、排序、理由、探测小测 | `recommendation.json`、prompt |
| **R4 质量/交付** | 校验、测试、CI、隐私、提交检查 | `validation_report.json`、测试 |

一人可兼多角；**每个产物只有一个最终负责人**。任务写在 GitHub Issue/PR，不另建任务板。

## 7. 工作流

Git/GitHub 的具体命令与自然语言映射见 [`shortcuts.md`](shortcuts.md)。

1. **领任务**：Issue 写清目标、输入、输出、验收；没有 Issue 就先开一个。
2. **开分支**：`feat/r2-diagnosis-beta`、`fix/r1-qmatrix-ref`、`docs/r4-shortcuts`、`test/r4-validator`。
3. **先契约/测试**：改 schema/fixture，再写实现。
4. **跑验证**：`check_contracts` + `check_examples` + `validate_outputs`（有产物时）+ `pytest`（见 §8）。
5. **提 PR**：关联 Issue；贴命令与结果；作者不能自审；合约变更需 R1 + R4 双审。
6. **记变更**：在 [`CHANGELOG.md`](CHANGELOG.md) 顶部加一条（改了什么 / 验证 / 回退），一个可交付单元一条。
7. **合并**：通过检查后合并；删分支；更新 Issue。禁止直接 push `main`、禁止 force-push。

提交信息：Conventional Commits；正文写“改了什么 / 为什么 / 怎么验证 / 未验证项”。

## 8. 质量门

| 门 | 检查 | 现在怎么跑 |
|---|---|---|
| G0 结构/样例 | 必需目录/文件、schema 头、CSV 表头/类型/主键 | `check_contracts` + `check_examples` |
| G1 Schema | 字段/类型/枚举 | `python scripts/validate_outputs.py --schema ... --data ...` |
| G2 引用 | 所有 ID 存在、无悬空 | 数据层 `python scripts/validate_canonical.py`；诊断层 `python -m knowflow.cli verify-run`（默认最近一次） |
| G3 一致性 | `evidence_count`=长度、`mastery` 可复算 | 数据层去重/五态已覆盖；诊断层由 `verify-run` 重算五态、覆盖、Beta、班级汇总并比对产物哈希 |
| G4 隐私 | 受限数据未入库（`git check-ignore` 复核）/无密钥/PII | `python scripts/check_contracts.py` |
| G5 测试 | 契约/单元/端到端 | `python -m pytest` |

G2/G3 已覆盖 canonical 数据层与任务2诊断层；任务3 的约束/排序校验尚未实现，**不假装通过**，在 PR 里写“待实现”。

## 9. LLM 规则

- 输入只能是 `schemas/llm/llm_summary.schema.json`：计数、比率、状态、错误模式；不含原始作答/姓名/自由文本。
- 输出只能是 `schemas/llm/llm_response.schema.json`：`reason`/`check`/摘要/错因标签。
- **数字锁/ID 锁**：输出中的数字与 ID 必须来自输入白名单；不合规重试 ≤2 后降级模板。
- `llm.enabled=false` 时全流程必须能跑通（模板/规则），LLM 可关闭。
- prompt 与代码同审；不把真实数据/密钥/姓名放进 prompt 或示例。

## 10. 数据安全

- 数据集放置见 §4；`data/raw`、`data/interim`、真实 CSV、模型权重、`.env` 永不提交；`examples/` 只放合成数据。
- 官方数据先脱敏再落盘；姓名/学号/联系方式直接丢弃。
- 第三方 API 只接收 `llm_summary`；关闭供应商训练/留存（若可配置）。
- 赛后按要求删除数据；保留 manifest（文件名/哈希/行数）和删除记录，不保留数据副本。
- 发现数据/密钥误入 Git：立即停止推送，按 `shortcuts.md` §5 处理并轮换密钥。

## 11. 常用命令

```powershell
# 契约/隐私
python scripts/check_contracts.py

# 合成 CSV 行级校验
python scripts/check_examples.py

# 数据处理：官方数据 → canonical（需先跑 ingest_raw）
python scripts/build_canonical.py --dataset-id official-v1
python scripts/validate_canonical.py --dataset-id official-v1

# 任务2：canonical → 个人/班级画像（输出只进 artifacts/，gitignore）
$env:PYTHONPATH='src'; python -m knowflow.cli run --dataset official-v1
# verify-run / evidence 省略 --run 时默认最近一次；也可 --run artifacts/run/<实际目录名>
$env:PYTHONPATH='src'; python -m knowflow.cli verify-run
$env:PYTHONPATH='src'; python -m knowflow.cli evidence --record R-0001

# 测试
python -m pytest

# 校验一个产物
python scripts/validate_outputs.py `
  --schema schemas/output/student_profile.schema.json `
  --data tests/fixtures/student_profile.min.json

# CLI（未安装包时加 PYTHONPATH=src）
$env:PYTHONPATH='src'; python -m knowflow.cli check
```

## 12. 禁止

- ❌ 把 `data/raw`、`data/interim`、真实 CSV、PDF/PPT/视频/设计文档、模型权重、密钥提交到仓库。
- ❌ 把原始记录、姓名、自由文本答案发给第三方 API。
- ❌ 让 LLM 计算/改写 mastery、正确率、排名、覆盖度。
- ❌ 手写/猜测 `material_id`、`issue_id`、`record_id`。
- ❌ 把“未记录”当成“未掌握”或“答错”。
- ❌ 为了跑通放宽 schema/测试；未验证就写“已完成”。
- ❌ 直接 push `main`、force-push、合并未经 review 的合约变更。

## 13. 变更记录

> 这里只记**协作文档本身**的版本号。项目事件流（改了什么、怎么验证、怎么回退）记在 [`CHANGELOG.md`](CHANGELOG.md)，两者不重复维护。

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.12 | 2026-11-12 | `verify-run` / `evidence` 的 `--run` 可省略（默认最近一次），`latest` 亦可；目录不存在时给可读报错而不是 `[Errno 22]`；文档去掉“照抄 `<目录>`”的坑 |
| v0.11 | 2026-11-12 | 文档同步：脚本/schema/测试/表数计数校正（七脚本、18 schemas、10 表、93 tests）；里程碑与 G2/G3 状态更新；README 增加「跑任务2」；PR 模板加 `verify-run` 检查 |
| v0.10 | 2026-11-12 | 诊断层落地：`diagnosis/`（Beta 纯 Python 实现、个人/班级画像、`run`/`verify-run`/`evidence`），只读 canonical 表，复用 `cleaning/states.py`；不引入 scipy，不进真实数据；测试 93 项 |
| v0.9 | 2026-11-12 | 输出契约升 **v0.5**：诊断层字段（`node_id`/`scope_known`/Beta 区间与概率/`rubric_evidence`/`rubric_patterns`）、两种新状态与两类新问题、`issue_id` 改为知识点序号；输入表仍 canonical v0.4。见 [`schemas/CONTRACT.md`](schemas/CONTRACT.md) §8 |
| v0.8 | 2026-11-12 | 新增证据层 `record_details.csv`（契约 v0.4，10 张表）：原文零加工 + 行号回查 + `kept` 标记；写盘改原子替换；适配错误信息不回显原文；五态记账下沉 `cleaning/states.py` |
| v0.7 | 2026-11-12 | 合成样例补 `nodes.csv`（输入表 8 → 9 张），`records.node_id` 接入节点；`check_examples` 覆盖 9 张表；补记 v0.3 数据层的 CHANGELOG |
| v0.6 | 2026-11-10 | 数据层落地：`src/knowflow/io/`、`build_canonical` / `validate_canonical`；契约 v0.3（nodes、证据字段、nullable）；新增本机 `data/README-processing.md`（gitignore） |
| v0.5 | 2026-11-09 | 引入 [`CHANGELOG.md`](CHANGELOG.md)：阅读顺序、§2 仓库边界、§4 目录、§7 工作流（新增第 6 步「记变更」）同步 |
| v0.4 | 2026-11-09 | 补 `scripts/ingest_raw.py` 与 §4「复现当前结构」四步：解决 `git pull` 不携带数据、新组员无法重建 `data/raw/official-v1/` 的缺口；新增**入库**的纯指纹 `data/manifests/official-v1.structure.json`（路径 + `sha256` + 行数，无数据内容），`--check` 默认以它为基准 |
| v0.3 | 2026-11-09 | M1-a 契约补丁：`evidence_state` 增 `pending`；`state_counts`/`records_by_state` 增 `pending` 记账；写明 `assigned`/`attempted` 判定与 `applicable` 口径；受限目录检查改为 `git check-ignore`；落地 `data/raw/official-v1/` |
| v0.1 | 2026-11-08 | 初版地基 |
