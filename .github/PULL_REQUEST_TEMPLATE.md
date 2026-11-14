# Pull Request

## 关联

- Issue：`KF-xxx`（或 `#123`）
- 角色：R?
- 分支：`feat/...`

## 改了什么

<!-- 一句话；列主要文件/模块 -->

## 为什么

<!-- 动机/问题；合约变更请说明兼容性 -->

## 怎么验证

```text
命令：
结果：
```

- [ ] `python scripts/check_contracts.py` 通过
- [ ] `python scripts/check_examples.py` 通过（如涉及 CSV）
- [ ] `python -m pytest` 通过
- [ ] 产物 `validate_outputs.py` 通过（如适用）
- [ ] 诊断产物 `python -m knowflow.cli verify-run` 通过（默认最近一次；也可 `--run <目录>`）
- [ ] 建议产物 `python -m knowflow.cli verify-recommend` 通过（默认最近一次；也可 `--run <目录>`）
- [ ] 新增/修改逻辑有测试或 fixture
- [ ] 已在 [`CHANGELOG.md`](../CHANGELOG.md) 顶部记一条（改了什么 / 验证 / 回退）

## 合约影响

- [ ] 未改 `schemas/` / 枚举 / ID 规则
- [ ] 改了：已更新 `schemas/CONTRACT.md` + fixtures，并说明消费方

## 数据与隐私

- [ ] 没有提交 `data/raw/`、`data/interim/`、真实 CSV、模型权重
- [ ] 没有提交 `.env`、API Key、密码
- [ ] 没有真实姓名/学号/联系方式
- [ ] 没有把设计文档/PDF/PPT/视频/真实结果包放进仓库
- [ ] LLM 输入只有 `llm_summary`（如涉及）

## 评审

- [ ] 作者不是唯一 reviewer
- [ ] 合约变更已由 R1 + R4 双审
- [ ] 已知限制/未验证项已写

## 备注

<!-- 风险、下一步 -->
