"""Read-only material catalog for Task-3 recommendations.

The knowledge base is the Task-1 artifact.  Task 3 never invents material IDs:
every candidate comes from ``materials`` and every assessment candidate must be
mapped through ``qmatrix``.  Textbook slices without a knowledge mapping remain
available at objective level only.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def load_knowledge_base(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [key for key in ("materials", "knowledge", "qmatrix", "edges") if key not in data]
    if missing:
        raise ValueError(f"knowledge base missing keys: {missing}")
    return data


def parse_rubric(raw) -> list[dict]:
    """Return rubric points as ``{point_id, text, max_score}``.

    A malformed rubric is a data error, not a reason to guess.  The recommendation
    layer only uses rubric text to prefer a matching practice item.
    """

    if raw in (None, ""):
        return []
    items = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(items, list):
        raise ValueError("rubric_json must be a JSON array")
    result = []
    for item in items:
        if not isinstance(item, dict) or "id" not in item or "text" not in item:
            raise ValueError("rubric item must contain id/text/points")
        result.append(
            {
                "point_id": str(item["id"]),
                "text": str(item["text"]),
                "max_score": float(item.get("points", 0)),
            }
        )
    return result


def build_catalog(knowledge_base: dict) -> dict:
    knowledge_rows = knowledge_base["knowledge"]
    objective_rows = knowledge_base.get("objectives", [])
    material_rows = knowledge_base["materials"]
    qmatrix_rows = knowledge_base["qmatrix"]
    edge_rows = knowledge_base["edges"]

    objective_order = {
        row["objective_id"]: index for index, row in enumerate(objective_rows)
    }
    if not objective_order:
        objective_order = {
            row["objective_id"]: index
            for index, row in enumerate(
                sorted({knowledge_row["objective_id"] for knowledge_row in knowledge_rows})
            )
        }
    knowledge = {}
    for index, row in enumerate(knowledge_rows):
        knowledge[row["knowledge_id"]] = {
            "knowledge_id": row["knowledge_id"],
            "objective_id": row["objective_id"],
            "name": row["name"],
            "cognitive_type": row.get("cognitive_type"),
            "sort_order": int(row.get("sort_order", index) or 0),
        }

    material_ids = {row["material_id"] for row in material_rows}
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in qmatrix_rows:
        if float(row.get("weight", 1) or 0) <= 0:
            continue
        if row["material_id"] not in material_ids:
            raise ValueError(f"qmatrix refers to unknown material {row['material_id']}")
        if row["knowledge_id"] not in knowledge:
            raise ValueError(f"qmatrix refers to unknown knowledge {row['knowledge_id']}")
        mapping[row["material_id"]].add(row["knowledge_id"])

    materials = {}
    for row in material_rows:
        material_id = row["material_id"]
        materials[material_id] = {
            "material_id": material_id,
            "title": row.get("title") or material_id,
            "body": row.get("body") or "",
            "material_type": row.get("material_type") or "reference",
            "item_format": row.get("item_format"),
            "objective_id": row.get("objective_id"),
            "difficulty": row.get("difficulty"),
            "est_minutes": row.get("est_minutes"),
            "rubric": parse_rubric(row.get("rubric_json")),
            "knowledge_ids": sorted(mapping.get(material_id, set())),
        }

    by_knowledge: dict[str, list[str]] = defaultdict(list)
    explain_by_knowledge: dict[str, list[str]] = defaultdict(list)
    for material_id, material in materials.items():
        for kid in material["knowledge_ids"]:
            by_knowledge[kid].append(material_id)
            if material["material_type"] == "explain":
                explain_by_knowledge[kid].append(material_id)
    for values in (*by_knowledge.values(), *explain_by_knowledge.values()):
        values.sort()

    references_by_objective: dict[str, list[str]] = defaultdict(list)
    for material_id, material in materials.items():
        if material["material_type"] == "reference" and material["objective_id"]:
            references_by_objective[material["objective_id"]].append(material_id)

    prerequisites: dict[str, list[str]] = defaultdict(list)
    for edge in edge_rows:
        if edge.get("edge_type") != "prerequisite":
            continue
        source, target = edge.get("from_id"), edge.get("to_id")
        if source in knowledge and target in knowledge:
            prerequisites[target].append(source)

    return {
        "materials": materials,
        "knowledge": knowledge,
        "objective_order": objective_order,
        "by_knowledge": dict(by_knowledge),
        "explain_by_knowledge": dict(explain_by_knowledge),
        "references_by_objective": dict(references_by_objective),
        "prerequisites": dict(prerequisites),
    }
