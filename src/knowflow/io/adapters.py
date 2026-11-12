"""Official CSV -> minimal diagnosis contract. No answers or solution text exported."""

import csv
import hashlib
import math
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from knowflow.cleaning import clean_records, evidence_state
from knowflow.cleaning.records import STATES

TABLES = {
    "模拟学生": {"学生编号", "模拟班级编号", "年级"},
    "课程要求": {
        "主题编号",
        "主题",
        "主题目标",
        "指标编号",
        "观察指标",
        "课标整理编号",
        "课标文件页／正文页",
        "教材正文页",
    },
    "题目与材料": {
        "材料编号",
        "主题编号",
        "材料类型",
        "题型",
        "题干或内容",
        "选项",
        "参考答案",
        "参考解析",
        "满分",
        "评分点",
        "指标编号",
        "来源或资料文件",
    },
    "测验节点": {"节点编号", "模拟测验日期", "已教及测量主题", "说明", "可用题目编号"},
    "作答记录": {
        "记录编号",
        "学生编号",
        "材料编号",
        "主题编号",
        "节点编号",
        "作答事件编号",
        "修订版本",
        "模拟提交时间",
        "评分状态",
        "得分",
        "满分",
        "学生最终作答",
        "解答过程",
        "评分点得分",
    },
    "字段说明": {"数据表", "字段名", "类型", "含义", "取值或格式", "示例", "为空时"},
}


def load_csv(path: Path, expected: set[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or set(headers) != expected:
            raise ValueError(
                f"{path.name}: column mismatch; missing={sorted(expected - set(headers))}, unknown={sorted(set(headers) - expected)}"
            )
        rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError(f"{path.name}: malformed CSV row")
    return [{k: v.strip() for k, v in r.items()} for r in rows]


def unique(rows, field, table):
    ids = [r[field] for r in rows]
    if any(not x for x in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"{table}: missing/duplicate {field}")


def numeric_id(raw: str, prefix: str, output: str, width: int, maximum: int) -> str:
    match = re.fullmatch(re.escape(prefix) + r"([0-9]+)", raw)
    if not match or not 1 <= int(match[1]) <= maximum:
        raise ValueError(f"unsupported {prefix} identifier")
    return f"{output}{int(match[1]):0{width}d}"


def split_ids(value):
    return [x.strip() for x in re.split(r"[、,，;；]", value) if x.strip()]


def finite_number(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


def point_definitions(text: str, source_id: str, material_id: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        match = re.fullmatch(
            re.escape(source_id) + r"P([0-9]+)\s+(.+?)\s+([0-9]+(?:\.[0-9]+)?)分", line.strip()
        )
        if not match:
            raise ValueError(f"{source_id}: unrecognized scoring rubric; review adapter")
        result.append(
            {
                "point_id": f"{material_id}P{int(match[1])}",
                "label": match[2],
                "max_score": finite_number(match[3]),
            }
        )
    if len({p["point_id"] for p in result}) != len(result) or any(
        p["max_score"] <= 0 for p in result
    ):
        raise ValueError(f"{source_id}: duplicate/nonpositive scoring points")
    return result


def parse_points(raw: str, material: dict, score: float) -> list[dict]:
    defs = {p["point_id"]: p for p in material["point_definitions"]}
    points = {}
    for part in split_ids(raw):
        match = re.fullmatch(
            re.escape(material["source_material_id"]) + r"P([0-9]+)=([0-9]+(?:\.[0-9]+)?)", part
        )
        if not match:
            raise ValueError("malformed score points")
        pid = f"{material['material_id']}P{int(match[1])}"
        if pid not in defs or pid in points:
            raise ValueError("unknown or duplicate score point")
        value = finite_number(match[2])
        if not 0 <= value <= defs[pid]["max_score"]:
            raise ValueError("score point out of bounds")
        points[pid] = {**defs[pid], "score": value}
    if set(points) != set(defs) or not math.isclose(
        sum(p["score"] for p in points.values()), score, abs_tol=1e-8
    ):
        raise ValueError("score points do not reconcile with official total")
    return [points[pid] for pid in sorted(points)]


def adapt_official(
    raw_root: Path, dataset_id: str, generated_at: str, previous_map=None, knowledge_base=None
) -> dict:
    base = raw_root / "4_赛题数据" / "模拟学情数据"
    tables = {name: load_csv(base / f"{name}.csv", fields) for name, fields in TABLES.items()}
    for name, key in [
        ("模拟学生", "学生编号"),
        ("课程要求", "指标编号"),
        ("题目与材料", "材料编号"),
        ("测验节点", "节点编号"),
    ]:
        unique(tables[name], key, name)
    if not tables["课程要求"] or not tables["测验节点"]:
        raise ValueError("knowledge requirements and test nodes must not be empty")
    students = [
        {
            "student_id": numeric_id(r["学生编号"], "D", "S", 3, 999),
            "group_id": numeric_id(r["模拟班级编号"], "DC", "G", 1, 99),
            "grade": int(r["年级"]),
            "stage": "middle",
            "notes": None,
        }
        for r in tables["模拟学生"]
    ]
    student_map = {
        r["学生编号"]: s["student_id"] for r, s in zip(tables["模拟学生"], students, strict=True)
    }
    knowledge_map = dict((previous_map or {}).get("knowledge", {}))
    used = {int(k.split("-")[1]) for k in knowledge_map.values()}
    for source in sorted(r["指标编号"] for r in tables["课程要求"]):
        if source not in knowledge_map:
            next_id = max(used, default=0) + 1
            if next_id > 999:
                raise ValueError("knowledge ID capacity exceeded")
            knowledge_map[source] = f"K-{next_id:02d}"
            used.add(next_id)
    knowledge = [
        {
            "knowledge_id": knowledge_map[r["指标编号"]],
            "objective_id": numeric_id(r["课标整理编号"], "CR", "OBJ-7M-", 2, 999),
            "name": r["观察指标"],
            "source_indicator_id": r["指标编号"],
        }
        for r in tables["课程要求"]
    ]
    materials, material_map = [], {}
    for row in tables["题目与材料"]:
        if row["材料类型"] != "题目":
            continue  # R1 owns unmeasured learning cards / textbook resources.
        mid = numeric_id(row["材料编号"], "Q", "M-", 3, 999)
        material_map[row["材料编号"]] = mid
        indicators = split_ids(row["指标编号"])
        if not indicators or any(k not in knowledge_map for k in indicators):
            raise ValueError(f"{mid}: missing/unknown knowledge mapping")
        maximum = finite_number(row["满分"])
        points = point_definitions(row["评分点"], row["材料编号"], mid)
        if maximum <= 0 or (
            points and not math.isclose(sum(p["max_score"] for p in points), maximum)
        ):
            raise ValueError(f"{mid}: invalid rubric total")
        materials.append(
            {
                "material_id": mid,
                "source_material_id": row["材料编号"],
                "topic_id": row["主题编号"],
                "max_score": maximum,
                "knowledge_ids": sorted({knowledge_map[k] for k in indicators}),
                "point_definitions": points,
            }
        )
    if knowledge_base is not None:
        # Explicit R1 override must cover every observed-capable question.
        known = {k["knowledge_id"]: k for k in knowledge_base["knowledge"]}
        for m in materials:
            mapped = sorted(
                {
                    q["knowledge_id"]
                    for q in knowledge_base["qmatrix"]
                    if q["material_id"] == m["material_id"] and q["weight"] > 0
                }
            )
            if not mapped or any(k not in known for k in mapped):
                raise ValueError(f"R1 mapping does not cover {m['material_id']}")
            m["knowledge_ids"] = mapped
        old_sources = {k["knowledge_id"]: k["source_indicator_id"] for k in knowledge}
        knowledge = [
            {
                "knowledge_id": k,
                "objective_id": v["objective_id"],
                "name": v["name"],
                "source_indicator_id": old_sources.get(k, f"R1:{k}"),
            }
            for k, v in sorted(known.items())
        ]
    by_material = {m["material_id"]: m for m in materials}
    nodes = []
    for row in tables["测验节点"]:
        if not re.fullmatch(r"N[0-9]{2,3}", row["节点编号"]):
            raise ValueError("unsupported node ID")
        date.fromisoformat(row["模拟测验日期"])
        source_items = split_ids(row["可用题目编号"])
        if any(q not in material_map for q in source_items):
            raise ValueError("node refers to unknown/non-question material")
        taught = set(split_ids(row["已教及测量主题"]))
        scope = sorted(
            {
                material_map[q]
                for q in source_items
                if by_material[material_map[q]]["topic_id"] in taught
            }
        )
        nodes.append(
            {"node_id": row["节点编号"], "date": row["模拟测验日期"], "material_ids": scope}
        )
    by_node = {n["node_id"]: n for n in nodes}
    candidates, participation, record_sources = [], set(), {}
    for row_no, raw in enumerate(tables["作答记录"], 2):
        errors, warnings = [], []

        def mapped_id(field, prefix, out, width, maximum, raw=raw, errors=errors):
            try:
                return numeric_id(raw[field], prefix, out, width, maximum)
            except ValueError:
                errors.append(f"invalid_{field}")
                return None

        rid = mapped_id("记录编号", "DR", "R-", 4, 9999)
        sid = student_map.get(raw["学生编号"])
        mid = material_map.get(raw["材料编号"])
        node_id = raw["节点编号"]
        if sid is None:
            errors.append("unknown_student")
        if mid is None:
            errors.append("unknown_material")
        if node_id not in by_node:
            errors.append("unknown_node")
        if sid and node_id in by_node:
            participation.add((sid, node_id))
        if mid and node_id in by_node and mid not in by_node[node_id]["material_ids"]:
            errors.append("material_outside_node_scope")
        if mid and raw["主题编号"] != by_material[mid]["topic_id"]:
            errors.append("topic_mismatch")
        expected_event = f"{raw['学生编号']}-{node_id}-{raw['材料编号']}"
        if raw["作答事件编号"] != expected_event:
            errors.append("event_identity_mismatch")
        order_invalid = False
        try:
            version = int(raw["修订版本"])
            submitted = datetime.fromisoformat(raw["模拟提交时间"])
            if version < 1 or submitted.tzinfo is None:
                raise ValueError("invalid order")
        except ValueError:
            order_invalid = True
            version = 0
            errors.append("invalid_revision_or_timestamp")
        score, maximum = None, 1.0
        status = raw["评分状态"]
        if status not in {"已评分", "待评分", "未作答"}:
            errors.append("unknown_grading_status")
        try:
            maximum = finite_number(raw["满分"])
            if maximum <= 0 or (mid and maximum != by_material[mid]["max_score"]):
                errors.append("max_score_mismatch")
            if status == "已评分":
                score = finite_number(raw["得分"])
                if not 0 <= score <= maximum:
                    errors.append("score_out_of_bounds")
            elif raw["得分"]:
                errors.append("ungraded_record_has_score")
        except ValueError:
            errors.append("invalid_score")
        points = []
        if status == "已评分" and mid and score is not None and not errors:
            try:
                points = parse_points(raw["评分点得分"], by_material[mid], score)
            except ValueError:
                warnings.append("unreliable_or_missing_score_points")
        if status == "未作答" and (raw["学生最终作答"] or raw["解答过程"]):
            warnings.append("unattempted_with_content")
        if status == "已评分" and not raw["学生最终作答"]:
            warnings.append("graded_answer_missing")
        candidate = {
            "record_id": rid,
            "student_id": sid,
            "material_id": mid,
            "assigned": True,
            "attempted": status != "未作答",
            "score": score,
            "max_score": maximum,
            "is_correct": score == maximum if score is not None else None,
            "answer": None,
            "submitted_at": raw["模拟提交时间"],
            "duration_seconds": None,
            "attempt_no": version,
            "source": dataset_id,
            "node_id": node_id,
            "event_id": expected_event,
            "score_points": points,
            "_row": row_no,
            "_errors": errors,
            "_warnings": warnings,
            "_order_invalid": order_invalid,
        }
        candidates.append(candidate)
        if rid is not None:
            record_sources[rid] = {
                "relative_path": "4_赛题数据/模拟学情数据/作答记录.csv",
                "source_row": row_no,
                "source_record_id": raw["记录编号"],
            }
    records, decisions, anomalies = clean_records(candidates)
    states = Counter(evidence_state(r) for r in records)
    error_counts = Counter(reason for r in candidates for reason in r["_errors"] + r["_warnings"])
    files = [
        {
            "path": (base / f"{name}.csv").relative_to(raw_root).as_posix(),
            "sha256": hashlib.sha256((base / f"{name}.csv").read_bytes()).hexdigest(),
            "rows": len(rows),
        }
        for name, rows in tables.items()
    ]
    quality = {
        "schema_version": "0.3.0",
        "dataset_id": dataset_id,
        "generated_at": generated_at,
        "input_files": files,
        "input_records": len(candidates),
        "total_records": len(records),
        "duplicates_removed": sum(d["decision"] == "superseded" for d in decisions),
        "rejected_records": sum(d["decision"] == "rejected" for d in decisions),
        "partial_credit_records": sum(
            r["score"] is not None and 0 < r["score"] < r["max_score"] for r in records
        ),
        "records_by_state": {s: states[s] for s in STATES},
        "missing": {
            "students_without_records": len(
                set(student_map.values()) - {r["student_id"] for r in records}
            ),
            "items_without_records": len(set(by_material) - {r["material_id"] for r in records}),
            "empty_answers": sum(not r["学生最终作答"] for r in tables["作答记录"]),
        },
        "anomalies": anomalies,
        "field_quality": [
            {"field": "records", "issue": key, "count": value}
            for key, value in sorted(error_counts.items())
        ],
        "handling_rules": [
            "按作答事件取修订版本、带时区时间、记录ID最大者；不同节点不合并。",
            "先选择最新修订，再校验得分；最新无效不恢复旧分。",
            "total_records为清洗后行数；input_records=total_records+duplicates_removed+rejected_records。",
            "部分得分属于未满分证据，但另报部分得分率及评分点；不等同于完全错误。",
            "待评分与未作答均不计入掌握度；无记录不造行。",
            "参与节点由记录中的有效学生及节点ID证明；未知参与范围的覆盖率为null。",
            "评分点与官方总分冲突时保留总分、停用评分点；不按答案字符串重新评分。",
            "missing.empty_answers统计原始输入的空最终作答；作答全文不进入中间包。",
        ],
        "decisions": decisions,
    }
    retained_ids = {r["record_id"] for r in records}
    return {
        "schema_version": "0.3.0",
        "dataset_id": dataset_id,
        "generated_at": generated_at,
        "raw_root": str(raw_root.resolve()),
        "students": sorted(students, key=lambda r: r["student_id"]),
        "knowledge": sorted(knowledge, key=lambda r: r["knowledge_id"]),
        "materials": sorted(materials, key=lambda r: r["material_id"]),
        "nodes": sorted(nodes, key=lambda r: (r["date"], r["node_id"])),
        "participation": [{"student_id": s, "node_id": n} for s, n in sorted(participation)],
        "records": records,
        "record_sources": {k: v for k, v in record_sources.items() if k in retained_ids},
        "id_map": {"students": student_map, "knowledge": knowledge_map, "materials": material_map},
        "quality_report": quality,
        "mapping_source": "R1 knowledge_base override"
        if knowledge_base is not None
        else "official explicit indicator mapping; not a complete Task 1 knowledge base",
    }
