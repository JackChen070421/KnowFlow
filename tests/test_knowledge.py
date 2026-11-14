from copy import deepcopy

import pytest

from knowflow.cli import main
from knowflow.contracts import repo_root
from knowflow.knowledge.pipeline import (
    build_knowledge_base,
    validate_knowledge_base,
    write_knowledge_base,
)


@pytest.fixture
def base():
    return build_knowledge_base(
        repo_root() / "examples/synthetic/input", "synthetic", "2026-11-12T00:00:00Z"
    )


def test_roundtrip(base, tmp_path):
    import json

    path = write_knowledge_base(base, tmp_path / "knowledge_base.json")
    assert json.loads(path.read_text(encoding="utf-8")) == base
    assert {r["edge_type"] for r in base["edges"]} >= {"contains", "prerequisite", "confusable"}
    with pytest.raises(FileExistsError):
        write_knowledge_base(base, path)


@pytest.mark.parametrize(
    "fault", ["reference", "duplicate", "count", "coverage", "cycle", "parent", "self", "grade"]
)
def test_reject_invalid(base, fault):
    data = deepcopy(base)
    if fault == "reference":
        data["knowledge"][0]["objective_id"] = "OBJ-7M-99"
    elif fault == "duplicate":
        data["qmatrix"].append(deepcopy(data["qmatrix"][0]))
        data["counts"]["qmatrix_count"] += 1
    elif fault == "count":
        data["counts"]["knowledge_count"] += 1
    elif fault == "coverage":
        data["qmatrix"] = []
        data["counts"]["qmatrix_count"] = 0
    elif fault == "cycle":
        edge = next(e for e in data["edges"] if e["edge_type"] == "prerequisite")
        data["edges"].append(
            dict(from_id=edge["to_id"], to_id=edge["from_id"], edge_type="prerequisite")
        )
        data["counts"]["edge_count"] += 1
    elif fault == "parent":
        data["knowledge"][0]["parent_id"] = data["knowledge"][0]["knowledge_id"]
    elif fault == "self":
        data["edges"][0]["to_id"] = data["edges"][0]["from_id"]
    elif fault == "grade":
        data["grade"] = 8
    with pytest.raises(ValueError):
        validate_knowledge_base(data)


def test_cli(tmp_path):
    assert (
        main(
            [
                "knowledge",
                "--dataset",
                "synthetic",
                "--input",
                str(repo_root() / "examples/synthetic/input"),
                "--output",
                str(tmp_path / "kb.json"),
            ]
        )
        == 0
    )
    assert main(["knowledge", "--dataset", "../escape"]) == 2


def test_preserve_text_and_null(tmp_path):
    import shutil

    source = repo_root() / "examples/synthetic/input"
    for name in ("objectives", "knowledge", "materials", "qmatrix", "edges"):
        shutil.copyfile(source / f"{name}.csv", tmp_path / f"{name}.csv")
    import csv

    path = tmp_path / "objectives.csv"
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    rows[0]["objective_text"] = "  原文\n不改写  "
    rows[0]["source_material_id"] = ""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    data = build_knowledge_base(tmp_path, "synthetic")
    assert data["objectives"][0]["objective_text"] == "  原文\n不改写  "
    assert data["objectives"][0]["source_material_id"] is None


@pytest.fixture
def curation():
    import hashlib

    base = repo_root() / "examples/synthetic/input"
    return {
        "dataset_id": "synthetic",
        "source_sha256": {
            f"{name}.csv": hashlib.sha256((base / f"{name}.csv").read_bytes()).hexdigest()
            for name in ("objectives", "knowledge", "materials", "qmatrix", "edges")
        },
        "objectives": [],
        "knowledge": [],
        "edges": [],
    }


def test_curation_preserves_inputs(base, curation):
    from knowflow.knowledge.pipeline import apply_curation

    before = deepcopy(base)
    curation["knowledge"] = [
        {
            "knowledge_id": base["knowledge"][0]["knowledge_id"],
            "description": "Reviewed explanation with textbook locator",
        }
    ]
    result = apply_curation(base, curation, repo_root() / "examples/synthetic/input")
    assert result["knowledge"][0]["description"] == curation["knowledge"][0]["description"]
    assert base == before
    assert result["qmatrix"] == base["qmatrix"]


@pytest.mark.parametrize("fault", ["hash", "dataset", "mapping", "source", "edge", "duplicate"])
def test_curation_rejects_unsafe_updates(base, curation, fault):
    from knowflow.knowledge.pipeline import apply_curation

    if fault == "hash":
        curation["source_sha256"]["knowledge.csv"] = "changed"
    elif fault == "dataset":
        curation["dataset_id"] = "other"
    elif fault == "mapping":
        curation["knowledge"] = [
            {"knowledge_id": base["knowledge"][0]["knowledge_id"], "objective_id": "OBJ-7M-99"}
        ]
    elif fault == "source":
        curation["objectives"] = [
            {
                "objective_id": base["objectives"][0]["objective_id"],
                "objective_text": "Without source",
            }
        ]
    elif fault == "edge":
        curation["edges"] = [{"from_id": "K-01", "to_id": "K-02", "edge_type": "prerequisite"}]
    else:
        row = {"knowledge_id": base["knowledge"][0]["knowledge_id"], "description": "source"}
        curation["knowledge"] = [row, row]
    with pytest.raises(ValueError):
        apply_curation(base, curation, repo_root() / "examples/synthetic/input")


@pytest.mark.parametrize("input_kind", ["default", "missing", "file"])
def test_cli_missing_canonical_directory(tmp_path, monkeypatch, capsys, input_kind):
    import knowflow.cli as cli

    monkeypatch.setattr(cli, "repo_root", lambda: tmp_path)
    output = tmp_path / "output.json"
    args = ["knowledge", "--dataset", "does-not-exist", "--output", str(output)]
    base = tmp_path / "data/interim/does-not-exist"
    if input_kind != "default":
        base = tmp_path / "canonical"
        if input_kind == "file":
            base.write_text("not a directory", encoding="utf-8")
        args += ["--input", str(base)]
    assert main(args) == 2
    error = capsys.readouterr().err
    assert f"canonical tables not found: {base}; run scripts/build_canonical.py first" in error
    assert "Errno" not in error
    assert not output.exists()
