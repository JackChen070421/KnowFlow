"""Task-3 schema, reference, numeric-lock, and scope checks."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from knowflow.contracts import build_registry, repo_root
from knowflow.recommend.catalog import build_catalog, load_knowledge_base
from knowflow.recommend.rules import MIN_EVIDENCE, POLICY_VERSION

NUMBER = re.compile(r"(?<![A-Za-z0-9_-])\d+(?:\.\d+)?(?![A-Za-z0-9_-])")
SCHEMA_ID = "https://knowflow.local/schemas/output/recommendation.schema.json"
GAP_STATUSES = {"confirmed_weak", "likely_weak", "mixed_performance"}


@lru_cache(maxsize=4)
def schema_validator() -> Draft202012Validator:
    root = repo_root()
    schema = json.loads(
        (root / "schemas" / "output" / "recommendation.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(
        schema, registry=build_registry(root), format_checker=FormatChecker()
    )


def schema_errors(instance: dict) -> list[str]:
    return [
        f"recommendation:{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in schema_validator().iter_errors(instance)
    ]


def _state(profile: dict, knowledge_id: str) -> dict:
    return next(
        (s for s in profile["knowledge_states"] if s["knowledge_id"] == knowledge_id),
        {},
    )


def _numbers(text: str) -> set[float]:
    return {float(value) for value in NUMBER.findall(text or "")}


def allowed_numbers(issue: dict, state: dict) -> set[float]:
    """Numbers a reason/check may use: evidence counts plus the policy constants."""

    allowed = {1.0, 2.0, 3.0, float(MIN_EVIDENCE), 5.0}
    for key in ("evidence_count", "applicable_items"):
        value = state.get(key)
        if isinstance(value, (int, float)):
            allowed.add(float(value))
    block = state.get("review") or {}
    for key in ("usable_evidence_count", "usable_full_credit"):
        value = block.get(key)
        if isinstance(value, (int, float)):
            allowed.add(float(value))
    if block:
        allowed.add(float(len(block.get("disputed_record_ids") or [])))
    allowed |= _numbers(issue.get("statement", ""))
    allowed |= _numbers(str(issue.get("evidence", {}).get("stat", "")))
    for item in issue.get("rubric_evidence", []):
        allowed |= _numbers(item.get("criterion", ""))
    for value in (state.get("state_counts") or {}).values():
        if isinstance(value, (int, float)):
            allowed.add(float(value))
    for value in (state.get("performance") or {}).values():
        if isinstance(value, (int, float)):
            allowed.add(float(value))
    return allowed


def _attempted_materials(records: list[dict], student_id: str, node_id: str) -> set[str]:
    return {
        record["material_id"]
        for record in records
        if record["student_id"] == student_id
        and record["node_id"] == node_id
        and record.get("attempted")
    }


def _material_error(material: dict, issue: dict) -> str | None:
    knowledge_id = issue["knowledge_id"]
    if material["material_type"] == "assessment":
        if knowledge_id not in material["knowledge_ids"]:
            return "assessment material is not mapped to the issue knowledge"
    elif material["material_type"] == "explain":
        if knowledge_id not in material["knowledge_ids"]:
            return "explain material is not mapped to the issue knowledge"
    elif material["material_type"] == "reference":
        if material["objective_id"] and material["objective_id"] != issue["objective_id"]:
            return "reference material is not in the issue objective"
    return None


def validate_recommendation(
    rec: dict,
    profile: dict,
    catalog: dict,
    node_available: set[str],
    records: list[dict],
    profile_sha256: str | None = None,
    review: dict | None = None,
) -> list[str]:
    errors = schema_errors(rec)
    if errors:
        return errors
    if rec["student_id"] != profile["student_id"]:
        errors.append("student_id does not match profile")
    if rec.get("node_id") and rec["node_id"] != profile["node_id"]:
        errors.append("node_id does not match profile")
    if profile_sha256 and rec["source"].get("profile_sha256") != profile_sha256:
        errors.append("profile_sha256 does not match profile file")

    issues = {issue["issue_id"]: issue for issue in profile.get("issues", [])}
    disputed = set(review["disputed_record_ids"]) if review else set()
    context = rec.get("review_context")
    if review is None:
        if context is not None:
            errors.append("review_context present without a review source")
    elif context is None:
        errors.append("review source present but recommendation lacks review_context")
    else:
        if context["report_sha256"] != review["report_sha256"]:
            errors.append("review_context report hash does not match the review report")
        if context["policy"] != review["policy"]:
            errors.append("review_context policy does not match")
        if not set(context["excluded_record_ids"]) <= disputed:
            errors.append("review_context cites records that are not disputed")
    attempted = _attempted_materials(records, profile["student_id"], profile["node_id"])
    seen_materials: set[str] = set()
    for index, item in enumerate(rec["plan"], 1):
        if item["seq"] != index:
            errors.append(f"plan[{index}]: seq is not contiguous")
        issue = issues.get(item["issue_id"])
        if issue is None:
            errors.append(f"plan[{index}]: issue_id not in profile")
            continue
        state = _state(profile, issue["knowledge_id"])
        block = state.get("review") or {}
        if "basis_records" in item:
            basis = set(item["basis_records"])
            if basis & disputed:
                errors.append(f"plan[{index}]: basis_records use a disputed record")
            expected_basis = {point["record_id"] for point in issue.get("rubric_evidence", [])}
            if basis != expected_basis:
                errors.append(f"plan[{index}]: basis_records do not match the issue evidence")
        if (
            block
            and block["usable_status"] == "insufficient_evidence"
            and item.get("activity_type") != "probe"
        ):
            errors.append(f"plan[{index}]: usable evidence is insufficient; must be a probe")
        if item["knowledge_ids"] != [issue["knowledge_id"]]:
            errors.append(f"plan[{index}]: knowledge_ids do not match issue")
        if item["objective_id"] != issue["objective_id"]:
            errors.append(f"plan[{index}]: objective_id does not match issue")
        if item["primary_material_id"] not in item["material_ids"]:
            errors.append(f"plan[{index}]: primary_material_id is not in material_ids")
        for material_id in item["material_ids"]:
            material = catalog["materials"].get(material_id)
            if material is None:
                errors.append(f"plan[{index}]: unknown material {material_id}")
                continue
            error = _material_error(material, issue)
            if error:
                errors.append(f"plan[{index}]: {material_id}: {error}")
            if material["material_type"] == "assessment" and material_id not in node_available:
                errors.append(f"plan[{index}]: {material_id}: assessment outside node scope")
            if material_id in seen_materials:
                errors.append(f"plan[{index}]: material reused across plan items: {material_id}")
            seen_materials.add(material_id)
        allowed = allowed_numbers(issue, _state(profile, issue["knowledge_id"]))
        for field in ("reason", "check"):
            unknown = _numbers(item[field]) - allowed
            if unknown:
                errors.append(f"plan[{index}]: {field} contains unlocked numbers {sorted(unknown)}")
        if issue["issue_id"] not in item["reason"]:
            errors.append(f"plan[{index}]: reason does not cite issue_id")
        if not item["check"].strip():
            errors.append(f"plan[{index}]: empty check")

    for entry in rec.get("review_required", []):
        if entry["issue_id"] not in issues:
            errors.append("review_required: issue_id not in profile")
        if review is None:
            errors.append("review_required present without a review source")
        elif not set(entry["record_ids"]) <= disputed:
            errors.append("review_required: record_ids are not disputed")

    graph_edges = catalog.get("graph_edges") or {}
    for index, item in enumerate(rec["plan"], 1):
        check = item["prerequisite_check"]
        reviewed = set(check.get("reviewed_edges") or [])
        draft = set(check.get("draft_edges") or [])
        if reviewed & draft:
            errors.append(f"plan[{index}]: a graph edge cannot be both reviewed and draft")
        for edge_id in reviewed | draft:
            edge = graph_edges.get(edge_id)
            if edge is None:
                errors.append(f"plan[{index}]: unknown graph edge {edge_id}")
                continue
            expected = "reviewed" if edge_id in reviewed else "draft"
            if edge["review_status"] != expected:
                errors.append(f"plan[{index}]: graph edge {edge_id} status mismatch")
        if check["satisfied"] != (not check["missing_knowledge_ids"]):
            errors.append(f"plan[{index}]: prerequisite satisfied flag mismatch")
        knowledge_id = item["knowledge_ids"][0]
        for source in (check.get("missing_knowledge_ids") or []) + (
            check.get("pending_knowledge_ids") or []
        ):
            backed = any(
                edge["edge_id"] in reviewed
                and edge["relation_type"] == "prerequisite"
                and edge["target_node_id"] == knowledge_id
                and edge["source_node_id"] == source
                for edge in graph_edges.values()
            )
            if not backed:
                errors.append(f"plan[{index}]: prerequisite {source} is not backed by a reviewed edge")
        for note in item.get("relation_notes") or []:
            edge = graph_edges.get(note["edge_id"])
            if edge is None:
                errors.append(f"plan[{index}]: relation note cites an unknown edge")
            elif edge["review_status"] != note["review_status"]:
                errors.append(f"plan[{index}]: relation note status mismatch")
    for entry in rec.get("deferred", []):
        if entry["issue_id"] not in issues:
            errors.append("deferred: issue_id not in profile")

    plan_ids: dict[str, int] = {}
    if "plan_version" in rec or "plan_id" in rec:
        version = rec.get("plan_version")
        if not isinstance(version, int) or version < 1:
            errors.append("plan_version missing or invalid")
        else:
            expected_id = f"PLAN-{rec['student_id'][1:]}-{rec['node_id']}-v{version}"
            if rec.get("plan_id") != expected_id:
                errors.append("plan_id does not match student/node/version")
    for index, item in enumerate(rec["plan"], 1):
        if item["seq"] != index:
            errors.append(f"plan[{index}]: seq is not contiguous")
        plan_item_id = item.get("plan_item_id")
        if plan_item_id:
            if plan_item_id in plan_ids:
                errors.append(f"plan[{index}]: duplicate plan_item_id")
            plan_ids[plan_item_id] = index
            if item.get("plan_version", rec.get("plan_version")) > (rec.get("plan_version") or 0):
                errors.append(f"plan[{index}]: item version is newer than the plan")
            if item.get("status") not in {"planned", "in_progress"}:
                errors.append(f"plan[{index}]: invalid status")
        condition = item.get("completion_condition")
        if condition:
            if not set(condition["material_ids"]) <= set(item["material_ids"]):
                errors.append(f"plan[{index}]: completion condition cites unused materials")
            if condition["type"] == "probe_evidence" and item["activity_type"] != "probe":
                errors.append(f"plan[{index}]: probe completion condition on a non-probe item")
            if condition["type"] == "full_credit" and item["activity_type"] == "probe":
                errors.append(f"plan[{index}]: full-credit condition on a probe item")
    for index, item in enumerate(rec["plan"], 1):
        for parent in item.get("prerequisite_item_ids") or []:
            if parent not in plan_ids:
                errors.append(f"plan[{index}]: prerequisite item {parent} is not in the plan")
            elif plan_ids[parent] >= index:
                errors.append(f"plan[{index}]: prerequisite item {parent} must come earlier")
    history_ids: set[str] = set()
    for entry in rec.get("history") or []:
        plan_item_id = entry["plan_item_id"]
        if plan_item_id in history_ids:
            errors.append("history: duplicate completed item")
        if plan_item_id in plan_ids:
            errors.append("history: a completed item must not stay in the active plan")
        history_ids.add(plan_item_id)
    diff = rec.get("plan_diff")
    if diff:
        active_issues = {item["issue_id"] for item in rec["plan"]}
        diff_completed = {entry["plan_item_id"] for entry in diff["completed"]}
        if not diff_completed <= history_ids:
            errors.append("plan_diff: completed entry is not in history")
        for entry in diff["added"]:
            if entry["issue_id"] not in active_issues:
                errors.append("plan_diff: added issue is not in the plan")
        for entry in diff["retained"]:
            if entry["issue_id"] not in active_issues:
                errors.append("plan_diff: retained issue is not in the plan")
        for entry in diff["removed"]:
            if entry["issue_id"] in active_issues:
                errors.append("plan_diff: removed issue is still in the plan")

    probe = rec["probe_plan"]
    if len(set(probe["items"])) != len(probe["items"]):
        errors.append("probe_plan: duplicate material")
    if probe["needed"] != bool(probe["items"]):
        errors.append("probe_plan.needed must equal bool(items)")
    for material_id in probe["items"]:
        material = catalog["materials"].get(material_id)
        if material is None:
            errors.append(f"probe_plan: unknown material {material_id}")
            continue
        if material["material_type"] != "assessment":
            errors.append(f"probe_plan: {material_id} is not an assessment item")
        if material_id in attempted:
            errors.append(f"probe_plan: {material_id} was already attempted")
        if material_id not in node_available:
            errors.append(f"probe_plan: {material_id} is outside node scope")
    scoring = probe.get("scoring")
    if scoring:
        weights = scoring["weights"]
        for candidate in scoring["candidates"]:
            total = sum(
                weights.get(name, 0.0) * value
                for name, value in candidate["components"].items()
            )
            if abs(total - candidate["total"]) > 1e-6:
                errors.append(
                    f"probe_plan: candidate {candidate['material_id']} total is not recomputable"
                )
        candidate_ids = {candidate["material_id"] for candidate in scoring["candidates"]}
        if not set(probe["items"]) <= candidate_ids:
            errors.append("probe_plan: selected probe is missing from the scoring record")
    if not profile["coverage"]["scope_known"]:
        if rec["plan"] or probe["items"] or probe["needed"]:
            errors.append("scope_unknown profile must not receive a plan")
    return errors


def _load_local_run(run: Path, manifest: dict) -> tuple[dict, Path]:
    knowledge_path = run / "knowledge_base.json"
    if not knowledge_path.is_file():
        knowledge_path = Path(manifest["source_knowledge"]["original_path"])
    if not knowledge_path.is_file():
        raise ValueError("knowledge base not found for verification")
    bundle_path = run / "inputs" / "diagnosis_input.json"
    if not bundle_path.is_file():
        bundle_path = Path(manifest["source_run"]["path"]) / "diagnosis_input.json"
    if not bundle_path.is_file():
        raise ValueError("diagnosis input not found for verification")
    return json.loads(bundle_path.read_text(encoding="utf-8")), knowledge_path


def _profile_path(run: Path, manifest: dict, node_id: str, student_id: str) -> Path:
    local = run / "inputs" / "nodes" / node_id / "students" / f"{student_id}.json"
    if local.is_file():
        return local
    return Path(manifest["source_run"]["path"]) / "nodes" / node_id / "students" / f"{student_id}.json"


def validate_saved_recommendations(run: Path) -> dict:
    run = Path(run)
    manifest_path = run / "run_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"not a completed recommendation run: {run}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle, knowledge_path = _load_local_run(run, manifest)
    catalog = build_catalog(load_knowledge_base(knowledge_path))
    review = None
    if manifest.get("review"):
        from knowflow.review.pipeline import context_from_run_manifest

        review = context_from_run_manifest(manifest)
    nodes = {node["node_id"]: node for node in bundle["nodes"]}
    records = bundle["records"]

    targets = manifest["targets"]
    errors: list[str] = []
    warnings: list[str] = []
    for target in targets:
        path = run / target["path"]
        if not path.is_file():
            errors.append(f"{target['path']}: missing")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != target["sha256"]:
            errors.append(f"{target['path']}: sha256 changed")
        rec = json.loads(path.read_text(encoding="utf-8"))
        node_id = rec.get("node_id")
        if node_id not in nodes:
            errors.append(f"{target['path']}: unknown node {node_id}")
            continue
        profile_path = _profile_path(run, manifest, node_id, rec["student_id"])
        if not profile_path.is_file():
            errors.append(f"{target['path']}: profile missing")
            continue
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile_sha = hashlib.sha256(profile_path.read_bytes()).hexdigest()
        errors.extend(
            f"{target['path']}: {error}"
            for error in validate_recommendation(
                rec,
                profile,
                catalog,
                set(nodes[node_id]["material_ids"]),
                records,
                profile_sha,
                review,
            )
        )
        for item in rec["plan"]:
            for material_id in item["material_ids"]:
                material = catalog["materials"][material_id]
                if material["material_type"] != "assessment" and material_id not in nodes[node_id]["material_ids"]:
                    warnings.append(f"{target['path']}: {material_id} is outside node assessment scope")
    if not targets:
        errors.append("no recommendation targets in manifest")
    index_path = run / "index.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if index.get("counts", {}).get("students") != len(targets):
            errors.append("index counts do not match manifest targets")
        recs = [
            json.loads((run / target["path"]).read_text(encoding="utf-8"))
            for target in targets
            if (run / target["path"]).is_file()
        ]
        if index.get("counts", {}).get("plan_items") != sum(len(rec["plan"]) for rec in recs):
            errors.append("index plan_items do not match recommendation files")
        if index.get("counts", {}).get("probe_needed_students") != sum(
            rec["probe_plan"]["needed"] for rec in recs
        ):
            errors.append("index probe_needed_students do not match recommendation files")
        for entry in index.get("students", []):
            if not (run / entry["path"]).is_file():
                errors.append(f"index points to missing file: {entry['path']}")
    else:
        errors.append("index.json missing")

    checks = [
        {
            "id": "task3.schema_and_references",
            "level": "error",
            "passed": not errors,
            "message": "任务3 schema、issue/材料/画像引用与节点范围"
            + ("通过" if not errors else f"失败：{'; '.join(errors[:10])}"),
            "refs": [],
        },
        {
            "id": "task3.numeric_lock",
            "level": "error",
            "passed": not any("unlocked numbers" in error for error in errors),
            "message": "reason/check 中的数字来自 issue 证据或策略常量",
            "refs": [],
        },
        {
            "id": "task3.probe_is_unattempted",
            "level": "error",
            "passed": not any("already attempted" in error for error in errors),
            "message": "probe_plan 只使用该生在该节点未作答的测评题",
            "refs": [],
        },
        {
            "id": "task3.heuristic_difficulty_time",
            "level": "warning",
            "passed": True,
            "message": "difficulty/est_minutes 为规则推算值；官方材料没有这两个字段",
            "refs": [],
        },
    ]
    if warnings:
        checks.append(
            {
                "id": "task3.material_scope",
                "level": "warning",
                "passed": True,
                "message": f"{len(warnings)} 处讲解材料不在节点测评范围内，按已登记材料使用",
                "refs": sorted(set(warnings))[:20],
            }
        )
    passed = sum(1 for check in checks if check["passed"])
    failed = sum(1 for check in checks if not check["passed"] and check["level"] == "error")
    return {
        "schema_version": "1.1.0",
        "run_id": run.name,
        "generated_at": manifest["generated_at"],
        "targets": targets,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
            "warnings": sum(1 for check in checks if check["level"] == "warning"),
        },
        "gate": "pass" if not errors else "fail",
        "errors": errors[:50],
        "policy_version": POLICY_VERSION,
    }
