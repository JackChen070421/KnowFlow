# schemas/ · 机器契约（第 1 层）

> 最后更新：2026-11-10
> 字段/枚举速查：[`CONTRACT.md`](CONTRACT.md)。**先改 schema，再改代码。**

---

## 1. 目录

```text
schemas/
├─ CONTRACT.md              # 人读速查：ID/枚举/CSV 列/缺失语义
├─ input/                   # canonical CSV 的一行
│  ├─ objectives / knowledge / materials / qmatrix
│  ├─ edges / students / records / tasks
├─ output/                  # 整份 JSON
│  ├─ knowledge_base / data_quality_report
│  ├─ student_profile / class_profile
│  └─ recommendation / validation_report
└─ llm/
   ├─ llm_summary           # 唯一允许进 LLM 的对象
   └─ llm_response          # LLM 输出
```

- `input/diagnosis_input.schema.json`校验整个任务2输入包；其他 `input/*` 校验 CSV 的**一行**；整表还要查主键/外键。
- `output/*` 校验整份 JSON；`knowledge_base` 通过 `$ref` 复用 `input/*`。
- `llm/*` 是边界契约：只有 `llm_summary` 可以进模型。

---

## 2. 约定

| 项 | 约定 |
|---|---|
| JSON Schema | draft 2020-12 |
| `$id` | `https://knowflow.local/schemas/<path>`，全局唯一 |
| 根类型 | `object`；`additionalProperties: false` |
| 可空 | `["string","null"]`，不要用 `0`/`false`/`""` 冒充“不知道” |
| 主键 | `x-primary-key`；整表校验时查唯一 |
| 日期 | ISO 8601 带时区 |
| 数值 | mastery/ratio 0–1；difficulty 1–5；est_minutes 1–120 |

---

## 3. 怎么校验

```powershell
# 单个 JSON
python scripts/validate_outputs.py `
  --schema schemas/output/student_profile.schema.json `
  --data tests/fixtures/student_profile.min.json

# 仓库结构 + schema + 隐私
python scripts/check_contracts.py

# 合成 CSV 行级校验
python scripts/check_examples.py
```

Python 里：

```python
from pathlib import Path
from knowflow.contracts import validate_instance

errors = validate_instance(
    Path("schemas/output/recommendation.schema.json"),
    Path("tests/fixtures/recommendation.min.json"),
)
assert errors == [], errors
```

---

## 4. 变更规则

1. 改 schema + [`CONTRACT.md`](CONTRACT.md) + fixtures。
2. 跑 `check_contracts` + `check_examples` + `pytest`。
3. PR 写清：为什么改、谁消费、旧产物是否兼容。
4. 删字段/改语义/改枚举 = **major**；加可选字段/加枚举值 = **minor**；只改描述 = patch。
5. 不兼容时保留旧 schema 一个版本 + 迁移脚本。

---

## 5. 常见问题

### v0.3诊断结果怎样验证？

`python -m knowflow verify-run --run artifacts/run/<运行目录>` 会核对结果文件哈希、完整输出集合、Schema、引用、五态计数、覆盖率、Beta结果、评分点与班级汇总。它只覆盖任务2，不代表任务3约束或赛事提交审核通过。

新增 `mixed_performance`、`not_applicable`、`performance_gap`、`score_point_gap`，覆盖率和班级覆盖均值可能为null。v0.3输出通过条件Schema要求新字段；消费者需按 `CONTRACT.md` §8 更新。

### 为什么 `state_counts` 里一定有 `pending`？

官方数据有“待评分”记录：学生交了、老师没给分。它既不是对也不是错，所以既不能进 `observed_*`，也不能丢进 `unobserved`。`pending` 让这类记录**被显式记账**，诊断层据此既不算 n、也不判错，只是把它计入覆盖度缺口。

### 为什么 `mastery` 允许 `null`？

无观测不能写 0。`null` 表达“不知道”，对应 `insufficient_evidence`；这是“缺少记录不等于未掌握”的字段级体现。

### 为什么 `knowledge_base` 用 `$ref`？

避免两套字段定义。`input/*` 是行定义，`knowledge_base` 只是打包。

### 为什么 LLM 输出要 `numbers_used`？

数字锁。输出数字必须来自 `llm_summary.allowed_numbers`；文本里的数字也要检查。防止模型做算术或编造统计量。

### 新增输出字段要改哪些？

`schemas/output/*` → `CONTRACT.md` → fixtures → 生产代码 → validator → 消费方。顺序不能反。

---

## 6. 禁止

- ❌ 实现里加字段但 schema 不更新。
- ❌ 用 `null` 之外的默认值表示“没有观测”。
- ❌ 复用 `$id`。
- ❌ 把真实数据写进 `examples/` 或 `tests/fixtures/`。
- ❌ 用 `additionalProperties: true` 绕过契约。
