"""Adapt validated task outputs for the dashboard, without changing public contracts.

All generated data stays in ignored artifacts/web. Raw answers are deliberately
absent from the snapshot; an explicit, local evidence request can retrieve them.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from knowflow.contracts import repo_root
from knowflow.diagnosis.pipeline import build_bundle, run_diagnosis
from knowflow.diagnosis.validation import validate_saved_run
from knowflow.io.pipeline import run_adapt
from knowflow.knowledge.graph import load_graph
from knowflow.knowledge.pipeline import (
    build_knowledge_base,
    validate_knowledge_base,
    write_knowledge_base,
)
from knowflow.recommend.pipeline import recommend_run, verify_recommend
from knowflow.review.pipeline import build_context, load_report, scan_dataset
from knowflow.review.validation import validate_report


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_summary(records: list[dict]) -> dict:
    """Only scored attempts enter the score denominator; absent scope stays null."""
    assigned = [r for r in records if r["assigned"]]
    attempted = [r for r in assigned if r["attempted"]]
    graded = [r for r in attempted if r["score"] is not None]
    maximum = sum(r["max_score"] for r in graded)
    return {
        "assigned": len(assigned),
        "attempted": len(attempted),
        "graded": len(graded),
        "pending": len(attempted) - len(graded),
        "not_attempted": len(assigned) - len(attempted),
        "completion": len(attempted) / len(assigned) if assigned else None,
        "score_ratio": sum(r["score"] for r in graded) / maximum if maximum else None,
        "earned_score": sum(r["score"] for r in graded),
        "possible_score": maximum,
    }


def source_fingerprint(root: Path, raw: Path) -> str:
    digest = hashlib.sha256()
    files = list(raw.rglob("*.csv"))
    files += list((root / "src/knowflow").rglob("*.py"))
    files += list((root / "schemas").rglob("*.json"))
    graph_root = root / "knowledge"
    if graph_root.is_dir():
        files += list(graph_root.rglob("*.json"))
    for path in sorted(files):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare(refresh: bool = False, llm: bool | None = None) -> Path:
    """Build a private, isolated snapshot from official raw data, or reuse its cache.

    ``llm=None`` keeps whichever mode the cached snapshot used, so starting the
    dashboard after one ``--llm`` build does not silently rebuild with templates.
    """

    root = repo_root()
    raw = root / "data/raw/official-v1"
    if not raw.is_dir():
        raise ValueError("请先把赛事资料按 README 放入 data/raw/official-v1。Git 不包含官方数据。")
    fingerprint = source_fingerprint(root, raw)
    cache = root / "artifacts/web/latest.json"
    cached = read_json(cache) if cache.is_file() else {}
    effective_llm = llm if llm is not None else bool(cached.get("llm", False))
    if cached and not refresh:
        run = root / cached["run"]
        if (
            cached.get("fingerprint") == fingerprint
            and bool(cached.get("llm", False)) == effective_llm
            and (run / "knowledge_base.json").is_file()
        ):
            return run
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run = root / "artifacts/web" / stamp
    canonical = run / "canonical/official-v1"
    print("[1/5] Preparing an isolated canonical dataset...", flush=True)
    run_adapt(raw, canonical, dataset_id="official-v1")
    print("[2/5] Building the course knowledge base...", flush=True)
    graph_path = root / "knowledge" / "curriculum_graph.json"
    graph = load_graph(graph_path) if graph_path.is_file() else None
    knowledge = build_knowledge_base(canonical, "official-v1", graph=graph)
    write_knowledge_base(knowledge, run / "knowledge_base.json")
    print("[3/5] Scanning for disputed scores...", flush=True)
    scan_dataset("official-v1", root=canonical.parent, output=run / "review")
    review = build_context(load_report(run / "review"), run / "review", "official")
    print("[4/5] Building student and class profiles...", flush=True)
    bundle, _ = build_bundle("official-v1", root=canonical.parent)
    run_diagnosis(bundle, run / "diagnosis", node_id="all", review=review)
    print("[5/5] Building evidence-linked recommendations...", flush=True)
    report = recommend_run(
        run=str(run / "diagnosis"),
        knowledge=str(run / "knowledge_base.json"),
        node="all",
        output=str(run / "recommendations"),
        llm=effective_llm,
        previous="none",
    )
    if report["gate"] != "pass":
        raise ValueError("建议校验未通过，请查看本机运行目录中的 validation_report.json。")
    write_json(
        cache,
        {
            "run": run.relative_to(root).as_posix(),
            "fingerprint": fingerprint,
            "llm": effective_llm,
        },
    )
    return run


def load_dashboard(run: Path) -> dict:
    """Verify saved outputs before exposing a deliberately limited presentation view."""
    run = run.resolve()
    knowledge = read_json(run / "knowledge_base.json")
    validate_knowledge_base(knowledge)
    diagnostic_gate = validate_saved_run(run / "diagnosis")
    recommendation_gate = verify_recommend(str(run / "recommendations"))
    if diagnostic_gate["gate"] != "pass" or recommendation_gate["gate"] != "pass":
        raise ValueError("画像或建议的复算校验未通过；请使用 --refresh 重新生成。")
    # Recommendations must reference this exact knowledge base and these profiles.
    if read_json(run / "recommendations/knowledge_base.json") != knowledge:
        raise ValueError("建议与课程知识底座不属于同一个版本。")
    bundle = read_json(run / "diagnosis/diagnosis_input.json")
    review_report = None
    review_path = run / "review" / "review_report.json"
    if review_path.is_file():
        review_report = read_json(review_path)
        review_errors = validate_report(review_report)
        if review_errors:
            raise ValueError("存疑评分审查报告未通过校验；请使用 --refresh 重新生成。")
    students, classes, recommendations = {}, {}, {}
    for node in bundle["nodes"]:
        nid = node["node_id"]
        students[nid], classes[nid], recommendations[nid] = {}, {}, {}
        for path in sorted((run / "diagnosis/nodes" / nid / "students").glob("*.json")):
            profile = read_json(path)
            sid = profile["student_id"]
            students[nid][sid] = profile
            recommendation = read_json(run / "recommendations/nodes" / nid / "students" / path.name)
            if (
                recommendation["source"]["profile_sha256"]
                != hashlib.sha256(path.read_bytes()).hexdigest()
            ):
                raise ValueError("个人建议引用的画像版本不一致。")
            recommendations[nid][sid] = recommendation
        for path in sorted((run / "diagnosis/nodes" / nid / "classes").glob("*.json")):
            profile = read_json(path)
            classes[nid][profile["class_id"]] = profile
    # A small allowlist prevents future upstream fields leaking raw answers by accident.
    record_fields = (
        "record_id",
        "student_id",
        "material_id",
        "node_id",
        "assigned",
        "attempted",
        "score",
        "max_score",
        "state",
        "rubric_scores",
    )
    records = [{k: r[k] for k in record_fields if k in r} for r in bundle["records"]]
    stats = {
        node["node_id"]: {
            s["student_id"]: record_summary(
                [
                    r
                    for r in records
                    if r["node_id"] == node["node_id"] and r["student_id"] == s["student_id"]
                ]
            )
            for s in bundle["students"]
        }
        for node in bundle["nodes"]
    }
    material_fields = (
        "material_id",
        "title",
        "material_type",
        "objective_id",
        "source",
        "item_format",
        "difficulty",
        "est_minutes",
        "license",
    )
    view_knowledge = {
        k: knowledge[k] for k in ("objectives", "knowledge", "edges", "qmatrix", "counts")
    }
    if "curriculum_graph" in knowledge:
        view_knowledge["curriculum_graph"] = knowledge["curriculum_graph"]
    view_knowledge["materials"] = [
        {k: m.get(k) for k in material_fields} for m in knowledge["materials"]
    ]
    recommendation_manifest = read_json(run / "recommendations" / "run_manifest.json")
    llm_items = int((recommendation_manifest.get("llm") or {}).get("items_used") or 0)
    return {
        "meta": {
            "dataset_id": bundle["dataset_id"],
            "generated_at": bundle["generated_at"],
            "snapshot_id": run.name,
            "snapshot_version": "1",
            "subject": knowledge["subject"],
            "grade": knowledge["grade"],
            "local_only": True,
            "recommendation_mode": "规则推荐 + LLM 润色" if llm_items else "规则推荐",
            "validation": {"knowledge": "pass", "diagnosis": "pass", "recommendation": "pass"},
        },
        "students": [
            {k: s[k] for k in ("student_id", "group_id", "grade")} for s in bundle["students"]
        ],
        "nodes": bundle["nodes"],
        "knowledge_base": view_knowledge,
        "profiles": students,
        "classes": classes,
        "recommendations": recommendations,
        "records": records,
        "stats": stats,
        "quality": bundle["quality_report"],
        "reviews": None
        if review_report is None
        else {
            "policy": review_report["policy"],
            "counts": review_report["counts"],
            "candidates": review_report["candidates"],
        },
        "review_meta": None
        if review_report is None
        else {
            "rule_version": review_report["rule_version"],
            "generated_at": review_report["generated_at"],
            "decisions_applied": review_report.get("decisions_applied", 0),
        },
    }
