# data/ · 本机数据（第 2 层，默认不入库）

> 最后更新：2026-11-09
> **这里的数据不进 Git、不进 LLM、不进公开仓库。**
> 仓库只保留目录与 `.gitkeep`；`data/raw/official-v1/` 下有本机的官方资料包副本，被 Git 忽略。

---

## 0. 当前数据集（`official-v1`）

官方资料包已原样落地：`data/raw/official-v1/`，**21 个文件 / 73.0 MB**，目录结构与文件名均未修改，内容逐文件哈希比对一致。

> ⚠️ **`git pull` 不会带来数据。** 本目录被 `.gitignore` 忽略，组员拉下来只有 `README.md` 和两个 `.gitkeep`。要重建这个结构，必须用下面的命令，而不是靠拷贝别人的仓库。

**复现（每台新机器跑一次）：**

```powershell
# 1) 从赛题组统一渠道拿到 赛题资料包，解压到任意路径
# 2) 落地 + 生成指纹（本机 manifest 进 gitignore，不进库）
python scripts/ingest_raw.py --source "D:\赛题数据"
# 3) 自检：默认对照已入库的 data/manifests/official-v1.structure.json
python scripts/ingest_raw.py --check
# 4) 确认没有进库
python scripts/check_contracts.py
```

期望输出：

```text
INGEST OK dataset_id=official-v1 files=21 bytes=76518706
CHECK OK dataset_id=official-v1 files=21 bytes=76518706
  compared against ...\data\manifests\official-v1.structure.json
```

**两个文件，别搞混：**

| 文件 | 入库？ | 用途 |
|---|---|---|
| `data/manifests/official-v1.structure.json` | ✅ **入库** | 纯指纹（路径 + `sha256` + 字节数 + 行数），**无任何数据内容**。第 3 步的基准：组员不用交换文件，就能知道自己的数据是否与主仓**字节一致** |
| `data/raw/official-v1/manifest.json` | ❌ 不入库 | 本机落地产物，多带 `received_at`/来源等易变字段，只用于自己复查 |

> 为什么 `data/manifests/` 可以入库而 `data/raw/` 不行：前者只有哈希与计数，泄露不了内容；后者是**材料本身**。`.gitignore` 里为此开了一条精确例外 `!data/manifests/*.structure.json`，`data/raw/**` 依然全封闭。

**官方材料换版本时**（赛方更新了包）：`python scripts/ingest_raw.py --source "<新路径>" --force --export-structure` 重新钉住指纹，并在 PR 说明变了几行、为什么。**不要**为了过检查去手改这份清单——`pytest` 里有针对 21 个文件、806 行记录的锁定断言。

如果只想临时对照别人的一份：

```powershell
python scripts/ingest_raw.py --check --expected "D:\收到的\manifest.json"
```

| 内容 | 文件 | 说明 |
|---|---|---|
| 赛题规则 | `1_赛题规则.pdf`（9 页） | 三项任务与评分标准 |
| 说明文档 | `2_参赛说明.docx`、`3_典型案例说明.docx`、`4_赛题数据/赛题数据说明.docx` | 任务口径、案例要求、数据性质 |
| 学情数据 CSV | `4_赛题数据/模拟学情数据/*.csv`（6 个） | 40 学生 / 806 记录 / 54 题 / 2 节点 |
| 学情数据 Excel | `4_赛题数据/模拟学情数据索引.xlsx` | 与 CSV 逐格一致的镜像，另含 `数据说明` sheet |
| 课程标准 | `5_课程标准及相关教学资源/课程标准_2022.pdf`（189 页） | **纯扫描件、无文本层，知识层需 OCR** |
| 教材切片 | `5_课程标准及相关教学资源/B01–B08_相关资料切片.pdf` | 有文本层；B02/B05/B06 对应 T03/T01/T02，其余 5 份为干扰项 |
| 清单（入库） | `data/manifests/official-v1.structure.json` | 纯指纹：每文件 `sha256`、字节数、CSV 行数、XLSX sheet 数 |
| 清单（本机） | `data/raw/official-v1/manifest.json` | 同上 + `received_at`/来源；不进库 |

确认这些文件不会被提交（应全部显示 `IGNORED`，且 `git status` 为空）：

```powershell
git check-ignore -v data/raw/official-v1/manifest.json
git check-ignore -v data/raw/official-v1/4_赛题数据/模拟学情数据/作答记录.csv
git status --porcelain
```

> 数据处理的完整规则、例子与赛题对照见本机 `data/README-processing.md`（已列入 `.gitignore`，不随公开仓外传）；每次运行的异常与处置以 `data/interim/<dataset_id>/data_quality_report.json` 为准（本机生成）。**仓库内不放审计报告与原始数据。**

---

## 0.1 数据处理（本机，official-v1）

```powershell
python scripts/ingest_raw.py --source "D:\competition\2026NOV\赛题数据"
python scripts/ingest_raw.py --check
python scripts/build_canonical.py --dataset-id official-v1
python scripts/validate_canonical.py --dataset-id official-v1
python scripts/export_digest.py --check
```

产物 `data/interim/official-v1/`：10 张 canonical CSV + `data_quality_report.json`（均 gitignore）。

### 0.2 队友复刻与互证

产物不入库，靠**同一条流水线重新算**；一致性靠两条指纹证明：

| 命令 | 证明什么 |
|---|---|
| `ingest_raw --check` | 我们拿到的是**同一份原始包**（21 文件 sha256 + 字节数 + 行数） |
| `validate_canonical` | 磁盘上的表 = 用这份 raw 重算的结果（逐字节比对，手改会被抓） |
| `export_digest --check` | **我算的和你算的一样**（每张表的行数 + sha256 + 聚合计数） |

`data/manifests/official-v1.expected.json` 只含行数、哈希和聚合计数，不含任何单元格内容，可以入库。两种指纹分工：

- `*.structure.json` 管**输入**（官方包指纹），
- `*.expected.json` 管**产物**（10 张表指纹）。

不一致时：输入指纹不对 → 数据包版本不同；产物指纹不对 → 代码/依赖版本不同，报错会点出是哪张表。

| 表 | 行数 | 说明 |
|---|---|---|
| `objectives.csv` | 3 | 课标条目 OBJ-7M-01..03 |
| `knowledge.csv` | 9 | 知识点 K-01..09 |
| `materials.csv` | 65 | 54 题 + 3 学习卡 + 8 教材切片 |
| `qmatrix.csv` | 63 | 54 题 + 3 卡 × 3 指标 |
| `edges.csv` | 9 | 课标 → 知识点 contains |
| `students.csv` | 40 | S001..S040，G1/G2 |
| `nodes.csv` | 2 | N01/N02，含可用题目与已教主题 |
| `records.csv` | 799 | **分析层**：806 条原始记录去掉 7 条旧修订版本 |
| `record_details.csv` | 806 | **证据层**：官方 CSV 一行一行，原文零加工 + 行号回查；7 条旧修订 `kept=false` |
| `tasks.csv` | 0 | 仅表头；任务由建议层定义 |

质量报告基线：`records_by_state = 405/385/4/5/0`、`duplicates_removed = 7`、`anomalies = 13`、`missing = 0/0/5`。

---

## 1. 目录

```text
data/
├─ raw/                        官方原始数据（只读；按 dataset_id 分子目录）
│  ├─ .gitkeep
│  └─ official-v1/             本机官方资料包副本（21 文件 / 73 MB，gitignore）
├─ manifests/                  ✅ 入库：纯指纹，无数据内容
│  ├─ official-v1.structure.json   输入指纹（21 个官方文件）
│  └─ official-v1.expected.json    产物指纹（10 张表的行数 + sha256）
├─ interim/                    canonical 中间表（适配层生成，gitignore）
│  ├─ .gitkeep
│  └─ official-v1/             10 张 CSV + data_quality_report.json
├─ README-processing.md        本机数据处理说明（gitignore，不随公开仓外传）
└─ README.md
```

- `raw/<dataset_id>/`：官方 CSV/JSON、数据字典、说明。
- `manifests/<dataset_id>.structure.json`：`sha256` + 字节数 + 行数，**允许入库**；是复现的判定基准。
- `interim/<dataset_id>/`：适配后的 canonical 表，字段见 [`../schemas/CONTRACT.md`](../schemas/CONTRACT.md)。
- 运行产物放 `artifacts/run/<run_id>/`（gitignore）；不放进 `data/`。

---

## 2. 硬规则

1. `data/raw/`、`data/interim/` 下任何文件不得 `git add`；`.gitignore` 已拦截，`check_contracts` 另用 `git check-ignore` 复核。**数据可以在本机，但不许进库。**
2. **唯一例外**是 `data/manifests/*.structure.json`：只有路径、`sha256`、字节数、行数，没有任何数据内容。不要往里塞別的东西（尤其是原始作答、题干全文）。
3. 不得把数据复制到 `examples/`、`tests/fixtures/`、仓库根、聊天记录、网盘或第三方 API。
4. 官方文件**原样放** `data/raw/<dataset_id>/`，不改名、不先手工改列名；映射由适配器负责。
5. 官方数据若含个人信息：**先脱敏再落盘**；原文件不放进仓库目录。
6. 赛后按赛题要求删除；删除前导出 manifest（文件名/哈希/行数），删除后写记录，不保留数据副本。
7. 公开仓的 `examples/` 与 `tests/fixtures/` 只放自行构造的合成样例。

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

本数据集已生成 `data/raw/official-v1/manifest.json`（21 个文件，含 `sha256` 与 6 个 CSV 的行数：806 / 42 / 40 / 2 / 9 / 65）。它同样被 `.gitignore` 忽略，**不要提交**。

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
