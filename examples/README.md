# examples/ · 合成样例（支撑契约层/验证层）

> 最后更新：2026-11-08
> **这里只放自行构造、可公开的合成样例。真实学情数据一律不得进入本目录。**
> 真实数据规则见 [`../data/README.md`](../data/README.md) 与 [`../AGENT.md`](../AGENT.md) §10。

---

## 1. 为什么需要合成样例

1. **契约可验证**：在没有官方数据时，先证明字段/枚举/引用能跑通。
2. **多人可并行**：R1/R2/R3 用同一份样例对接，不互相等。
3. **可公开**：仓库/演示可以展示合成样例，不泄露真实数据。
4. **回归测试**：算法改动后，用同一份样例对比输出。

---

## 2. 当前样例

| 目录 | 内容 | 用途 |
|---|---|---|
| `synthetic/` | 七年级数学“一元一次方程”小样例：2 条课标、4 个知识点、13 份材料、3 名学生、13 条记录 | 跑通三任务、契约测试、演示 |

文件：

```text
examples/synthetic/input/
├─ objectives.csv
├─ knowledge.csv
├─ materials.csv
├─ qmatrix.csv
├─ edges.csv
├─ students.csv
├─ records.csv
└─ tasks.csv
```

详见 [`synthetic/README.md`](synthetic/README.md)。

---

## 3. 使用方式

```powershell
# 契约检查（不依赖数据）
python scripts/check_contracts.py

# 合成 CSV 行级校验
python scripts/check_examples.py

# 校验一个产物
python scripts/validate_outputs.py `
  --schema schemas/output/student_profile.schema.json `
  --data tests/fixtures/student_profile.min.json
```

> 当前 M0 只提供契约与 fixtures；完整管线在 M1–M3 落地，配置随代码一起加。

---

## 4. 新增合成样例的规则

1. 新建 `examples/<case-name>/`，不要覆盖 `synthetic/`。
2. 必须包含 8 张输入表；字段与 `schemas/input/*.schema.json` 一致。
3. 学生 ID 用 `Sxxx`，不得用真实姓名/学号；备注写“合成样例”。
4. 材料 ID 用 `M-xxx`，记录 ID 用 `R-xxxx`，知识点 `K-xx`。
5. 提供 `README.md`：故事、覆盖的知识点、四态分布、预期用途。
6. **不要**放真实数据、真实题目截图、真实学生作业。
7. 新增样例后跑 `check_contracts` + `check_examples` + `pytest`；必要时加 fixture。

---

## 5. 禁止

- ❌ 把官方数据改个名字放进 `examples/`。
- ❌ 用真实学生姓名/学号/成绩单。
- ❌ 用未授权的教材题目/图片。
- ❌ 为了让样例“好看”而伪造四态/掌握度；样例要能暴露边界（未作答、无记录、n<3）。
