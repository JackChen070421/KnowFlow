"""Replay feedback events onto a recommendation and expose stable state."""

from __future__ import annotations

from collections import defaultdict


def _sorted(events: list[dict]) -> list[dict]:
    return sorted(events, key=lambda event: (event["created_at"], event["event_id"]))


def state_for(events: list[dict], student_id: str, node_id: str) -> dict:
    relevant = [
        event
        for event in events
        if event["student_id"] == student_id and event["node_id"] == node_id
    ]
    items: dict[str, dict] = {}
    comments: dict[str, list[dict]] = defaultdict(list)
    general_comments: list[dict] = []
    student_feedback: list[dict] = []
    for event in _sorted(relevant):
        kind = event["event_type"]
        if kind == "teacher_adjustment":
            entry = items.setdefault(
                event["plan_item_id"],
                {
                    "locked": False,
                    "removed": False,
                    "materials": None,
                    "est_minutes": None,
                    "difficulty": None,
                    "adjustments": [],
                    "snapshot": {},
                },
            )
            entry["adjustments"].append(event)
            if event.get("snapshot"):
                entry["snapshot"].update(event["snapshot"])
            action = event["action"]
            if action == "lock":
                entry["locked"] = True
                entry["removed"] = False
            elif action == "unlock":
                entry["locked"] = False
            elif action == "remove":
                entry["removed"] = True
                entry["locked"] = False
            elif action == "restore":
                entry["removed"] = False
            elif action == "replace_materials":
                entry["materials"] = list(event["payload"]["material_ids"])
            elif action == "set_time":
                entry["est_minutes"] = event["payload"]["est_minutes"]
            elif action == "set_difficulty":
                entry["difficulty"] = event["payload"]["difficulty"]
        elif kind == "teacher_comment":
            item_id = event.get("plan_item_id")
            record = {
                "event_id": event["event_id"],
                "text": event["text"],
                "actor": event["actor"],
                "created_at": event["created_at"],
                "issue_id": event.get("issue_id"),
            }
            if item_id:
                comments[item_id].append(record)
            else:
                general_comments.append(record)
        elif kind == "student_feedback":
            student_feedback.append(event)
    return {
        "events": relevant,
        "items": items,
        "comments": dict(comments),
        "general_comments": general_comments,
        "student_feedback": student_feedback,
    }


def locked_items(state: dict) -> list[dict]:
    locked = []
    for plan_item_id, entry in state["items"].items():
        if not entry["locked"] or entry["removed"]:
            continue
        snapshot = entry["snapshot"]
        if not snapshot.get("issue_id") or not snapshot.get("knowledge_id"):
            continue
        locked.append(
            {
                "plan_item_id": plan_item_id,
                "issue_id": snapshot["issue_id"],
                "knowledge_id": snapshot["knowledge_id"],
                "activity_type": snapshot.get("activity_type", "consolidate"),
                "seq": int(snapshot.get("seq", 1)),
                "material_ids": list(entry["materials"] or snapshot.get("material_ids") or []),
                "est_minutes": entry["est_minutes"] or snapshot.get("est_minutes"),
                "difficulty": entry["difficulty"] or snapshot.get("difficulty"),
                "reason": next(
                    (
                        event["reason"]
                        for event in reversed(entry["adjustments"])
                        if event["action"] == "lock"
                    ),
                    "教师锁定",
                ),
                "event_id": entry["adjustments"][-1]["event_id"],
            }
        )
    return sorted(locked, key=lambda item: (item["seq"], item["plan_item_id"]))


def removed_items(state: dict) -> list[dict]:
    removed = []
    for plan_item_id, entry in state["items"].items():
        if not entry["removed"]:
            continue
        snapshot = entry["snapshot"]
        removed.append(
            {
                "plan_item_id": plan_item_id,
                "issue_id": snapshot.get("issue_id"),
                "knowledge_id": snapshot.get("knowledge_id"),
                "reason": next(
                    (
                        event["reason"]
                        for event in reversed(entry["adjustments"])
                        if event["action"] == "remove"
                    ),
                    "教师移除",
                ),
                "event_id": entry["adjustments"][-1]["event_id"],
            }
        )
    return removed


def apply_to_recommendation(rec: dict, state: dict, catalog: dict) -> dict:
    unmatched = []
    applied = []
    by_item = {item["plan_item_id"]: item for item in rec.get("plan", []) if item.get("plan_item_id")}
    by_issue = {item["issue_id"]: item for item in rec.get("plan", [])}
    by_knowledge = {
        item["knowledge_ids"][0]: item for item in rec.get("plan", []) if item.get("knowledge_ids")
    }
    for plan_item_id, entry in state["items"].items():
        snapshot = entry["snapshot"]
        item = (
            by_item.get(plan_item_id)
            or by_issue.get(snapshot.get("issue_id"))
            or by_knowledge.get(snapshot.get("knowledge_id"))
        )
        if item is None:
            if entry["adjustments"]:
                unmatched.append(plan_item_id)
            continue
        if entry["removed"]:
            unmatched.append(plan_item_id)
            continue
        if entry["materials"]:
            materials = [mid for mid in entry["materials"] if mid in catalog["materials"]]
            if materials:
                item["material_ids"] = materials
                item["primary_material_id"] = materials[0]
                if "completion_condition" in item:
                    item["completion_condition"]["material_ids"] = materials
        if entry["est_minutes"] is not None:
            item["est_minutes"] = entry["est_minutes"]
        if entry["difficulty"] is not None:
            item["difficulty"] = entry["difficulty"]
        if entry["locked"]:
            item["teacher_locked"] = True
        item["adjustments"] = [
            {
                "event_id": event["event_id"],
                "action": event["action"],
                "reason": event.get("reason"),
                "actor": event["actor"],
                "created_at": event["created_at"],
            }
            for event in entry["adjustments"]
        ]
        applied.append(item["plan_item_id"])
    for item in rec.get("plan", []):
        comments = state["comments"].get(item.get("plan_item_id"), [])
        extra = [
            comment
            for item_comments in state["comments"].values()
            for comment in item_comments
            if comment.get("issue_id") == item["issue_id"]
        ]
        merged_comments = {comment["event_id"]: comment for comment in comments + extra}
        if merged_comments:
            item["teacher_comments"] = list(merged_comments.values())
        feedback_items = [
            event
            for event in state["student_feedback"]
            if event.get("plan_item_id") == item.get("plan_item_id")
            or (event.get("issue_id") and event["issue_id"] == item["issue_id"])
        ]
        if feedback_items:
            item["student_feedback"] = [
                {
                    "event_id": event["event_id"],
                    "kind": event["kind"],
                    "rating": event.get("rating"),
                    "text": event.get("text"),
                    "created_at": event["created_at"],
                }
                for event in feedback_items
            ]
    has_plan_feedback = any(
        entry["adjustments"] for entry in state["items"].values()
    ) or bool(state["comments"]) or bool(state["general_comments"])
    feedback = {
        "applied": has_plan_feedback,
        "source": "local_feedback",
        "events": len(state["events"]),
        "teacher_adjustments": sum(
            1 for event in state["events"] if event["event_type"] == "teacher_adjustment"
        ),
        "student_feedback": len(state["student_feedback"]),
        "comments": sum(len(value) for value in state["comments"].values())
        + len(state["general_comments"]),
        "applied_items": applied,
        "unmatched_items": unmatched,
    }
    if state["general_comments"]:
        feedback["general_comments"] = state["general_comments"]
    if state["student_feedback"]:
        feedback["student_feedback_items"] = [
            {
                "event_id": event["event_id"],
                "plan_item_id": event.get("plan_item_id"),
                "kind": event["kind"],
                "rating": event.get("rating"),
                "text": event.get("text"),
                "created_at": event["created_at"],
            }
            for event in state["student_feedback"]
        ]
    rec["feedback"] = feedback
    return rec
