# 变更记录

记录**会影响他人**的改动：改了什么、为什么、怎么验证、怎么回退。
`git log` 是逐提交流水；这里只记「一个可交付的最小单元」，供回溯、交接，以及答辩时讲"我们是怎么迭代的"。

- **方向**：最新在最上（第一条 `---` 之后）；同日"后发生在前"。
- **粒度**：一个 PR / 一组相关改动一条；纯措辞、格式化不必记。
- **长度**：每条 ≤ 15 行。论证细节放 PR 正文，这里只留结论与证据。
- **没验证就写"未验证"**，不要留空。

---

## 2026-11-12 — 任务1 canonical 知识底座生成

- 新增 `knowledge` CLI 与知识层，按现有 schema 打包五张 canonical 表；不改输入或诊断逻辑。
- 校验原文出处字段、主键/引用/计数、Q-matrix 测评覆盖、父子/包含/先修无环；保留已有易混边。
- 输出默认进 `artifacts/knowledge/`，不覆盖已有文件，不推断缺失关系。
- 新增 18 项回归测试；全量 pytest 115 passed，契约/合成表/产物 schema 检查通过。
- 补充哈希绑定的本机 curation 接口：只允许课标/说明/有依据关系更新，保持诊断ID和Q-matrix不变。
- 官方数据已核验并生成本机任务1成果（3主题/9指标/21内容细项）；真实内容与成果不进Git。
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
