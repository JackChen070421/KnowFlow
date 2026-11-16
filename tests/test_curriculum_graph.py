"""Direction-2 checks: the formal curriculum graph is one validated source."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from knowflow.contracts import repo_root
from knowflow.knowledge.graph import graph_index, graph_warnings, load_graph, validate_graph
from knowflow.knowledge.pipeline import apply_curation, build_knowledge_base

ROOT = repo_root()
GRAPH_PATH = ROOT / "knowledge" / "curriculum_graph.json"
SOURCE_FILES = ("objectives", "knowledge", "materials", "qmatrix", "edges")


def _graph() -> dict:
    return load_graph(GRAPH_PATH)


def _recount(graph: dict) -> dict:
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
    return graph


def _edge(**overrides) -> dict:
    edge = {
        "edge_id": "GE-9001",
        "source_node_id": "C-001",
        "target_node_id": "C-002",
        "relation_type": "prerequisite",
        "source_reference": "synthetic",
        "rationale": "synthetic",
        "review_status": "draft",
        "evidence_level": "manual_unsourced",
    }
    edge.update(overrides)
    return edge


# --------------------------------------------------------------------------- #
# committed asset
# --------------------------------------------------------------------------- #


def test_committed_graph_is_valid_and_fully_draft() -> None:
    graph = _graph()
    validate_graph(graph)
    assert graph["counts"] == {
        "node_count": 21,
        "edge_count": 18,
        "prerequisite_count": 16,
        "confusable_count": 1,
        "related_count": 1,
        "draft_count": 18,
        "reviewed_count": 0,
    }
    assert all(edge["review_status"] == "draft" for edge in graph["edges"])
    for edge in graph["edges"]:
        assert edge["source_reference"].strip()
        assert edge["rationale"].strip()
        assert edge["edge_id"].startswith("GE-")


def test_isolated_nodes_are_reported_not_fatal() -> None:
    warnings = graph_warnings(_graph())
    assert any("C-007" in warning for warning in warnings)
    assert any("18 of 18 relations are not reviewed" in warning for warning in warnings)


def test_graph_schema_is_registered() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "output" / "curriculum_graph.schema.json").read_text(encoding="utf-8")
    )
    assert schema["$id"].endswith("/output/curriculum_graph.schema.json")
    assert "prerequisite" in schema["$defs"]["relation_type"]["enum"]


def test_frontend_has_no_hardcoded_graph() -> None:
    js = (ROOT / "src" / "knowflow" / "web" / "static" / "knowledge-map.js").read_text(
        encoding="utf-8"
    )
    assert "C-001" not in js
    assert '"from": "C-' not in js
    assert "curriculum_graph" in js


def test_symmetric_relations_are_stored_once_and_indexed() -> None:
    index = graph_index(_graph())
    confusable = [edge for edge in index["edges"] if edge["relation_type"] == "confusable_with"]
    assert len(confusable) == 1
    assert {confusable[0]["source_node_id"], confusable[0]["target_node_id"]} == {"C-009", "C-017"}
    for node_id in ("C-009", "C-017"):
        assert confusable[0]["edge_id"] in [edge["edge_id"] for edge in index["node_edges"][node_id]]


# --------------------------------------------------------------------------- #
# structural validation
# --------------------------------------------------------------------------- #


def test_catalog_maps_textbook_relations_to_knowledge() -> None:
    from knowflow.recommend.catalog import build_catalog

    catalog = build_catalog(
        {
            "materials": [],
            "knowledge": [],
            "qmatrix": [],
            "edges": [],
            "objectives": [],
            "curriculum_graph": _graph(),
        }
    )
    assert catalog["graph"]["edge_count"] == 18
    assert catalog["reviewed_prerequisites"] == {}
    assert "GE-0017" in [
        entry["edge_id"] for entry in catalog["pending_node_confusable"]["K-04"]
    ]


def test_prerequisite_cycle_is_rejected() -> None:
    graph = _recount(
        _graph_with(_edge(edge_id="GE-9001", source_node_id="C-006", target_node_id="C-003"))
    )
    with pytest.raises(ValueError, match="cycle"):
        validate_graph(graph)


def _graph_with(*edges: dict) -> dict:
    graph = _graph()
    graph["edges"].extend(copy.deepcopy(list(edges)))
    return graph


def test_unknown_textbook_endpoint_is_rejected() -> None:
    graph = _recount(
        _graph_with(_edge(source_node_id="C-999", target_node_id="C-001"))
    )
    with pytest.raises(ValueError, match="unknown textbook node"):
        validate_graph(graph)


def test_unknown_knowledge_endpoint_is_rejected() -> None:
    graph = _recount(
        _graph_with(_edge(edge_id="GE-9002", source_node_id="K-99", target_node_id="C-001"))
    )
    with pytest.raises(ValueError, match="unknown knowledge"):
        validate_graph(graph, {"K-01"})


def test_self_loop_is_rejected() -> None:
    graph = _recount(
        _graph_with(_edge(source_node_id="C-001", target_node_id="C-001"))
    )
    with pytest.raises(ValueError, match="self loop"):
        validate_graph(graph)


def test_duplicate_symmetric_edge_is_rejected() -> None:
    graph = _recount(
        _graph_with(_edge(edge_id="GE-9003", relation_type="confusable_with",
                          source_node_id="C-009", target_node_id="C-017"))
    )
    with pytest.raises(ValueError, match="duplicate confusable_with"):
        validate_graph(graph)


def test_symmetric_relation_must_be_stored_canonically() -> None:
    graph = _recount(
        _graph_with(_edge(edge_id="GE-9004", relation_type="confusable_with",
                          source_node_id="C-017", target_node_id="C-009"))
    )
    with pytest.raises(ValueError, match="canonically"):
        validate_graph(graph)


def test_counts_mismatch_is_rejected() -> None:
    graph = _graph()
    graph["counts"]["edge_count"] += 1
    with pytest.raises(ValueError, match="counts mismatch"):
        validate_graph(graph)


# --------------------------------------------------------------------------- #
# knowledge base integration
# --------------------------------------------------------------------------- #


def _example_graph() -> dict:
    return {
        "schema_version": "1.0.0",
        "graph_id": "synthetic-graph",
        "version": "1.0.0",
        "subject": "math",
        "grade": 7,
        "source": "synthetic",
        "nodes": [
            {
                "node_id": "C-001",
                "title": "合成教材细目",
                "theme_index": 0,
                "summary": "合成",
                "source_locator": "synthetic p.1",
                "textbook": "B05",
                "pdf_page": 1,
                "knowledge_ids": ["K-01"],
                "material_id": "M-003",
            }
        ],
        "edges": [
            {
                "edge_id": "GE-0001",
                "source_node_id": "K-01",
                "target_node_id": "K-07",
                "relation_type": "prerequisite",
                "source_reference": "synthetic",
                "rationale": "synthetic",
                "review_status": "reviewed",
                "evidence_level": "textbook_locator",
                "created_version": "1.0.0",
            }
        ],
        "counts": {
            "node_count": 1,
            "edge_count": 1,
            "prerequisite_count": 1,
            "confusable_count": 0,
            "related_count": 0,
            "draft_count": 0,
            "reviewed_count": 1,
        },
    }


def test_graph_changes_knowledge_base_hash() -> None:
    examples = ROOT / "examples" / "synthetic" / "input"
    plain = build_knowledge_base(examples, "synthetic", "2026-11-16T00:00:00Z")
    with_graph = build_knowledge_base(
        examples, "synthetic", "2026-11-16T00:00:00Z", graph=_example_graph()
    )
    assert "curriculum_graph" not in plain
    assert with_graph["curriculum_graph"]["counts"]["node_count"] == 1
    assert json.dumps(plain, sort_keys=True) != json.dumps(with_graph, sort_keys=True)
    assert hashlib.sha256(json.dumps(plain, sort_keys=True).encode()).hexdigest() != hashlib.sha256(
        json.dumps(with_graph, sort_keys=True).encode()
    ).hexdigest()


def test_knowledge_base_rejects_graph_with_unknown_knowledge() -> None:
    graph = _example_graph()
    graph["edges"][0]["target_node_id"] = "K-99"
    with pytest.raises(ValueError, match="unknown knowledge"):
        build_knowledge_base(
            ROOT / "examples" / "synthetic" / "input", "synthetic", graph=graph
        )


# --------------------------------------------------------------------------- #
# local review through the existing curation mechanism
# --------------------------------------------------------------------------- #


def _curation_base(tmp_path: Path) -> Path:
    base = tmp_path / "canonical"
    base.mkdir()
    for name in SOURCE_FILES:
        (base / f"{name}.csv").write_text(f"{name}\n", encoding="utf-8")
    return base


def _source_sha(base: Path) -> dict[str, str]:
    return {
        f"{name}.csv": hashlib.sha256((base / f"{name}.csv").read_bytes()).hexdigest()
        for name in SOURCE_FILES
    }


def _minimal_knowledge_base() -> dict:
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "synthetic-graph",
        "version": "1.0.0",
        "subject": "math",
        "grade": 7,
        "source": "synthetic",
        "nodes": [
            {
                "node_id": "C-001",
                "title": "合成细目",
                "theme_index": 0,
                "summary": "合成",
                "source_locator": "synthetic p.1",
                "textbook": "B05",
                "pdf_page": 1,
                "knowledge_ids": ["K-01"],
                "material_id": "M-001",
            }
        ],
        "edges": [
            {
                "edge_id": "GE-0001",
                "source_node_id": "K-01",
                "target_node_id": "K-02",
                "relation_type": "prerequisite",
                "source_reference": "synthetic",
                "rationale": "synthetic",
                "review_status": "draft",
                "evidence_level": "manual_unsourced",
            }
        ],
        "counts": {
            "node_count": 1,
            "edge_count": 1,
            "prerequisite_count": 1,
            "confusable_count": 0,
            "related_count": 0,
            "draft_count": 1,
            "reviewed_count": 0,
        },
    }
    return {
        "schema_version": "1.0.0",
        "dataset_id": "synthetic-graph",
        "generated_at": "2026-11-16T00:00:00+00:00",
        "subject": "math",
        "grade": 7,
        "counts": {
            "objective_count": 1,
            "knowledge_count": 2,
            "material_count": 2,
            "qmatrix_count": 2,
            "edge_count": 0,
        },
        "objectives": [
            {
                "objective_id": "OBJ-7M-01",
                "subject": "math",
                "grade": 7,
                "theme": "合成",
                "unit": "合成",
                "objective_text": "合成目标",
                "verb_level": "apply",
                "source_material_id": None,
                "source_locator": "synthetic",
            }
        ],
        "knowledge": [
            {
                "knowledge_id": "K-01",
                "objective_id": "OBJ-7M-01",
                "parent_id": None,
                "name": "合成一",
                "level": "knowledge",
                "cognitive_type": "concept",
                "description": None,
                "sort_order": 0,
            },
            {
                "knowledge_id": "K-02",
                "objective_id": "OBJ-7M-01",
                "parent_id": None,
                "name": "合成二",
                "level": "knowledge",
                "cognitive_type": "procedure",
                "description": None,
                "sort_order": 1,
            },
        ],
        "materials": [
            {
                "material_id": "M-001",
                "title": "合成题一",
                "body": "合成",
                "material_type": "assessment",
                "difficulty": None,
                "objective_id": "OBJ-7M-01",
                "options_json": None,
                "answer_key": "1",
                "explanation": None,
                "rubric_json": None,
                "attachments_json": None,
                "est_minutes": None,
                "source": "synthetic",
                "license": "synthetic",
                "item_format": "blank",
            },
            {
                "material_id": "M-002",
                "title": "合成题二",
                "body": "合成",
                "material_type": "assessment",
                "difficulty": None,
                "objective_id": "OBJ-7M-01",
                "options_json": None,
                "answer_key": "2",
                "explanation": None,
                "rubric_json": None,
                "attachments_json": None,
                "est_minutes": None,
                "source": "synthetic",
                "license": "synthetic",
                "item_format": "blank",
            },
        ],
        "qmatrix": [
            {
                "material_id": "M-001",
                "knowledge_id": "K-01",
                "weight": 1.0,
                "difficulty": None,
                "item_type": "assessment",
                "is_primary": True,
            },
            {
                "material_id": "M-002",
                "knowledge_id": "K-02",
                "weight": 1.0,
                "difficulty": None,
                "item_type": "assessment",
                "is_primary": True,
            },
        ],
        "edges": [],
        "curriculum_graph": graph,
    }


def _curation(base: Path, **overrides) -> dict:
    curation = {
        "dataset_id": "synthetic-graph",
        "source_sha256": _source_sha(base),
        "objectives": [],
        "knowledge": [],
        "edges": [],
    }
    curation.update(overrides)
    return curation


def test_curation_can_review_an_edge_and_bump_the_version(tmp_path: Path) -> None:
    base = _curation_base(tmp_path)
    result = apply_curation(
        _minimal_knowledge_base(),
        _curation(
            base,
            curriculum_graph={
                "version": "1.1.0",
                "edges": [
                    {
                        "edge_id": "GE-0001",
                        "review_status": "reviewed",
                        "evidence_level": "textbook_locator",
                        "source_reference": "B05 §4.2 上册 95–98 页",
                    }
                ],
            },
        ),
        base,
    )
    graph = result["curriculum_graph"]
    assert graph["version"] == "1.1.0"
    assert graph["edges"][0]["review_status"] == "reviewed"
    assert graph["counts"]["reviewed_count"] == 1
    assert graph["counts"]["draft_count"] == 0


def test_curation_can_add_a_reviewed_edge(tmp_path: Path) -> None:
    base = _curation_base(tmp_path)
    new_edge = {
        "edge_id": "GE-0002",
        "source_node_id": "C-001",
        "target_node_id": "K-02",
        "relation_type": "related_to",
        "source_reference": "synthetic",
        "rationale": "synthetic",
        "review_status": "reviewed",
        "evidence_level": "textbook_locator",
    }
    result = apply_curation(
        _minimal_knowledge_base(),
        _curation(base, curriculum_graph={"new_edges": [new_edge]}),
        base,
    )
    graph = result["curriculum_graph"]
    assert graph["counts"]["edge_count"] == 2
    assert graph["counts"]["related_count"] == 1
    assert graph["counts"]["reviewed_count"] == 1


def test_curation_cannot_change_edge_endpoints(tmp_path: Path) -> None:
    base = _curation_base(tmp_path)
    with pytest.raises(ValueError, match="may only change"):
        apply_curation(
            _minimal_knowledge_base(),
            _curation(
                base,
                curriculum_graph={
                    "edges": [{"edge_id": "GE-0001", "source_node_id": "K-02"}]
                },
            ),
            base,
        )


def test_curation_cannot_review_without_traceable_evidence(tmp_path: Path) -> None:
    base = _curation_base(tmp_path)
    with pytest.raises(ValueError, match="traceable evidence level"):
        apply_curation(
            _minimal_knowledge_base(),
            _curation(
                base,
                curriculum_graph={
                    "edges": [{"edge_id": "GE-0001", "review_status": "reviewed"}]
                },
            ),
            base,
        )


def test_stale_curation_is_refused(tmp_path: Path) -> None:
    base = _curation_base(tmp_path)
    curation = _curation(base, curriculum_graph={"version": "1.1.0"})
    (base / "knowledge.csv").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source hashes changed"):
        apply_curation(_minimal_knowledge_base(), curation, base)


def test_curation_requires_a_built_graph(tmp_path: Path) -> None:
    base = _curation_base(tmp_path)
    data = _minimal_knowledge_base()
    data.pop("curriculum_graph")
    with pytest.raises(ValueError, match="build the knowledge base with --graph"):
        apply_curation(data, _curation(base, curriculum_graph={"version": "1.1.0"}), base)
