"""KnowFlow command line entry point.

Repository checks, single-file schema validation, the Task-2 diagnosis flow
(``run`` / ``verify-run`` / ``evidence``), the Task-3 recommendation flow
(``recommend`` / ``verify-recommend``), and the optional language layer
(``explain``).  The LLM edge is off by default; rules remain the fallback.

Owner: R4.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import get_settings
from .contracts import (
    check_repo,
    iter_schema_paths,
    repo_root,
    validate_instance,
)


def _cmd_check(_: argparse.Namespace) -> int:
    root = repo_root()
    errors = check_repo(root)
    if errors:
        print("KnowFlow contract check: FAILED")
        for error in errors:
            print(f"  - {error}")
        return 1
    count = len(iter_schema_paths(root))
    print(f"KnowFlow contract check: OK ({count} schemas)")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    schema_path = Path(args.schema)
    data_path = Path(args.data)
    for path, label in ((schema_path, "schema"), (data_path, "data")):
        if not path.is_file():
            print(f"{label} not found: {path}", file=sys.stderr)
            return 2
    errors = validate_instance(schema_path, data_path)
    if errors:
        print(f"schema validation: FAILED ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("schema validation: OK (0 errors)")
    return 0


def _cmd_version(_: argparse.Namespace) -> int:
    print(f"knowflow {__version__}")
    return 0


def _cmd_config(_: argparse.Namespace) -> int:
    """Print resolved settings (never the key itself) to debug local setup."""

    settings = get_settings()
    print(f"llm.enabled   = {settings.llm_enabled}")
    print(f"llm.ready     = {settings.llm_ready}")
    print(f"llm.provider  = {settings.llm_provider}")
    print(f"llm.model     = {settings.llm_model}")
    print(f"llm.base_url  = {settings.llm_base_url}")
    print(f"llm.api_key   = {'(set)' if settings.llm_api_key else '(empty)'}")
    print(f"llm.timeout   = {settings.llm_timeout_seconds}s")
    print(f"data_dir      = {settings.data_dir}")
    print(f"artifact_dir  = {settings.artifact_dir}")
    print(f"log_level     = {settings.log_level}")
    print(f"random_seed   = {settings.random_seed}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from .diagnosis.mastery import DiagnosisConfig
    from .diagnosis.pipeline import build_bundle, run_diagnosis
    from .review.pipeline import build_context, load_report

    bundle, _ = build_bundle(args.dataset)
    config = (
        DiagnosisConfig(**json.loads(Path(args.config).read_text(encoding="utf-8")))
        if args.config
        else DiagnosisConfig()
    )
    review = None
    if args.review:
        report = load_report(Path(args.review))
        review = build_context(report, Path(args.review), args.review_policy)
    elif args.review_policy != "official":
        print("KnowFlow: --review-policy requires --review <目录>", file=sys.stderr)
        return 2
    supplemental = []
    if args.supplemental:
        from .feedback.ledger import load_events

        supplemental = load_events(Path(args.supplemental))
    output = (
        Path(args.output)
        if args.output
        else repo_root()
        / "artifacts"
        / "run"
        / f"{bundle['dataset_id']}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    )
    result = run_diagnosis(
        bundle,
        output,
        config,
        args.node,
        review,
        supplemental,
        args.previous,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_knowledge(args: argparse.Namespace) -> int:
    from .knowledge.graph import load_graph
    from .knowledge.pipeline import apply_curation, build_knowledge_base, write_knowledge_base

    base = Path(args.input) if args.input else repo_root() / "data/interim" / args.dataset
    if not base.is_dir():
        raise ValueError(
            f"canonical tables not found: {base}; run scripts/build_canonical.py first"
        )
    graph = load_graph(args.graph) if args.graph else None
    data = build_knowledge_base(base, args.dataset, graph=graph)
    if args.curation:
        data = apply_curation(
            data, json.loads(Path(args.curation).read_text(encoding="utf-8")), base
        )
    output = (
        Path(args.output)
        if args.output
        else repo_root()
        / "artifacts/knowledge"
        / f"{args.dataset}-{datetime.now():%Y%m%d-%H%M%S-%f}"
        / "knowledge_base.json"
    )
    path = write_knowledge_base(data, output)
    print(json.dumps({"output": str(path), "counts": data["counts"]}, ensure_ascii=False, indent=2))
    return 0


def _resolve_run(value: str | None) -> Path:
    from .diagnosis.pipeline import latest_run_dir

    if value in (None, "", "latest"):
        return latest_run_dir()
    return Path(value)


def _cmd_verify_run(args: argparse.Namespace) -> int:
    from .diagnosis.validation import validate_saved_run

    result = validate_saved_run(_resolve_run(args.run))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "pass" else 1


def _cmd_evidence(args: argparse.Namespace) -> int:
    from .diagnosis.pipeline import export_evidence

    path = export_evidence(_resolve_run(args.run), args.record)
    print(f"LOCAL EVIDENCE {path}")
    return 0


def _cmd_recommend(args: argparse.Namespace) -> int:
    from .recommend.pipeline import recommend_run

    result = recommend_run(
        run=args.run,
        knowledge=args.knowledge,
        node=args.node,
        output=args.output,
        llm=args.llm,
        progress=args.progress,
        previous=args.previous,
        probe_weights=(
            json.loads(Path(args.probe_weights).read_text(encoding="utf-8"))
            if args.probe_weights
            else None
        ),
        feedback=args.feedback,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "pass" else 1


def _cmd_path_event(args: argparse.Namespace) -> int:
    from .diagnosis.pipeline import load_canonical
    from .recommend.path import (
        append_event,
        load_events,
        make_event,
        progress_path,
        validate_event_refs,
    )
    from .recommend.pipeline import latest_recommend_dir

    _, tables, _ = load_canonical(args.dataset)
    plan_path = Path(args.plan) if args.plan else latest_recommend_dir()
    if plan_path.is_dir():
        plan_path = plan_path / "nodes" / args.node / "students" / f"{args.student}.json"
    if not plan_path.is_file():
        raise ValueError(f"recommendation not found: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    items = plan.get("plan") or []
    if args.seq is not None:
        item = next((entry for entry in items if entry.get("seq") == args.seq), None)
    else:
        item = next(
            (entry for entry in items if entry.get("plan_item_id") == args.plan_item), None
        )
    if item is None:
        raise ValueError("plan item not found; pass --seq or --plan-item from the current plan")
    path = Path(args.progress) if args.progress else progress_path(args.dataset)
    existing = load_events(path)
    event = make_event(
        student_id=args.student,
        node_id=args.node,
        plan_version=int(item.get("plan_version") or plan.get("plan_version") or 1),
        event_type=args.event,
        issue_id=item["issue_id"],
        knowledge_id=item["knowledge_ids"][0],
        material_ids=list(item["material_ids"]),
        activity_type=item.get("activity_type") or "consolidate",
        seq=int(item["seq"]),
        source=args.source,
        note=args.note,
        existing=existing,
    )
    errors = validate_event_refs(event, tables)
    if errors:
        raise ValueError("invalid progress event: " + "; ".join(errors))
    append_event(path, event)
    print(
        json.dumps(
            {
                "event": event,
                "progress_file": str(path.resolve()),
                "warning": "进度事件只记录执行状态，不代表答对或掌握；诊断不会被改写。",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _feedback_args(args: argparse.Namespace) -> tuple[dict, dict, dict]:
    from .diagnosis.pipeline import build_bundle
    from .recommend.catalog import build_catalog, load_knowledge_base
    from .recommend.pipeline import default_knowledge_path

    bundle, _ = build_bundle(args.dataset)
    knowledge = load_knowledge_base(default_knowledge_path())
    return bundle, build_catalog(knowledge), {}


def _cmd_feedback_attempt(args: argparse.Namespace) -> int:
    from .feedback.ledger import (
        append_event,
        feedback_path,
        load_events,
        make_event,
        validate_event,
    )

    bundle, _, _ = _feedback_args(args)
    material = next(
        (m for m in bundle["materials"] if m["material_id"] == args.material), None
    )
    if material is None:
        raise ValueError(f"material {args.material} is not an assessment item")
    max_score = args.max_score if args.max_score is not None else material["max_score"]
    path = Path(args.events) if args.events else feedback_path(args.dataset)
    existing = load_events(path)
    points = json.loads(Path(args.rubric_json).read_text(encoding="utf-8")) if args.rubric_json else None
    event = make_event(
        event_type="supplemental_attempt",
        student_id=args.student,
        node_id=args.node,
        actor="student",
        source=args.source,
        material_id=args.material,
        score=args.score,
        max_score=max_score,
        submitted_at=args.submitted_at,
        rubric_points=points,
        note=args.note,
        existing=existing,
    )
    errors = validate_event(event, bundle, {"materials": {}})
    if errors:
        raise ValueError("invalid supplemental attempt: " + "; ".join(errors))
    append_event(path, event)
    print(
        json.dumps(
            {"event": event, "events_file": str(path.resolve())},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_feedback_adjust(args: argparse.Namespace) -> int:
    from .feedback.ledger import (
        append_event,
        feedback_path,
        load_events,
        make_event,
        plan_snapshot,
        validate_event,
    )
    from .recommend.pipeline import latest_recommend_dir

    bundle, catalog, _ = _feedback_args(args)
    plan_path = Path(args.plan) if args.plan else latest_recommend_dir()
    if plan_path.is_dir():
        plan_path = plan_path / "nodes" / args.node / "students" / f"{args.student}.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    items = plan.get("plan") or []
    if args.seq is not None:
        item = next((entry for entry in items if entry.get("seq") == args.seq), None)
    else:
        item = next(
            (entry for entry in items if entry.get("plan_item_id") == args.plan_item), None
        )
    if item is None:
        raise ValueError("plan item not found in the current recommendation")
    payload = {}
    if args.materials:
        payload["material_ids"] = [value.strip() for value in args.materials.split(",") if value.strip()]
    if args.minutes is not None:
        payload["est_minutes"] = args.minutes
    if args.difficulty is not None:
        payload["difficulty"] = args.difficulty
    path = Path(args.events) if args.events else feedback_path(args.dataset)
    existing = load_events(path)
    event = make_event(
        event_type="teacher_adjustment",
        student_id=args.student,
        node_id=args.node,
        actor="teacher",
        source=args.source,
        plan_item_id=item["plan_item_id"],
        plan_version=item.get("plan_version", plan["plan_version"]),
        action=args.action,
        issue_id=item["issue_id"],
        knowledge_id=item["knowledge_ids"][0],
        activity_type=item.get("activity_type", "consolidate"),
        payload=payload or None,
        reason=args.reason,
        snapshot=plan_snapshot(item),
        existing=existing,
    )
    errors = validate_event(event, bundle, catalog)
    if errors:
        raise ValueError("invalid teacher adjustment: " + "; ".join(errors))
    append_event(path, event)
    print(
        json.dumps(
            {"event": event, "events_file": str(path.resolve())},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_feedback_comment(args: argparse.Namespace) -> int:
    from .feedback.ledger import (
        append_event,
        feedback_path,
        load_events,
        make_event,
        validate_event,
    )
    from .recommend.pipeline import latest_recommend_dir

    bundle, catalog, _ = _feedback_args(args)
    plan_item_id = None
    if args.seq is not None or args.plan_item:
        plan_path = Path(args.plan) if args.plan else latest_recommend_dir()
        if plan_path.is_dir():
            plan_path = plan_path / "nodes" / args.node / "students" / f"{args.student}.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        items = plan.get("plan") or []
        item = next(
            (
                entry
                for entry in items
                if (args.seq is not None and entry.get("seq") == args.seq)
                or (args.plan_item and entry.get("plan_item_id") == args.plan_item)
            ),
            None,
        )
        if item is None:
            raise ValueError("plan item not found")
        plan_item_id = item["plan_item_id"]
    path = Path(args.events) if args.events else feedback_path(args.dataset)
    event = make_event(
        event_type="teacher_comment",
        student_id=args.student,
        node_id=args.node,
        actor="teacher",
        source=args.source,
        plan_item_id=plan_item_id,
        text=args.text,
        existing=load_events(path),
    )
    errors = validate_event(event, bundle, catalog)
    if errors:
        raise ValueError("invalid teacher comment: " + "; ".join(errors))
    append_event(path, event)
    print(json.dumps({"event": event}, ensure_ascii=False, indent=2))
    return 0


def _cmd_feedback_student(args: argparse.Namespace) -> int:
    from .feedback.ledger import (
        append_event,
        feedback_path,
        load_events,
        make_event,
        validate_event,
    )

    bundle, catalog, _ = _feedback_args(args)
    path = Path(args.events) if args.events else feedback_path(args.dataset)
    event = make_event(
        event_type="student_feedback",
        student_id=args.student,
        node_id=args.node,
        actor="student",
        source=args.source,
        plan_item_id=args.plan_item,
        kind=args.kind,
        rating=args.rating,
        text=args.text,
        existing=load_events(path),
    )
    errors = validate_event(event, bundle, catalog)
    if errors:
        raise ValueError("invalid student feedback: " + "; ".join(errors))
    append_event(path, event)
    print(json.dumps({"event": event}, ensure_ascii=False, indent=2))
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    from .llm.explain import explain_student

    result = explain_student(
        student=args.student,
        knowledge_id=args.knowledge_id,
        node=args.node,
        run=args.run,
        knowledge=args.knowledge,
        output=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_review_scan(args: argparse.Namespace) -> int:
    from .review.pipeline import scan_dataset

    result = scan_dataset(
        args.dataset,
        output=Path(args.output) if args.output else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_review_decide(args: argparse.Namespace) -> int:
    from .review.pipeline import decide

    result = decide(
        args.dataset,
        args.record,
        args.status,
        args.note,
        reviewer=args.reviewer,
        source=args.source,
        flag_codes=args.code or [],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_verify_recommend(args: argparse.Namespace) -> int:
    from .recommend.pipeline import verify_recommend

    result = verify_recommend(args.run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["gate"] == "pass" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowflow",
        description="KnowFlow: evidence-traceable learning diagnosis.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check", help="check repository structure, schemas and data hygiene"
    )
    check_parser.set_defaults(func=_cmd_check)

    validate_parser = subparsers.add_parser(
        "validate", help="validate one JSON document against a schema"
    )
    validate_parser.add_argument("--schema", required=True, help="path to *.schema.json")
    validate_parser.add_argument("--data", required=True, help="path to JSON data")
    validate_parser.set_defaults(func=_cmd_validate)

    version_parser = subparsers.add_parser("version", help="print version")
    version_parser.set_defaults(func=_cmd_version)

    config_parser = subparsers.add_parser(
        "config", help="print resolved settings (keys are masked)"
    )
    config_parser.set_defaults(func=_cmd_config)

    run_parser = subparsers.add_parser(
        "run", help="run Task 2 on canonical tables: cleaning view, profiles, verification"
    )
    run_parser.add_argument("--dataset", default="official-v1")
    run_parser.add_argument(
        "--node", default="all", help="all, latest, or a node ID such as N02"
    )
    run_parser.add_argument("--config", help="JSON diagnosis parameter overrides; recorded in the run")
    run_parser.add_argument(
        "--review",
        help="review-scan 产出的目录；启用后把存疑证据排除出问题识别与建议",
    )
    run_parser.add_argument(
        "--review-policy",
        choices=["official", "exclude_flagged"],
        default="official",
        help="official=画像顶层数字沿用官方账本；exclude_flagged=按剔除存疑证据后的口径",
    )
    run_parser.add_argument(
        "--output", help="new run directory; defaults to artifacts/run/<dataset>-<timestamp>"
    )
    run_parser.add_argument(
        "--supplemental",
        help="feedback events JSONL; supplemental attempts become derived evidence (canonical untouched)",
    )
    run_parser.add_argument("--previous", help="previous run directory for diagnosis_diff.json")
    run_parser.set_defaults(func=_cmd_run)

    verify_parser = subparsers.add_parser(
        "verify-run", help="revalidate and recompute a saved Task-2 run"
    )
    verify_parser.add_argument(
        "--run",
        help="run directory or 'latest'; defaults to the newest run under artifacts/run",
    )
    verify_parser.set_defaults(func=_cmd_verify_run)

    evidence_parser = subparsers.add_parser(
        "evidence", help="export original answer/steps locally for a cited record"
    )
    evidence_parser.add_argument(
        "--run",
        help="run directory or 'latest'; defaults to the newest run under artifacts/run",
    )
    evidence_parser.add_argument("--record", required=True)
    evidence_parser.set_defaults(func=_cmd_evidence)

    knowledge_parser = subparsers.add_parser(
        "knowledge", help="build and validate Task-1 knowledge base"
    )
    knowledge_parser.add_argument("--dataset", default="official-v1")
    knowledge_parser.add_argument(
        "--input", help="canonical directory; defaults to data/interim/<dataset>"
    )
    knowledge_parser.add_argument(
        "--output", help="new JSON file; defaults to artifacts/knowledge/<run>/knowledge_base.json"
    )
    knowledge_parser.add_argument(
        "--curation", help="reviewed local annotations pinned to canonical hashes"
    )
    knowledge_parser.add_argument(
        "--graph",
        help="formal curriculum graph JSON, e.g. knowledge/curriculum_graph.json",
    )
    knowledge_parser.set_defaults(func=_cmd_knowledge)

    recommend_parser = subparsers.add_parser(
        "recommend", help="build Task-3 learning plans from a Task-2 run and knowledge base"
    )
    recommend_parser.add_argument(
        "--run",
        help="Task-2 run directory or 'latest'; defaults to the newest run under artifacts/run",
    )
    recommend_parser.add_argument(
        "--knowledge",
        help="Task-1 knowledge_base.json; defaults to artifacts/knowledge/official-v1-frozen/",
    )
    recommend_parser.add_argument(
        "--node", default="latest", help="latest, all, or a node ID such as N02"
    )
    recommend_parser.add_argument(
        "--output", help="new recommendation directory; defaults to artifacts/recommend/<dataset>-<timestamp>"
    )
    recommend_parser.add_argument(
        "--llm",
        action="store_true",
        help="let the optional language layer rewrite reason/check (falls back to templates)",
    )
    recommend_parser.add_argument(
        "--progress",
        help="local progress events JSONL; defaults to data/progress/<dataset>/events.jsonl",
    )
    recommend_parser.add_argument(
        "--previous",
        help="previous recommendation file/dir for the plan diff; defaults to the newest matching run",
    )
    recommend_parser.add_argument(
        "--feedback",
        help="feedback events JSONL; defaults to data/feedback/<dataset>/events.jsonl",
    )
    recommend_parser.add_argument(
        "--probe-weights",
        help="JSON file overriding probe weights (issue_relevance/coverage_gain/"
        "prerequisite_value/material_quality/redundancy_penalty)",
    )
    recommend_parser.set_defaults(func=_cmd_recommend)

    path_event_parser = subparsers.add_parser(
        "path-event", help="append one local progress event for a plan item"
    )
    path_event_parser.add_argument("--dataset", default="official-v1")
    path_event_parser.add_argument("--student", required=True)
    path_event_parser.add_argument("--node", required=True)
    path_event_parser.add_argument(
        "--plan", help="recommendation file/dir; defaults to the newest recommend run"
    )
    path_event_parser.add_argument("--seq", type=int, help="plan item seq")
    path_event_parser.add_argument("--plan-item", help="plan_item_id (alternative to --seq)")
    path_event_parser.add_argument(
        "--event", required=True, choices=["started", "completed"]
    )
    path_event_parser.add_argument(
        "--progress", help="event ledger path; defaults to data/progress/<dataset>/events.jsonl"
    )
    path_event_parser.add_argument("--note")
    path_event_parser.add_argument("--source", default="local_demo_user")
    path_event_parser.set_defaults(func=_cmd_path_event)

    attempt_parser = subparsers.add_parser(
        "feedback-attempt", help="append one supplemental graded attempt (derived evidence)"
    )
    attempt_parser.add_argument("--dataset", default="official-v1")
    attempt_parser.add_argument("--student", required=True)
    attempt_parser.add_argument("--node", required=True)
    attempt_parser.add_argument("--material", required=True)
    attempt_parser.add_argument("--score", type=float, required=True)
    attempt_parser.add_argument("--max-score", type=float)
    attempt_parser.add_argument("--rubric-json", help="JSON array of criterion/score/max_score")
    attempt_parser.add_argument("--submitted-at")
    attempt_parser.add_argument("--events", help="ledger path; defaults to data/feedback/<dataset>/events.jsonl")
    attempt_parser.add_argument("--source", default="local_demo_user")
    attempt_parser.add_argument("--note")
    attempt_parser.set_defaults(func=_cmd_feedback_attempt)

    adjust_parser = subparsers.add_parser(
        "feedback-adjust", help="append a teacher adjustment for one plan item"
    )
    adjust_parser.add_argument("--dataset", default="official-v1")
    adjust_parser.add_argument("--student", required=True)
    adjust_parser.add_argument("--node", required=True)
    adjust_parser.add_argument("--plan", help="recommendation file/dir; defaults to the newest run")
    adjust_parser.add_argument("--seq", type=int)
    adjust_parser.add_argument("--plan-item")
    adjust_parser.add_argument(
        "--action",
        required=True,
        choices=["lock", "unlock", "remove", "restore", "replace_materials", "set_time", "set_difficulty"],
    )
    adjust_parser.add_argument("--reason", required=True)
    adjust_parser.add_argument("--materials", help="comma-separated material ids")
    adjust_parser.add_argument("--minutes", type=int)
    adjust_parser.add_argument("--difficulty", type=int)
    adjust_parser.add_argument("--events")
    adjust_parser.add_argument("--source", default="local_demo_user")
    adjust_parser.set_defaults(func=_cmd_feedback_adjust)

    comment_parser = subparsers.add_parser(
        "feedback-comment", help="append a teacher comment (no effect on diagnosis)"
    )
    comment_parser.add_argument("--dataset", default="official-v1")
    comment_parser.add_argument("--student", required=True)
    comment_parser.add_argument("--node", required=True)
    comment_parser.add_argument("--plan")
    comment_parser.add_argument("--seq", type=int)
    comment_parser.add_argument("--plan-item")
    comment_parser.add_argument("--text", required=True)
    comment_parser.add_argument("--events")
    comment_parser.add_argument("--source", default="local_demo_user")
    comment_parser.set_defaults(func=_cmd_feedback_comment)

    student_parser = subparsers.add_parser(
        "feedback-student", help="append student feedback (no effect on diagnosis)"
    )
    student_parser.add_argument("--dataset", default="official-v1")
    student_parser.add_argument("--student", required=True)
    student_parser.add_argument("--node", required=True)
    student_parser.add_argument("--plan-item")
    student_parser.add_argument(
        "--kind", required=True, choices=["difficulty", "confusion", "request", "other"]
    )
    student_parser.add_argument("--rating", type=int, choices=[1, 2, 3, 4, 5])
    student_parser.add_argument("--text")
    student_parser.add_argument("--events")
    student_parser.add_argument("--source", default="local_demo_user")
    student_parser.set_defaults(func=_cmd_feedback_student)

    explain_parser = subparsers.add_parser(
        "explain", help="explain one saved issue with the optional language layer"
    )
    explain_parser.add_argument("--run", help="Task-2 run directory or 'latest'")
    explain_parser.add_argument("--node", help="node ID; defaults to the newest node")
    explain_parser.add_argument("--student", required=True, help="student ID such as S001")
    explain_parser.add_argument("--knowledge-id", required=True, help="knowledge ID such as K-07")
    explain_parser.add_argument(
        "--knowledge", help="Task-1 knowledge_base.json; defaults to the frozen copy"
    )
    explain_parser.add_argument(
        "--output", help="new directory; defaults to artifacts/explain/<dataset>-<timestamp>"
    )
    explain_parser.set_defaults(func=_cmd_explain)

    verify_recommend_parser = subparsers.add_parser(
        "verify-recommend", help="revalidate a saved Task-3 recommendation run"
    )
    verify_recommend_parser.add_argument(
        "--run",
        help="recommendation directory or 'latest'; defaults to the newest under artifacts/recommend",
    )
    verify_recommend_parser.set_defaults(func=_cmd_verify_recommend)

    review_scan_parser = subparsers.add_parser(
        "review-scan",
        help="scan canonical records for disputed scores and write a local review report",
    )
    review_scan_parser.add_argument("--dataset", default="official-v1")
    review_scan_parser.add_argument(
        "--output", help="new review directory; defaults to artifacts/review/<dataset>-<timestamp>"
    )
    review_scan_parser.set_defaults(func=_cmd_review_scan)

    review_decide_parser = subparsers.add_parser(
        "review-decide",
        help="append one human review decision to the local ledger (never changes scores)",
    )
    review_decide_parser.add_argument("--dataset", default="official-v1")
    review_decide_parser.add_argument("--record", required=True, help="record_id such as R-0685")
    review_decide_parser.add_argument(
        "--status",
        required=True,
        choices=["confirmed_issue", "dismissed", "needs_more_evidence"],
        help="confirmed_issue=确认评分有问题；dismissed=确认无误；needs_more_evidence=需补材料",
    )
    review_decide_parser.add_argument("--note", required=True, help="why this decision was made")
    review_decide_parser.add_argument(
        "--reviewer",
        default="local_demo_user",
        help="local demo role; not an authenticated teacher identity",
    )
    review_decide_parser.add_argument(
        "--source", default="local manual review", help="what the decision is based on"
    )
    review_decide_parser.add_argument(
        "--code",
        action="append",
        help="flag code this decision addresses (repeatable)",
    )
    review_decide_parser.set_defaults(func=_cmd_review_decide)

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"KnowFlow: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
