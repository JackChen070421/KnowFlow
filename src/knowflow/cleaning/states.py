"""Evidence-state bucketing — the layer-4 boundary of the data pipeline.

These functions only **count evidence**; they do not judge a student. Anything
that turns counts into a conclusion (mastery, ``confirmed_weak``, coverage
ratios, recommendations) belongs to ``diagnosis/`` and is out of scope here.

Keeping the bucketing out of ``src/knowflow/io/`` is deliberate: the data layer
must not grow diagnosis semantics, or M2 will implement them twice.
"""

from __future__ import annotations

STATES = (
    "observed_correct",
    "observed_wrong",
    "assigned_not_attempted",
    "pending",
    "unobserved",
)


def classify_state(record: dict[str, object]) -> str:
    """Bucket one record by its evidence fields only."""

    if not record["attempted"]:
        return "assigned_not_attempted"
    if record["score"] is None:
        return "pending"
    return "observed_correct" if record["is_correct"] else "observed_wrong"


def state_counts(records: list[dict[str, object]]) -> dict[str, int]:
    """Five-state counts over the canonical records."""

    counts = {state: 0 for state in STATES}
    for record in records:
        counts[classify_state(record)] += 1
    return counts
