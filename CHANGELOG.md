# 变更记录

记录**会影响他人**的改动：改了什么、为什么、怎么验证、怎么回退。
`git log` 是逐提交流水；这里只记「一个可交付的最小单元」，供回溯、交接，以及答辩时讲"我们是怎么迭代的"。

- **方向**：最新在最上（第一条 `---` 之后）；同日"后发生在前"。
- **粒度**：一个 PR / 一组相关改动一条；纯措辞、格式化不必记。
- **长度**：每条 ≤ 15 行。论证细节放 PR 正文，这里只留结论与证据。
- **没验证就写"未验证"**，不要留空。

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
