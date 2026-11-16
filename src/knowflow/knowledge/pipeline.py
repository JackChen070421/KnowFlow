"""Build a traceable knowledge base without inferring unsupported relationships."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict, deque
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from knowflow.contracts import build_registry, load_json, repo_root

from .graph import validate_graph

TABLES = {
    "objectives": "objective",
    "knowledge": "knowledge",
    "materials": "material",
    "qmatrix": "qmatrix",
    "edges": "edge",
}

GRAPH_PATCH_FIELDS = {
    "review_status",
    "source_reference",
    "rationale",
    "evidence_level",
    "updated_version",
    "note",
}
GRAPH_REQUIRED_EDGE_FIELDS = {
    "edge_id",
    "source_node_id",
    "target_node_id",
    "relation_type",
    "source_reference",
    "rationale",
    "review_status",
    "evidence_level",
}


def _schema(name):
    return load_json(repo_root() / "schemas" / "input" / f"{name}.schema.json")


def _coerce(value, spec):
    types = spec.get("type", "string")
    types = [types] if isinstance(types, str) else types
    if value == "" and "null" in types:
        return None
    if "string" in types:
        return value  # Preserve original text, including whitespace.
    if "boolean" in types:
        if value.lower() not in {"true", "false"}:
            raise ValueError("invalid boolean")
        return value.lower() == "true"
    if "integer" in types:
        return int(value)
    if "number" in types:
        return float(value)
    return value


def load_tables(base: Path) -> dict:
    tables = {}
    for name in TABLES:
        schema = _schema(name)
        with (base / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            if (
                len(fields) != len(set(fields))
                or set(fields) - schema["properties"].keys()
                or set(schema["required"]) - set(fields)
            ):
                raise ValueError(f"{name}: invalid CSV header")
            rows = []
            for index, row in enumerate(reader, 2):
                try:
                    if None in row or None in row.values():
                        raise ValueError("invalid row width")
                    rows.append(
                        {
                            key: _coerce(value, schema["properties"][key])
                            for key, value in row.items()
                        }
                    )
                except (ValueError, TypeError):
                    raise ValueError(f"{name}: invalid CSV row {index}") from None
            tables[name] = rows
    return tables


def _acyclic(pairs, label):
    adjacency = defaultdict(set)
    degree = defaultdict(int)
    for start, end in pairs:
        degree.setdefault(start, 0)
        if end not in adjacency[start]:
            adjacency[start].add(end)
            degree[end] += 1
    queue = deque(node for node, count in degree.items() if count == 0)
    seen = 0
    while queue:
        node = queue.popleft()
        seen += 1
        for child in adjacency[node]:
            degree[child] -= 1
            if degree[child] == 0:
                queue.append(child)
    if seen != len(degree):
        raise ValueError(f"{label}: cycle")


def validate_knowledge_base(data: dict) -> None:
    schema = load_json(repo_root() / "schemas/output/knowledge_base.schema.json")
    validator = Draft202012Validator(
        schema, registry=build_registry(), format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    for error in validator.iter_errors(data):
        raise ValueError(
            f"knowledge_base schema: {'/'.join(map(str, error.absolute_path))} ({error.validator})"
        )
    for name, singular in TABLES.items():
        keys = _schema(name)["x-primary-key"]
        identities = [tuple(row.get(key) for key in keys) for row in data[name]]
        if len(set(identities)) != len(identities):
            raise ValueError(f"{name}: duplicate primary key")
        if data["counts"][f"{singular}_count"] != len(identities):
            raise ValueError(f"{name}: count mismatch")
    objectives = {r["objective_id"] for r in data["objectives"]}
    knowledge = {r["knowledge_id"] for r in data["knowledge"]}
    materials = {r["material_id"] for r in data["materials"]}
    all_ids = objectives | knowledge | materials

    def ref(value, allowed):
        if value is not None and value not in allowed:
            raise ValueError("knowledge_base: dangling reference")

    for row in data["objectives"]:
        ref(row.get("source_material_id"), materials)
        if (row["subject"], row["grade"]) != (data["subject"], data["grade"]):
            raise ValueError("objectives: mixed subject/grade")
        if not row["source_locator"].strip() or not row["objective_text"].strip():
            raise ValueError("objectives: missing source/text")
    parents = []
    for row in data["knowledge"]:
        ref(row["objective_id"], objectives)
        ref(row.get("parent_id"), knowledge)
        if row.get("parent_id"):
            parents.append((row["parent_id"], row["knowledge_id"]))
    for row in data["materials"]:
        ref(row.get("objective_id"), objectives)
    for row in data["qmatrix"]:
        ref(row["material_id"], materials)
        ref(row["knowledge_id"], knowledge)
    assessed = {
        r["material_id"]
        for r in data["materials"]
        if r["material_type"] in {"practice", "assessment"}
    }
    mapped = {r["material_id"] for r in data["qmatrix"]}
    covered = {r["knowledge_id"] for r in data["qmatrix"] if r["material_id"] in assessed}
    if assessed - mapped or knowledge - covered:
        raise ValueError("qmatrix: missing assessment coverage")
    for row in data["edges"]:
        ref(row["from_id"], all_ids)
        ref(row["to_id"], all_ids)
        if row["from_id"] == row["to_id"]:
            raise ValueError("edges: self loop")
    _acyclic(parents, "knowledge parents")
    for kind in ("contains", "prerequisite"):
        pairs = [(r["from_id"], r["to_id"]) for r in data["edges"] if r["edge_type"] == kind]
        _acyclic(pairs + (parents if kind == "contains" else []), kind)
    graph = data.get("curriculum_graph")
    if graph is not None:
        validate_graph(graph, knowledge)
        for node in graph["nodes"]:
            if not set(node["knowledge_ids"]) <= knowledge:
                raise ValueError("curriculum_graph: node maps to unknown knowledge")
            if node["material_id"] not in materials:
                raise ValueError("curriculum_graph: node refers to unknown material")


def build_knowledge_base(
    base: Path, dataset_id: str, generated_at: str | None = None, graph: dict | None = None
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dataset_id):
        raise ValueError("invalid dataset ID")
    tables = load_tables(Path(base))
    if not tables["objectives"]:
        raise ValueError("objectives: empty")
    first = tables["objectives"][0]
    result = dict(
        schema_version="1.0.0",
        dataset_id=dataset_id,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        subject=first["subject"],
        grade=first["grade"],
        counts={f"{singular}_count": len(tables[name]) for name, singular in TABLES.items()},
        **tables,
    )
    if graph is not None:
        result["curriculum_graph"] = deepcopy(graph)
    validate_knowledge_base(result)
    return result


def write_knowledge_base(data: dict, output: Path) -> Path:
    validate_knowledge_base(data)
    output = output.resolve()
    root = repo_root().resolve()
    if output.is_relative_to(root) and not output.is_relative_to(root / "artifacts"):
        raise ValueError("repository outputs must be under artifacts/ (Git-ignored)")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return output


def apply_curation(data: dict, curation: dict, base: Path) -> dict:
    """Apply reviewed local annotations without changing diagnostic IDs or mappings.

    Curation is dataset-specific local data, never a new canonical table.
    Hashes pin all five input files; only source text, descriptions, edges and
    the curriculum graph's review/provenance fields vary.
    """
    required = {"dataset_id", "source_sha256", "objectives", "knowledge", "edges"}
    allowed = required | {"curriculum_graph"}
    if not required <= set(curation) or set(curation) - allowed:
        raise ValueError("curation: unexpected/missing fields")
    if curation["dataset_id"] != data["dataset_id"]:
        raise ValueError("curation: dataset mismatch")
    expected = {
        f"{name}.csv": hashlib.sha256((base / f"{name}.csv").read_bytes()).hexdigest()
        for name in TABLES
    }
    if curation["source_sha256"] != expected:
        raise ValueError("curation: source hashes changed; review annotations again")
    result = deepcopy(data)
    for table, key, allowed_fields in (
        ("objectives", "objective_id", {"objective_text", "source_locator", "notes"}),
        ("knowledge", "knowledge_id", {"description"}),
    ):
        index = {row[key]: row for row in result[table]}
        seen = set()
        for patch in curation[table]:
            identity = patch.get(key)
            if identity not in index or identity in seen or set(patch) - allowed_fields - {key}:
                raise ValueError(f"curation: invalid {table} patch")
            seen.add(identity)
            if (
                table == "objectives"
                and not {"objective_text", "source_locator", "notes"} <= patch.keys()
            ):
                raise ValueError("curation: source text requires locator and provenance notes")
            index[identity].update(patch)
    for edge in curation["edges"]:
        if not isinstance(edge.get("note"), str) or not edge["note"].strip():
            raise ValueError("curation: relationship requires rationale and source note")
    result["edges"].extend(deepcopy(curation["edges"]))
    result["counts"]["edge_count"] = len(result["edges"])
    if "curriculum_graph" in curation:
        _apply_graph_curation(result, curation["curriculum_graph"])
    validate_knowledge_base(result)
    return result


def _apply_graph_curation(result: dict, patch: dict) -> None:
    """Patch review/provenance fields of graph edges, or add reviewed new edges.

    Endpoints and relation types of existing edges are immutable here: changing
    what a relation connects is a new graph version, not an annotation.
    """

    graph = result.get("curriculum_graph")
    if graph is None:
        raise ValueError("curation: build the knowledge base with --graph before patching it")
    if not isinstance(patch, dict) or set(patch) - {"version", "edges", "new_edges"}:
        raise ValueError("curation: curriculum_graph accepts version/edges/new_edges")
    if "version" in patch:
        graph["version"] = patch["version"]
    by_id = {edge["edge_id"]: edge for edge in graph["edges"]}
    for item in patch.get("edges", []):
        edge_id = item.get("edge_id")
        if edge_id not in by_id:
            raise ValueError(f"curation: unknown edge_id {edge_id}")
        if set(item) - GRAPH_PATCH_FIELDS - {"edge_id"}:
            raise ValueError(
                "curation: graph edge patches may only change review status, provenance, "
                "rationale, evidence level or version"
            )
        updated = {**by_id[edge_id], **{key: value for key, value in item.items() if key != "edge_id"}}
        if updated["review_status"] == "reviewed":
            if updated["evidence_level"] == "manual_unsourced":
                raise ValueError(
                    f"curation: {edge_id} needs a traceable evidence level before it can be reviewed"
                )
            if not str(updated["source_reference"]).strip():
                raise ValueError(f"curation: {edge_id} needs a source reference before review")
        by_id[edge_id] = updated
    for edge in patch.get("new_edges", []):
        if set(edge) != GRAPH_REQUIRED_EDGE_FIELDS:
            raise ValueError(
                "curation: a new graph edge must carry exactly the required fields "
                f"{sorted(GRAPH_REQUIRED_EDGE_FIELDS)}"
            )
        if edge["edge_id"] in by_id:
            raise ValueError(f"curation: duplicate edge_id {edge['edge_id']}")
        by_id[edge["edge_id"]] = deepcopy(edge)
    graph["edges"] = [by_id[edge_id] for edge_id in by_id]
    _recount_graph(graph)


def _recount_graph(graph: dict) -> None:
    edges = graph["edges"]
    graph["counts"] = {
        "node_count": len(graph["nodes"]),
        "edge_count": len(edges),
        "prerequisite_count": sum(edge["relation_type"] == "prerequisite" for edge in edges),
        "confusable_count": sum(edge["relation_type"] == "confusable_with" for edge in edges),
        "related_count": sum(edge["relation_type"] == "related_to" for edge in edges),
        "draft_count": sum(edge["review_status"] == "draft" for edge in edges),
        "reviewed_count": sum(edge["review_status"] == "reviewed" for edge in edges),
    }
