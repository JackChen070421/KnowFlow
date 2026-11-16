"""Explainable probe selection (heuristic, not a measurement model).

The official materials carry no difficulty, discrimination or response model, so
this module never claims IRT-style information. It scores only observable facts:
Q-matrix coverage, current unresolved knowledge, reviewed prerequisite value,
material completeness, redundancy and prior exposure. Every component is
recorded so the choice can be recomputed by hand.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

PROBE_POLICY_VERSION = "probe-heuristic-1"
COMPONENTS = (
    "issue_relevance",
    "coverage_gain",
    "prerequisite_value",
    "material_quality",
    "redundancy_penalty",
)


@dataclass(frozen=True)
class ProbeWeights:
    """Configurable weights; recorded in run_manifest and in the product."""

    issue_relevance: float = 1.5
    coverage_gain: float = 2.0
    prerequisite_value: float = 1.0
    material_quality: float = 0.5
    redundancy_penalty: float = 1.0

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def __post_init__(self) -> None:
        if any(value < 0 for value in asdict(self).values()):
            raise ValueError("probe weights must be non-negative")


def _material_quality(material: dict) -> float:
    rubric = material.get("rubric") or []
    quality = 1.0 if rubric and all(point["max_score"] > 0 for point in rubric) else 0.0
    if material.get("item_format") in {"blank", "choice"}:
        quality += 0.5
    return quality


def eligible_materials(
    *,
    knowledge_id: str,
    catalog: dict,
    node_available: set[str],
    attempted: set[str],
    pending: set[str],
    scored: set[str],
    disputed: set[str],
) -> list[str]:
    """Assessment items for this knowledge that may serve as new observation."""

    eligible = []
    for material_id, material in catalog["materials"].items():
        if material["material_type"] != "assessment":
            continue
        if knowledge_id not in material["knowledge_ids"]:
            continue
        if material_id not in node_available:
            continue
        if material_id in attempted or material_id in pending or material_id in scored:
            continue
        if material_id in disputed:
            continue
        eligible.append(material_id)
    return sorted(eligible)


def score_probes(
    issue: dict,
    *,
    profile: dict,
    catalog: dict,
    node_available: set[str],
    attempted: set[str],
    pending: set[str],
    scored: set[str],
    disputed: set[str],
    unresolved_knowledge: set[str],
    selected: list[str],
    weights: ProbeWeights,
) -> list[dict]:
    """Score every eligible probe for one issue; return all components, sorted."""

    knowledge_id = issue["knowledge_id"]
    prerequisites = {
        entry["source_knowledge_id"]
        for entry in catalog.get("reviewed_prerequisites", {}).get(knowledge_id, [])
    }
    candidates = []
    for material_id in eligible_materials(
        knowledge_id=knowledge_id,
        catalog=catalog,
        node_available=node_available,
        attempted=attempted,
        pending=pending,
        scored=scored,
        disputed=disputed,
    ):
        material = catalog["materials"][material_id]
        knowledge_ids = set(material["knowledge_ids"])
        coverage = len(knowledge_ids & unresolved_knowledge)
        relevance = 1.0 if knowledge_id in knowledge_ids else 0.0
        prerequisite_hits = len(knowledge_ids & prerequisites)
        quality = _material_quality(material)
        redundancy = sum(
            1 for chosen in selected if set(catalog["materials"][chosen]["knowledge_ids"]) & knowledge_ids
        )
        components = {
            "issue_relevance": relevance,
            "coverage_gain": float(coverage),
            "prerequisite_value": float(prerequisite_hits),
            "material_quality": float(quality),
            "redundancy_penalty": -float(redundancy),
        }
        total = sum(weights.as_dict()[name] * value for name, value in components.items())
        reasons = [f"覆盖 {coverage} 个待确认知识点"] if coverage else []
        if relevance:
            reasons.append("命中当前问题的知识点")
        if prerequisite_hits:
            reasons.append(f"可作为 {prerequisite_hits} 个先修知识点的检查")
        if quality >= 1.0:
            reasons.append("题目有完整评分点")
        if redundancy:
            reasons.append(f"与已选题目重复 {redundancy} 个知识点")
        candidates.append(
            {
                "material_id": material_id,
                "total": round(total, 6),
                "components": components,
                "reasons": reasons,
            }
        )
    candidates.sort(key=lambda item: (-item["total"], -item["components"]["coverage_gain"], item["material_id"]))
    return candidates


def select_probes(
    issue: dict,
    *,
    profile: dict,
    catalog: dict,
    node_available: set[str],
    attempted: set[str],
    pending: set[str],
    scored: set[str],
    disputed: set[str],
    unresolved_knowledge: set[str],
    selected: list[str],
    weights: ProbeWeights,
    limit: int = 3,
) -> tuple[list[str], list[dict]]:
    candidates = score_probes(
        issue,
        profile=profile,
        catalog=catalog,
        node_available=node_available,
        attempted=attempted,
        pending=pending,
        scored=scored,
        disputed=disputed,
        unresolved_knowledge=unresolved_knowledge,
        selected=selected,
        weights=weights,
    )
    return [item["material_id"] for item in candidates[:limit]], candidates


def scoring_block(
    weights: ProbeWeights,
    candidates: list[dict],
    limit: int = 10,
    must_include: set[str] | None = None,
) -> dict:
    ordered = list(candidates)
    if must_include:
        required = [item for item in ordered if item["material_id"] in must_include]
        rest = [item for item in ordered if item["material_id"] not in must_include]
        ordered = required + rest[: max(0, limit - len(required))]
    return {
        "policy_version": PROBE_POLICY_VERSION,
        "weights": weights.as_dict(),
        "candidates": ordered[: max(limit, len(must_include or ()))],
    }
