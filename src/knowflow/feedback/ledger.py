"""Append-only teaching feedback and supplemental evidence (contract v0.10).

The canonical tables are never rewritten.  A ``supplemental_attempt`` becomes an
independent evidence record (``EV-...``) used only for a derived diagnosis run;
teacher adjustments change *plans*, not scores or mastery.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.contracts import build_registry, repo_root

FEEDBACK_POLICY_VERSION = "feedback-rules-1"
FEEDBACK_SCHEMA_VERSION = "1.0.0"
FEEDBACK_DIR = "data/feedback"
FEEDBACK_FILE = "events.jsonl"
ACTIONS = {
    "lock",
    "unlock",
    "remove",
    "restore",
    "replace_materials",
    "set_time",
    "set_difficulty",
}
REQUIRES_SNAPSHOT = {"lock", "remove"}
PAYLOAD_REQUIRED = {
    "replace_materials": "material_ids",
    "set_time": "est_minutes",
    "set_difficulty": "difficulty",
}


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def feedback_path(dataset_id: str, root: Path | None = None) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dataset_id):
        raise ValueError("dataset ID must be a safe directory name")
    base = Path(root) if root is not None else repo_root()
    return base / FEEDBACK_DIR / dataset_id / FEEDBACK_FILE


def _validator() -> Draft202012Validator:
    root = repo_root()
    schema = json.loads(
        (root / "schemas" / "output" / "feedback_event.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        schema, registry=build_registry(root), format_checker=FormatChecker()
    )


def event_errors(event: dict) -> list[str]:
    return [
        f"feedback_event:{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in _validator().iter_errors(event)
    ]


def _rubric_errors(points: list[dict], material: dict) -> list[str]:
    rubric = {point["point_id"]: point for point in material["rubric"]}
    errors = []
    for point in points:
        point_id = point.get("point_id")
        by_id = rubric.get(point_id) if point_id else None
        by_text = next(
            (item for item in rubric.values() if item["label"] == point["criterion"]), None
        )
        target = by_id or by_text
        if target is None:
            errors.append(f"unknown rubric criterion: {point['criterion']}")
            continue
        if point["max_score"] != target["max_score"]:
            errors.append(f"rubric max score mismatch: {point['criterion']}")
        if point["score"] > point["max_score"]:
            errors.append(f"rubric score exceeds max: {point['criterion']}")
        if point["score"] < 0:
            errors.append(f"negative rubric score: {point['criterion']}")
    return errors


def _validate_supplemental(event: dict, bundle: dict) -> list[str]:
    errors = []
    material = next(
        (m for m in bundle["materials"] if m["material_id"] == event["material_id"]), None
    )
    if material is None:
        return [f"material {event['material_id']} is not an assessment item"]
    node = next((row for row in bundle["nodes"] if row["node_id"] == event["node_id"]), None)
    if node is not None and event["material_id"] not in node["material_ids"]:
        errors.append(f"{event['material_id']} is outside node scope")
    if abs(event["max_score"] - material["max_score"]) > 1e-9:
        errors.append("max_score does not match the material")
    if event["score"] > event["max_score"] + 1e-9:
        errors.append("score exceeds max_score")
    points = event.get("rubric_points") or []
    if points:
        errors.extend(_rubric_errors(points, material))
        if abs(sum(p["score"] for p in points) - event["score"]) > 1e-9:
            errors.append("rubric point sum must equal the total score")
    return errors


def _validate_adjustment(event: dict, bundle: dict, catalog: dict) -> list[str]:
    errors = []
    action = event["action"]
    if event["actor"] != "teacher":
        errors.append("teacher adjustments must use actor=teacher")
    if action not in ACTIONS:
        errors.append(f"unknown action {action}")
        return errors
    if action in REQUIRES_SNAPSHOT:
        snapshot = event.get("snapshot") or {}
        for field in ("issue_id", "knowledge_id", "activity_type", "seq", "material_ids"):
            if field not in snapshot:
                errors.append(f"{action} requires snapshot.{field}")
        if not event.get("reason", "").strip():
            errors.append(f"{action} requires a reason")
    required = PAYLOAD_REQUIRED.get(action)
    if required:
        payload = event.get("payload") or {}
        if required not in payload:
            errors.append(f"{action} requires payload.{required}")
        if action == "replace_materials":
            for material_id in payload.get("material_ids") or []:
                if material_id not in catalog["materials"]:
                    errors.append(f"unknown material {material_id}")
                    continue
                known = set(catalog["materials"][material_id]["knowledge_ids"])
                if event.get("knowledge_id") and event["knowledge_id"] not in known:
                    errors.append(f"{material_id} does not map to {event['knowledge_id']}")
                node = next(
                    (row for row in bundle["nodes"] if row["node_id"] == event["node_id"]), None
                )
                if node is not None and material_id not in node["material_ids"]:
                    errors.append(f"{material_id} is outside node scope")
        if action == "set_time" and not 1 <= payload.get("est_minutes", 0) <= 120:
            errors.append("est_minutes must be 1..120")
        if action == "set_difficulty" and not 1 <= payload.get("difficulty", 0) <= 5:
            errors.append("difficulty must be 1..5")
    if action in {"lock", "remove"} and not event.get("reason", "").strip():
        errors.append("lock/remove requires a reason")
    if action in {"unlock", "restore"} and event["actor"] != "teacher":
        errors.append("unlock/restore requires a teacher")
    return errors


def validate_event(event: dict, bundle: dict, catalog: dict) -> list[str]:
    errors = event_errors(event)
    if errors:
        return errors
    students = {row["student_id"] for row in bundle["students"]}
    nodes = {row["node_id"] for row in bundle["nodes"]}
    knowledge = {row["knowledge_id"] for row in bundle["knowledge"]}
    if event["student_id"] not in students:
        errors.append(f"unknown student {event['student_id']}")
    if event["node_id"] not in nodes:
        errors.append(f"unknown node {event['node_id']}")
    if "knowledge_id" in event and event["knowledge_id"] not in knowledge:
        errors.append(f"unknown knowledge {event['knowledge_id']}")
    if "plan_item_id" in event and not event["plan_item_id"].startswith(
        f"PL-{event['student_id'][1:]}-{event['node_id']}-v"
    ):
        errors.append("plan_item_id does not match student/node")
    if "issue_id" in event and not event["issue_id"].startswith(f"IS-{event['student_id'][1:]}-"):
        errors.append("issue_id does not match student")
    if event["event_type"] == "supplemental_attempt":
        errors.extend(_validate_supplemental(event, bundle))
    elif event["event_type"] == "teacher_adjustment":
        errors.extend(_validate_adjustment(event, bundle, catalog))
    elif event["event_type"] == "teacher_comment":
        if event["actor"] != "teacher":
            errors.append("teacher comments must use actor=teacher")
    elif event["event_type"] == "student_feedback":
        if event["actor"] != "student":
            errors.append("student feedback must use actor=student")
    return errors


def load_events(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text:
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {number} is not valid JSON: {exc}") from exc
        if not isinstance(event, dict):
            raise ValueError(f"{path}: line {number} must be a JSON object")
        events.append(event)
    return events


def append_event(path: Path, event: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def next_event_id(events: list[dict]) -> str:
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%dT%H%M%S")
    used = {event["event_id"] for event in events}
    for index in range(1, 10_000):
        candidate = f"EV-{stamp}-{index:04d}"
        if candidate not in used:
            return candidate
    raise ValueError("cannot allocate a feedback event id")


def make_event(
    *,
    event_type: str,
    student_id: str,
    node_id: str,
    actor: str,
    source: str = "local_demo_user",
    event_id: str | None = None,
    created_at: str | None = None,
    existing: list[dict] | None = None,
    **fields,
) -> dict:
    event = {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "event_id": event_id or next_event_id(existing or []),
        "event_type": event_type,
        "student_id": student_id,
        "node_id": node_id,
        "created_at": created_at or now_iso(),
        "actor": actor,
        "source": source,
    }
    event.update({key: value for key, value in fields.items() if value is not None})
    return event


def plan_snapshot(item: dict) -> dict:
    return {
        "issue_id": item["issue_id"],
        "knowledge_id": item["knowledge_ids"][0],
        "activity_type": item["activity_type"],
        "seq": item["seq"],
        "material_ids": list(item["material_ids"]),
        "est_minutes": item["est_minutes"],
        "difficulty": item["difficulty"],
    }


def supplemental_record(event: dict, material: dict) -> dict:
    """Convert one supplemental event into an evidence record (never canonical)."""

    points = []
    rubric = {point["point_id"]: point for point in material["rubric"]}
    for point in event.get("rubric_points") or []:
        point_id = point.get("point_id")
        if point_id is None:
            point_id = next(
                (key for key, value in rubric.items() if value["label"] == point["criterion"]),
                f"SP-{len(points) + 1}",
            )
        points.append(
            {
                "point_id": point_id,
                "label": point["criterion"],
                "max_score": point["max_score"],
                "score": point["score"],
            }
        )
    return {
        "record_id": event["event_id"],
        "student_id": event["student_id"],
        "material_id": event["material_id"],
        "node_id": event["node_id"],
        "assigned": True,
        "attempted": True,
        "score": event["score"],
        "max_score": event["max_score"],
        "is_correct": abs(event["score"] - event["max_score"]) <= 1e-9,
        "submitted_at": event.get("submitted_at") or event["created_at"],
        "duration_seconds": None,
        "attempt_no": int(event.get("attempt_no", 1)),
        "source": "supplemental",
        "score_points": points,
    }


def supplemental_events(events: list[dict], student_id: str | None = None) -> list[dict]:
    selected = [event for event in events if event["event_type"] == "supplemental_attempt"]
    if student_id:
        selected = [event for event in selected if event["student_id"] == student_id]
    return sorted(selected, key=lambda event: (event["created_at"], event["event_id"]))
