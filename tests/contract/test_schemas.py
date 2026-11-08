"""Contract smoke tests: repository structure, schema IDs and fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowflow.contracts import check_repo, iter_schema_paths, validate_instance

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def test_repository_contracts() -> None:
    errors = check_repo(ROOT)
    assert errors == [], "\n".join(errors)


def test_schema_headers_and_unique_ids() -> None:
    seen: dict[str, Path] = {}
    for path in iter_schema_paths(ROOT):
        schema = json.loads(path.read_text(encoding="utf-8"))
        for key in ("$schema", "$id", "title", "type"):
            assert key in schema, f"{path}: missing {key}"
        assert schema["$schema"].endswith("2020-12/schema"), path
        assert schema["$id"].startswith(
            "https://knowflow.local/schemas/"
        ), f"{path}: bad $id {schema['$id']}"
        assert schema["$id"] not in seen, f"duplicate $id: {schema['$id']}"
        seen[schema["$id"]] = path
    assert len(seen) >= 16


def test_student_profile_fixture_is_valid() -> None:
    errors = validate_instance(
        ROOT / "schemas" / "output" / "student_profile.schema.json",
        FIXTURES / "student_profile.min.json",
        root=ROOT,
    )
    assert errors == [], "\n".join(errors)


def test_recommendation_fixture_is_valid() -> None:
    errors = validate_instance(
        ROOT / "schemas" / "output" / "recommendation.schema.json",
        FIXTURES / "recommendation.min.json",
        root=ROOT,
    )
    assert errors == [], "\n".join(errors)


def test_knowledge_base_fixture_is_valid_with_refs() -> None:
    errors = validate_instance(
        ROOT / "schemas" / "output" / "knowledge_base.schema.json",
        FIXTURES / "knowledge_base.min.json",
        root=ROOT,
    )
    assert errors == [], "\n".join(errors)


def test_llm_summary_fixture_is_valid() -> None:
    errors = validate_instance(
        ROOT / "schemas" / "llm" / "llm_summary.schema.json",
        FIXTURES / "llm_summary.min.json",
        root=ROOT,
    )
    assert errors == [], "\n".join(errors)


def test_llm_response_fixture_is_valid() -> None:
    errors = validate_instance(
        ROOT / "schemas" / "llm" / "llm_response.schema.json",
        FIXTURES / "llm_response.min.json",
        root=ROOT,
    )
    assert errors == [], "\n".join(errors)


def test_missing_null_mastery_is_allowed() -> None:
    """A knowledge state with no observation may carry mastery=null."""

    fixture = json.loads(
        (FIXTURES / "student_profile.min.json").read_text(encoding="utf-8")
    )
    fixture["knowledge_states"].append(
        {
            "knowledge_id": "K-06",
            "objective_id": "OBJ-7M-03",
            "mastery": None,
            "confidence": "low",
            "evidence_count": 0,
            "status": "insufficient_evidence",
            "state_counts": {
                "observed_correct": 0,
                "observed_wrong": 0,
                "assigned_not_attempted": 0,
                "unobserved": 1,
            },
            "evidence": [],
        }
    )
    # Validate via jsonschema directly to avoid writing a temp file.
    from jsonschema import Draft202012Validator

    from knowflow.contracts import build_registry

    schema = json.loads(
        (ROOT / "schemas" / "output" / "student_profile.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, registry=build_registry(ROOT))
    assert list(validator.iter_errors(fixture)) == []


@pytest.mark.parametrize(
    "field",
    ["student_id", "group_id", "source_dataset"],
)
def test_required_profile_fields_are_present(field: str) -> None:
    fixture = json.loads(
        (FIXTURES / "student_profile.min.json").read_text(encoding="utf-8")
    )
    assert field in fixture
