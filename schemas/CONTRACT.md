# 数据契约（canonical v0.3 任务2实现）

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
| 问题 | `issue_id` | `IS-<学生序号>-<知识点数字部分，两或三位>` | `IS-012-01` |
| 群体/任务 | `group_id` / `task_id` | `G<序号>` / `T<序号>` | `G2` / `T1` |

ID 不复用、不回收、不手敲新增；跨文件引用必须能解析。学生一律伪匿名，禁止姓名/学号/联系方式。

---

## 2. 枚举（机器值）

| 枚举 | 取值 |
|---|---|
| `verb_level` | `know` / `understand` / `master` / `apply` |
| `cognitive_type` | `concept` / `procedure` / `application` |
| `material_type` | `reference` / `explain` / `example` / `practice` / `assessment` / `probe` |
| `evidence_state` | `observed_correct` / `observed_wrong` / `assigned_not_attempted` / `pending` / `unobserved` |
| `status` | `confirmed_weak` / `likely_weak` / `insufficient_evidence` / `likely_mastered` / `confirmed_mastered` / `mixed_performance` / `not_applicable` |
| `confidence` | `low` / `medium` / `high` |
| `issue_type` | 原有六类 + `performance_gap`（表现偏弱、错因未定）/ `score_point_gap`（有分点评分依据的失分） |
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

诊断粒度：`knowledge_states[]` 是唯一计算源；`objective_states[]` 是按 `evidence_count` 加权的派生视图，必须列出 `derived_from` 与 `unobserved_knowledge_ids`。课标层的 `evidence_count` 按记录ID去重，避免一题多知识点重复记账；加权均值不是一个重新拟合的后验分布。

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
- 先按同一作答事件分组，再按 `attempt_no` → 带时区的 `submitted_at` → `record_id` 取最后一条；不同测验节点的同题记录独立保留。最新版本得分无效时隔离该版本，不恢复旧分。事件身份、顺序或记录主键有歧义时隔离并报告。

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
- `ratio = observed_items / applicable_items`；`pending`、`assigned_not_attempted`、`unobserved` 都落在缺口里，但**成因不同，必须分别报**。无参与证据或分母为0时 `ratio=null`，并给出 `scope_known`；不填0。
- 按节点单独诊断。参与仅由记录中的有效学生ID和节点ID证明，不假定全班参加；节点不包含某知识点的题目时为 `not_applicable`，无参与记录时为 `insufficient_evidence` 并注明适用范围待确认。

### 5.4 可核对的不变式

| 位置 | 不变式 |
|---|---|
| `data_quality_report.records_by_state` | `observed_correct + observed_wrong + pending + assigned_not_attempted == total_records`；`unobserved` 恒为 `0`（无记录不落行） |
| `student_profile.knowledge_states[].state_counts` | 五项之和 = 该知识点可测材料数；`evidence_count == observed_correct + observed_wrong` |
| `data_quality_report` v0.3 | `input_records == total_records + duplicates_removed + rejected_records`；`total_records`是清洗后保留行数；`decisions`逐行记账 |

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

仍未定（等独立评测数据）：是否提供独立参与/布置名单、是否出现 `assigned=false`、字段或ID是否扩展。跨节点同题已按独立事件保留，不能混成一次修订。

未确认的字段不猜；适配层显式报告未知列/缺列，人工确认后再写入 canonical。

---

## 8. 任务2诊断输入与算法

- 新增 `input/diagnosis_input.schema.json`，它校验整个诊断输入包，其他 `input` schema仍校验CSV行。输入包位于 `data/interim/<dataset>/diagnosis_input.json`；不进Git。
- 包含学生、题目最小元数据、指标映射、测验节点范围、参与证据、清洗后记录、来源行索引和质量报告；不包含原始答案或解答过程。
- 只使用官方明确标注的题目—观察指标对应关系启动任务2；不填造课标原文、题目难度、先修关系，也不声称已完成任务1。学习卡和教材由R1构建知识底座。
- 默认ID：D数字→S三位，DC数字→G数字，Q数字→M三位，DR数字→R四位，CR数字→OBJ-7M两位。知识点初次按指标ID排序分配，随后复用本机 `id_map.json`，新增指标只追加。跨团队和独立数据集需共用已确认映射，不能各自生成后直接拼接。
- `run --knowledge-base <文件>` 可使用R1的已校验知识底座覆盖知识点与Q-matrix；要求沿用材料ID且覆盖所有可测题目。所有正权重关系用于关联；当前模型不使用权重或难度调分。
- `records`新增 `node_id`、`event_id`、`score_points`；v0.3诊断输入包必须提供。`attempt_no`暂承接官方修订版本，不把它解释成独立练习次数。
- 评分点与总分不一致时保留有效官方总分、停用评分点，记录警告；不使用答案字符串重新判分。`observed_wrong`在有部分得分时表示“未满分”；`performance`另报满分/部分得分/零分人数或项数及平均归一化得分。

默认模型：`Beta(1+k,1+n-k)`，n为当前节点有效评分题数，k为满分题数；`mastery=(k+1)/(n+2)`。无评分时为null。此量估计当前材料范围内的满分成功率，不等同于整体能力百分比。

参数全部由 `DiagnosisConfig` 管理并写入运行清单：最少观测3、薄弱阈值0.4、掌握阈值0.75、确认后验概率0.9、可信区间质量0.9。区间宽度≤0.35为high、≤0.6为medium，否则low；n<3强制low。均为开发基线，不是赛事指定阈值或已校准教育标准。

状态顺序：无范围可测→not_applicable；范围未知/无评分/n<3→insufficient_evidence；低于0.4的后验概率≥0.9→confirmed_weak；高于0.75的后验概率≥0.9→confirmed_mastered；均值<0.4→likely_weak；均值≥0.75→likely_mastered；其余→mixed_performance。3次全错为likely_weak，3次全对为likely_mastered，不直接确认。

每个学生×知识点至多一个问题ID，跨节点稳定；完整引用键为 `(source_dataset,node_id,issue_id)`。证据不足也可携带已观察到的评分点失分，但不据此确认一般性错因。`rubric_evidence`引用有效记录和官方评分点；原始作答通过本机 `evidence` 命令按哈希与逻辑行号核对。

班级：先算个人、再按学生等权汇总；null排除，不补0。`knowledge_distribution`的掌握/薄弱/不足/混合/不适用计数之和等于学生数。`common_issues.prevalence`分母是所选班级全体学生；`rubric_patterns.prevalence`分母是该知识点对应评分点有可信评分的不同学生数。评分点标签按原文精确分组，不自动做语义合并或推断因果。

本分支的格式变化须在合并前由R1/R4审查。旧格式样例仍可校验；v0.3生产结果的新增字段由条件Schema强制要求。消费者须显式处理新增状态、问题类型和可空覆盖率。

## 9. 变更记录

| 版本 | 变更 | 兼容性 |
|---|---|---|
| **v0.3** | 节点/事件/评分点、诊断输入包、混合与不适用状态、可空覆盖率、逐行审计及任务2复算 | 增量接口；旧样例保留兼容，新生产方必填扩展字段；消费者须适配新值，合并前R1/R4审查 |
| **v0.2** | 新增 `pending` 态；`state_counts` / `records_by_state` 增加 `pending` 记账字段（必填）；明确 `assigned` / `attempted` 判定与 `applicable` 口径；§7 四项结案；新增两条不变式 | **minor**：无字段删除、无既有取值语义变更；M0 阶段无生产方与历史产物 |
| v0.1 | 初版 | — |
