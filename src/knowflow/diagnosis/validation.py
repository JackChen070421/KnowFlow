"""Task-2 schema, reference, and recomputation checks (not Task-3 approval)."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.cleaning.states import STATES, classify_state
from knowflow.contracts import build_registry, repo_root
from knowflow.diagnosis.mastery import DiagnosisConfig, estimate_mastery
from knowflow.diagnosis.profiles import MASTERED, WEAK, optional_mean, rubric_patterns

BUNDLE_KEYS = {
    "dataset_id",
    "generated_at",
    "canonical_root",
    "students",
    "knowledge",
    "materials",
    "nodes",
    "participation",
    "records",
    "record_sources",
    "quality_report",
}


@lru_cache(maxsize=8)
def schema_validator(name):
    root = repo_root()
    schema = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
    return Draft202012Validator(
        schema, registry=build_registry(root), format_checker=FormatChecker()
    )


def schema_errors(instance, name):
    return [
        f"{name}:{'/'.join(map(str, e.absolute_path))}: {e.message}"
        for e in schema_validator(name).iter_errors(instance)
    ]


def validate_bundle(bundle: dict) -> list[str]:
    """Checks for the canonical-backed diagnosis input (local artifact, no schema file).

    The bundle is derived from ``data/interim/<dataset>/``; its contract is
    ``schemas/input/*.schema.json`` plus the invariants below.  Raw answer text is
    deliberately absent, so this also guards the data boundary.
    """

    errors: list[str] = []
    missing = BUNDLE_KEYS - set(bundle)
    if missing:
        return [f"bundle missing keys: {sorted(missing)}"]

    def check(condition, message):
        if not condition:
            errors.append(message)

    entities = {}
    for key, id_key in [
        ("students", "student_id"),
        ("knowledge", "knowledge_id"),
        ("materials", "material_id"),
        ("nodes", "node_id"),
        ("records", "record_id"),
    ]:
        entities[key] = {x[id_key]: x for x in bundle[key]}
        check(len(entities[key]) == len(bundle[key]), f"duplicate {id_key}")
    students, knowledge, materials, nodes, records = (
        entities[k] for k in ["students", "knowledge", "materials", "nodes", "records"]
    )
    numeric_knowledge = [int(k.split("-")[1]) for k in knowledge]
    check(
        len(set(numeric_knowledge)) == len(numeric_knowledge),
        "knowledge IDs collide when constructing stable issue IDs",
    )
    for m in materials.values():
        check(
            bool(m["knowledge_ids"]) and set(m["knowledge_ids"]) <= set(knowledge),
            f"{m['material_id']}: unknown/empty knowledge mapping",
        )
        rubric_total = sum(p["max_score"] for p in m["rubric"])
        check(
            m["max_score"] > 0 and (not m["rubric"] or math.isclose(m["max_score"], rubric_total)),
            f"{m['material_id']}: invalid rubric total",
        )
    for node in nodes.values():
        check(set(node["material_ids"]) <= set(materials), f"{node['node_id']}: unknown material")
    participation = {(p["student_id"], p["node_id"]) for p in bundle["participation"]}
    check(
        all(s in students and n in nodes for s, n in participation),
        "unknown participation reference",
    )
    event_keys = set()
    for r in records.values():
        rid = r["record_id"]
        if (
            r["student_id"] not in students
            or r["node_id"] not in nodes
            or r["material_id"] not in materials
        ):
            errors.append(f"{rid}: unknown entity reference")
            continue
        key = (r["student_id"], r["node_id"], r["material_id"])
        check(key not in event_keys, f"{rid}: duplicate student/node/material")
        event_keys.add(key)
        check((r["student_id"], r["node_id"]) in participation, f"{rid}: missing participation")
        check(
            r["material_id"] in nodes[r["node_id"]]["material_ids"],
            f"{rid}: outside applicable scope",
        )
        check(
            r["assigned"] and "answer" not in r and "steps_json" not in r,
            f"{rid}: assignment or raw-answer boundary violated",
        )
        check(
            r["max_score"] == materials[r["material_id"]]["max_score"],
            f"{rid}: inconsistent max score",
        )
        if r["score"] is not None:
            check(
                r["attempted"] and 0 <= r["score"] <= r["max_score"], f"{rid}: invalid graded score"
            )
            check(
                r["is_correct"] == (r["score"] == r["max_score"]),
                f"{rid}: invalid correctness flag",
            )
        else:
            check(
                r["is_correct"] is None and not r["score_points"],
                f"{rid}: ungraded record has grading evidence",
            )
        defs = {p["point_id"]: p for p in materials[r["material_id"]]["rubric"]}
        if r["score_points"]:
            check(
                len({p["point_id"] for p in r["score_points"]}) == len(r["score_points"]),
                f"{rid}: duplicate scoring point",
            )
            check(
                {p["point_id"] for p in r["score_points"]} == set(defs), f"{rid}: incomplete rubric"
            )
            check(
                math.isclose(sum(p["score"] for p in r["score_points"]), r["score"]),
                f"{rid}: scoring point total mismatch",
            )
            for point in r["score_points"]:
                check(
                    point["point_id"] in defs and point["score"] <= point["max_score"],
                    f"{rid}: invalid scoring point",
                )
                if point["point_id"] in defs:
                    check(
                        point["max_score"] == defs[point["point_id"]]["max_score"]
                        and point["label"] == defs[point["point_id"]]["label"],
                        f"{rid}: rubric metadata mismatch",
                    )
    check(
        set(bundle["record_sources"]) == set(records),
        "record source index must exactly cover retained records",
    )
    for rid, source in bundle["record_sources"].items():
        check(source.get("csv_record_number", 0) >= 2, f"{rid}: invalid evidence row number")
    q = bundle["quality_report"]
    check(q["dataset_id"] == bundle["dataset_id"], "quality dataset mismatch")
    check(
        q["input_records"] == q["total_records"] + q["duplicates_removed"] + q["rejected_records"],
        "input count conservation failed",
    )
    check(q["total_records"] == len(records), "retained record count mismatch")
    states = Counter(classify_state(r) for r in records.values())
    check(q["records_by_state"] == {s: states[s] for s in STATES}, "quality state counts mismatch")
    decisions = q["decisions"]
    check(
        sorted(d["source_row"] for d in decisions) == list(range(2, q["input_records"] + 2)),
        "audit must account for each input row once",
    )
    for decision, field in [
        ("retained", "total_records"),
        ("superseded", "duplicates_removed"),
        ("rejected", "rejected_records"),
    ]:
        check(
            sum(d["decision"] == decision for d in decisions) == q[field],
            f"audit {decision} count mismatch",
        )
    check(
        {d["record_id"] for d in decisions if d["decision"] == "retained"} == set(records),
        "audit retained IDs mismatch",
    )
    check(
        q["partial_credit_records"]
        == sum(
            r["score"] is not None and 0 < r["score"] < r["max_score"] for r in records.values()
        ),
        "partial-credit count mismatch",
    )
    return errors


def validate_student(profile: dict, bundle: dict, config: DiagnosisConfig) -> list[str]:
    errors = schema_errors(profile, "output/student_profile.schema.json")
    if errors:
        return errors

    def check(condition, message):
        if not condition:
            errors.append(f"{profile['student_id']}/{profile['node_id']}: {message}")

    sid, nid = profile["student_id"], profile["node_id"]
    students = {s["student_id"]: s for s in bundle["students"]}
    nodes = {n["node_id"]: n for n in bundle["nodes"]}
    if sid not in students or nid not in nodes:
        return errors + ["unknown profile student/node"]
    check(
        profile["group_id"] == students[sid]["group_id"]
        and profile["source_dataset"] == bundle["dataset_id"],
        "profile identity mismatch",
    )
    scope_known = {"student_id": sid, "node_id": nid} in bundle["participation"]
    scope = set(nodes[nid]["material_ids"]) if scope_known else set()
    records = {
        r["record_id"]: r for r in bundle["records"] if r["student_id"] == sid and r["node_id"] == nid
    }
    graded = {rid: r for rid, r in records.items() if r["attempted"] and r["score"] is not None}
    observed = {r["material_id"] for r in graded.values()}
    c = profile["coverage"]
    check(c["scope_known"] == scope_known, "scope-known flag mismatch")
    check(
        c["applicable_items"] == len(scope) and c["observed_items"] == len(observed),
        "coverage counts mismatch",
    )
    check(
        c["ratio"] == (round(len(observed) / len(scope), 6) if scope else None),
        "coverage ratio mismatch",
    )
    states = {s["knowledge_id"]: s for s in profile["knowledge_states"]}
    check(
        len(states) == len(profile["knowledge_states"])
        and set(states) == {k["knowledge_id"] for k in bundle["knowledge"]},
        "knowledge coverage/uniqueness mismatch",
    )
    for kid, state in states.items():
        definition = next((k for k in bundle["knowledge"] if k["knowledge_id"] == kid), None)
        check(
            definition is not None and state["objective_id"] == definition["objective_id"],
            f"{kid}: objective reference mismatch",
        )
        items = {m["material_id"] for m in bundle["materials"] if kid in m["knowledge_ids"]} & scope
        relevant = [r for r in records.values() if r["material_id"] in items]
        expected_ids = sorted(
            r["record_id"] for r in relevant if r["score"] is not None and r["attempted"]
        )
        counts = Counter(classify_state(r) for r in relevant)
        counts["unobserved"] = len(items) - len(relevant)
        check(
            state["state_counts"] == {s: counts[s] for s in STATES}, f"{kid}: state counts mismatch"
        )
        check(
            state["evidence"] == expected_ids and state["evidence_count"] == len(expected_ids),
            f"{kid}: evidence mismatch",
        )
        check(state["applicable_items"] == len(items), f"{kid}: applicable count mismatch")
        expected = estimate_mastery(counts["observed_correct"], len(expected_ids), config)
        if scope_known and not items:
            expected["status"] = "not_applicable"
        for key in [
            "mastery",
            "confidence",
            "status",
            "credible_interval",
            "weak_probability",
            "mastered_probability",
        ]:
            check(state[key] == expected[key], f"{kid}: {key} cannot be reproduced")
        rs = [graded[rid] for rid in expected_ids]
        perf = {
            "full_credit": counts["observed_correct"],
            "partial_credit": sum(0 < r["score"] < r["max_score"] for r in rs),
            "zero_credit": sum(r["score"] == 0 for r in rs),
            "mean_score_ratio": optional_mean(r["score"] / r["max_score"] for r in rs),
        }
        check(state["performance"] == perf, f"{kid}: score statistics mismatch")
    check(
        c["observed_knowledge"] == sum(s["evidence_count"] > 0 for s in states.values()),
        "observed knowledge mismatch",
    )
    check(
        c["total_knowledge"] == sum(s["applicable_items"] > 0 for s in states.values()),
        "applicable knowledge mismatch",
    )
    objective_ids = [o["objective_id"] for o in profile["objective_states"]]
    check(
        len(set(objective_ids)) == len(objective_ids)
        and set(objective_ids) == {k["objective_id"] for k in bundle["knowledge"]},
        "objective coverage/uniqueness mismatch",
    )
    for objective in profile["objective_states"]:
        children = [
            s
            for s in states.values()
            if s["objective_id"] == objective["objective_id"] and s["status"] != "not_applicable"
        ]
        weight = sum(s["evidence_count"] for s in children)
        average = (
            round(
                sum(s["mastery"] * s["evidence_count"] for s in children if s["mastery"] is not None)
                / weight,
                6,
            )
            if weight
            else None
        )
        check(objective["mastery"] == average, "objective weighted mean mismatch")
        check(
            objective["evidence_count"] == len({rid for s in children for rid in s["evidence"]}),
            "objective evidence double-counted",
        )
        check(
            objective["derived_from"] == [s["knowledge_id"] for s in children],
            "objective derived_from mismatch",
        )
        check(
            objective["unobserved_knowledge_ids"]
            == [s["knowledge_id"] for s in children if not s["evidence_count"]],
            "objective unobserved list mismatch",
        )
    check(
        len({i["issue_id"] for i in profile["issues"]}) == len(profile["issues"]),
        "duplicate issue ID",
    )
    for issue in profile["issues"]:
        kid = issue["knowledge_id"]
        if kid not in states:
            errors.append("issue refers to unknown knowledge")
            continue
        check(
            issue["issue_id"] == f"IS-{sid[1:]}-{int(kid.split('-')[1]):02d}", "unstable issue ID"
        )
        check(issue["objective_id"] == states[kid]["objective_id"], "issue objective mismatch")
        stat = (
            f"full_credit={states[kid]['performance']['full_credit']}"
            f"/{states[kid]['evidence_count']}; "
            f"partial_credit={states[kid]['performance']['partial_credit']}"
        )
        check(issue["evidence"]["stat"] == stat, "issue statistic mismatch")
        check(issue["evidence"]["records"] == states[kid]["evidence"], "issue evidence mismatch")
        check(
            issue["evidence"]["material_ids"]
            == sorted({graded[r]["material_id"] for r in states[kid]["evidence"] if r in graded}),
            "issue material references mismatch",
        )
        for point in issue["rubric_evidence"]:
            record = graded.get(point["record_id"])
            check(
                record is not None and point["record_id"] in states[kid]["evidence"],
                "rubric points to wrong student/node/knowledge",
            )
            if record:
                check(
                    point["material_id"] == record["material_id"]
                    and {
                        "point_id": point["point_id"],
                        "label": point["criterion"],
                        "score": point["score"],
                        "max_score": point["max_score"],
                    }
                    in record["score_points"],
                    "rubric evidence cannot be reproduced",
                )
    return errors


def validate_class(profile: dict, students: list[dict], bundle: dict) -> list[str]:
    errors = schema_errors(profile, "output/class_profile.schema.json")
    if errors:
        return errors
    selected = [
        p
        for p in students
        if p["node_id"] == profile["node_id"]
        and (profile["class_id"] == "ALL" or p["group_id"] == profile["class_id"])
    ]

    def check(condition, message):
        if not condition:
            errors.append(f"{profile['class_id']}/{profile['node_id']}: {message}")

    check(profile["student_count"] == len(selected), "class population mismatch")
    distribution_ids = [d["knowledge_id"] for d in profile["knowledge_distribution"]]
    check(
        len(set(distribution_ids)) == len(distribution_ids)
        and set(distribution_ids) == {k["knowledge_id"] for k in bundle["knowledge"]},
        "class knowledge coverage/uniqueness mismatch",
    )
    for row in profile["knowledge_distribution"]:
        states = [
            s
            for p in selected
            for s in p["knowledge_states"]
            if s["knowledge_id"] == row["knowledge_id"]
        ]
        for field, values in [
            ("mastered_count", MASTERED),
            ("weak_count", WEAK),
            ("insufficient_count", {"insufficient_evidence"}),
            ("mixed_count", {"mixed_performance"}),
            ("not_applicable_count", {"not_applicable"}),
        ]:
            check(
                row[field] == sum(s["status"] in values for s in states),
                f"{row['knowledge_id']}: {field} mismatch",
            )
        check(row["student_count"] == len(selected), "knowledge population mismatch")
        check(
            row["mean_mastery"] == optional_mean(s["mastery"] for s in states),
            "class mean mismatch (null must not be zero)",
        )
        check(
            row["mean_score_ratio"]
            == optional_mean(s["performance"]["mean_score_ratio"] for s in states),
            "class score ratio mismatch",
        )
        check(
            row["observed_student_count"] == sum(s["evidence_count"] > 0 for s in states),
            "observed population mismatch",
        )
    c = profile["coverage_summary"]
    check(
        c["students_below_0_5"]
        == sum(
            p["coverage"]["ratio"] is not None and p["coverage"]["ratio"] < 0.5 for p in selected
        ),
        "low-coverage population mismatch",
    )
    check(
        c["students_with_insufficient_evidence"]
        == sum(bool(p["lists"]["needs_observation"]) for p in selected),
        "insufficient population mismatch",
    )
    check(
        c["mean_ratio"] == optional_mean(p["coverage"]["ratio"] for p in selected),
        "class coverage mean mismatch",
    )
    check(
        c["students_with_known_scope"] == sum(p["coverage"]["scope_known"] for p in selected),
        "class known-scope count mismatch",
    )
    expected_issues = {(i["knowledge_id"], i["type"]) for p in selected for i in p["issues"]}
    actual_issues = [(i["knowledge_id"], i["issue_type"]) for i in profile["common_issues"]]
    check(
        len(set(actual_issues)) == len(actual_issues) and set(actual_issues) == expected_issues,
        "common issues omitted or duplicated",
    )
    for issue in profile["common_issues"]:
        ids = sorted(
            {
                p["student_id"]
                for p in selected
                for i in p["issues"]
                if i["knowledge_id"] == issue["knowledge_id"] and i["type"] == issue["issue_type"]
            }
        )
        check(
            issue["student_count"] == len(ids) and issue["example_student_ids"] == ids[:5],
            "common issue members mismatch",
        )
        check(
            issue["denominator"] == len(selected)
            and issue["prevalence"] == (round(len(ids) / len(selected), 6) if selected else 0),
            "common issue denominator mismatch",
        )
    check(
        profile["rubric_patterns"]
        == rubric_patterns(bundle, profile["node_id"], {p["student_id"] for p in selected}),
        "class scoring-point aggregation mismatch",
    )
    members = [sid for t in profile["tiers"] for sid in t["student_ids"]]
    check(
        len(members) == len(set(members)) and set(members) == {p["student_id"] for p in selected},
        "tiers must partition the class exactly once",
    )
    return errors


def validate_saved_run(path: Path) -> dict:
    path = Path(path)
    if not path.is_dir():
        raise ValueError(
            f"run directory not found: {path} (pass a directory under artifacts/run, "
            "or omit --run to use the newest run)"
        )
    manifest_path = path / "run_manifest.json"
    input_path = path / "diagnosis_input.json"
    if not manifest_path.is_file() or not input_path.is_file():
        raise ValueError(
            f"not a completed run (missing run_manifest.json/diagnosis_input.json): {path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle = json.loads(input_path.read_text(encoding="utf-8"))
    config = DiagnosisConfig(**manifest["configuration"])
    errors = validate_bundle(bundle)
    valid_nodes = {n["node_id"] for n in bundle["nodes"]}
    selected_nodes = manifest["nodes"]
    if (
        not selected_nodes
        or len(set(selected_nodes)) != len(selected_nodes)
        or not set(selected_nodes) <= valid_nodes
    ):
        errors.append("invalid manifest node selection")
    expected_paths = {"data_quality_report.json"}
    for node in selected_nodes:
        expected_paths.update(
            f"nodes/{node}/students/{s['student_id']}.json" for s in bundle["students"]
        )
        expected_paths.update(
            f"nodes/{node}/classes/{g}.json"
            for g in {s["group_id"] for s in bundle["students"]} | {"ALL"}
        )
    actual_paths = [t["path"] for t in manifest["targets"]]
    if len(set(actual_paths)) != len(actual_paths) or set(actual_paths) != expected_paths:
        errors.append("manifest target set is incomplete or duplicated")
    students, classes = [], []
    for name, expected_hash in manifest.get("auxiliary_files", {}).items():
        auxiliary = (path / name).resolve()
        if (
            not auxiliary.is_relative_to(path.resolve())
            or not auxiliary.is_file()
            or hashlib.sha256(auxiliary.read_bytes()).hexdigest() != expected_hash
        ):
            errors.append(f"missing or modified auxiliary file: {name}")
    for target in manifest["targets"]:
        file = (path / target["path"]).resolve()
        if not file.is_relative_to(path.resolve()):
            errors.append("target path escapes run directory")
            continue
        if not file.is_file():
            errors.append(f"missing output: {target['path']}")
            continue
        if hashlib.sha256(file.read_bytes()).hexdigest() != target["sha256"]:
            errors.append(f"changed output: {target['path']}")
        name = target["schema_id"].split("/schemas/", 1)[1]
        data = json.loads(file.read_text(encoding="utf-8"))
        found_errors = schema_errors(data, name)
        errors.extend(found_errors)
        if found_errors:
            continue
        if name == "output/student_profile.schema.json":
            if target["path"] != f"nodes/{data['node_id']}/students/{data['student_id']}.json":
                errors.append("student profile path/identity mismatch")
            students.append(data)
        elif name == "output/class_profile.schema.json":
            if target["path"] != f"nodes/{data['node_id']}/classes/{data['class_id']}.json":
                errors.append("class profile path/identity mismatch")
            classes.append(data)
        elif name == "output/data_quality_report.schema.json" and data != bundle["quality_report"]:
            errors.append("quality report differs from the input snapshot")
    if not errors:
        for profile in students:
            errors.extend(validate_student(profile, bundle, config))
        for profile in classes:
            errors.extend(validate_class(profile, students, bundle))
    return {
        "run": str(path),
        "gate": "fail" if errors else "pass",
        "errors": errors,
        "student_profiles": len(students),
        "class_profiles": len(classes),
    }
