"""Independent, entirely synthetic official-format data; never read competition files."""

import csv

import pytest

from knowflow.io.adapters import TABLES, adapt_official

STAMP = "2026-11-10T12:00:00+08:00"


@pytest.fixture
def official_tables():
    tables = {name: [] for name in TABLES}
    tables["模拟学生"] = [
        {"学生编号": f"D{i:02d}", "模拟班级编号": "DC01" if i <= 2 else "DC02", "年级": "7"}
        for i in range(1, 5)
    ]
    tables["课程要求"] = [
        {
            "主题编号": f"T{i:02d}",
            "主题": f"合成主题{i}",
            "主题目标": "仅用于测试",
            "指标编号": f"T{i:02d}I1",
            "观察指标": f"合成指标{i}",
            "课标整理编号": f"CR{i:02d}",
            "课标文件页／正文页": "1／1",
            "教材正文页": "1",
        }
        for i in [1, 2]
    ]
    for i in range(1, 5):
        qid = f"Q{i:03d}"
        multi = i == 4
        tables["题目与材料"].append(
            {
                "材料编号": qid,
                "主题编号": "T02" if multi else "T01",
                "材料类型": "题目",
                "题型": "解答题" if multi else "填空题",
                "题干或内容": "纯合成题干",
                "选项": "",
                "参考答案": "合成参考",
                "参考解析": "合成解析",
                "满分": "3" if multi else "1",
                "评分点": "\n".join(
                    f"{qid}P{j} 合成步骤{j} 1分" for j in range(1, 4 if multi else 2)
                ),
                "指标编号": "T02I1" if multi else "T01I1",
                "来源或资料文件": "synthetic",
            }
        )
    tables["测验节点"] = [
        {
            "节点编号": "N01",
            "模拟测验日期": "2026-01-01",
            "已教及测量主题": "T01",
            "说明": "合成阶段一",
            "可用题目编号": "Q001、Q002、Q003",
        },
        {
            "节点编号": "N02",
            "模拟测验日期": "2026-06-01",
            "已教及测量主题": "T01、T02",
            "说明": "合成阶段二",
            "可用题目编号": "Q001、Q002、Q003、Q004",
        },
    ]
    records = tables["作答记录"]

    def add(student, node, item, score, version=1, status="已评分"):
        qid = f"Q{item:03d}"
        number = len(records) + 1
        point_values = (
            ([1, 1, 0] if score == 2 else [1, 1, 1] if score == 3 else [0, 0, 0])
            if item == 4
            else [min(score or 0, 1)]
        )
        records.append(
            {
                "记录编号": f"DR{number:04d}",
                "学生编号": student,
                "材料编号": qid,
                "主题编号": "T02" if item == 4 else "T01",
                "节点编号": node,
                "作答事件编号": f"{student}-{node}-{qid}",
                "修订版本": str(version),
                "模拟提交时间": f"2026-06-01T10:{number:02d}:00+08:00",
                "评分状态": status,
                "得分": str(score) if score is not None else "",
                "满分": "3" if item == 4 else "1",
                "学生最终作答": "" if status == "未作答" else "synthetic-private-answer",
                "解答过程": "synthetic-private-steps" if item == 4 else "",
                "评分点得分": "；".join(
                    f"{qid}P{j}={value}" for j, value in enumerate(point_values, 1)
                )
                if score is not None
                else "",
            }
        )

    add("D01", "N01", 1, 0)
    add("D01", "N01", 1, 1, 2)
    add("D01", "N01", 2, None, status="待评分")
    add("D01", "N01", 3, None, status="未作答")
    for i in [1, 2, 3]:
        add("D01", "N02", i, 0)
    add("D01", "N02", 4, 2)
    for i in [1, 2, 3]:
        add("D02", "N02", i, 1)
    add("D03", "N01", 1, 1)
    add("D03", "N01", 1, 10, 2)
    return tables


@pytest.fixture
def write_official(tmp_path):
    def write(tables, name="raw"):
        root = tmp_path / name
        directory = root / "4_赛题数据" / "模拟学情数据"
        directory.mkdir(parents=True, exist_ok=True)
        for table, headers in TABLES.items():
            with (directory / f"{table}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=sorted(headers))
                writer.writeheader()
                for row in tables[table]:
                    writer.writerow(row)
        return root

    return write


@pytest.fixture
def bundle(official_tables, write_official):
    return adapt_official(write_official(official_tables), "synthetic-task2", STAMP)
