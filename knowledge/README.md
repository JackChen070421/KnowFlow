# knowledge/ · 正式课程图谱（可入库的教学资产）

> 最后更新：2026-11-16（契约 v0.8，方向二）
> 这里只放**人工整理的教学关系**，不含任何学生数据、作答或个人信息。

---

## 1. 文件

| 文件 | 作用 |
|---|---|
| `curriculum_graph.json` | 教材细目层图谱：21 个节点、18 条关系（16 先修 + 1 易混 + 1 相关） |
| `README.md` | 本说明 |

机器契约：[`../schemas/output/curriculum_graph.schema.json`](../schemas/output/curriculum_graph.schema.json)；

---

## 2. 为什么是独立文件

- 节点是**教材细目** `C-001…C-021`，知识点是 `K-01…K-09`，两套 ID 空间**不混用**；跨层关系用 `K-xx` 端点显式表达。
- 关系需要 `edge_id`、`source_reference`、`rationale`、`review_status`、`evidence_level`；这些字段不属于 canonical 的 `edges.csv`（后者是课标→知识点的包含关系）。
- 图谱变化必须让知识底座哈希变化，从而让下游产物失效：构建时整份图谱写进 `knowledge_base.json`，`recommend` 记录知识底座 sha256。

## 3. 关系语义（契约固定）

| 类型 | 方向 | 含义 | 可否用于排序 |
|---|---|---|---|
| `prerequisite` | 有向 | source 是 target 的先修（学 target 前需要 source） | **仅 `reviewed`** |
| `confusable_with` | 对称 | 两个知识点容易混用，适合对比辨析 | 否（只用于提示/材料检索） |
| `related_to` | 对称 | 可对照或相关，**不表示先修、不表示因果** | 否 |

对称关系按 `source_node_id < target_node_id` 规范化存储一次；读取方必须双向解释。重复的反向边会被校验拒绝。

## 4. 审核状态

- `draft`：人工整理但未复核（当前 18 条全部是 draft）。
- `needs_revision` / `rejected`：需修订 / 确认不成立。
- `reviewed`：已人工核对。**只有 reviewed 的先修关系参与计划排序**；draft 关系在建议里只显示“关系待核验”。

未审核关系不得在诊断或建议中被当成事实，也不得据此阻断学生学习。

## 5. 如何复核（本机、哈希绑定）

1. 构建带图谱的知识底座：

   ```powershell
   python -m knowflow.cli knowledge --dataset official-v1 `
     --graph knowledge/curriculum_graph.json
   ```

2. 新建/编辑本机标注文件（不进 Git），只允许改审核与出处字段，不能改端点或类型：

   ```json
   {
     "dataset_id": "official-v1",
     "source_sha256": { "objectives.csv": "…", "knowledge.csv": "…", "materials.csv": "…", "qmatrix.csv": "…", "edges.csv": "…" },
     "objectives": [],
     "knowledge": [],
     "edges": [],
     "curriculum_graph": {
       "version": "1.1.0",
       "edges": [
         {
           "edge_id": "GE-0005",
           "review_status": "reviewed",
           "evidence_level": "textbook_locator",
           "source_reference": "B05 §4.2 上册 97–102 页",
           "rationale": "整式加减以合并同类项为核心步骤。",
           "updated_version": "1.1.0"
         }
       ]
     }
   }
   ```

3. 带标注重建：`--curation <本机文件>`。`source_sha256` 与 canonical 五张表不一致时**拒绝套用**；标记 `reviewed` 时必须有可核对出处，不能停留在 `manual_unsourced`。

4. 复核后重新生成画像与建议；`run_manifest` / `recommend/run_manifest.json` 会记录知识底座哈希，旧产物不会静默复用。

## 6. 不做的事

- 不从诊断数据自动生成“易混关系”并写成事实；不把 `related_to` 当先修。
- 不因 `confusable_with` 直接判定某学生“混淆了这两个知识点”。
- 不手改 `edge_id` 或端点来“修复”一条关系；那是新版本 + 重新评审。
- 结构校验会报告孤立节点（当前 C-007、C-016 尚未整理出关系）与未复核关系数量；孤立节点是提示，不是错误，但补关系前不应用于任何结论。
