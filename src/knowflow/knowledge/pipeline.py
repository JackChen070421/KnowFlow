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

TABLES = {
    "objectives": "objective",
    "knowledge": "knowledge",
    "materials": "material",
    "qmatrix": "qmatrix",
    "edges": "edge",
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


def build_knowledge_base(base: Path, dataset_id: str, generated_at: str | None = None) -> dict:
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
    Hashes pin all five input files; only source text, descriptions and edges vary.
    """
    if set(curation) != {"dataset_id", "source_sha256", "objectives", "knowledge", "edges"}:
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
    for table, key, allowed in (
        ("objectives", "objective_id", {"objective_text", "source_locator", "notes"}),
        ("knowledge", "knowledge_id", {"description"}),
    ):
        index = {row[key]: row for row in result[table]}
        seen = set()
        for patch in curation[table]:
            identity = patch.get(key)
            if identity not in index or identity in seen or set(patch) - allowed - {key}:
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
    validate_knowledge_base(result)
    return result
