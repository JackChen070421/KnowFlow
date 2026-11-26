# 数据契约（contract v0.10；输入表 canonical 仍为 v0.4.0）

本机变式训练新增独立存储契约，见 [training.md](training.md)。不改变 canonical 和正式诊断口径。

> 机器定义以 `schemas/**/*.schema.json` 为准；本文只做速查。
> 改字段/枚举/ID = 改合同：先改 schema + 本文，再改代码和 fixtures。
> v0.5 扩展输出契约（个人/群体画像、质量报告）；v0.6 扩任务3建议；v0.7 加存疑评分审查；v0.8 加正式课程图谱；v0.9 加学习路径与补充观测；v0.10 加教学反馈与补充证据闭环。`records` 等输入表未变，`CANONICAL_VERSION` 仍为 `0.4.0`。

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
| `status` | `confirmed_weak` / `likely_weak` / `insufficient_evidence` / `unobserved` / `likely_mastered` / `confirmed_mastered` / `mixed_performance` / `not_applicable` |
| `confidence` | `low` / `medium` / `high` |
| `issue_type` | `concept_confusion` / `procedure_gap` / `reading_error` / `prerequisite_gap` / `transfer_gap` / `insufficient_evidence` / `performance_gap` / `score_point_gap` |
| `edge_type` | `prerequisite` / `contains` / `confusable` / `related` |

中文标签只用于 UI/文档；机器读写一律用英文枚举。

v0.5 新增值的含义（消费方必须显式处理，不许落到 `else` 分支）：

- `mixed_performance`：证据都有效，但结论落在中间地带（既没到薄弱也没到掌握）。它**不是**"数据不足"，不得折算成五类里的任何一个。
- `not_applicable`：该节点没有该知识点的可测题目（分母为 0）。它不是"未掌握"，也不进覆盖率分母。
- `performance_gap`：确实偏弱，但错因没有证据支撑，只报"表现差距"。
- `score_point_gap`：有官方评分点失分作为依据的差距，证据在 `rubric_evidence[]`。

v0.6 新增值：

- `unobserved`：该节点**有**该知识点的可测题目，但一条已评分作答都没有（`evidence_count=0` 且 `pending=0`）。它不是"证据不足"，也不是"未掌握"；它要的动作是**布置基线题**，而 `insufficient_evidence`（有评分但不足门槛、或已作答待评分）要的动作是**再测一次**。两者分别进 `lists.needs_coverage` 与 `lists.needs_observation`。
- `knowledge_states[].evidence_action`：动作与状态解耦。`probe`（无任何记录）/ `not_attempted`（已布置未作答）/ `pending`（已作答待评分）/ `sparse_weak`（评分少但后验偏弱，低置信度巩固）/ `sparse_mastered`（评分少但都对，一次复核）/ `sparse_mixed`（评分少且中间，继续补观测）；非稀疏状态为 `null`。语言层据此写动作，不得因 `status` 一律降级成"补充观测"。

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
| `knowledge_base.json` | `schema_version, dataset_id, generated_at, subject, grade, counts, objectives, knowledge, materials, qmatrix, edges, curriculum_graph?` |
| `data_quality_report.json` | `schema_version, dataset_id, generated_at, input_files, input_records, total_records, duplicates_removed, rejected_records, partial_credit_records, records_by_state, missing, anomalies, field_quality, handling_rules, decisions` |
| `student_profile.json` | `schema_version, student_id, group_id, node_id, generated_at, source_dataset, coverage, knowledge_states, objective_states, issues, lists` |
| `class_profile.json` | `schema_version, class_id, node_id, generated_at, source_dataset, student_count, coverage_summary, knowledge_distribution, common_issues, rubric_patterns, tiers, group_differences?` |
| `recommendation.json` | `schema_version, student_id, node_id?, generated_at, source, generated_by, plan, probe_plan, review_context?, review_required?, plan_id?, plan_version?, history?, plan_diff?, progress?, deferred?` |
| `validation_report.json` | `schema_version, run_id, generated_at, targets, checks, summary, gate, errors?, policy_version?` |

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

- 无观测：`mastery=null`，`status` 为 `unobserved`（有题但 0 条评分）或 `insufficient_evidence`（0<n<门槛，或已作答待评分），**不要写 0**。
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
| `class_profile.knowledge_distribution[]` | `mastered + weak + insufficient + unobserved + mixed + not_applicable == student_count`；`mean_mastery` 的分母是 `observed_student_count` |
| `class_profile.common_issues[].prevalence` | `student_count / denominator`，且 `denominator == student_count`（按全体学生口径） |
| `class_profile.rubric_patterns[].prevalence` | `affected_student_count / observed_student_count`，分母只算该评分点有可信评分的学生 |

### 5.5 状态判读顺序（v0.6 固定，阈值属算法配置）

契约只固定**顺序与含义**，不固定具体数值；数值由 `DiagnosisConfig` 管，写进运行清单：

1. 该节点没有该知识点的可测题目 → `not_applicable`（`mastery=null`，不进分母）；
2. 有可测题、有效评分 `n=0` 且无待评分 → `unobserved`（未覆盖，进 `needs_coverage`）；
3. 有效题数 `0 < n < min_evidence`，或 `n=0` 但有已作答待评分 → `insufficient_evidence`（进 `needs_observation`；`mastery` 可为 null，但不得写 0）；
4. `P(p < 薄弱阈值) ≥ 确认门槛` → `confirmed_weak`；
5. `P(p > 掌握阈值) ≥ 确认门槛` → `confirmed_mastered`；
6. 均值 `< 薄弱阈值` → `likely_weak`；均值 `≥ 掌握阈值` → `likely_mastered`；
7. 其余 → `mixed_performance`。

`min_evidence` 与"覆盖缺失线"是两个独立设置：前者决定判读门槛（默认 2 条），后者只影响看板上的覆盖率标注。门槛只决定"要不要给方向性结论"，不决定"能不能说已确认"：2 条证据在任何组合下都达不到 `confirmation_probability`（默认 0.9），最多得到 `likely_*` / `mixed_performance`。题量本身少于门槛的知识点，`status_reason` 必须写明"题目不足"，而不是归因于学生。

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

## 9. v0.6：任务3建议层输出契约

v0.6 把任务3的**规则版**写进契约。仍不接 LLM；`llm.enabled=false` 时全流程可跑通。任务3 的输入是**任务2 的同一节点画像 + 任务1 的 `knowledge_base.json`**，不新增输入表。

**产物（`recommendation.json`）**

| 字段 | 约束 | 为什么 |
|---|---|---|
| `node_id` | 可选，`^N[0-9]{2}$` | 默认按最新节点生成；同一学生不同节点不混用证据 |
| `plan[].activity_type` | 可选枚举 `explain/practice/consolidate/probe/review/extend` | 教师筛选；不改变 `seq` 语义 |
| `plan[].issue_id` | 必须来自该生画像的 `issues[]` | 建议必须回应一个已识别问题 |
| `plan[].material_ids` | 非空、唯一、真实存在；`primary_material_id` 必在列表 | 不手写材料 ID |
| `plan[].primary_material_id` | 优先测评材料；讲解卡可作辅助 | 支持“先讲后练”，但主材料可检查 |
| `plan[].reason` | 必须引用 `issue_id`；数字只能来自该 issue 证据、状态计数或策略常量（1/2/3/5） | 数字锁，不让模型改数字 |
| `plan[].check` | 可验证：做哪几题、哪个评分点满分、至少几题全对 | 教师可当场复核 |
| `plan[].difficulty` / `est_minutes` | 必填整数；本版为**规则推算值**，不是官方难度或精确用时 | 官方材料无这两个字段；运行说明必须声明 |
| `plan[].prerequisite_check` | 由 `knowledge_base.edges` 的 `prerequisite` 边计算；无边时 `satisfied=true` | 不编造先修关系 |
| `probe_plan.items` | 该生在该节点**未作答**的测评题；`needed` 必须等于 `items` 非空 | 补充观测不能拿旧作答冒充新证据 |

**生成规则（`r3-rules-1`）**

- 每个学生最多 3 条计划：薄弱/评分点失分优先，其次证据不足；不把“证据不足”写成“未掌握”。
- 已确认/疑似薄弱：讲解卡（若有）+ 同评分点复测 + 同知识点新题；没有新题时允许重做错题。
- 证据不足：只给未作答测评题，并在 `probe_plan` 中列同一批题；达到至少 3 次有效评分后再判断。
- 参与范围未知（`scope_known=false`）：计划为空，提示先确认范围。
- 表现较好且无 issue：不强行加练；计划为空、`probe_plan.needed=false`。

**材料范围**

- 测评题只用节点 `available_material_ids` 内、且 Q-matrix 映射到该知识点的材料。
- 讲解卡/教材切片不在节点测评范围时仍可使用（已登记材料），validator 记 warning，不伪装成节点内材料。

**明确不做**

- 不接 LLM；不生成自由文本数字；不把 `difficulty=null` 当 1；本轮只做个人建议，不做班级级建议。

---

## 10. v0.7：存疑评分审查（方向一）

目标：把「有官方分数」和「评分可信」分开。规则只产出**复核线索**，人工结论作为**独立事件**追加，官方分数永远不改。新增一张产物 `review_report.json`，并给个人画像与建议加可选字段；旧产物（无这些字段）仍然合法。

**核心边界**

- 规则只读 canonical（`records.csv` / `materials.csv` / `record_details.csv`），不写 canonical；审查产物**不含** `answer` / `final_answer` / `solution_process` 原文。
- 文本比对只用于**单值题**（`blank` / `choice`），只回答“作答与参考答案是否字面一致”，**不是判分器**；解答题仅在得分为 0 时才允许用同一线索。
- 线索 ≠ 结论：`flagged` 不是“答对了”，`dismissed` 也不是“答错了”；都只说明评分是否需要人工看一眼。
- 系统不得生成“修正后官方分数”。需要更正时必须由授权来源单独出事件，本轮**不实现**。

**规则（`review-rules-1`）**

| `code` | 触发（确定性） | 默认是否参与隔离 |
|---|---|---|
| `answer_matches_key_under_credit` | 已评分未满分；单值题（或解答题且 0 分）；规范化后作答 == `answer_key` | 是 |
| `rubric_total_mismatch` | 已评分；评分点可解析；`Σ评分点 ≠ 官方分`（理由列出 0 分评分点） | 是 |
| `score_exceeds_max_clamped` | 数据层 `anomalies` 记录的“得分超满分、已按评分点合计截断” | 否（仅审计；排除会丢证据） |
| `answer_key_mismatch_full_credit` | 单值题作答 ≠ 参考答案却满分 | 否（默认关闭；“x=9 vs 9”这类写法差异会全线误报） |

**审查状态**

| `review_status` | 含义 | 是否算存疑 |
|---|---|---|
| `flagged` | 规则发现线索，尚无人工结论（**缺失状态的默认值**） | 是 |
| `needs_more_evidence` | 人工判断需补材料后再定 | 是 |
| `confirmed_issue` | 人工确认该评分确有问题 | 是 |
| `dismissed` | 人工确认该评分无误 | 否 |

**口径（两套数字，都可复算）**

- `state_counts` / `evidence` / `evidence_count` / `performance` 永远是**官方账本**，不因审查而变。
- `knowledge_states[].review`（仅有存疑记录时出现）同时给出 `official_*` 与 `usable_*`（去掉存疑记录后）；`disputed_record_ids` 列出被排除的记录。
- 顶层 `mastery/status` 由 `--review-policy` 决定：`official`（默认）取官方口径，`exclude_flagged` 取 `usable_*`。两种取值都写进 `run_manifest.review`，可审计。
- `issues[].rubric_evidence` 只放**可用**失分；存疑失分放 `issues[].disputed_rubric_evidence`，不参与措辞与建议。
- 若可用证据因此低于 `min_evidence`，仍输出 `insufficient_evidence`，**不补造结论**。

**建议层**

- `plan[].basis_records` 列出该计划项真正依据的 `record_id`，不得包含存疑记录。
- `plan[].review_flags` 说明该知识点下被排除的记录及状态。
- `review_required[]` 用于“只剩存疑依据”的 issue：不生成巩固计划，只提示人工复核/补充观测。
- `review_context` 记录本次使用的报告哈希、策略与被排除记录；`verify-recommend` 校验三者一致。

**审查账本（本机）**

- 位置：`data/reviews/<dataset_id>/decisions.jsonl`（不进 Git，追加式，一行一个事件，最新生效、历史保留）。
- 每行必须带 `review_status / reviewer_role / review_note / reviewed_at / policy_version / source_reference / flag_codes`；`reviewer_role` 默认 `local_demo_user`，**不是认证教师身份**。
- 账本旁 `ledger_meta.json` 钉住三张 canonical 表的 `sha256`；哈希变化时拒绝套用旧结论，必须重新扫描复核（与 `apply_curation` 同一思路）。

**明确不做**：不做通用数学等价判分；不让 LLM 标记或改分；不把 `pending` 当作可判分（官方数据中 4 条 pending 有 2 条作答与参考答案字面一致，自动判分就会把“未评分”变成“满分”）。

---

## 11. v0.8：正式课程图谱（方向二）

目标：前端展示、诊断与建议读**同一份**受 Schema 约束的图谱；关系有稳定 ID、类型、来源、理由和审核状态；只有 `reviewed` 的先修关系能影响计划顺序。

**唯一数据源**

- 源文件：`knowledge/curriculum_graph.json`（可入库的教学资产，不含学生数据），构建时整份写入 `knowledge_base.json.curriculum_graph`。
- 前端从 `/api/snapshot` 的 `knowledge_base.curriculum_graph` 读取；建议层经 `recommend/catalog.py` 读取同一对象。**不再有第二份硬编码关系。**
- 图谱不改变 canonical 的 `edges.csv`（课标→知识点的包含关系）；两者是不同层：`edges` 是课程级材料/知识点包含，图谱是教材细目层的教学关系。

**节点与边**

| 对象 | 字段 | 约束 |
|---|---|---|
| 节点 | `node_id / title / theme_index / summary / source_locator / textbook / pdf_page / knowledge_ids / material_id` | `node_id` 固定 `C-xxx`，不与 `K-xx` 混用；`knowledge_ids` 必须存在；`material_id` 必须存在 |
| 边 | `edge_id / source_node_id / target_node_id / relation_type / source_reference / rationale / review_status / evidence_level / created_version? / updated_version?` | `edge_id` 固定 `GE-nnnn`、不复用；端点可为 `C-xxx` 或 `K-xx`；来源与理由必填 |

| `relation_type` | 方向 | 含义 | 可否排序 |
|---|---|---|---|
| `prerequisite` | 有向 | source 是 target 的先修 | 仅 `reviewed` |
| `confusable_with` | 对称 | 容易混用，适合对比辨析 | 否 |
| `related_to` | 对称 | 可对照/相关，**不是先修、不是因果** | 否 |

对称关系按 `source_node_id < target_node_id` 规范化**存储一次**；读取方双向解释。重复反向边、重复边、自环、悬空端点、先修环都会被拒绝（错误信息给出环路径或重复边 ID）。

**审核状态**

`draft`（人工整理未复核，当前 18 条全部为 draft）/ `needs_revision` / `rejected` / `reviewed`。

- 未审核的先修关系**不得**用于排序或阻断；建议里写入 `prerequisite_check.draft_edges` 与 `note`“关系待核验”。
- `validation`：`plan[].prerequisite_check.reviewed_edges` 必须是 `reviewed`；`draft_edges` 必须非 `reviewed`；`missing_knowledge_ids` / `pending_knowledge_ids` 必须由 reviewed 先修边支撑。
- 人工复核走既有本机标注机制（`--curation`）：只允许改审核状态、出处、理由、证据等级与版本，**不能改端点或类型**；标记 `reviewed` 必须有可核对出处（`manual_unsourced` 不行）。五张表哈希变化时拒绝套用。

**进入决策**

- 先修：`reviewed` 且目标知识点薄弱 → 先安排先修巩固；`insufficient_evidence` → 先补观测，**不判薄弱**；已掌握 → 不重复安排。
- 预算仍是每人 3 项；因先修或预算被挤出的 issue 写入 `recommendation.deferred[]` 并给理由。
- 易混：优先使用同时映射到两个知识点的材料（`shared_materials`）做对比；没有材料时只给“教师补充观察”提示，**不虚构对比题**，也**不据此判定学生混淆**。
- 图谱缺失（旧底座）：`catalog.graph = null`，建议退回 v0.6 行为（`satisfied=true`、无关系提示）。

**版本与下游**

图谱内容在 `knowledge_base.json` 内，任一关系或版本变化都会改变知识底座哈希；`recommend/run_manifest.json` 记录该哈希，旧画像是旧版本，不会被静默复用。

**明确不做**：不从诊断数据自动生成先修/易混关系；不把 `related_to` 当先修；不把 `confusable_with` 当学生混淆的证据；不手改端点“修复”关系。

---

## 12. v0.9：学习路径与主动补充观测（方向三）

目标：把“若干材料”升级为**有依赖、有完成条件、可调整、可追溯版本**的学习路径；补充观测（probe）的选择从“材料编号前 3 个”升级为可解释的启发式评分。

**计划项（`recommendation.plan[]`）**

| 字段 | 说明 |
|---|---|
| `plan_item_id` | `PL-<学生三位>-<节点>-v<版本>-<知识点两位>`；同一版本内稳定、不重复 |
| `plan_version` | 该计划项所属版本（与顶层一致；历史项保留旧版本） |
| `status` | `planned` / `in_progress`（`completed` 只出现在 `history`） |
| `prerequisite_item_ids` | 必须先于本项完成的计划项 ID；只能指向**更早**的项 |
| `prerequisite_knowledge_ids` | 先修知识（reviewed 边缺失/待补观测 + 已排在更早位置的先修） |
| `completion_condition` | 结构化完成条件：`probe_evidence`（`min_graded`）或 `full_credit`（`min_full_credit` + 可选 `criterion`） |

顶层：`plan_id`（`PLAN-<学生三位>-<节点>-v<版本>`）、`plan_version`、`history[]`（已完成快照，不计入本轮预算）、`plan_diff`（上一版与本版的增/删/保留/完成及原因）、`progress`（应用事件数、完成/进行中、未匹配数）。

**规划规则（确定性）**

问题选择与排序沿用 v0.8：先排除无材料/不适用；证据不足→补观测；薄弱→巩固；reviewed 先修薄弱/证据不足→先补先修或观测；已掌握先修不重复；易混只用 reviewed + 共享材料做对比；预算 3 项，超出写 `deferred`。`plan_item_id` 与 `prerequisite_item_ids` 由最终顺序生成。

**补充观测评分（`probe_plan.scoring`，`probe-heuristic-1`）**

候选必须：本节点可用、`assessment`、映射到该知识点、**未作答、非 pending、未评分、非存疑**。分量：`issue_relevance`、`coverage_gain`、`prerequisite_value`、`material_quality`、`redundancy_penalty`（负值）。`total = Σ weight × component`，权重写入 `probe_plan.scoring.weights` 与 `run_manifest.policy.probe_weights`；报告里列出候选分量，可逐项复算。

**这是规则启发式，不是测量学信息量**：官方没有难度、区分度或响应模型，禁止声称 IRT/信息函数；没有数据的分量按 0 处理，不伪造。

**进度事件（`path_event.jsonl`，本机、追加式、Git 忽略）**

- 位置：`data/progress/<dataset>/events.jsonl`；一行一个事件，字段见 `schemas/output/path_event.schema.json`。
- `started`：该项保留为 `in_progress`，不重新规划；`completed`：进入 `history`，其知识点不再参与本轮新计划。
- 事件**不携带分数**，不改变诊断、掌握度或历史成绩；`completed` 只表示“执行完成”，不代表答对或掌握。
- 预算只计当前活动项（`planned`+`in_progress`）；已完成项进 `history`，不计入 3 项上限。
- 版本：无变化保持不变；有新增/完成/内容变化时 `plan_version + 1`，`plan_diff` 记录旧版本、原因与差异。旧计划与历史不被静默删除。

**边界**：方向三只处理“执行进度”，不把新作答写入诊断；带评分的新证据、教师评阅与重新诊断由方向五的 `feedback_event` 账本实现（见 §13）。`recommend --progress <file>` 可指定事件文件；默认读 `data/progress/<dataset>/events.jsonl`（不存在则忽略）。

**明确不做**：不按题号先后当作信息量；不让 LLM 决定题目或顺序；不虚构完成条件；不因“完成活动”推断掌握。

---

## 13. v0.10：教学反馈与补充证据闭环（方向五）

目标：让“教师调整、学生反馈、补充作答”进入同一条可追溯链路，同时保证**官方分数、canonical 和历史结论不被改写**。

**事件账本（`feedback_event.jsonl`，本机、追加式、Git 忽略）**

- 位置：`data/feedback/<dataset>/events.jsonl`；一行一个事件，字段见 `schemas/output/feedback_event.schema.json`。
- 四种事件：
  - `supplemental_attempt`：补充作答（学生/本机录入），带 `material_id`、`score`、`max_score`、可选 `rubric_points`；
  - `teacher_adjustment`：教师调整计划项（`lock`/`unlock`/`remove`/`restore`/`replace_materials`/`set_time`/`set_difficulty`），必须带理由；`lock`/`remove` 还要带计划项快照；
  - `teacher_comment`：教师评语，只展示，不改分数或计划；
  - `student_feedback`：学生反馈（`difficulty`/`confusion`/`request`/`other`，可带 1–5 评分与文本），只展示。
- `actor` 区分 `teacher` / `student`；`source` 记录本机来源。没有认证，只允许本机演示使用。

**补充证据 → 派生诊断**

- 补充作答转成独立记录 `EV-...`（`source=supplemental`），写入本次 run 的 `supplemental_input.json`；`diagnosis_input.json` 仍是 canonical 快照，官方分数与质量报告不变。
- 派生 run 用 canonical + 补充记录计算画像/班级/质量复算；`verify-run` 读取 `supplemental_input.json` 复算，manifest 的 `supplemental` 与 `auxiliary_files` 绑定哈希。
- 可选 `--previous <run>` 输出 `diagnosis_diff.json`：逐学生列出状态变化、mastery 变化、issue 增删；`supplemental_events` 记录来源。
- 补充证据没有人工复核状态；不得把它当作官方成绩，报告中必须标注“派生/本机补充”。

**教师调整 → 计划重放**

- 事件按 `(created_at, event_id)` 重放；同一计划项以最新 `lock`/`unlock`/`remove`/`restore` 决定状态，`replace_materials`/`set_time`/`set_difficulty` 取最新值。
- 锁定项在重排时保留原 `plan_item_id`/材料，并计入 3 项预算；移除项不进入计划，写入 `deferred` 并注明“教师移除”；`restore` 可逆。
- 调整按 `issue_id` 回退匹配：计划版本升级导致 `plan_item_id` 变化时，仍能应用到同一知识点的当前项；旧事件保留在 `adjustments` 中。
- 教师调整只改计划字段，不改诊断、掌握度或官方分数；`recommendation.feedback` 记录应用数、未匹配项与来源。

**前端接口**

- `POST /api/feedback`（仅回环地址、同源 JSON、`X-KnowFlow-Feedback: 1`）：教师调整/评语、学生反馈、补充作答；写账本后重建本机快照。
- 教师端“教学调整与反馈闭环”面板；学生端计划卡“太难/没看懂/需要更多例题”反馈按钮；计划卡展示锁定、调整理由、教师评语。
- 注意：这是**单机演示**，没有账号、权限与并发控制；“教师/学生”角色只是页面视角，不是安全边界。

**明确不做**：不把补充证据写进 canonical；不让教师调整改分数；不因教师评语推断掌握；不把本机事件当正式成绩或对外提交材料。

---

## 14. 变更记录

| 版本 | 变更 | 兼容性 |
|---|---|---|
| **v0.10** | 新增 `feedback_event.jsonl` 契约与 `data/feedback`（本机）；补充作答派生 `EV-...` 证据、`supplemental_input.json`、`diagnosis_diff.json`；建议新增 `feedback`/`teacher_locked`/`adjustments`/`teacher_comments`/`student_feedback`；`/api/feedback` 与教师/学生反馈界面 | **minor（输出/本机）**：canonical 不变；输出只加可选字段与两个本机文件；EV 记录 ID 扩展了画像/建议的 record_id 模式 |
| **v0.9** | `recommendation` 加 `plan_id/plan_version/history/plan_diff/progress`、`plan[].plan_item_id/plan_version/status/prerequisite_item_ids/prerequisite_knowledge_ids/completion_condition`、`probe_plan.scoring`；新增 `path_event.jsonl` 契约；`recommend --progress/--previous`、`path-event` 命令 | **minor（输出）**：只加可选字段与一个新事件表；无字段删除；旧建议仍可校验 |
| **v0.8** | 新增 `curriculum_graph.json`（21 节点 / 18 关系，含 `edge_id`、类型、来源、理由、审核状态）；`knowledge_base.json` 加可选 `curriculum_graph`；`recommendation.json` 的 `prerequisite_check` 加 `pending_knowledge_ids/reviewed_edges/draft_edges/note`、`plan[].relation_notes`、顶层 `deferred`；新增 `knowledge --graph` 与 curation 的图谱复核补丁 | **minor（输出）**：只加可选字段与一个新资产；无字段删除；旧底座（无图谱）行为不变，旧产物仍可校验 |
| **v0.7** | 新增 `review_report.json`（存疑评分候选 + 人工结论，`x-primary-key=record_id`）；`student_profile.knowledge_states[].review`、`issues[].disputed_rubric_evidence`；`recommendation.review_context` / `review_required` / `plan[].basis_records` / `plan[].review_flags`；诊断新增 `--review-policy official|exclude_flagged` | **minor（输出）**：只加可选字段与一个新产物；无字段删除、无既有取值语义变更；旧画像/旧建议仍可通过 schema 与 `verify-run`/`verify-recommend` |
| **v0.6** | 任务3建议层输出契约：`recommendation.json` 加可选 `node_id`、`plan[].activity_type`；明确 `issue_id`/材料/`check`/`probe_plan` 的约束与 `difficulty`/`est_minutes` 的启发式口径；`validation_report.json` 加可选 `errors`/`policy_version` | **minor（输出）**：只加可选字段，无字段删除、无既有取值语义变更；任务2 产物不受影响 |
| **v0.5** | 诊断层输出契约：个人/群体画像加 `node_id`、`scope_known`、Beta 统计（区间/两侧概率）、`applicable_items`、`status_reason`、`performance`、`rubric_evidence`、`rubric_patterns`；`status` 加 `mixed_performance`/`not_applicable`，`issue_type` 加 `performance_gap`/`score_point_gap`；`issue_id` 第二段改为知识点序号（跨节点稳定）；质量报告加逐行 `decisions` 等可选字段与三条不变式 | **minor（输出）**：无字段删除、无既有取值语义变更；输入表 canonical 仍 `0.4.0`，`records.csv` 不变。消费方需显式处理新增状态/类型与可空 `ratio` |
| **v0.4** | 新增证据层 `record_details.csv`（原文零加工 + `csv_record_number` 回查 + `kept` 标记被替代的修订）；`records` 字段不变，仍为分析层；写盘改为临时文件 + 原子替换；适配错误信息不再回显单元格原文；五态记账下沉到 `src/knowflow/cleaning/states.py` | **minor**：只新增表，无字段删除、无既有取值语义变更；消费方只读 `records` 的无需改动 |
| **v0.3** | 新增 `nodes.csv` 与 `records.node_id`；`records` 增 `rubric_scores_json`/`steps_json`，`materials` 增 `item_format`/`explanation`/`rubric_json`；`materials.objective_id`、`materials.difficulty`、`qmatrix.difficulty` 允许 `null`；去重改为节点内；§5.3 明确 applicable 数据源；§7 增 ID 映射附录 | **minor**：只加可选字段/新增表/放宽 required；无字段删除、无已有取值语义变更；消费方需处理 `null` |
| **v0.2** | 新增 `pending` 态；`state_counts` / `records_by_state` 增加 `pending` 记账字段（必填）；明确 `assigned` / `attempted` 判定与 `applicable` 口径；§7 四项结案；新增两条不变式 | **minor**：无字段删除、无既有取值语义变更；M0 阶段无生产方与历史产物 |
| v0.1 | 初版 | — |
