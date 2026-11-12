# 数据契约（contract v0.5；输入表 canonical 仍为 v0.4）

> 机器定义以 `schemas/**/*.schema.json` 为准；本文只做速查。
> 改字段/枚举/ID = 改合同：先改 schema + 本文，再改代码和 fixtures。
> v0.5 只扩展**输出**契约（个人/群体画像、质量报告）；`records` 等输入表未变，`CANONICAL_VERSION` 仍为 `0.4.0`。两者不要互相冒充。

---

## 1. ID

| 实体 | 字段 | 规则 | 示例 |
|---|---|---|---|
| 课标条目 | `objective_id` | `OBJ-<年级><学科>-<序号>` | `OBJ-7M-03` |
| 知识点 | `knowledge_id` | `K-<两位序号>` | `K-07` |
| 材料/题目 | `material_id` | `M-<三位序号>` | `M-021` |
| 作答记录 | `record_id` | `R-<四位序号>` | `R-0031` |
| 学生 | `student_id` | `S<三位序号>` | `S012` |
| 问题 | `issue_id` | `IS-<学生三位>-<知识点序号两位>` | `IS-012-07` |
| 群体/任务 | `group_id` / `task_id` | `G<序号>` / `T<序号>` | `G2` / `T1` |

ID 不复用、不回收、不手敲新增；跨文件引用必须能解析。学生一律伪匿名，禁止姓名/学号/联系方式。

`issue_id` 第二段是 `knowledge_id` 的数字部分（`K-07` → `07`），**不是顺序号**：同一学生同一知识点在不同节点、不同重算之间保持同一个 ID，建议层可以直接引用而不用每次重新对表。与之配套的约束是**每个学生 × 知识点至多一条 issue**；将来需要第二条时先升契约版本，不要私自加后缀。

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
| `issue_type` | `concept_confusion` / `procedure_gap` / `reading_error` / `prerequisite_gap` / `transfer_gap` / `insufficient_evidence` / `performance_gap` / `score_point_gap` |
| `edge_type` | `prerequisite` / `contains` / `confusable` / `related` |

中文标签只用于 UI/文档；机器读写一律用英文枚举。

v0.5 新增值的含义（消费方必须显式处理，不许落到 `else` 分支）：

- `mixed_performance`：证据都有效，但结论落在中间地带（既没到薄弱也没到掌握）。它**不是**"数据不足"，不得折算成五类里的任何一个。
- `not_applicable`：该节点没有该知识点的可测题目（分母为 0）。它不是"未掌握"，也不进覆盖率分母。
- `performance_gap`：确实偏弱，但错因没有证据支撑，只报"表现差距"。
- `score_point_gap`：有官方评分点失分作为依据的差距，证据在 `rubric_evidence[]`。

---

## 3. 输入 CSV

UTF-8、逗号分隔、首行表头、一行一实体。完整字段见对应 schema。

| 文件 | 关键列 |
|---|---|
| `objectives.csv` | `objective_id, subject, grade, theme, unit, objective_text, verb_level, source_material_id, source_locator` |
| `knowledge.csv` | `knowledge_id, objective_id, parent_id, name, level, cognitive_type, description, sort_order` |
| `materials.csv` | `material_id, title, body, material_type, item_format, difficulty, objective_id, options_json, answer_key, explanation, rubric_json, attachments_json, est_minutes, source, license` |
| `qmatrix.csv` | `material_id, knowledge_id, weight, difficulty, item_type, is_primary`；主键二元组 |
| `edges.csv` | `from_id, to_id, edge_type, weight, note` |
| `students.csv` | `student_id, group_id, grade, stage, notes` |
| `nodes.csv` | `node_id, title, exam_date, taught_objective_ids_json, available_material_ids_json, note`；一次考试事件 |
| `records.csv` | `record_id, student_id, material_id, node_id, assigned, attempted, score, max_score, is_correct, answer, rubric_scores_json, steps_json, submitted_at, duration_seconds, attempt_no, source` |
| `record_details.csv` | `csv_record_number, source_record_id, record_id, student_id, material_id, node_id, kept, final_answer, solution_process, scoring_point_scores`；证据层，一行对应官方 CSV 一行 |
| `tasks.csv` | `task_id, title, goal, target_scope, target_ids_json, material_scope_json, constraints_json, expected_output` |

约束：

- `objective_text` 原文照录，不改写。
- `score` 必须在 `[0, max_score]`；`attempted=false` 时 `score/is_correct` 为 `null`。
- `qmatrix` 每个 `practice/assessment` 至少挂 1 个知识点；每个知识点至少 1 个 `practice/assessment`。
- `prerequisite`/`contains` 不能成环；无自环。
- 官方未提供的 `difficulty`、教材切片的 `objective_id` 为 `null`：**不猜、不用哨兵值**；下游把 `null` 当“未知”，不得当作 1 或最低难度。
- `answer` / `steps_json` / `rubric_scores_json` 是**本机证据字段**：只写 `data/interim/`（gitignore），禁止送 LLM 或外传。
- `record_details` 与 `records` 的分工：`records` 是**分析层**（一条观测一行，去重后 799 行）；`record_details` 是**证据层**（官方 CSV 一行一行，806 行，原文不动）。`kept=false` 的行是被更高修订替代的旧版本，只留在证据层，`record_id` 指向替代它的那条；因此 `record_details` 行数必须等于原始作答记录行数，且每条 `records` 必须恰有一条 `kept=true` 的明细。

---

## 4. 输出 JSON

| 文件 | 顶层字段 |
|---|---|
| `knowledge_base.json` | `schema_version, dataset_id, generated_at, subject, grade, counts, objectives, knowledge, materials, qmatrix, edges` |
| `data_quality_report.json` | `schema_version, dataset_id, generated_at, input_files, input_records, total_records, duplicates_removed, rejected_records, partial_credit_records, records_by_state, missing, anomalies, field_quality, handling_rules, decisions` |
| `student_profile.json` | `schema_version, student_id, group_id, node_id, generated_at, source_dataset, coverage, knowledge_states, objective_states, issues, lists` |
| `class_profile.json` | `schema_version, class_id, node_id, generated_at, source_dataset, student_count, coverage_summary, knowledge_distribution, common_issues, rubric_patterns, tiers, group_differences?` |
| `recommendation.json` | `schema_version, student_id, generated_at, source, generated_by, plan, probe_plan` |
| `validation_report.json` | `schema_version, run_id, generated_at, targets, checks, summary, gate` |

诊断粒度：`knowledge_states[]` 是唯一计算源；`objective_states[]` 是按 `evidence_count` 加权的派生视图，必须列出 `derived_from` 与 `unobserved_knowledge_ids`。画像按测验节点产出，`node_id` 必填；同一学生不同节点是两份画像，不合并。

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
- 同一学生同一材料**同一节点**多条记录：按 `attempt_no` → `submitted_at` → `record_id` 取最后一条，并记录去重数。
- **跨节点同题不算重复**：同一学生在 N01、N02 各答一次是两次独立观测，靠 `node_id` 区分，两行都保留。

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
- 数据源：`nodes.csv` 的 `available_material_ids_json`（可用题目）与 `taught_objective_ids_json`（已教主题），配合 `records.node_id` 确定“该生参加了哪些节点”。没有 `nodes.csv` 的数据集（M0 合成样例曾走此路，v0.3 起样例也带 `nodes.csv`）退回用 `tasks.material_scope_json` 定义分母。
- `coverage.observed_items`：有评分记录的作答项数（`observed_correct + observed_wrong`）。
- `coverage.applicable_items`：上述 `applicable` 的去重材料数。
- `ratio = observed_items / applicable_items`；`pending`、`assigned_not_attempted`、`unobserved` 都落在缺口里，但**成因不同，必须分别报**。
- 无参与证据或分母为 0 时 `ratio=null` 且 `scope_known=false`。**不填 0，也不假定全班参加**：参与只由记录里的有效学生 ID + 节点 ID 证明。

### 5.4 可核对的不变式

| 位置 | 不变式 |
|---|---|
| `data_quality_report.records_by_state` | `observed_correct + observed_wrong + pending + assigned_not_attempted == total_records`；`unobserved` 恒为 `0`（无记录不落行） |
| `data_quality_report`（v0.5 审计） | `input_records == total_records + duplicates_removed + rejected_records`；`decisions` 行数 == `input_records`（官方 CSV 每行恰好一条决策） |
| `student_profile.knowledge_states[].state_counts` | 五项之和 = 该知识点可测材料数；`evidence_count == observed_correct + observed_wrong` |
| `student_profile.knowledge_states[].applicable_items` | 等于该条 `state_counts` 五项之和；`not_applicable` 时为 `0` |
| `class_profile.knowledge_distribution[]` | `mastered + weak + insufficient + mixed + not_applicable == student_count`；`mean_mastery` 的分母是 `observed_student_count` |
| `class_profile.common_issues[].prevalence` | `student_count / denominator`，且 `denominator == student_count`（按全体学生口径） |
| `class_profile.rubric_patterns[].prevalence` | `affected_student_count / observed_student_count`，分母只算该评分点有可信评分的学生 |

### 5.5 状态判读顺序（v0.5 固定，阈值属算法配置）

契约只固定**顺序与含义**，不固定具体数值；数值由 `DiagnosisConfig` 管，写进运行清单：

1. 该节点没有该知识点的可测题目 → `not_applicable`（`mastery=null`，不进分母）；
2. 无有效评分，或有效题数 `n < 3` → `insufficient_evidence`（`mastery` 可为 null，但不得写 0）；
3. `P(p < 薄弱阈值) ≥ 确认门槛` → `confirmed_weak`；
4. `P(p > 掌握阈值) ≥ 确认门槛` → `confirmed_mastered`；
5. 均值 `< 薄弱阈值` → `likely_weak`；均值 `≥ 掌握阈值` → `likely_mastered`；
6. 其余 → `mixed_performance`。

`mastery = (k+1)/(n+2)`，`k` 为满分题数，`n` 为有效评分题数。它估计的是**当前材料范围内的满分成功率**，不是"整体能力百分比"；部分得分另看 `performance.mean_score_ratio`。

---

## 6. 适配与版本

- 官方数据先经 `src/knowflow/io/`（`mapping.py` ID、`adapters.py` 字段、`quality.py` 清洗/报告、`pipeline.py` I/O 与校验）映射；下游不直接读官方列名。
- 生成：`python scripts/build_canonical.py --dataset-id official-v1` → `data/interim/official-v1/`（10 张表 + `data_quality_report.json`，均 gitignore）。
- 复检：`python scripts/validate_canonical.py --dataset-id official-v1`（G2 引用 + G3 一致性，逐字节比对磁盘文件）。
- 官方数据字典到达后只改适配层 + 本文附录，不改诊断/建议。
- `schema_version` semver：删字段/改语义/改枚举 = major；加可选字段/加枚举值 = minor；只改描述 = patch。
- 变更必须更新 schema、本文、fixtures，并跑 `check_contracts` + `check_examples` + `pytest`。
- **本文版本与输入表版本分开记**：本文 `v0.5` / `CANONICAL_VERSION=0.4.0`。v0.5 只扩展输出契约；只有动 CSV 列才改 canonical 版本和 `data/manifests/*.expected.json`。两者混用会造成"两个 v0.3"式的歧义。

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

### 7.1 官方 → canonical ID 映射（official-v1）

| 官方 | canonical | 规则 |
|---|---|---|
| `CR01/02/03` | `OBJ-7M-01/02/03` | 保留序号 |
| `T01I1…T03I3` | `K-01…K-09` | 主题序 × 指标序；9 行固定表 |
| `Q001–Q054` | `M-001–M-054` | 保留序号 |
| `L01–L03` | `M-055–M-057` | 接在题后 |
| `B01–B08` | `M-058–M-065` | 接在卡后 |
| `DR0001–DR0806` | `R-0001–R-0806` | 保留序号 |
| `D01–D40` | `S001–S040` | 保留序号 |
| `DC01/DC02` | `G1/G2` | 班序 |
| `N01/N02` | `N01/N02` | 原样 |
| `Q043P2` 等评分点 | `M-043P2` | 材料 ID 替换，P 序号保留 |

教材切片与课标条目的对应（其余 5 条官方明确“未标注主题和指标”，`objective_id=null`）：

| 切片 | objective_id |
|---|---|
| `B02` | `OBJ-7M-03` |
| `B05` | `OBJ-7M-01` |
| `B06` | `OBJ-7M-02` |

其他固定判定（写进适配层，逐条可复核）：

- `verb_level=apply`：三条主题目标均为“能……”。
- `cognitive_type`：`K-01/K-03/K-06/K-09 = application`，`K-02/K-04/K-05/K-07/K-08 = procedure`。
- `materials.unit`（objectives.unit）：取对应教材切片的章节标签（官方无单元字段）。
- `title`：`"{官方编号} {题型/学习卡/教材切片}"`，确定性占位，不改 ID。

---

## 8. v0.5：诊断层输出契约

v0.5 只做一件事：**把 M2 诊断层已经算出来的东西写进契约**，让 R3 建议层可以照着字段写代码，而不是照着聊天记录猜。不新增输入表，不引入原文，不引入 LLM。

**个人画像（`student_profile.json`）**

| 字段 | 约束 | 为什么 |
|---|---|---|
| `node_id` | 必填，`^N[0-9]{2}$` | 画像按节点产出；跨节点合并会重复计一次作答 |
| `coverage.scope_known` | 必填布尔 | 区分"覆盖率 0"和"不知道分母"；`false` 时 `ratio` 必须为 `null` |
| `coverage.ratio` | `number|null` | 无参与证据时是"不知道"，不是"没做" |
| `knowledge_states[].credible_interval` | 必填，长度 2 的区间或 `null` | 掌握度必须带不确定性；`n=0` 为 `null` |
| `knowledge_states[].weak_probability` / `mastered_probability` | 必填，`[0,1]` 或 `null` | 让"为什么不是 confirmed"可复算 |
| `knowledge_states[].applicable_items` | 必填，整数 | 等于 `state_counts` 五项之和，防止分母与计数两套真相 |
| `knowledge_states[].status_reason` | 必填，非空 | 枚举值不能自己解释自己 |
| `knowledge_states[].performance` | 必填对象 | 部分得分/零分另报；避免把"未满分"说成"答错" |
| `issues[].rubric_evidence` | 必填数组 | **空数组 = 已核查且无可引用评分点**，不是"没算" |

**群体画像（`class_profile.json`）**

- `node_id` 必填；`coverage_summary.students_with_known_scope` 必填，并作为 `mean_ratio` 的实际分母。
- `knowledge_distribution[]` 的 `mastered_count / weak_count / insufficient_count / mixed_count / not_applicable_count` 五项必须存在，且**之和等于 `student_count`**；否则"分布"会漏人。
- `common_issues[]` 必须写 `denominator` 与 `denominator_basis`；本版只允许 `all_students_in_selected_class`。换口径必须换枚举并升版本。
- `rubric_patterns[]` 的分母是**该评分点有可信评分的不同学生数**，不是全班人数；标签按官方原文精确分组，不自动做语义合并。
- `null` 一律排除出均值，**不补 0**。

**质量报告（`data_quality_report.json`）**

`input_records / rejected_records / partial_credit_records / decisions` 为可选字段：**数据层产物可以不带，诊断运行必须带**。`decisions` 逐行记账（`retained / superseded / rejected` + 原因），满足"官方 CSV 每一行恰好一条决策，不静默丢弃"；`retained` 可以无附加原因，`superseded` / `rejected` 必须写原因。之所以不设为全局必填：现有 `build_canonical` 产物不带这些字段，强行必填会让数据层与诊断层互相阻塞；这一层强制由诊断层的 `verify-run` 负责，而不是 JSON Schema。

**明确不做**：不把 `answer` / `steps_json` 原文引入任何输出（证据仍走本机 `record_details.csv` 与按需导出）；不规定 Beta 的阈值数值（那是算法配置，写进运行清单即可）；不为"以后可能要"预留字段。

---

## 9. 变更记录

| 版本 | 变更 | 兼容性 |
|---|---|---|
| **v0.5** | 诊断层输出契约：个人/群体画像加 `node_id`、`scope_known`、Beta 统计（区间/两侧概率）、`applicable_items`、`status_reason`、`performance`、`rubric_evidence`、`rubric_patterns`；`status` 加 `mixed_performance`/`not_applicable`，`issue_type` 加 `performance_gap`/`score_point_gap`；`issue_id` 第二段改为知识点序号（跨节点稳定）；质量报告加逐行 `decisions` 等可选字段与三条不变式 | **minor（输出）**：无字段删除、无既有取值语义变更；输入表 canonical 仍 `0.4.0`，`records.csv` 不变。消费方需显式处理新增状态/类型与可空 `ratio` |
| **v0.4** | 新增证据层 `record_details.csv`（原文零加工 + `csv_record_number` 回查 + `kept` 标记被替代的修订）；`records` 字段不变，仍为分析层；写盘改为临时文件 + 原子替换；适配错误信息不再回显单元格原文；五态记账下沉到 `src/knowflow/cleaning/states.py` | **minor**：只新增表，无字段删除、无既有取值语义变更；消费方只读 `records` 的无需改动 |
| **v0.3** | 新增 `nodes.csv` 与 `records.node_id`；`records` 增 `rubric_scores_json`/`steps_json`，`materials` 增 `item_format`/`explanation`/`rubric_json`；`materials.objective_id`、`materials.difficulty`、`qmatrix.difficulty` 允许 `null`；去重改为节点内；§5.3 明确 applicable 数据源；§7 增 ID 映射附录 | **minor**：只加可选字段/新增表/放宽 required；无字段删除、无已有取值语义变更；消费方需处理 `null` |
| **v0.2** | 新增 `pending` 态；`state_counts` / `records_by_state` 增加 `pending` 记账字段（必填）；明确 `assigned` / `attempted` 判定与 `applicable` 口径；§7 四项结案；新增两条不变式 | **minor**：无字段删除、无既有取值语义变更；M0 阶段无生产方与历史产物 |
| v0.1 | 初版 | — |
