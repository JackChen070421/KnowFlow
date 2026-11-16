"""Formal curriculum graph: schema, structure checks and read-only indexes.

The graph is an authored teaching asset, not student data. Every edge carries a
stable ID, a type, its provenance and a review status. Only ``reviewed``
prerequisites may influence ordering; everything else is display/prompt material.
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.contracts import build_registry, repo_root

SCHEMA_NAME = "output/curriculum_graph.schema.json"
SYMMETRIC_TYPES = {"confusable_with", "related_to"}
RELATION_TYPES = {"prerequisite", "confusable_with", "related_to"}
REVIEWED = "reviewed"


@lru_cache(maxsize=1)
def schema_validator() -> Draft202012Validator:
    root = repo_root()
    schema = json.loads((root / "schemas" / SCHEMA_NAME).read_text(encoding="utf-8"))
    return Draft202012Validator(
        schema, registry=build_registry(root), format_checker=FormatChecker()
    )


def schema_errors(graph: dict) -> list[str]:
    return [
        f"curriculum_graph:{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in schema_validator().iter_errors(graph)
    ]


def load_graph(path: Path | str) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"curriculum graph not found: {path}")
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    return graph


def _cycle_path(edges: dict[str, list[str]]) -> list[str] | None:
    """Return one readable cycle in the prerequisite subgraph, if any."""

    colour: dict[str, int] = {}
    stack: list[str] = []
    position: dict[str, int] = {}

    def visit(node: str) -> list[str] | None:
        colour[node] = 1
        position[node] = len(stack)
        stack.append(node)
        for child in edges.get(node, []):
            if colour.get(child) == 1:
                return stack[position[child] :] + [child]
            if colour.get(child, 0) == 0:
                found = visit(child)
                if found:
                    return found
        stack.pop()
        position.pop(node)
        colour[node] = 2
        return None

    for node in sorted(edges):
        if colour.get(node, 0) == 0:
            found = visit(node)
            if found:
                return found
    return None


def validate_graph(graph: dict, knowledge_ids: set[str] | None = None) -> None:
    """Raise ``ValueError`` with a readable message on the first structural fault.

    ``knowledge_ids`` enables endpoint-existence checks for K-xx endpoints; CI
    can validate the committed graph without the (Git-ignored) canonical tables.
    """

    errors = schema_errors(graph)
    if errors:
        raise ValueError(errors[0])

    nodes = graph["nodes"]
    edges = graph["edges"]
    node_ids = [node["node_id"] for node in nodes]
    if len(set(node_ids)) != len(node_ids):
        raise ValueError("curriculum_graph: duplicate node_id")
    edge_ids = [edge["edge_id"] for edge in edges]
    if len(set(edge_ids)) != len(edge_ids):
        raise ValueError("curriculum_graph: duplicate edge_id")

    counts = graph["counts"]
    expected = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "prerequisite_count": sum(edge["relation_type"] == "prerequisite" for edge in edges),
        "confusable_count": sum(edge["relation_type"] == "confusable_with" for edge in edges),
        "related_count": sum(edge["relation_type"] == "related_to" for edge in edges),
        "draft_count": sum(edge["review_status"] == "draft" for edge in edges),
        "reviewed_count": sum(edge["review_status"] == "reviewed" for edge in edges),
    }
    if counts != expected:
        raise ValueError(f"curriculum_graph: counts mismatch, expected {expected}")

    known_nodes = set(node_ids)
    known = set(known_nodes) | set(knowledge_ids or set())
    for edge in edges:
        edge_id = edge["edge_id"]
        source, target = edge["source_node_id"], edge["target_node_id"]
        if source == target:
            raise ValueError(f"{edge_id}: self loop")
        for endpoint in (source, target):
            if endpoint.startswith("C-") and endpoint not in known_nodes:
                raise ValueError(f"{edge_id}: unknown textbook node {endpoint}")
            if endpoint.startswith("K-") and knowledge_ids is not None and endpoint not in known:
                raise ValueError(f"{edge_id}: unknown knowledge {endpoint}")
        if edge["relation_type"] in SYMMETRIC_TYPES and not source < target:
            raise ValueError(
                f"{edge_id}: symmetric relation {edge['relation_type']} must be stored "
                "canonically with source_node_id < target_node_id"
            )

    seen: dict[tuple[str, str, str], str] = {}
    symmetric_pairs: dict[tuple[str, str, str], str] = {}
    prerequisite_adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        relation = edge["relation_type"]
        if relation == "prerequisite":
            key = ("prerequisite", edge["source_node_id"], edge["target_node_id"])
            if key in seen:
                raise ValueError(
                    f"{edge['edge_id']}: duplicate prerequisite edge "
                    f"{key[1]} -> {key[2]} (also {seen[key]})"
                )
            seen[key] = edge["edge_id"]
            prerequisite_adjacency[edge["source_node_id"]].append(edge["target_node_id"])
        else:
            pair = (relation, *sorted((edge["source_node_id"], edge["target_node_id"])))
            if pair in symmetric_pairs:
                raise ValueError(
                    f"{edge['edge_id']}: duplicate {relation} edge ({pair[1]}, {pair[2]}) "
                    f"already stored as {symmetric_pairs[pair]}"
                )
            symmetric_pairs[pair] = edge["edge_id"]

    cycle = _cycle_path(prerequisite_adjacency)
    if cycle:
        raise ValueError("curriculum_graph: prerequisite cycle: " + " -> ".join(cycle))


def graph_warnings(graph: dict) -> list[str]:
    """Non-fatal observations: isolated nodes, and how many relations are unreviewed."""

    touched = {edge["source_node_id"] for edge in graph["edges"]} | {
        edge["target_node_id"] for edge in graph["edges"]
    }
    warnings = [
        f"isolated textbook node (no relation): {node['node_id']}"
        for node in graph["nodes"]
        if node["node_id"] not in touched
    ]
    draft = sum(edge["review_status"] != "reviewed" for edge in graph["edges"])
    if draft:
        warnings.append(f"{draft} of {len(graph['edges'])} relations are not reviewed")
    return warnings


def graph_index(graph: dict) -> dict:
    """Read-only view used by the catalog and the recommendation rules."""

    nodes = {node["node_id"]: node for node in graph["nodes"]}
    knowledge_prerequisites: dict[str, list[dict]] = defaultdict(list)
    knowledge_confusable: dict[str, list[dict]] = defaultdict(list)
    knowledge_related: dict[str, list[dict]] = defaultdict(list)
    node_edges: dict[str, list[dict]] = defaultdict(list)
    for edge in graph["edges"]:
        for endpoint in (edge["source_node_id"], edge["target_node_id"]):
            node_edges[endpoint].append(edge)
        relation = edge["relation_type"]
        if relation == "prerequisite":
            if edge["target_node_id"].startswith("K-"):
                knowledge_prerequisites[edge["target_node_id"]].append(edge)
            continue
        bucket = knowledge_confusable if relation == "confusable_with" else knowledge_related
        for endpoint in (edge["source_node_id"], edge["target_node_id"]):
            if endpoint.startswith("K-"):
                bucket[endpoint].append(edge)
    return {
        "graph_id": graph["graph_id"],
        "version": graph["version"],
        "nodes": nodes,
        "edges": graph["edges"],
        "knowledge_prerequisites": dict(knowledge_prerequisites),
        "knowledge_confusable": dict(knowledge_confusable),
        "knowledge_related": dict(knowledge_related),
        "node_edges": dict(node_edges),
    }


def prerequisite_partners(index: dict, knowledge_id: str, reviewed_only: bool) -> list[dict]:
    """Direct prerequisites of a knowledge point, optionally reviewed only."""

    partners = []
    for edge in index["knowledge_prerequisites"].get(knowledge_id, []):
        if reviewed_only and edge["review_status"] != REVIEWED:
            continue
        partners.append(edge)
    return partners


def confusable_partners(index: dict, knowledge_id: str, reviewed_only: bool = False) -> list[dict]:
    return [
        edge
        for edge in index["knowledge_confusable"].get(knowledge_id, [])
        if not reviewed_only or edge["review_status"] == REVIEWED
    ]
