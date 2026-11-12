# 变更记录

记录**会影响他人**的改动：改了什么、为什么、怎么验证、怎么回退。
`git log` 是逐提交流水；这里只记「一个可交付的最小单元」，供回溯、交接，以及答辩时讲"我们是怎么迭代的"。

- **方向**：最新在最上（第一条 `---` 之后）；同日"后发生在前"。
- **粒度**：一个 PR / 一组相关改动一条；纯措辞、格式化不必记。
- **长度**：每条 ≤ 15 行。论证细节放 PR 正文，这里只留结论与证据。
- **没验证就写"未验证"**，不要留空。

---

## 2026-11-10 — R2 任务2可运行基础流程

分支 `feat/r2-diagnosis-pipeline`；本机实现，尚未提交或推送。

- **实现**：官方CSV适配、事件修订清洗、五态、分节点Beta与部分得分、评分点证据、个人/班级画像、案例候选、本机原始证据查看。
- **契约**：v0.3新增诊断输入包、节点/事件/评分点、混合与不适用状态、可空覆盖率、未知错因类型；合并前需R1/R4审查。
- **核对**：任务2引用与计算复核、结果哈希、逐行清洗审计；修复旧合成样例的未作答计数和覆盖分母。
- **验证**：44项测试通过；17 schemas、8张样例、原始数据指纹检查通过；正式数据生成80份个人及6份群体画像，任务2校验通过。
- **边界**：未实现任务1完整知识底座、任务3建议、LLM或展示UI；默认阈值和正式案例仍需团队复核。
- **回退**：本次尚无提交；保留官方原始资料，按本条变更范围撤销本地代码修改，或待合并后revert对应提交。

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
