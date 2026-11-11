"""Record cleaning, evidence bucketing (re-exported) and the data-quality report."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass

from ..cleaning.states import classify_state, state_counts
from . import adapters, mapping
from .errors import AdaptError

STATUS_SCORED = "已评分"
STATUS_PENDING = "待评分"
STATUS_NOT_ATTEMPTED = "未作答"


@dataclass(frozen=True)
class Anomaly:
    """One record-level finding, mirrored into ``anomalies[]``."""

    record_id: str | None
    reason: str
    action: str

    def as_dict(self) -> dict[str, str | None]:
        return {"record_id": self.record_id, "reason": self.reason, "action": self.action}


@dataclass
class ReportCounters:
    """Numbers gathered while cleaning, used by ``field_quality``."""

    score_clamped: int = 0
    rubric_mismatch: int = 0
    theme_conflict: int = 0
    node_reassigned: int = 0
    duplicates_removed: int = 0
    empty_answers: int = 0


def node_index(nodes: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Parse the node JSON cells into lookup sets."""

    index: dict[str, dict[str, object]] = {}
    for node in nodes:
        index[str(node["node_id"])] = {
            "exam_date": str(node["exam_date"]),
            "taught": set(json.loads(str(node["taught_objective_ids_json"]))),
            "available": set(json.loads(str(node["available_material_ids_json"]))),
        }
    return index


def _material_theme(official: dict[str, str]) -> str:
    return (official.get("主题编号") or "").strip()


RECORD_FIELDS: tuple[str, ...] = (
    "record_id",
    "student_id",
    "material_id",
    "node_id",
    "assigned",
    "attempted",
    "score",
    "max_score",
    "is_correct",
    "answer",
    "rubric_scores_json",
    "steps_json",
    "submitted_at",
    "duration_seconds",
    "attempt_no",
    "source",
)


def _verbatim(value: str | None) -> str | None:
    """Zero processing: keep the cell exactly as submitted; blank becomes null."""

    if value is None or not value.strip():
        return None
    return value


def _record_row(item: dict[str, object]) -> dict[str, object]:
    """Analysis layer: only the fields the records schema declares."""

    return {field: item[field] for field in RECORD_FIELDS}


def _detail_row(item: dict[str, object]) -> dict[str, object]:
    """Evidence layer: one row per source CSV row, raw text untouched."""

    return {
        "csv_record_number": item["_line"],
        "source_record_id": item["_source_record_id"],
        "record_id": item.get("_superseded_by") or item["record_id"],
        "student_id": item["student_id"],
        "material_id": item["material_id"],
        "node_id": item["node_id"],
        "kept": bool(item["_kept"]),
        "final_answer": _verbatim(item["_raw_answer"]),  # type: ignore[arg-type]
        "solution_process": _verbatim(item["_raw_steps"]),  # type: ignore[arg-type]
        "scoring_point_scores": _verbatim(item["_raw_rubric"]),  # type: ignore[arg-type]
    }


def build_records(
    record_rows: list[dict[str, str]],
    nodes: list[dict[str, object]],
    official_materials: dict[str, dict[str, str]],
    anomalies: list[Anomaly],
    counters: ReportCounters,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Map, validate, clean and de-duplicate official records.

    Returns ``(records, details)``:

    - ``records`` — analysis layer, one row per surviving observation;
    - ``details`` — evidence layer, one row per **source CSV row** (raw text
      untouched, superseded revisions included, ``csv_record_number`` for
      traceability).

    De-duplication key is ``(student, material, node)``: the same event
    resubmitted keeps its highest revision, while two exam nodes answering the
    same item stay two independent observations.
    """

    index = node_index(nodes)
    prepared: list[dict[str, object]] = []

    for line_no, row in enumerate(record_rows, start=2):
        official_record = (row["记录编号"] or "").strip()
        try:
            record_id = mapping.record_id_for(official_record)
        except ValueError as exc:
            raise AdaptError(f"作答记录.csv:{line_no} {exc}") from exc

        status = (row["评分状态"] or "").strip()
        if status not in mapping.RECORD_STATUS:
            raise AdaptError(
                f"作答记录.csv:{line_no} 未知评分状态 {status!r}（只允许 "
                + "/".join(mapping.RECORD_STATUS)
                + "）"
            )

        official_material = (row["材料编号"] or "").strip()
        if official_material not in official_materials:
            raise AdaptError(
                f"作答记录.csv:{line_no} 材料 {official_material!r} 不在题目与材料表中"
            )
        material_id = mapping.material_id_for(official_material)

        node_id = (row["节点编号"] or "").strip()
        if node_id not in index:
            raise AdaptError(f"作答记录.csv:{line_no} 节点 {node_id!r} 不在测验节点表中")

        if material_id not in index[node_id]["available"]:
            candidates = [
                candidate
                for candidate, meta in index.items()
                if material_id in meta["available"]
            ]
            submitted_date = (row["模拟提交时间"] or "")[:10]
            matches = [
                candidate
                for candidate in candidates
                if index[candidate]["exam_date"] == submitted_date
            ]
            if len(matches) == 1:
                anomalies.append(
                    Anomaly(
                        record_id,
                        f"记录节点 {node_id} 的可用题目不含 {official_material}",
                        f"提交日期与可用题目双重证据一致，改判 node_id={matches[0]}",
                    )
                )
                counters.node_reassigned += 1
                node_id = matches[0]
            else:
                raise AdaptError(
                    f"作答记录.csv:{line_no} 节点 {node_id} 不含材料 "
                    f"{official_material}，且无法用提交日期唯一改判"
                )

        record_theme = (row["主题编号"] or "").strip()
        material_theme = _material_theme(official_materials[official_material])
        if record_theme and material_theme and record_theme != material_theme:
            anomalies.append(
                Anomaly(
                    record_id,
                    f"记录主题 {record_theme} 与材料 {official_material} 主题 "
                    f"{material_theme} 不一致",
                    "以材料主题为准；canonical 记录不落主题字段",
                )
            )
            counters.theme_conflict += 1

        max_raw = (row["满分"] or "").strip()
        if not max_raw:
            raise AdaptError(f"作答记录.csv:{line_no} 缺少满分")
        max_score = int(max_raw)
        material_max = (official_materials[official_material].get("满分") or "").strip()
        if material_max and int(material_max) != max_score:
            raise AdaptError(
                f"作答记录.csv:{line_no} 满分 {max_score} 与材料 "
                f"{official_material} 满分 {material_max} 不一致"
            )

        score_raw = (row["得分"] or "").strip()
        score = int(score_raw) if score_raw else None
        rubric_raw = row["评分点得分"]

        if score is not None and score > max_score:
            rubric_total = adapters.rubric_sum(rubric_raw)
            if rubric_total != max_score:
                raise AdaptError(
                    f"作答记录.csv:{line_no} 得分 {score} 超出满分 {max_score}，"
                    f"评分点合计 {rubric_total}，无法安全截断"
                )
            anomalies.append(
                Anomaly(
                    record_id,
                    f"得分 {score} 超出满分 {max_score}",
                    f"评分点合计 {rubric_total} 与满分一致，截断为 {max_score}；"
                    "原值保留在 data/raw",
                )
            )
            counters.score_clamped += 1
            score = max_score

        if status == STATUS_SCORED and score is None:
            raise AdaptError(f"作答记录.csv:{line_no} 已评分却缺少得分")
        if status != STATUS_SCORED and score is not None:
            raise AdaptError(
                f"作答记录.csv:{line_no} {status} 却带有得分 {score}"
            )

        if status == STATUS_SCORED and score is not None:
            rubric_total = adapters.rubric_sum(rubric_raw)
            if rubric_total is not None and rubric_total != score:
                anomalies.append(
                    Anomaly(
                        record_id,
                        f"得分 {score} 与评分点合计 {rubric_total} 不一致",
                        "以官方得分为准；评分点仅作过程证据",
                    )
                )
                counters.rubric_mismatch += 1

        answer = adapters._text(row["学生最终作答"])
        if status == STATUS_NOT_ATTEMPTED and answer:
            anomalies.append(
                Anomaly(
                    record_id,
                    "评分状态为未作答，但存在作答文本",
                    "按未作答处理（attempted=false）；answer 保留原文",
                )
            )

        if not answer:
            counters.empty_answers += 1

        attempt_no = int((row["修订版本"] or "").strip() or 0) or None
        if status == STATUS_SCORED:
            attempt_no = attempt_no or 1

        prepared.append(
            {
                "record_id": record_id,
                "student_id": mapping.student_id_for((row["学生编号"] or "").strip()),
                "material_id": material_id,
                "node_id": node_id,
                "assigned": True,
                "attempted": status != STATUS_NOT_ATTEMPTED,
                "score": score,
                "max_score": max_score,
                "is_correct": (score == max_score) if score is not None else None,
                "answer": answer,
                "submitted_at": adapters._text(row["模拟提交时间"]),
                "duration_seconds": None,
                "attempt_no": attempt_no,
                "source": mapping.DATASET_ID,
                "rubric_scores_json": adapters.parse_rubric_scores(rubric_raw),
                "steps_json": adapters.split_steps(row["解答过程"]),
                "_line": line_no,
                "_source_record_id": official_record,
                "_raw_answer": row["学生最终作答"],
                "_raw_steps": row["解答过程"],
                "_raw_rubric": rubric_raw,
            }
        )

    ordered = sorted(
        prepared,
        key=lambda item: (
            str(item["student_id"]),
            str(item["material_id"]),
            str(item["node_id"]),
            int(item["attempt_no"] or 0),
            str(item["submitted_at"] or ""),
            str(item["record_id"]),
        ),
    )
    kept: list[dict[str, object]] = []
    superseded: list[dict[str, object]] = []
    for _, group in itertools.groupby(
        ordered,
        key=lambda item: (
            str(item["student_id"]),
            str(item["material_id"]),
            str(item["node_id"]),
        ),
    ):
        members = list(group)
        survivor = members[-1]
        survivor["_kept"] = True
        kept.append(survivor)
        for item in members[:-1]:
            item["_kept"] = False
            item["_superseded_by"] = survivor["record_id"]
            superseded.append(item)
            anomalies.append(
                Anomaly(
                    str(item["record_id"]),
                    "同一作答事件存在更高修订版本",
                    f"保留 {survivor['record_id']}（attempt_no={survivor['attempt_no']}）；"
                    "本行不进 records，原文保留在 record_details",
                )
            )
            counters.duplicates_removed += 1

    kept.sort(key=lambda item: str(item["record_id"]))
    records = [_record_row(item) for item in kept]
    details = sorted(
        (_detail_row(item) for item in kept + superseded),
        key=lambda row: int(row["csv_record_number"]),
    )
    return records, details





def find_partial_node_students(
    records: list[dict[str, object]],
    nodes: list[dict[str, object]],
    anomalies: list[Anomaly],
) -> None:
    node_ids = {str(node["node_id"]) for node in nodes}
    taken: dict[str, set[str]] = {}
    for record in records:
        taken.setdefault(str(record["student_id"]), set()).add(str(record["node_id"]))
    for student_id in sorted(taken):
        missing = node_ids - taken[student_id]
        if missing:
            anomalies.append(
                Anomaly(
                    None,
                    f"学生 {student_id} 只有 {sorted(taken[student_id])} 的记录，"
                    f"缺少 {sorted(missing)}",
                    "不推断；缺失节点的可测内容按 unobserved 处理，"
                    "覆盖度分母按已参加节点计算",
                )
            )


def build_report(
    *,
    dataset_id: str,
    generated_at: str,
    input_files: list[dict[str, object]],
    students: list[dict[str, object]],
    materials: list[dict[str, object]],
    records: list[dict[str, object]],
    anomalies: list[Anomaly],
    counters: ReportCounters,
) -> dict[str, object]:
    states = state_counts(records)
    if states["unobserved"] != 0:
        raise AdaptError("records_by_state.unobserved 必须为 0（无记录不落行）")

    student_ids = {str(row["student_id"]) for row in students}
    seen_students = {str(row["student_id"]) for row in records}
    item_materials = {
        str(row["material_id"])
        for row in materials
        if row["material_type"] in {"assessment", "practice", "probe"}
    }
    seen_materials = {str(row["material_id"]) for row in records}

    difficulty_missing = sum(1 for row in materials if row["difficulty"] is None)
    duration_missing = sum(1 for row in records if row["duration_seconds"] is None)
    reference_rows = [row for row in materials if row["material_type"] == "reference"]
    mapped_reference = sum(1 for row in reference_rows if row["objective_id"] is not None)
    unmapped_reference = len(reference_rows) - mapped_reference

    field_quality = [
        {
            "field": "difficulty",
            "issue": "官方数据未提供难度；canonical 置 null，不猜、不按最低难度处理",
            "count": difficulty_missing,
        },
        {
            "field": "duration_seconds",
            "issue": "官方无用时字段；恒为 null，不分析",
            "count": duration_missing,
        },
        {
            "field": "objective_id",
            "issue": "教材切片无主题/指标；按章节名匹配到唯一主题",
            "count": mapped_reference,
        },
        {
            "field": "objective_id",
            "issue": "教材切片无主题/指标；章节名不匹配任何主题，保持 null",
            "count": unmapped_reference,
        },
        {
            "field": "score",
            "issue": "得分超出满分；按评分点合计截断并记异常",
            "count": counters.score_clamped,
        },
        {
            "field": "score",
            "issue": "得分与评分点合计不一致；以官方得分为准",
            "count": counters.rubric_mismatch,
        },
        {
            "field": "主题编号(raw)",
            "issue": "记录主题与材料主题冲突；以材料主题为准",
            "count": counters.theme_conflict,
        },
        {
            "field": "节点编号(raw)",
            "issue": "记录节点与可用题目/日期矛盾；按双重证据改判",
            "count": counters.node_reassigned,
        },
    ]

    handling_rules = [
        "去重键 = (student_id, material_id, node_id)，按 attempt_no → submitted_at → record_id 取最后一条；同一学生在两个测验节点各答一次不算重复。",
        "评分状态=已评分 → assigned=true, attempted=true, score=得分, is_correct=(score==max_score)；待评分 → attempted=true, score/is_correct=null；未作答 → attempted=false, score/is_correct=null。",
        "assigned 只由官方记录推出；禁止用节点可用题目展开成 assigned=true，无记录不落行（unobserved 由聚合层判定）。",
        "得分 > 满分仅在评分点合计等于满分时截断，并记录 anomalies；否则中止。",
        "得分与评分点合计不一致时以官方得分为准，评分点只作过程证据。",
        "记录主题与材料主题冲突时以材料主题为准；canonical records 不含主题字段。",
        "记录节点与节点可用题目/日期矛盾时，仅当提交日期与另一节点日期一致且材料只属于该节点时改判，否则中止。",
        "缺少记录不等于答错/未掌握：未作答与 pending 分开记账，unobserved 不写成 0 分。",
        "官方未提供难度与用时：difficulty/duration_seconds 为 null，不分析、不猜。",
        "教材切片无主题/指标：能由章节名唯一匹配的映射到课标条目，其余保持 null。",
        "作答文本、解答步骤与评分点得分只保留在本机 canonical（gitignore），禁止送 LLM 或外传。",
        "official-v1 不预置学习任务：tasks.csv 仅表头，任务条件由建议层按场景定义。",
        "先修/易混边未生成：官方表格不含此类关系；先修需课标/教材解析，易混需诊断层从错题统计，非遗漏。",
    ]

    sorted_anomalies = sorted(
        (anomaly.as_dict() for anomaly in anomalies),
        key=lambda item: (str(item["record_id"] or ""), str(item["reason"])),
    )

    return {
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "generated_at": generated_at,
        "input_files": input_files,
        "total_records": len(records),
        "duplicates_removed": counters.duplicates_removed,
        "records_by_state": states,
        "missing": {
            "students_without_records": len(student_ids - seen_students),
            "items_without_records": len(item_materials - seen_materials),
            "empty_answers": counters.empty_answers,
        },
        "anomalies": sorted_anomalies,
        "field_quality": field_quality,
        "handling_rules": handling_rules,
    }
