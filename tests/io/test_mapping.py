"""ID mapping must be one-to-one and match the patterns in CONTRACT.md."""

from __future__ import annotations

import re

import pytest

from knowflow.io import mapping


def test_material_ids_are_bijective() -> None:
    canonical = [mapping.material_id_for(f"Q{i:03d}") for i in range(1, 55)]
    canonical += [mapping.material_id_for(f"L{i:02d}") for i in range(1, 4)]
    canonical += [mapping.material_id_for(f"B{i:02d}") for i in range(1, 9)]
    assert canonical == [f"M-{i:03d}" for i in range(1, 66)]
    assert len(set(canonical)) == 65
    for material_id in canonical:
        assert re.fullmatch(r"M-[0-9]{3}", material_id)
        assert mapping.material_id_for(mapping.material_official_id(material_id)) == material_id


def test_other_ids() -> None:
    assert mapping.record_id_for("DR0001") == "R-0001"
    assert mapping.record_id_for("DR0806") == "R-0806"
    assert mapping.student_id_for("D01") == "S001"
    assert mapping.student_id_for("D40") == "S040"
    assert mapping.group_id_for("DC01") == "G1"
    assert mapping.group_id_for("DC02") == "G2"
    assert mapping.objective_for_theme("T03") == "OBJ-7M-03"
    assert mapping.knowledge_for_indicator("T01I1") == "K-01"
    assert mapping.knowledge_for_indicator("T03I3") == "K-09"
    assert len(mapping.INDICATOR_TO_KNOWLEDGE) == 9


@pytest.mark.parametrize(
    "function,value",
    [
        (mapping.material_id_for, "X001"),
        (mapping.material_id_for, "Q000"),
        (mapping.record_id_for, "R0001"),
        (mapping.student_id_for, "S001"),
        (mapping.group_id_for, "DC99"),
        (mapping.knowledge_for_indicator, "T09I9"),
    ],
)
def test_unknown_ids_raise(function, value) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        function(value)


def test_split_ids() -> None:
    assert mapping.split_ids("T01、T02") == ["T01", "T02"]
    assert mapping.split_ids("Q001、Q002；Q003") == ["Q001", "Q002", "Q003"]
    assert mapping.split_ids("") == []
