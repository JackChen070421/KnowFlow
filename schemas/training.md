# 本机变式训练契约 v1

`generator=demo` 请求仅允许 official-v1 的 unified 模式。产物增加
`generator=local_demo`、`title`、`note`、`student_count`、`basis`；basis 为各知识点的
`status_counts`、薄弱或不稳定人数 `focus_count` 和题数 `question_count`。
模拟题每题 `max_score=10`，不调用模型，不伪造学生作答，仍以 draft 保存待教师复核。

独立于 canonical 与正式诊断，存放在 Git 忽略的 `data/training/<dataset>/`。
试卷由 UUID `paper_id` 标识；包含 `mode`（personal/unified）、可空的
`student_id`、`node_id`、服务端选择的 `knowledge_ids`、`questions`、生成时间。
题目 `question_id` 由代码分配；模型仅生成 `prompt`、`answer`、`explanation` 和
白名单中的 `knowledge_id`。传给模型的内容仅为知识名称与汇总状态，不含学生 ID、
原始题目、作答或姓名。生成结果为待教师复核的练习，答案不发给学生。

扫描以 PDF/PNG/JPEG 上传，限制 12 MB，服务端解码校验后以 UUID `scan_id`
保存；必须关联已存在的试卷与学生，个人卷禁止关联其他学生。扫描只做本机存档，
不将原始扫描发给第三方。教师逐题核对并提交 [0,1] 的 `scores`，每题必填，
保存 `reviewed_by`、时间与评分；重复提交拒绝，空白不自动计零。
扫描上传后状态为 pending，复核后为 reviewed。新练习记录与原始成绩隔离，
按学生/测验/知识点返回评分数、平均得分率。它们是个人地图中的补充训练证据，
不冒充原始试题的作答，不自动覆盖正式 Beta 掌握度。

教师可通过 `POST /api/training/delete` 删除试卷（`paper_id`）。删除写入 `deleted_at`，保留本地历史文件；试卷及关联扫描从列表隐藏，禁止继续发布、上传、复核和生成 PDF。学生不可删除。
