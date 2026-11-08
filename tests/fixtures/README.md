# tests/fixtures · 契约样例

> 最后更新：2026-11-08

这里的 JSON 是**手写的合成样例**，用来验证 schema 和字段是否能对上，**不是真实学情数据**，也不是算法跑出来的结果。

- `student_profile.min.json`：个体画像正例
- `recommendation.min.json`：建议正例
- `knowledge_base.min.json`：知识底座 `$ref` 正例
- `llm_summary.min.json`：LLM 输入正例
- `llm_response.min.json`：LLM 输出正例

用途：

```powershell
python scripts/validate_outputs.py `
  --schema schemas/output/student_profile.schema.json `
  --data tests/fixtures/student_profile.min.json
```

规则：

- **永远不要**把真实数据放进 `tests/fixtures/`。
- 真实原始数据放 `data/raw/<dataset_id>/`；canonical 放 `data/interim/<dataset_id>/`；两者都不进 Git。
- 改 schema 后同步改 fixture，并跑 `pytest`。
