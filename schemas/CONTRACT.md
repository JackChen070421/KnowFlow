# 数据契约（canonical v0.2）

> 机器定义以 `schemas/**/*.schema.json` 为准；本文只做速查。
> 改字段/枚举/ID = 改合同：先改 schema + 本文，再改代码和 fixtures。

---

## 1. ID

| 实体 | 字段 | 规则 | 示例 |
|---|---|---|---|
| 课标条目 | `objective_id` | `OBJ-<年级><学科>-<序号>` | `OBJ-7M-03` |
| 知识点 | `knowledge_id` | `K-<两位序号>` | `K-07` |
| 材料/题目 | `material_id` | `M-<三位序号>` | `M-021` |
| 作答记录 | `record_id` | `R-<四位序号>` | `R-0031` |
| 学生 | `student_id` | `S<三位序号>` | `S012` |
| 问题 | `issue_id` | `IS-<学生序号>-<两位序号>` | `IS-012-01` |
| 群体/任务 | `group_id` / `task_id` | `G<序号>` / `T<序号>` | `G2` / `T1` |

ID 不复用、不回收、不手敲新增；跨文件引用必须能解析。学生一律伪匿名，禁止姓名/学号/联系方式。

---

## 2. 枚举（机器值）

| 枚举 | 取值 |
|---|---|
| `verb_level` | `know` / `understand` / `master` / `apply` |
| `cognitive_type` | `concept` / `procedure` / `application` |
| `material_type` | `reference` / `explain` / `example` / `practice` / `assessment` / `probe` |
| `evidence_state` | `observed_correct` / `observed_wrong` / `assigned_not_attempted` / `unobserved` |
| `status` | `confirmed_weak` / `likely_weak` / `insufficient_evidence` / `likely_mastered` / `confirmed_mastered` |
| `confidence` | `low` / `medium` / `high` |
| `issue_type` | `concept_confusion` / `procedure_gap` / `reading_error` / `prerequisite_gap` / `transfer_gap` / `insufficient_evidence` |
| `edge_type` | `prerequisite` / `contains` / `confusable` / `related` |

中文标签只用于 UI/文档；机器读写一律用英文枚举。

---

## 3. 输入 CSV

UTF-8、逗号分隔、首行表头、一行一实体。完整字段见对应 schema。

| 文件 | 关键列 |
|---|---|
| `objectives.csv` | `objective_id, subject, grade, theme, unit, objective_text, verb_level, source_material_id, source_locator` |
| `knowledge.csv` | `knowledge_id, objective_id, parent_id, name, level, cognitive_type, description, sort_order` |
| `materials.csv` | `material_id, title, body, material_type, difficulty, objective_id, options_json, answer_key, est_minutes, source, license` |
| `qmatrix.csv` | `material_id, knowledge_id, weight, difficulty, item_type, is_primary`；主键二元组 |
| `edges.csv` | `from_id, to_id, edge_type, weight, note` |
| `students.csv` | `student_id, group_id, grade, stage, notes` |
| `records.csv` | `record_id, student_id, material_id, assigned, attempted, score, max_score, is_correct, answer, submitted_at, duration_seconds, attempt_no, source` |
| `tasks.csv` | `task_id, title, goal, target_scope, target_ids_json, material_scope_json, constraints_json, expected_output` |

约束：

- `objective_text` 原文照录，不改写。
- `score` 必须在 `[0, max_score]`；`attempted=false` 时 `score/is_correct` 为 `null`。
- `qmatrix` 每个 `practice/assessment` 至少挂 1 个知识点；每个知识点至少 1 个 `practice/assessment`。
- `prerequisite`/`contains` 不能成环；无自环。

---

## 4. 输出 JSON

| 文件 | 顶层字段 |
|---|---|
| `knowledge_base.json` | `schema_version, dataset_id, generated_at, subject, grade, counts, objectives, knowledge, materials, qmatrix, edges` |
| `data_quality_report.json` | `schema_version, dataset_id, generated_at, input_files, total_records, duplicates_removed, records_by_state, missing, anomalies, field_quality, handling_rules` |
| `student_profile.json` | `schema_version, student_id, group_id, generated_at, source_dataset, coverage, knowledge_states, objective_states, issues, lists` |
| `class_profile.json` | `schema_version, class_id, generated_at, source_dataset, student_count, coverage_summary, knowledge_distribution, common_issues, tiers` |
| `recommendation.json` | `schema_version, student_id, generated_at, source, generated_by, plan, probe_plan` |
| `validation_report.json` | `schema_version, run_id, generated_at, targets, checks, summary, gate` |

诊断粒度：`knowledge_states[]` 是唯一计算源；`objective_states[]` 是按 `evidence_count` 加权的派生视图，必须列出 `derived_from` 与 `unobserved_knowledge_ids`。

建议五要素：`issue_id`、`material_ids`、`reason`、`check`、`seq`。材料必须真实存在；先修/时长/难度必须满足约束。

---

## 5. 五态、assigned 与可测范围

### 5.1 五种 `evidence_state`

| 条件 | `evidence_state` | 计入 `evidence_count` | 计入 `coverage.observed_items` |
|---|---|---|---|
| 已布置 + 已作答 + 已评分 + 答对 | `observed_correct` | 是 | 是 |
| 已布置 + 已作答 + 已评分 + 答错 | `observed_wrong` | 是 | 是 |
| 已布置 + 已作答 + **未评分** | `pending` | 否 | 否 |
| 已布置 + 未作答 | `assigned_not_attempted` | 否 | 否 |
| 未布置 / 无记录 | `unobserved` | 否 | 否 |

- 无观测：`mastery=null`、`status=insufficient_evidence`，**不要写 0**。
- `pending` 是“已作答但没分”：既不是对也不是错，**不得计入 n、不得判为 wrong、不得静默丢弃**。
- 未作答不等于答错；未记录不等于未掌握。
- 同一学生同一材料多条记录：按 `attempt_no` → `submitted_at` → `record_id` 取最后一条，并记录去重数。

### 5.2 `assigned` 怎么定（官方数据没有这个字段）

`assigned` 只表示**该生是否被布置过该材料**，只能由证据推出，不能由“题目存在”推出：

| 官方 `评分状态` | `assigned` | `attempted` | `score` | `is_correct` | 落行？ |
|---|---|---|---|---|---|
| 已评分 | `true` | `true` | 数值 | `score == max_score` | 是 |
| 待评分 | `true` | `true` | `null` | `null` | 是 |
| 未作答 | `true` | `false` | `null` | `null` | 是 |
| 无记录 | — | — | — | — | **否** |

三条硬规则：

1. **不得**把“测验节点可用题目”全量展开成 `assigned=true` 的记录行。节点列出的是**可测上限**，不是布置名单；展开会把“没考过”变成“没做”。
2. **无记录不落行**：`unobserved` 由聚合层按 `(student, knowledge)` 无观测判定，不写成 `assigned=false` 的行。
3. `assigned=false` 只留给**将来确实拿到布置名单**的数据集；本赛题数据中不会出现。

### 5.3 可测范围（applicable）与覆盖度

- `applicable`：该生在所参加测验节点上**能够**被测量的材料集合 = 节点 `可用题目` ∩ 该节点已教主题。它是**分母**，与 `assigned` 无关。
- `coverage.observed_items`：有评分记录的作答项数（`observed_correct + observed_wrong`）。
- `coverage.applicable_items`：上述 `applicable` 的去重材料数。
- `ratio = observed_items / applicable_items`；`pending`、`assigned_not_attempted`、`unobserved` 都落在缺口里，但**成因不同，必须分别报**。

### 5.4 可核对的不变式

| 位置 | 不变式 |
|---|---|
| `data_quality_report.records_by_state` | `observed_correct + observed_wrong + pending + assigned_not_attempted == total_records`；`unobserved` 恒为 `0`（无记录不落行） |
| `student_profile.knowledge_states[].state_counts` | 五项之和 = 该知识点可测材料数；`evidence_count == observed_correct + observed_wrong` |

---

## 6. 适配与版本

- 官方数据先经 `src/knowflow/io/adapters.py` 映射；下游不直接读官方列名。
- 官方数据字典到达后只改适配层 + 本文附录，不改诊断/建议。
- `schema_version` semver：删字段/改语义/改枚举 = major；加可选字段/加枚举值 = minor；只改描述 = patch。
- 变更必须更新 schema、本文、fixtures，并跑 `check_contracts` + `pytest`。

---

## 7. 官方数据已确认（原「当前未定」）

以下四项曾列为未定，接入 `official-v1` 后已确认：

| 原问题 | 结论 | 对契约的影响 |
|---|---|---|
| 官方“评分状态”取值与 `assigned` 是否存在 | 取值为 `已评分 / 待评分 / 未作答`；**没有 `assigned`** | 新增 `pending` 态；`assigned` 按 §5.2 推导 |
| 官方材料编号是否已带 `M-` 前缀 | 否：`Q001–Q054` 题、`L01–L03` 学习卡、`B01–B08` 教材切片 | 适配层统一映射到 `M-001…M-065` |
| 官方知识点编号与 `K-xx` 的映射 | 官方最细粒度是**观察指标** `T01I1–T03I3`（9 个）；课标条目为 `CR01–CR03` | `knowledge_id ← 指标`、`objective_id ← CR`；本数据集不再细分 |
| 是否有多次作答/时间/用时字段 | 有 `修订版本`（→ `attempt_no`）与 `模拟提交时间`（ISO 8601 +08:00）；**无用时** | `duration_seconds` 恒 `null`，不分析 |

仍未定（等独立评测数据）：是否会提供布置名单、是否出现 `assigned=false`、是否有跨节点同题的复核记录。

未确认的字段不猜；适配层显式报告未知列/缺列，人工确认后再写入 canonical。

---

## 8. 变更记录

| 版本 | 变更 | 兼容性 |
|---|---|---|
| **v0.2** | 新增 `pending` 态；`state_counts` / `records_by_state` 增加 `pending` 记账字段（必填）；明确 `assigned` / `attempted` 判定与 `applicable` 口径；§7 四项结案；新增两条不变式 | **minor**：无字段删除、无既有取值语义变更；M0 阶段无生产方与历史产物 |
| v0.1 | 初版 | — |
