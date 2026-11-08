# synthetic · 七年级数学小样例

> 最后更新：2026-11-08
> **全部为自行构造的合成数据，不含任何真实学生/学校/教材内容。**
> 用途：跑通三任务、契约测试、5 分钟演示；不是官方数据，不代表真实分布。

---

## 1. 故事

一个班（G2/G3）刚学完“一元一次方程”。学生 S012 在含负数移项上连续出错；S013 表现稳定；S021 记录很少，不能下结论。

样例故意覆盖四种证据状态：

| 学生 | 知识点 | 记录 | 四态 | 预期诊断 |
|---|---|---|---|---|
| S012 | K-07 移项与符号 | M-027 错、M-045 错、M-050 错 | 3 × `observed_wrong` | n=3, k=0 → mastery 0.20, `confirmed_weak` |
| S012 | K-08 合并同类项 | M-031 对 | 1 × `observed_correct` | n=1, k=1 → mastery 0.6667, `insufficient_evidence` |
| S012 | K-07 | M-041 已布置未作答 | `assigned_not_attempted` | 不计入 n，单独统计 |
| S012 | K-06 等式性质 | 无记录 | `unobserved` | `mastery=null`，需补充观测 |
| S013 | K-07 | M-027/M-045/M-050 全对 | 3 × `observed_correct` | n=3, k=3 → mastery 0.80, `confirmed_mastered` |
| S013 | K-08 | M-031 对 | 1 × `observed_correct` | n=1 → `insufficient_evidence` |
| S021 | K-07 | M-027 错、M-045 错、M-050 未作答 | 2 × `observed_wrong` + 1 × `assigned_not_attempted` | n=2 < 3 → `insufficient_evidence`（**不**判 confirmed_weak） |
| S021 | K-08 | M-031 错 | 1 × `observed_wrong` | n=1 → `insufficient_evidence` |

**关键演示点**：S021 有 2 次错误，但 n<3，系统仍然说“证据不足”，而不是“已确认薄弱”。这就是“缺少记录不等于未掌握”的反向版本：**证据不够，不下结论。**

---

## 2. 覆盖度

任务 T1 的材料范围是 6 份：`M-021/M-027/M-045/M-041/M-050/M-030`。

| 学生 | 已作答 | 已布置未作答 | 无记录 | 覆盖率 |
|---|---|---|---|---|
| S012 | 4（M-027/M-045/M-050/M-031） | 1（M-041） | 1（M-021） | 4/6 = 0.6667 |
| S013 | 4（M-027/M-045/M-050/M-031） | 0 | 2（M-021/M-041） | 4/6 = 0.6667 |
| S021 | 3（M-027/M-045/M-031） | 1（M-050） | 2（M-021/M-041） | 3/6 = 0.5 |

> `M-030`（讲解）与 `M-032`（探测）不在 T1 的 `material_scope_json` 里，只作为讲解/补测材料出现；覆盖度分母以 `tasks.material_scope_json` 为准。范围外材料若产生观测，要在质量报告中单独说明，不能悄悄扩大分母。

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
2. **算法开发**：M1–M3 用这份样例做 golden test；预期诊断见 §1。
3. **演示**：5 分钟视频/答辩用 S012 讲“问题→材料→检查→依据”；用 S021 讲“证据不足不乱判”。
4. **回归**：改算法后重跑，对比 `student_profile.json` 的 `state_counts/mastery/status`。

> 样例的预期值只用于回归，不是“标准答案”；官方数据到达后，以官方数据字典为准。

---

## 5. 不包含什么

- 不含真实学生姓名/学号/成绩；
- 不含教材原文/图片；
- 不含 60 道完整题量（只有 13 份材料，用于契约/流程）；
- 不含独立评测数据（评测集单独管理，不进仓库）。
