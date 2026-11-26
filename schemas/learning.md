# 学习空间契约 v1

学生端新增学习卡、两题补测、题库练习、AI 变式、错题集和收藏夹。学习记录独立
保存于 `data/learning/<dataset>/<student>.json`（Git 忽略），不改 canonical、正式
诊断阈值和原始成绩。学习卡按 `node_id + knowledge_id` 隔离；错题和收藏属于学生。

`GET /api/learning?student_id=&node_id=` 返回 cards、mistakes、favorites 和 AI 就绪状态。
所有写请求使用 `X-KnowFlow-Learning: 1`，学生只能操作登录账号自己的记录。
`POST /api/learning/{start,read,answer,generate,favorite,question}` 统一携带 student_id、node_id。
start/read/generate 另带 knowledge_id；answer 带 question_id、answer、request_id，
可带 probe_id；favorite 带 question_id、favorite（布尔值）。question 只读取本人题目。

题目由服务端分配 question_id；包含 knowledge_id、prompt、options、source、material_id。
未提交时不返回 answer/explanation。提交后的本机反馈返回 correct（true/false/null）、
参考答案和解析；null 表示无法可靠自动判分，不计为错误或已掌握。答案通过后端评分，
不信任前端传入的分数。重复 request_id 不产生第二条记录。

未覆盖/待观察卡先发两道程序校验的选择题（各 1 分），不是官方新考试；只有首次
独立完成两题才形成 probe_result。0/2 或 1/2 为 needs_practice，2/2 为 ready。
空白不计零；查看解析后重做仅用于练习，不覆盖补测首次结果。低分转为知识学习卡；
高分转为巩固/进阶卡。该标签明确为本次补测，不宣称长期掌握。

AI 生成只接收知识名称、教学概要、练习难度和已生成题面去重信息，不发送学生 ID、
原始作答、个人信息、官方原始题面。模型返回 2 道四选一题及答案解析；再用独立请求
（不带候选答案）核对。格式/答案不一致则明确报错，不伪装成本地模板成功。
独立复核仍是模型复核，页面标明 AI 来源和疑问可反馈，不自动改变正式学情。

题库原题按 Q-matrix 关联并保留出处。历史有分数的失分题进入错题集；新增判错题追加，
重做成功标记订正但保留历史。查看解析后本轮不计为独立正确。收藏及作答刷新后保留。
