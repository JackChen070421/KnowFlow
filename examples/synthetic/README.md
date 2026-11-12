# synthetic · 七年级数学小样例

> 最后更新：2026-11-10
> **全部为自行构造的合成数据，不含任何真实学生/学校/教材内容。**
> 用途：跑通三任务、契约测试、5 分钟演示；不是官方数据，不代表真实分布。

---

## 1. 故事

一个班（G2/G3）刚学完“一元一次方程”。学生 S012 在含负数移项上连续出错；S013 表现稳定；S021 记录很少，不能下结论。

这组CSV覆盖五态中的四态；待评分及异常修订等场景由 `tests/diagnosis/` 的独立合成数据覆盖。以下状态已按v0.3保守阈值更新：

| 学生 | 知识点 | 记录 | 五态 | 预期诊断 |
|---|---|---|---|---|
| S012 | K-07 移项与符号 | M-027 错、M-045 错、M-050 错 | 3 × `observed_wrong` | n=3, k=0 → mastery 0.20, `likely_weak` |
| S012 | K-08 合并同类项 | M-031 对 | 1 × `observed_correct` | n=1, k=1 → mastery 0.6667, `insufficient_evidence` |
| S012 | K-07 | M-041 已布置未作答 | `assigned_not_attempted` | 不计入 n，单独统计 |
| S012 | K-06 等式性质 | 当前任务范围无可测题 | 无适用材料 | `mastery=null`；本范围不适用，不能判断未掌握 |
| S013 | K-07 | M-027/M-045/M-050 全对 | 3 × `observed_correct` | n=3, k=3 → mastery 0.80, `likely_mastered` |
| S013 | K-08 | M-031 对 | 1 × `observed_correct` | n=1 → `insufficient_evidence` |
| S021 | K-07 | M-027 错、M-045 错、M-050 未作答 | 2 × `observed_wrong` + 1 × `assigned_not_attempted` | n=2 < 3 → `insufficient_evidence`（**不**判 confirmed_weak） |
| S021 | K-08 | M-031 错 | 1 × `observed_wrong` | n=1 → `insufficient_evidence` |

**关键演示点**：S021 有 2 次错误，但 n<3，系统仍然说“证据不足”，而不是“已确认薄弱”。这就是“缺少记录不等于未掌握”的反向版本：**证据不够，不下结论。**

---

## 2. 覆盖度

任务T1列出6份材料：`M-021/M-027/M-045/M-041/M-050/M-031`。其中M-021是讲解材料；测量覆盖率只使用其余5份可评分题目。

| 学生 | 已作答 | 已布置未作答 | 无记录 | 覆盖率 |
|---|---|---|---|---|
| S012 | 4（M-027/M-045/M-050/M-031） | 1（M-041） | 0 | 4/5 = 0.8 |
| S013 | 4（M-027/M-045/M-050/M-031） | 0 | 1（M-041） | 4/5 = 0.8 |
| S021 | 3（M-027/M-045/M-031） | 1（M-050） | 1（M-041） | 3/5 = 0.6 |

> `M-030`（讲解）与 `M-032`（探测）不在T1范围。任务范围中的讲解材料不进入测量分母。正式数据的分母按测验节点可用题目与已教主题交集计算，不能直接套用本旧样例的任务范围。

---

## 3. 文件

```text
input/
├─ objectives.csv   2 条课标（OBJ-7M-01 / OBJ-7M-03）
├─ knowledge.csv    4 个知识点（K-01 / K-06 / K-07 / K-08）
├─ materials.csv    13 份材料（reference/explain/practice/assessment/probe）
├─ qmatrix.csv      11 条材料×知识点
├─ edges.csv        8 条关系（contains/prerequisite/confusable）
├─ students.csv     3 名学生（S012/S013/S021）
├─ records.csv      13 条记录（含 2 条未作答）
└─ tasks.csv        2 个任务（T1 个体 / T2 班级）
```

关系图：

```text
OBJ-7M-03
├─ contains → K-06 等式性质
│              ├─ prerequisite → K-07 移项与符号
│              └─ prerequisite → K-08 合并同类项
├─ contains → K-07
└─ contains → K-08
K-07 ↔ confusable ↔ K-08
```

---

## 4. 怎么用

1. **契约测试**：用 `schemas/input/*.schema.json` 逐行校验。
2. **算法开发**：这8张表用于格式/字段演示；完整任务2回归使用 `tests/diagnosis/` 动态生成的纯合成官方格式数据，覆盖两个节点、修订、待评分和部分得分。
3. **演示**：5 分钟视频/答辩用 S012 讲“问题→材料→检查→依据”；用 S021 讲“证据不足不乱判”。
4. **回归**：改算法后重跑，对比 `student_profile.json` 的 `state_counts/mastery/status`。

> 手写JSON只用于格式示例；计算测试独立核对统计量。records.csv新增的N01与事件ID为合成上下文，不代表正式测验；score_points为空列表，因为本旧样例没有分点评分。

---

## 5. 不包含什么

- 不含真实学生姓名/学号/成绩；
- 不含教材原文/图片；
- 不含 60 道完整题量（只有 13 份材料，用于契约/流程）；
- 不含独立评测数据（评测集单独管理，不进仓库）。
