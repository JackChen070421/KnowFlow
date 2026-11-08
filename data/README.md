# data/ · 本机数据（第 2 层，默认不入库）

> 最后更新：2026-11-08
> **这里的数据不进 Git、不进 LLM、不进公开仓库。**
> 仓库只保留目录与 `.gitkeep`；真实数据只在本机受限目录。

---

## 1. 目录

```text
data/
├─ raw/          官方原始数据（只读；按 dataset_id 分子目录）
│  └─ .gitkeep
├─ interim/      canonical 中间表（适配层生成）
│  └─ .gitkeep
└─ README.md
```

- `raw/<dataset_id>/`：官方 CSV/JSON、数据字典、说明。
- `interim/<dataset_id>/`：适配后的 canonical 表，字段见 [`../schemas/CONTRACT.md`](../schemas/CONTRACT.md)。
- 运行产物放 `artifacts/run/<run_id>/`（gitignore）；不放进 `data/`。

---

## 2. 硬规则

1. `data/raw/`、`data/interim/` 下任何文件不得 `git add`；`.gitignore` 已拦截。
2. 不得把数据复制到 `examples/`、`tests/fixtures/`、仓库根、聊天记录、网盘或第三方 API。
3. 官方文件**原样放** `data/raw/<dataset_id>/`，不改名、不先手工改列名；映射由适配器负责。
4. 官方数据若含个人信息：**先脱敏再落盘**；原文件不放进仓库目录。
5. 赛后按赛题要求删除；删除前导出 manifest（文件名/哈希/行数），删除后写记录，不保留数据副本。
6. 公开仓的 `examples/` 与 `tests/fixtures/` 只放自行构造的合成样例。

---

## 3. 数据分级

| 级别 | 例子 | 入 Git | 入 LLM |
|---|---|---|---|
| 公开 | 合成样例 | ✅（仅 `examples/`） | ✅（合成） |
| 内部 | 自建知识底座、代码 | ✅ | 仅摘要 |
| 受限 | 官方课程材料、学情数据 | ❌ | ❌ |
| 机密 | 姓名/学号/联系方式、API Key | ❌ | ❌ |

---

## 4. 接入数据时的 manifest

每个数据集建一份 `manifest.json`（放 `data/raw/<dataset_id>/`，**不要提交**）：

```json
{
  "dataset_id": "dev-2026-11",
  "received_at": "2026-11-10T10:00:00+08:00",
  "source": "赛题组",
  "files": [
    {"path": "records.csv", "sha256": "...", "rows": 742}
  ],
  "data_dictionary_version": "v1",
  "notes": "仅本次大赛使用；赛后删除"
}
```

`data_quality_report.input_files` 会引用这些哈希；两者必须一致。

---

## 5. 赛后删除

1. 导出 `deletion_manifest.json`：数据集、文件列表、哈希、行数、删除时间、执行人。
2. 删除 `data/raw/<dataset_id>/`、`data/interim/<dataset_id>/`、`artifacts/` 相关产物。
3. 清理备份/网盘/聊天记录中的副本（如果有）。
4. 写 `deletion_record.md`：删了什么、怎么删、验证方式（路径不存在、哈希清单为空）。
5. **不要**把数据本身作为“证据”留在删除记录里；只留清单与哈希。

---

## 6. 常见问题

### 能不能把官方 CSV 放在 `examples/` 方便演示？

不能。`examples/` 只放自行构造的合成样例；官方数据一旦入库即构成“外传”。

### 能不能只提交“脱敏后”的记录？

需要团队/赛题组确认脱敏标准；默认不提交。公开仓只放合成样例。

### 删除后还要保留什么？

保留 manifest（文件名/哈希/行数）、删除记录、校验报告；不保留数据内容。
