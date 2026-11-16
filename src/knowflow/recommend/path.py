"""Learning-path identities, completion conditions and progress events.

Progress events are append-only local records (``data/progress/``, Git-ignored).
They say "started/completed a plan item"; they never carry a score and never
rewrite diagnosis or history. Only ``completed`` events close a plan item.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.contracts import build_registry, repo_root

PATH_POLICY_VERSION = "path-rules-1"
PATH_SCHEMA_VERSION = "1.0.0"
EVENT_TYPES = ("started", "completed")
PROGRESS_DIR = "data/progress"
PROGRESS_FILE = "events.jsonl"
SNAPSHOT_FIELDS = (
    "plan_item_id",
    "plan_version",
    "seq",
    "issue_id",
    "knowledge_id",
    "material_ids",
    "activity_type",
)


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def plan_id(student_id: str, node_id: str, version: int) -> str:
    return f"PLAN-{student_id[1:]}-{node_id}-v{version}"


def plan_item_id(student_id: str, node_id: str, version: int, knowledge_id: str) -> str:
    number = int(knowledge_id.split("-")[1])
    return f"PL-{student_id[1:]}-{node_id}-v{version}-{number:02d}"


def completion_condition(
    activity_type: str, material_ids: list[str], criteria: list[str]
) -> dict:
    """Structured, verifiable completion rule derived from the activity type."""

    if activity_type == "probe":
        return {"type": "probe_evidence", "material_ids": list(material_ids), "min_graded": 3}
    condition = {
        "type": "full_credit",
        "material_ids": list(material_ids),
        "min_full_credit": 1 if criteria else 2,
    }
    if criteria:
        condition["criterion"] = criteria[0]
    return condition


def _validator() -> Draft202012Validator:
    root = repo_root()
    schema = json.loads(
        (root / "schemas" / "output" / "path_event.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        schema, registry=build_registry(root), format_checker=FormatChecker()
    )


def event_errors(event: dict) -> list[str]:
    return [
        f"path_event:{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in _validator().iter_errors(event)
    ]


def validate_event_refs(event: dict, tables: dict) -> list[str]:
    """Check that the event points at real canonical entities and a coherent plan id."""

    errors = []
    students = {row["student_id"] for row in tables["students"]}
    nodes = {row["node_id"] for row in tables["nodes"]}
    knowledge = {row["knowledge_id"] for row in tables["knowledge"]}
    materials = {row["material_id"] for row in tables["materials"]}
    if event["student_id"] not in students:
        errors.append(f"unknown student {event['student_id']}")
    if event["node_id"] not in nodes:
        errors.append(f"unknown node {event['node_id']}")
    if event["knowledge_id"] not in knowledge:
        errors.append(f"unknown knowledge {event['knowledge_id']}")
    for material_id in event["material_ids"]:
        if material_id not in materials:
            errors.append(f"unknown material {material_id}")
    expected_plan = plan_id(event["student_id"], event["node_id"], event["plan_version"])
    if event["plan_id"] != expected_plan:
        errors.append("plan_id does not match student/node/version")
    if not event["plan_item_id"].startswith(
        f"PL-{event['student_id'][1:]}-{event['node_id']}-v{event['plan_version']}-"
    ):
        errors.append("plan_item_id does not match student/node/version")
    return errors


def progress_path(dataset_id: str, root: Path | None = None) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dataset_id):
        raise ValueError("dataset ID must be a safe directory name")
    base = Path(root) if root is not None else repo_root()
    return base / PROGRESS_DIR / dataset_id / PROGRESS_FILE


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
        errors = event_errors(event)
        if errors:
            raise ValueError(f"{path}: line {number}: {errors[0]}")
        events.append(event)
    return events


def next_event_id(events: list[dict]) -> str:
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%dT%H%M%S")
    used = {event["event_id"] for event in events}
    for index in range(1, 10_000):
        candidate = f"PE-{stamp}-{index:04d}"
        if candidate not in used:
            return candidate
    raise ValueError("cannot allocate a progress event id")


def make_event(
    *,
    student_id: str,
    node_id: str,
    plan_version: int,
    event_type: str,
    issue_id: str,
    knowledge_id: str,
    material_ids: list[str],
    activity_type: str,
    seq: int,
    event_id: str | None = None,
    created_at: str | None = None,
    source: str = "local_demo_user",
    note: str | None = None,
    existing: list[dict] | None = None,
) -> dict:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of {EVENT_TYPES}")
    event = {
        "schema_version": PATH_SCHEMA_VERSION,
        "event_id": event_id or next_event_id(existing or []),
        "student_id": student_id,
        "node_id": node_id,
        "plan_id": plan_id(student_id, node_id, plan_version),
        "plan_item_id": plan_item_id(student_id, node_id, plan_version, knowledge_id),
        "plan_version": plan_version,
        "event_type": event_type,
        "issue_id": issue_id,
        "knowledge_id": knowledge_id,
        "material_ids": list(material_ids),
        "activity_type": activity_type,
        "seq": int(seq),
        "created_at": created_at or now_iso(),
        "source": source,
    }
    if note:
        event["note"] = note
    return event


def append_event(path: Path, event: dict) -> None:
    errors = event_errors(event)
    if errors:
        raise ValueError("invalid progress event:\n" + "\n".join(errors))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def latest_events(events: list[dict]) -> dict[str, dict]:
    """Last event per plan item; later events supersede earlier ones."""

    latest: dict[str, dict] = {}
    for event in events:
        latest[event["plan_item_id"]] = event
    return latest


def path_state(events: list[dict], student_id: str, node_id: str) -> dict:
    """Split this student's events into completed snapshots and started items."""

    relevant = [event for event in events if event["student_id"] == student_id and event["node_id"] == node_id]
    latest = latest_events(relevant)
    completed = []
    started = []
    for event in sorted(latest.values(), key=lambda item: (item["plan_version"], item["seq"])):
        if event["event_type"] == "completed":
            completed.append(
                {
                    "plan_item_id": event["plan_item_id"],
                    "plan_version": event["plan_version"],
                    "seq": event["seq"],
                    "issue_id": event["issue_id"],
                    "knowledge_ids": [event["knowledge_id"]],
                    "material_ids": list(event["material_ids"]),
                    "activity_type": event["activity_type"],
                    "status": "completed",
                    "completed_at": event["created_at"],
                    **({"note": event["note"]} if event.get("note") else {}),
                }
            )
        else:
            started.append(dict(event))
    return {
        "events": relevant,
        "completed": completed,
        "started": started,
        "unmatched": 0,
    }


def merge_history(previous: dict | None, completed: list[dict]) -> list[dict]:
    """Keep every completed item forever; new events append, never replace."""

    history = list((previous or {}).get("history") or [])
    seen = {item["plan_item_id"] for item in history}
    for item in completed:
        if item["plan_item_id"] not in seen:
            history.append(item)
            seen.add(item["plan_item_id"])
    return history
