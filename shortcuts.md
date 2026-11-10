# GitHub 协作快捷指令

本文件把自然语言请求映射到 Agent 的 Git 命令与 GitHub 操作流程。它是操作指南，不是脚本，也不注册终端别名。

---

## 1. 项目与工具

- 仓库：<https://github.com/JackChen070421/KnowFlow>
- 远程名：`origin`；默认分支：`main`。
- `git`：本地版本管理、分支、拉取、推送、本地合并。
- GitHub 插件：查询仓库、PR、Issue、CI；在授权范围内创建/更新/合并 PR。
- `gh`：可选；未安装时优先用 GitHub 插件。

插件属于使用者环境，不是 Python 依赖；组员克隆后需各自连接 GitHub 账号并获得仓库权限。

---

## 2. 操作前检查

在仓库根目录执行：

```powershell
git status --short
git branch --show-current
git remote -v
git diff --stat
git diff --cached --stat
```

Agent 据此确定当前分支、未提交内容和操作范围。下文 `<branch>`、`<pr_number>`、`<head_sha>` 等为占位符，执行时替换。

用户明确提出拉取、推送、提交或合并时，Agent 在该范围内执行，不只做命令咨询。账号/权限/分支保护阻止执行时，报告具体原因。

---

## 3. 自然语言 → 操作

### “从 GitHub 同步到本地” / “拉取最新代码”

默认更新当前分支的 upstream；用户明确指定主分支时，在适合切换的工作区状态下切到 `main`。

```powershell
git fetch origin
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
git pull --ff-only
```

`--ff-only` 只接受快进，避免隐式合并提交。当前分支没有 upstream 时，先确定对应远程分支；不要把 `origin/main` 拉进任意功能分支。有未提交内容时先保护本地修改；历史分叉时转入合并流程，不用强制重置覆盖。

### “看看云端有哪些更新”

```powershell
git fetch origin
git log --oneline HEAD..'@{upstream}'
git diff --stat HEAD...'@{upstream}'
```

只查看，不修改当前分支文件。

### “提交本次修改”

先看完整 diff，确定本次任务文件；只暂存明确路径，不要把无关改动塞进提交。

```powershell
git diff
git add -- <file_1> <file_2>
git diff --cached
git commit -m '<commit_message>'
```

提交信息用 Conventional Commits：`feat:` / `fix:` / `docs:` / `test:` / `chore:`；正文写“改了什么 / 为什么 / 怎么验证 / 未验证项”。

**提交前必须做两件事**：

1. 在 [`CHANGELOG.md`](CHANGELOG.md) 顶部加一条（**一个可交付单元一条**，≤15 行：改了什么 / 验证 / 回退）。纯措辞、格式化不必记。
2. 跑下面这些：

```powershell
python scripts/check_contracts.py
python scripts/check_examples.py
python scripts/ingest_raw.py --check   # 动过数据目录时

# 有产物时再加一项：校验本次生成的 JSON
python scripts/validate_outputs.py --schema <schema> --data <json>

python -m pytest
```

用户只要求提交时，不额外推送。已有暂存内容可能来自别人，先核对范围。

### “检查格式 / 契约 / 样例 / 产物”

三个检查脚本分工不同；`ingest_raw` 负责官方数据落地，`build_canonical` / `validate_canonical` 负责数据处理与复检（都不是格式检查）。按下面的自然语言选择：

| 你说 | Agent 执行 | 检查什么 |
|---|---|---|
| “检查项目结构 / 契约 / 隐私”<br>“schema 有没有问题”<br>“有没有真实数据混进来” | `python scripts/check_contracts.py` | 必需目录/文件、schema 能否解析、`$id` 唯一、`data/raw`/`interim` 下的文件**是否被 Git 忽略**、`.gitignore` 是否挡住数据/密钥/权重 |
| “把赛题材料放进来”<br>“复现数据目录”<br>“新机器接数据” | `python scripts/ingest_raw.py --source "<赛题资料包路径>"` | 原样复制到 `data/raw/official-v1/`，写本机 `manifest.json`（`sha256` + 字节数 + 行数 + sheet 数） |
| “数据放对了吗”<br>“核对一下数据有没有缺”<br>“和别人那份一致吗” | `python scripts/ingest_raw.py --check` | 复算每文件 `sha256`/行数，默认对照**入库的** `data/manifests/official-v1.structure.json`（可用 `--expected` 指定别的基准） |
| “赛方更新了材料”<br>“重新钉指纹” | `python scripts/ingest_raw.py --source "<路径>" --force --export-structure` | 重新落地并改写 `data/manifests/official-v1.structure.json`；改完要在 PR 说明变了哪几行 |
| “把官方数据变成 canonical”<br>“生成中间表”<br>“跑数据处理” | `python scripts/build_canonical.py --dataset-id official-v1` | 官方 5 张 CSV → `data/interim/official-v1/` 9 张表 + `data_quality_report.json`（gitignore）；列/枚举不认识就中止 |
| “检查 canonical 对不对”<br>“质量报告可信吗”<br>“中间表有没有被手改” | `python scripts/validate_canonical.py --dataset-id official-v1` | G2 引用 + G3 一致性，重算后与磁盘产物逐字节比对 |
| “检查合成 CSV 格式”<br>“样例字段/表头对不对” | `python scripts/check_examples.py` | `examples/synthetic/input/` 的 8 张 CSV：表头、必填列、类型、主键唯一、逐行 schema |
| “校验这个 JSON 产物”<br>“这个输出符合 schema 吗” | `python scripts/validate_outputs.py --schema <schema> --data <json>` | 一份 JSON 是否通过指定 schema；适合 `knowledge_base` / `student_profile` / `recommendation` / `llm_summary` 等 |
| “提交前全检”<br>“把格式检查都跑一遍” | 依次跑上面三个检查 + `python -m pytest` | 结构/契约 → 合成 CSV → 本次产物 → 测试 |
| “记一下这次改了什么”<br>“更新变更记录”<br>“上次改到哪了”<br>“怎么回退” | 编辑 [`CHANGELOG.md`](CHANGELOG.md)（顶部加一条） | 一个可交付单元一条，≤15 行：改了什么 / 验证 / 回退。**不要**把逐条 commit 流水抄进来 |

> **`git pull` 不会带来数据。** 新组员拉到的是空的 `data/raw/`；“复现数据目录”必须自己跑一次 `ingest_raw --source`。

常用产物对应的 schema：

```text
knowledge_base.json    → schemas/output/knowledge_base.schema.json
student_profile.json   → schemas/output/student_profile.schema.json
class_profile.json     → schemas/output/class_profile.schema.json
recommendation.json    → schemas/output/recommendation.schema.json
validation_report.json → schemas/output/validation_report.schema.json
llm_summary.json       → schemas/llm/llm_summary.schema.json
llm_response.json      → schemas/llm/llm_response.schema.json
```

单文件校验示例：

```powershell
python scripts/validate_outputs.py `
  --schema schemas/output/student_profile.schema.json `
  --data tests/fixtures/student_profile.min.json
```

**判定规则**：

- 退出码 0 才算通过；失败逐条看 `  - ...` 或 `/json/pointer: message`。
- `check_contracts` 失败先修目录/schema/隐私，不要继续提交。
- `check_examples` 只校验合成样例，不校验 `data/raw` 官方数据。
- `validate_outputs` 只校验“一份 JSON 对一份 schema”，不查引用/一致性/约束（G2–G4 待实现）。
- 任何一步非 0：不要提交；把命令、失败项、修复计划贴进 PR/Issue。

### “推送到 GitHub”

```powershell
git branch --show-current
git push -u origin <branch>
```

只推送已提交内容；未提交文件不会被 push。推送被拒时先 `git fetch` 判断分叉原因，**不要自动强推**。

### “新建分支开发这个功能”

项目约定：

- `feat/<role>-<topic>`：新功能，如 `feat/r2-diagnosis-beta`
- `fix/<role>-<topic>`：修 bug
- `docs/<role>-<topic>`：文档/协作说明
- `test/<role>-<topic>`：测试/校验

从最新 `main` 开始：

```powershell
git switch main
git pull --ff-only origin main
git switch -c <branch>
```

若要把当前未提交工作移到新分支，直接 `git switch -c <branch>`，不要先切/拉主分支。

### “创建 PR”

先验证并推送功能分支，再用 GitHub 插件创建以 `main` 为目标的 PR；标题/说明包含改动与验证结果，关联 Issue（如 `KF-003`）。

有 `gh` 时：

```powershell
gh pr create --base main --head <branch> --title '<title>' --body-file <body_file>
```

PR 必须写：改了什么、为什么、怎么验证、已知限制、是否改 schema、是否含真实数据/密钥。

### “查看 PR / CI 状态”

优先用 GitHub 插件读取指定 PR、检查结果与评审意见；根据 PR 编号或当前分支匹配，避免选错 PR。

可选：

```powershell
gh pr view <pr_number>
gh pr checks <pr_number>
```

### “合并这个 PR”

先核对源分支、目标分支、最新提交、检查与评审状态，再用 GitHub 插件合并，并传入已核对的 head SHA。默认 merge commit；遵守分支保护与 required checks。

可选：

```powershell
gh pr merge <pr_number> --merge --match-head-commit <head_sha>
```

云端合并后，若本地就在目标分支且工作区干净，再 `git pull --ff-only`；否则只报告“云端已合并、本地未更新”。用户未要求时不删分支。

### “把 A 分支合并到 B 分支”

这是本地合并，不是合并 PR。先 `git fetch` 并确认 A/B 是本地还是远程，再在干净工作区执行：

```powershell
git switch <target_branch>
git merge <source_branch>
```

冲突时检查文件含义，解决能明确判断的部分并验证；需要选择功能行为时向用户说明。目标是受保护主分支时优先走 PR。合并不会自动推送，除非用户同时要求。

---

## 4. KnowFlow 专用规则

1. **一任务一分支一 PR**；不把多个不相关任务塞进一个 PR。
2. **不直接 push `main`**；不 force-push `main`；合约变更（`schemas/`、枚举、ID）需 R1 + R4 双审。
3. **仓库不放**：`data/raw`、`data/interim`、真实 CSV、模型权重、密钥、设计方案/PDF/PPT/视频/真实结果包。
4. **提交前检查**：`check_contracts`、`check_examples`、`validate_outputs`（有产物时）、`pytest` 全绿；没有验证就写“未验证”。
5. **不编造**：不手写 `material_id`/`issue_id`/`record_id`；不把“未记录”说成“未掌握”。
6. **PR 作者不能自审**；合并前确认 CI 和至少一名非作者 review。

---

## 5. 数据/密钥事故

发现真实数据或密钥误入 Git：

1. 立即停止推送，通知 R4/全员。
2. 未推送：`git rm --cached` 移除，确认 `.gitignore` 生效，提交修复。
3. 已推送：轮换密钥；用 `git filter-repo`/BFG 清理历史；按赛题要求删除副本并写事故记录。
4. 不要用 `git rm` 假装“历史已清理”；不要 force-push 公开仓而不通知团队。

---

## 6. 参考

- [Git pull](https://git-scm.com/docs/git-pull)
- [GitHub CLI: pr merge](https://cli.github.com/manual/gh_pr_merge)
- [GitHub CLI: auth login](https://cli.github.com/manual/gh_auth_login)
