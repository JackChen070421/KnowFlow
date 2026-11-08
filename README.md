# KnowFlow

> **学情诊断与个性化学习智能体** · “智慧学伴”赛道
> 第二届北京市大学生“人工智能+”创新大赛

KnowFlow 把课程材料、题目、学生作答记录，变成三样可核对的东西：

1. **知识底座**：课标 → 知识点 → 材料 → Q-matrix → 先修/易混关系；
2. **学情画像**：四态证据、覆盖度、Beta-Binomial 掌握度、问题清单；
3. **学习建议**：`issue_id` → `material_id` → `reason` → `check` → `seq`。

> 当前状态：**M0 地基**。仓库只保留数据契约、合成样例、契约检查与最小目录；业务模块随任务逐步增加。
> 入口：[`AGENT.md`](AGENT.md) · 数据契约：[`schemas/CONTRACT.md`](schemas/CONTRACT.md) · Git 操作：[`shortcuts.md`](shortcuts.md)

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
| **任务 2** 学情画像 | `student_profile.json` / `class_profile.json` | 四态、覆盖度、Beta 后验、问题识别 |
| **任务 3** 学习建议 | `recommendation.json` | 材料真实、理由可追、顺序合理、检查可验证 |

完整字段/枚举见 [`schemas/CONTRACT.md`](schemas/CONTRACT.md)。

---

## 分层架构（8 层）

| 层 | 目录/模块 | 作用 | 现状 |
|---|---|---|---|
| **1 契约层** | `schemas/` | 定义输入 CSV、输出 JSON、LLM 边界；多人协作的接口 | ✅ 16 schemas |
| **2 数据层** | `data/`、未来 `src/knowflow/io/` | `raw → canonical → interim`；隔离官方格式，原始数据不出本机 | 🟡 目录/schema，适配待 M1 |
| **3 知识层** | 未来 `src/knowflow/knowledge/` | 课标/知识点/材料/Q-matrix/先修与易混图 → `knowledge_base.json` | 🟡 schema，构建待 M1 |
| **4 诊断层** | 未来 `src/knowflow/cleaning/`、`diagnosis/` | 四态、覆盖度、Beta-Binomial、问题识别、个体/班级画像 | 🟡 schema，算法待 M2 |
| **5 建议层** | 未来 `src/knowflow/recommend/` | 材料检索、先修/难度/时长约束、排序、理由、探测小测、validator | 🟡 schema，算法待 M3 |
| **6 LLM 边缘层** | `schemas/llm/`、未来 `src/knowflow/llm/` | 只读 `llm_summary`，写 `reason`/`check`/摘要；数字锁、降级模板 | 🟡 schema，网关待 M3 |
| **7 验证层** | `scripts/`、`tests/`、未来 `src/knowflow/validation/` | 三个格式检查 + 契约测试 + 一致性/约束/隐私检查 → `validation_report` | ✅ 三脚本 + 11 tests |
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

当前 M0 只实现第 1 层、第 2 层目录、第 7 层检查、第 8 层协作；第 3–6 层先冻结 schema，再按 M1–M3 逐步加代码，不预先铺空目录。

三个格式检查：`check_contracts`（结构/契约/隐私）、`check_examples`（8 张合成 CSV）、`validate_outputs`（单份 JSON 对 schema）。自然语言映射见 [`shortcuts.md`](shortcuts.md)。

| 脚本 | 检查范围 | 成功标志 |
|---|---|---|
| `scripts/check_contracts.py` | 必需目录/文件、schema 解析与 `$id` 唯一、`data/raw` 与 `data/interim` 无数据、`.gitignore` 规则 | `OK (16 schemas)` |
| `scripts/check_examples.py` | `examples/synthetic/input/` 8 张 CSV 的表头、必填、类型、主键、逐行 schema | `OK (8 tables)` |
| `scripts/validate_outputs.py` | 一份 JSON 对一份 schema | `OK (0 errors)` |

---

## 仓库结构

```text
KnowFlow/
├─ AGENT.md / README.md / shortcuts.md
├─ schemas/                 # input / output / llm + CONTRACT.md
├─ examples/synthetic/      # 8 张合成 CSV，可公开、可回归
├─ src/knowflow/            # 目前只有 __init__ / __main__ / cli / contracts
├─ tests/                   # contract + fixtures
├─ scripts/                 # check_contracts / check_examples / validate_outputs
├─ data/raw/<dataset_id>/   # 官方原始数据，原样放，gitignore
├─ data/interim/<dataset_id>/ # 适配后 canonical，gitignore
└─ .github/                 # CI + PR 模板
```

**仓库不放**：设计方案、PDF、PPT、视频、真实结果包、真实学情数据、模型权重、密钥。
这些放仓库外的团队网盘或赛方提交渠道；仓库保持干净，避免污染和误传。

---

## 快速开始

要求：Python 3.11+、Git。

```powershell
cd KnowFlow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

python scripts/check_contracts.py
python scripts/check_examples.py
python -m pytest
```

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

> `python -m knowflow.cli run ...` 等业务入口随 M1–M3 落地；当前 CLI 只提供 `check` / `validate` / `version`。

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
| 数据字典 / manifest | 跟原始数据放一起 | ❌ |

`<dataset_id>` 用短英文/数字，例如 `dev-2026-11`、`eval-holdout`。

**接数据 5 步**：

1. 原样放：官方文件放 `data/raw/<dataset_id>/`，不要先手工改列名。
2. 留字典：数据字典/字段说明跟原始文件放一起。
3. 记 manifest：文件名、`sha256`、行数、来源、日期。
4. 写适配：在 `src/knowflow/io/` 把官方列名映射到 canonical，输出到 `data/interim/<dataset_id>/`。
5. 跑检查：`check_contracts` + `check_examples`（合成样例）+ `validate_outputs`（产物）+ `pytest`。

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
| **M1 知识底座** | 适配器、knowledge/Q-matrix/图 | ⬜ |
| **M2 诊断** | 四态、覆盖度、Beta、画像 | ⬜ |
| **M3 建议** | 检索、约束、LLM 理由、validator | ⬜ |
| **M4 交付** | 演示与提交（仓库外） | ⬜ |

每步只加当前需要的模块；不预先铺空目录。

---

## 文档

| 想知道 | 读 |
|---|---|
| 协作准则、角色、质量门 | [`AGENT.md`](AGENT.md) |
| 字段、ID、枚举、CSV/JSON 结构 | [`schemas/CONTRACT.md`](schemas/CONTRACT.md) |
| Schema 怎么用/怎么改 | [`schemas/README.md`](schemas/README.md) |
| Git/GitHub 操作 | [`shortcuts.md`](shortcuts.md) |
| 合成样例 | [`examples/synthetic/README.md`](examples/synthetic/README.md) |
| 数据存放与删除 | [`data/README.md`](data/README.md) |

---

## 声明

- 代码许可证待团队确认；第三方组件/课程材料的来源与许可证在仓库外登记。
- 赛题数据、课程材料、学生记录不随本仓库分发；`examples/` 均为自行构造的合成样例。
