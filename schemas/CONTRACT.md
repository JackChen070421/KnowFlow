# 数据契约（canonical v0.1）

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

## 5. 四态与缺失

| 条件 | 状态 | 计入 evidence_count |
|---|---|---|
| 已布置 + 已作答 + 答对 | `observed_correct` | 是 |
| 已布置 + 已作答 + 答错 | `observed_wrong` | 是 |
| 已布置 + 未作答 | `assigned_not_attempted` | 否 |
| 未布置 / 无记录 | `unobserved` | 否 |

- 无观测：`mastery=null`、`status=insufficient_evidence`，**不要写 0**。
- 未作答不等于答错；未记录不等于未掌握。
- 同一学生同一材料多条记录：按 `attempt_no` → `submitted_at` → `record_id` 取最后一条，并记录去重数。

---

## 6. 适配与版本

- 官方数据先经 `src/knowflow/io/adapters.py` 映射；下游不直接读官方列名。
- 官方数据字典到达后只改适配层 + 本文附录，不改诊断/建议。
- `schema_version` semver：删字段/改语义/改枚举 = major；加可选字段/加枚举 = minor。
- 变更必须更新 schema、本文、fixtures，并跑 `check_contracts` + `pytest`。

---

## 7. 当前未定

- 官方“评分状态”取值与 `assigned` 是否存在。
- 官方材料编号是否已带 `M-` 前缀。
- 官方知识点编号与 `K-xx` 的映射。
- 是否有多次作答/时间/用时字段。

未确认的字段不猜；适配层显式报告未知列/缺列，人工确认后再写入 canonical。
