# AGENT.md — KnowFlow 协作入口

> 适用：所有参与 KnowFlow 的人与 AI Agent。
> 最后更新：2026-11-08 · v0.2（精简版）
> 阅读顺序：本文件 → [`README.md`](README.md) → [`schemas/CONTRACT.md`](schemas/CONTRACT.md) → 你的任务。
> Git/GitHub 操作见 [`shortcuts.md`](shortcuts.md)；不要一上来通读全仓。

## 0. 30 秒总览

KnowFlow 是“智慧学伴”赛道的学情诊断与个性化学习智能体。输入课程材料、题目、学生作答记录，输出：

1. **知识底座**：课标 → 知识点 → 材料 → Q-matrix → 先修/易混关系；
2. **学情画像**：四态证据、覆盖度、Beta-Binomial 掌握度、问题清单；
3. **学习建议**：`issue_id` → `material_id` → `reason` → `check` → `seq`。

**一句话：数字由代码算，语言由模型写；所有结论必须能追到 ID。**

当前是 **M0 地基**：只保留数据契约、合成样例、契约检查与最小目录；业务模块随任务逐步增加。

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

**只放**：代码、schema、合成样例、契约检查、必要的协作说明（README/AGENT/shortcuts）。

**不放**：设计方案/PDF/PPT/视频/真实结果包/项目文档/真实学情数据/模型权重/密钥。
这些放仓库外的团队网盘或赛方提交渠道；仓库保持干净，避免污染和误传。

## 3. 分层架构（8 层）

| 层 | 目录/模块 | 作用 | 现状 |
|---|---|---|---|
| **1 契约层** | `schemas/` | 输入 CSV、输出 JSON、LLM 边界；多人接口 | ✅ |
| **2 数据层** | `data/`、未来 `io/` | `raw → canonical → interim`；隔离官方格式 | 🟡 |
| **3 知识层** | 未来 `knowledge/` | 课标/知识点/材料/Q-matrix/先修与易混图 | 🟡 |
| **4 诊断层** | 未来 `cleaning/`、`diagnosis/` | 四态/覆盖度/Beta/问题/个体与班级画像 | 🟡 |
| **5 建议层** | 未来 `recommend/` | 检索/约束/排序/理由/探测小测/validator | 🟡 |
| **6 LLM 边缘层** | `schemas/llm/`、未来 `llm/` | 只读摘要，写 `reason`/`check`；数字锁/降级 | 🟡 |
| **7 验证层** | `scripts/`、`tests/`、未来 `validation/` | 三脚本 + 契约测试 + 校验报告 | ✅ |
| **8 协作层** | `AGENT/README/shortcuts/.github` | 准则/流程/分支/PR/CI | ✅ |

数据流：`data/raw → io → data/interim → knowledge → diagnosis → recommend → JSON`；LLM 只写文字。

**三条边界**：

- **数据边界**：`raw → canonical → summary` 单向；LLM 只能看 summary。
- **计算边界**：数值只由 `diagnosis`/`recommend` 的纯函数计算。
- **语言边界**：LLM 只填 `reason`/`check`/摘要等文字；ID 与数字来自白名单。

第 3–6 层先冻结 schema，按 M1–M3 逐步加代码；暂不建 UI、报告层、交付物目录。

## 4. 目录（最小）

```text
KnowFlow/
├─ AGENT.md / README.md / shortcuts.md
├─ .gitignore / .gitattributes / .env.example / pyproject.toml
├─ schemas/                 # input / output / llm + CONTRACT.md
├─ examples/synthetic/      # 8 张合成 CSV，可公开、可回归
├─ src/knowflow/            # 目前只有 __init__ / __main__ / contracts / cli
├─ tests/                   # contract + fixtures
├─ scripts/                 # check_contracts / check_examples / validate_outputs
├─ data/
│  ├─ raw/<dataset_id>/     # 官方原始数据，原样放，不进 Git
│  ├─ interim/<dataset_id>/ # 适配后 canonical，不进 Git
│  └─ README.md
└─ .github/                 # CI + PR 模板
```

**数据集放置（必读）**：官方原始数据放 `data/raw/<dataset_id>/`（原样、不改名）；canonical 中间表放 `data/interim/<dataset_id>/`；两者都不进 Git。`examples/synthetic/`、`tests/fixtures/` 只放合成样例，**永远不放真实数据**。接数据时保留数据字典 + `manifest.json`，下游只读 `interim/`；详见 `data/README.md`。

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
| `evidence_state` | `observed_correct` / `observed_wrong` / `assigned_not_attempted` / `unobserved` |
| `status` | `confirmed_weak` / `likely_weak` / `insufficient_evidence` / `likely_mastered` / `confirmed_mastered` |
| `issue_type` | `concept_confusion` / `procedure_gap` / `reading_error` / `prerequisite_gap` / `transfer_gap` / `insufficient_evidence` |
| `material_type` | `reference` / `explain` / `example` / `practice` / `assessment` / `probe` |

字段、CSV 列、输出结构以 [`schemas/CONTRACT.md`](schemas/CONTRACT.md) 与 `schemas/` 为准。

## 6. 角色

| 角色 | 负责 | 主要产物 |
|---|---|---|
| **R1 知识/契约** | 课标/知识点/Q-matrix/图；守 schema | `knowledge_base.json`、schema |
| **R2 数据/诊断** | 适配、清洗、四态、覆盖度、Beta | canonical 表、`student_profile.json` |
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
6. **合并**：通过检查后合并；删分支；更新 Issue。禁止直接 push `main`、禁止 force-push。

提交信息：Conventional Commits；正文写“改了什么 / 为什么 / 怎么验证 / 未验证项”。

## 8. 质量门

| 门 | 检查 | 现在怎么跑 |
|---|---|---|
| G0 结构/样例 | 必需目录/文件、schema 头、CSV 表头/类型/主键 | `check_contracts` + `check_examples` |
| G1 Schema | 字段/类型/枚举 | `python scripts/validate_outputs.py --schema ... --data ...` |
| G2 引用 | 所有 ID 存在、无悬空 | 待实现（M1） |
| G3 一致性 | `evidence_count`=长度、`mastery` 可复算 | 待实现（M2） |
| G4 隐私 | 无真实数据/密钥/PII | `python scripts/check_contracts.py` |
| G5 测试 | 契约/单元/端到端 | `python -m pytest` |

未实现的 G2/G3 不假装通过；在 PR 里写“待实现”。

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

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.2 | 2026-11-08 | 精简到最小架构；移除 docs/team/prompts/configs/app/reports/deliverables；接入 shortcuts.md |
| v0.1 | 2026-11-08 | 初版地基 |
