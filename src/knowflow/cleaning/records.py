"""Keep event revisions separate from independent attempts at other nodes."""

from collections import Counter, defaultdict
from datetime import datetime

STATES = ("observed_correct", "observed_wrong", "assigned_not_attempted", "pending", "unobserved")


def evidence_state(record: dict) -> str:
    if not record["attempted"]:
        return "assigned_not_attempted"
    if record["score"] is None:
        return "pending"
    return "observed_correct" if record["score"] == record["max_score"] else "observed_wrong"


def clean_records(candidates: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Select latest revision *before* rejecting bad scores: never revive an old grade.

    Private adapter keys begin with '_'. Every input row gets exactly one decision.
    Ambiguous identity/order rejects the event rather than silently guessing.
    """
    groups = defaultdict(list)
    ids = Counter(r["record_id"] for r in candidates if r["record_id"] is not None)
    for row in candidates:
        key = row["event_id"] or f"invalid-row-{row['_row']}"
        groups[key].append(row)
    kept, decisions, anomalies = [], [], []
    for group in groups.values():
        ambiguous = any(r.get("_order_invalid") or ids[r["record_id"]] > 1 for r in group)
        identities = {(r["student_id"], r["node_id"], r["material_id"]) for r in group}
        ambiguous = ambiguous or len(identities) != 1
        if ambiguous:
            for row in group:
                reasons = list(dict.fromkeys(row["_errors"] + ["ambiguous_event_or_record_id"]))
                decisions.append(_decision(row, "rejected", reasons))
                anomalies.append(_anomaly(row, reasons, "quarantined; no older grade restored"))
            continue
        ordered = sorted(
            group,
            key=lambda r: (
                r["attempt_no"],
                datetime.fromisoformat(r["submitted_at"]),
                r["record_id"] or "",
            ),
        )
        latest = ordered[-1]
        for row in ordered[:-1]:
            decisions.append(_decision(row, "superseded", ["newer_revision"] + row["_errors"]))
            if row["_errors"]:
                anomalies.append(_anomaly(row, row["_errors"], "superseded by a later revision"))
        if latest["_errors"]:
            decisions.append(_decision(latest, "rejected", latest["_errors"]))
            anomalies.append(
                _anomaly(latest, latest["_errors"], "quarantined; no older grade restored")
            )
        else:
            decisions.append(_decision(latest, "retained", latest["_warnings"]))
            if latest["_warnings"]:
                anomalies.append(
                    _anomaly(
                        latest,
                        latest["_warnings"],
                        "official total retained; unreliable point scores omitted",
                    )
                )
            kept.append({k: v for k, v in latest.items() if not k.startswith("_")})
    # A malformed event identifier must not make the same material count twice.
    counts = Counter((r["student_id"], r["node_id"], r["material_id"]) for r in kept)
    bad = {
        r["record_id"] for r in kept if counts[r["student_id"], r["node_id"], r["material_id"]] > 1
    }
    for decision in decisions:
        if decision["decision"] == "retained" and decision["record_id"] in bad:
            decision.update(
                decision="rejected", reasons=["multiple_events_for_same_student_node_material"]
            )
            anomalies.append(
                {
                    "record_id": decision["record_id"],
                    "reason": decision["reasons"][0],
                    "action": "quarantined",
                }
            )
    return (
        sorted((r for r in kept if r["record_id"] not in bad), key=lambda r: r["record_id"]),
        sorted(decisions, key=lambda d: d["source_row"]),
        anomalies,
    )


def _decision(row, decision, reasons):
    return {
        "source_row": row["_row"],
        "record_id": row["record_id"],
        "decision": decision,
        "reasons": reasons,
    }


def _anomaly(row, reasons, action):
    return {"record_id": row["record_id"], "reason": "; ".join(reasons), "action": action}
