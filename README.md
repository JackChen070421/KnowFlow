# KnowFlow

[![ci](https://github.com/JackChen070421/KnowFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/JackChen070421/KnowFlow/actions/workflows/ci.yml)

> **学情诊断与个性化学习智能体** · “智慧学伴”赛道
> 第二届北京市大学生“人工智能+”创新大赛

KnowFlow 把课程材料、题目、学生作答记录，变成三样可核对的东西：

1. **知识底座**：课标 → 知识点 → 材料 → Q-matrix → 先修/易混关系；
2. **学情画像**：五态证据（含 `pending`）、覆盖度、Beta-Binomial 掌握度、问题清单；
3. **学习建议**：`issue_id` → `material_id` → `reason` → `check` → `seq`。

> 当前状态：**任务2 基础流程已实现**。可在本机完成 canonical 数据适配、按节点的个人/班级画像、复算与证据回查；任务1知识底座支持生成、校验和本机核对标注接入；学习建议模块仍待接入。
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
| **任务 2** 学情画像 | `student_profile.json` / `class_profile.json` | 五态、覆盖度、Beta 后验、问题识别 |
| **任务 3** 学习建议 | `recommendation.json` | 材料真实、理由可追、顺序合理、检查可验证 |

完整字段/枚举见 [`schemas/CONTRACT.md`](schemas/CONTRACT.md)。

---

## 分层架构（8 层）

| 层 | 目录/模块 | 作用 | 现状 |
|---|---|---|---|
| **1 契约层** | `schemas/` | 定义输入 CSV、输出 JSON、LLM 边界；多人协作的接口 | ✅ 18 schemas |
| **2 数据层** | `data/`、`src/knowflow/io/` | `raw → canonical → interim`；隔离官方格式，原始数据不出本机 | ✅ 适配层 + 10 张 canonical 表 |
| **3 知识层** | `src/knowflow/knowledge/` | 课标/知识点/材料/Q-matrix/先修与易混图 → `knowledge_base.json` | ✅ 生成与校验、本机课标/关系标注接入；教学内容需人工复核 |
| **4 诊断层** | `src/knowflow/cleaning/`、`src/knowflow/diagnosis/` | 五态、覆盖度、Beta-Binomial、问题识别、个体/班级画像 | ✅ 任务2基础版；只读 canonical，不写数据 |
| **5 建议层** | 未来 `src/knowflow/recommend/` | 材料检索、先修/难度/时长约束、排序、理由、探测小测、validator | 🟡 schema，算法待 M3 |
| **6 LLM 边缘层** | `schemas/llm/`、未来 `src/knowflow/llm/` | 只读 `llm_summary`，写 `reason`/`check`/摘要；数字锁、降级模板 | 🟡 schema，网关待 M3 |
| **7 验证层** | `scripts/`、`tests/`、`src/knowflow/diagnosis/validation.py` | 格式检查 + 数据复检 + 契约测试 + 诊断复算（五态/覆盖/Beta/班级汇总）→ `validation_report` | ✅ 七脚本 + 93 tests |
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

当前已实现第 1、2、3、4、7、8 层：契约、canonical 数据层、任务2诊断（按节点的五态/覆盖/Beta、个人与班级画像、复算与证据回查）。第 3 层支持知识底座生成与本机核对标注接入；第 5 层（学习建议）、第 6 层（LLM 边缘）仍待接入，这两层先冻结 schema 再逐步加代码，不预先铺空目录。

三个格式检查：`check_contracts`（结构/契约/隐私）、`check_examples`（10 张合成 CSV）、`validate_outputs`（单份 JSON 对 schema）。数据与诊断另有四个脚本/入口：`ingest_raw`（官方包原样落地 + 指纹，**不是** IO 适配层）、`build_canonical`（官方 CSV → 10 张 canonical 表 + 质量报告）、`validate_canonical`（canonical 复检）、`export_digest`（产物指纹互证）；诊断走 CLI 的 `run` / `verify-run` / `evidence`。自然语言映射见 [`shortcuts.md`](shortcuts.md)。

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
├─ src/knowflow/            # cli / contracts / config / io / cleaning / diagnosis
├─ tests/                   # contract + io + diagnosis + fixtures
├─ scripts/                 # check_contracts / check_examples / validate_outputs / ingest_raw / build_canonical / validate_canonical / export_digest
├─ data/raw/<dataset_id>/   # 官方原始数据，原样放，gitignore
├─ data/manifests/          # 纯指纹（路径/哈希/行数），可入库
├─ data/interim/<dataset_id>/ # 适配后 canonical，gitignore
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
uv run python -m knowflow.cli knowledge --dataset official-v1
# 无本机数据时，用合成样例验证：
uv run python -m knowflow.cli knowledge --dataset synthetic --input examples/synthetic/input
```

读取 canonical 的 objectives / knowledge / materials / qmatrix / edges 五张表，输出到
`artifacts/knowledge/<dataset>-<时间戳>/knowledge_base.json`；可用 `--output` 指定新 JSON 文件。
保留课标原文、出处、知识点父子关系、Q-matrix 与已有先修/易混边，不更改输入表。
写出前验证 schema、主键、引用、计数、测评覆盖及包含/先修图无环；已有输出文件不会覆盖。
可通过 `--curation <本机标注.json>` 接入经核对的课标原文、知识点说明和补充关系。
标注包含 `dataset_id`、五张 CSV 的 `source_sha256`、`objectives`/`knowledge` 补丁数组和 `edges` 新增数组；
只允许更新课标原文/出处/备注、知识点 description 和有依据说明的边，禁止改变诊断 ID 或 Q-matrix。
输入哈希变化时拒绝套用旧标注，需重新复核；真实标注与成果不进 Git。
先修与易混关系来自 `edges.csv`，没有证据时不自动生成；原始课标解析由已有 IO 适配层负责，
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

按层装可选依赖（core 只有校验与配置，其余按需）：

| extra | 内容 | 何时需要 |
|---|---|---|
| `io` | pandas | 可选：当前 io 层用标准库 `csv`，不依赖 pandas |
| `stats` | numpy, scipy | 可选统计库；**当前诊断不依赖**（Beta 用纯 Python 实现） |
| `llm` | openai | M3 LLM 边缘层 |
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

> 任务2 的业务入口是 `knowflow run` / `verify-run` / `evidence`（见上）；`check` / `validate` / `config` / `version` 仍在。数据处理仍由脚本完成（`build_canonical` / `validate_canonical` / `export_digest`）。

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
| **M1 知识底座** | 适配器、knowledge/Q-matrix/图 | ✅ 适配器、知识底座与图校验、本机核对标注接入；官方内容成果本机保存，需人工复核 |
| **M2 诊断** | 五态、覆盖度、Beta、画像 | ✅ 基础版（按节点、可复算、证据可回查） |
| **M3 建议** | 检索、约束、LLM 理由、validator | ⬜ |
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
