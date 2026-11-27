"""The WebUI map the companion receives together with the learning fact card.

Why this module exists
----------------------
The chat model reads validated learner data but cannot see the browser.  Asked
"在哪看薄弱知识点", it used to answer from the data or invent a menu item instead
of pointing at 「班级学情」→「知识诊断」.  This module is the single place that says
what the shipped interface contains and how it is operated.

It is navigation help, not learner data: it carries no counts, no IDs of people
and no conclusions.  The companion may only use it to explain where to click.

Keeping it in sync
------------------
``tests/diagnosis/test_ui_guide.py`` compares every constant below with the real
labels in ``web/static/app.js``, ``learning.js`` and ``training.js``.  When a
page, tab or button is added, renamed or removed:

1. update the constants and the prose here;
2. run ``python -m pytest tests/diagnosis/test_ui_guide.py``;
3. bump :data:`UI_GUIDE_VERSION` and note the change in ``CHANGELOG.md``.

Owner: R3.
"""

from __future__ import annotations

UI_GUIDE_VERSION = "2026-11-27"

TEACHER_NAV = ("班级学情", "课程知识地图", "学生明细", "数据与证据")
STUDENT_NAV = ("学习总览", "我的知识地图", "学习空间", "跨域探索")

TEACHER_REPORTS = (
    "成绩分布",
    "作答与覆盖",
    "知识诊断",
    "主题与班级",
    "测验记录",
    "学生热力图",
)
PROFILE_TABS = ("表现分析", "知识明细", "作答明细", "作答与历史", "学习建议")
TEACHER_PROFILE_TABS = (*PROFILE_TABS, "教学反馈")

SETTINGS_TABS = ("个人信息", "教学与 AI", "显示", "数据分析")
STUDENT_SETTINGS_TABS = ("个人信息", "显示")
COURSE_TABS = ("知识地图", "课程要求", "材料出处")
LEARNING_TABS = ("学习卡", "错题集", "收藏夹")
EXPLORE_TABS = ("解析", "模型", "任务", "自检")
EXPLORE_LABS = (
    "数轴上的镜像",
    "活动预算的两个方案",
    "共享充电宝的计费拐点",
    "两个人的共同空闲",
)
EXPLORE_MORE = ("真实任务墙", "学科联动", "数学小史")
TRAINING_TABS = ("试卷管理", "扫描与复核")
THEMES = ("白天", "黑夜", "护眼")

#: Interface names that contain a numeral.  When the companion quotes one of
#: these exactly, the number is part of a name, not a count of learners; the chat
#: audit is told so (see ``audit._inside_name``).  Keep in sync with the labels
#: above — the drift test fails when a new numeric label is not listed here.
NUMERIC_LABELS = ("两个人的共同空闲",)

TEACHER_VIEWS = {
    "overview": "班级学情",
    "course": "课程知识地图",
    "students": "学生明细",
    "quality": "数据与证据",
    "reviews": "存疑证据",
    "settings": "设置",
}
STUDENT_VIEWS = {
    "overview": "学习总览",
    "course": "我的知识地图",
    "plan": "学习空间",
    "explore": "跨域探索",
    "settings": "设置",
}

_HEADER = """界面怎么用（KnowFlow 本机 WebUI 地图）
下面这份地图只用于回答“在哪里看、怎么操作”。它不是学情数据：不要据此推断班级情况，也不要把页面名称当成数据字段。
- 这是本机 WebUI：登录页用本机账号登录，教师与学生进入不同工作台；学生账号只看本人画像与班级聚合，看不到其他学生明细和教师设置。登录后左侧是主导航，左下角是「设置」与悬浮的「AI 学伴」按钮；右上角头像菜单有「查看个人信息」「退出登录」。"""

_TEACHER = """- 教师工作台左侧导航：班级学情、课程知识地图、学生明细、数据与证据；左下角另有「设置」。
  · 班级学情：顶部用「测验」「班级范围」筛选；页内子页入口是「成绩分布」「作答与覆盖」「知识诊断」「主题与班级」「测验记录」「学生热力图」，点击切换。图表右上角「统计说明」解释口径；热力图点色块查看某学生某知识点的证据，点学生编号打开画像。
  · 课程知识地图：顶部切「知识地图」「课程要求」「材料出处」。地图可搜索知识点、按类别筛选、切「知识图谱 / 一览表」、切「按章节分类 / 按逻辑」，用放大、缩小按钮和「查看全图」缩放；点节点打开讲解，里面能看课程要求、关联知识和「学情与材料」。
  · 学生明细：先出现学生列表，可搜索学生编号，按「全部学生」「建议巩固」「范围待确认」「有练习提交」筛选，按「学生 ID」「得分率从高到低」「覆盖率从低到高」排序，并翻页；点学生进画像，画像内切「表现分析」「知识明细」「作答明细」「作答与历史」「学习建议」「教学反馈」；右上「导出摘要」下载本机摘要，「返回学生列表」回列表，「学生视角」可切到学生页预览。
  · 数据与证据：折叠卡片默认收起，点标题展开审计、记录状态分布、判断边界、源文件指纹与质量发现；页底「存疑数据」卡片点「进入存疑证据」，在存疑证据页核对评分、看复核备注、导出审核清单。
  · 设置：分区是「个人信息」「教学与 AI」「显示」「数据分析」。「个人信息」改姓名、学期、任教信息与用户名，点「修改密码」弹窗；「教学与 AI」选建议语气、报告长度、数据不足时的动作，往下是「LLM 文字层」的启用开关、厂商、API Key、模型、Base URL，可点「测试连接」；「显示」选「白天」「黑夜」「护眼」主题、界面动效与默认首页；「数据分析」改覆盖与掌握阈值，保存后按新阈值重建。
  · 变式训练：教师页右上角「变式训练 · PDF 与扫描回录」打开工作区，顶部切「试卷管理」「扫描与复核」。「试卷管理」里选「个人针对性训练」或「统一知识点训练」、学生、题数，点「通过 API 生成」或「生成全体 Demo 卷」；核对后点「已核对题目答案，发布」；对已发布卷可「预览题卷」「答案与解析」。「扫描与复核」里上传拍照或 PDF，再逐题填得分比例，点「确认逐题评分并入库」。"""

_STUDENT = """- 学生页左侧导航：学习总览、我的知识地图、学习空间、跨域探索；左下角「设置」。
  · 学习总览：看本人得分率、评分覆盖、知识状态与学习建议；「学习建议」汇总本轮前三项优先安排，可展开看课程要求、推荐依据与原始作答；页内还可切「表现分析」「知识明细」「作答明细」「作答与历史」；右上「导出摘要」下载本机摘要。
  · 我的知识地图：和教师端同一张地图，点节点看课程要求、本人证据与材料；顶部可切「知识地图」「课程要求」「材料出处」。
  · 学习空间：分区是「学习卡」「错题集」「收藏夹」；学习卡按「理解知识」「题库练习」「AI 变式」推进，可收藏题目、重做错题；需要先补证据时会先做基线题。
  · 跨域探索：顶部选实验（数轴上的镜像、活动预算的两个方案、共享充电宝的计费拐点、两个人的共同空闲），实验下方展开「解析」「模型」「任务」「自检」；再往下是「真实任务墙」「学科联动」「数学小史」。
  · 设置：分区是「个人信息」「显示」。"""

_COMPANION = """- 你就在「AI 学伴」窗口里：左下角悬浮按钮打开，标题栏可拖动、边缘可缩放；输入框旁选「简洁」或「证据」；回答下方的「查看推理依据」可展开依据；生成失败时点「重试这次提问」。"""

_RULES = """- 指路时用页面名、分区名、控件名（用「」标出），说清“点哪里、下一步看什么”；按界面从上到下的顺序说，不要一次背出整个菜单。
- 不写网址、文件路径、代码或快捷键，也不要输出 Markdown；纯文本气泡里只给中文名称和操作顺序。
- 不报“有几个页面 / 几个分区 / 几个子页”这类数量；页面名以这份地图为准，地图里没有的按钮、菜单和功能就是不存在，不要编造，改用“以页面实际显示为准”。
- 你只能说明怎么操作，不能替对方点击、提交、生成试卷、改分数或保存设置；要动手的步骤明确说“由你在页面上完成”。
- 遇到“我找不到”时，先复述目标，再给最直接的页面、分区和按钮；仍然对不上就问对方当前在哪个页面、看到哪些按钮，不要猜。"""


def webui_guide(audience: str = "teacher", view: str | None = None) -> str:
    """Render the interface map for one reader.

    ``audience`` is ``teacher`` or ``student``; unknown values fall back to the
    student version so a missing viewer can never expose teacher-only tools.
    ``view`` is the page the browser is on (``overview``/``course``/…) and is
    only used for a one-line "you are here" hint; an unknown or foreign view is
    ignored rather than trusted.
    """

    teacher = audience == "teacher"
    views = TEACHER_VIEWS if teacher else STUDENT_VIEWS
    blocks = [_HEADER]
    label = views.get(view or "")
    if label:
        blocks.append(f"对方此刻在「{label}」页。指路时可以点明这一点，但页面名仍要写全。")
    blocks.append(_TEACHER if teacher else _STUDENT)
    blocks.append(_COMPANION)
    blocks.append(_RULES)
    return "\n\n".join(blocks)
