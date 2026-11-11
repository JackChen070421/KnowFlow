# 变更记录

记录**会影响他人**的改动：改了什么、为什么、怎么验证、怎么回退。
`git log` 是逐提交流水；这里只记「一个可交付的最小单元」，供回溯、交接，以及答辩时讲"我们是怎么迭代的"。

- **方向**：最新在最上（第一条 `---` 之后）；同日"后发生在前"。
- **粒度**：一个 PR / 一组相关改动一条；纯措辞、格式化不必记。
- **长度**：每条 ≤ 15 行。论证细节放 PR 正文，这里只留结论与证据。
- **没验证就写"未验证"**，不要留空。

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

**`<commit>`** · PR [#N](链接) · `<branch>` → `main`

### 改了什么

- 按「契约 / 数据 / 代码 / 文档 / 测试」分组，只写结论。

### 验证

- 贴命令与结果；没跑就写「未验证」。

### 回退

- `git revert <commit>`，或需要人工清理的额外步骤。
```
