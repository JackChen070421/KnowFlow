"""Single-student, single-issue explanation: the smallest real LLM path.

This is the service the future chat UI will call: it reads one saved profile,
builds the summary whitelist, asks the model once and writes both the input and
the guarded output next to each other.  Numbers still come from the profile.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from knowflow.config import get_settings
from knowflow.contracts import repo_root
from knowflow.diagnosis.pipeline import latest_run_dir
from knowflow.recommend.catalog import build_catalog, load_knowledge_base
from knowflow.recommend.pipeline import default_knowledge_path
from knowflow.recommend.rules import MIN_EVIDENCE
from knowflow.recommend.validation import allowed_numbers

from .client import ChatClient, build_client
from .service import ReasonWriter
from .summary import build_issue_summary, summary_errors


def _resolve_run(value: str | None) -> Path:
    if value in (None, "", "latest"):
        return latest_run_dir()
    return Path(value)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def explain_student(
    *,
    student: str,
    knowledge_id: str,
    node: str | None = None,
    run: str | None = None,
    knowledge: str | None = None,
    output: str | None = None,
    client: ChatClient | None = None,
) -> dict:
    """Explain one issue for one student; never writes outside ``artifacts/``."""

    settings = get_settings()
    run_dir = _resolve_run(run)
    bundle = json.loads((run_dir / "diagnosis_input.json").read_text(encoding="utf-8"))
    nodes = bundle["nodes"]
    node_id = node or max(nodes, key=lambda item: (item["date"], item["node_id"]))["node_id"]
    if node_id not in {item["node_id"] for item in nodes}:
        raise ValueError(f"unknown node: {node_id}")
    profile_path = run_dir / "nodes" / node_id / "students" / f"{student}.json"
    if not profile_path.is_file():
        raise ValueError(f"student profile not found: {profile_path}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    issue = next(
        (item for item in profile.get("issues", []) if item["knowledge_id"] == knowledge_id),
        None,
    )
    if issue is None:
        raise ValueError(f"{student} 在 {node_id} 上没有 {knowledge_id} 的问题记录")
    state = next(
        (item for item in profile["knowledge_states"] if item["knowledge_id"] == knowledge_id),
        {},
    )

    knowledge_path = Path(knowledge) if knowledge else default_knowledge_path()
    catalog = build_catalog(load_knowledge_base(knowledge_path))
    candidate_ids = set((issue.get("evidence") or {}).get("material_ids") or [])
    candidate_ids |= set(catalog["by_knowledge"].get(knowledge_id, []))
    candidate_ids |= set(catalog["explain_by_knowledge"].get(knowledge_id, []))
    titles = {
        material_id: catalog["materials"][material_id]["title"]
        for material_id in candidate_ids
        if material_id in catalog["materials"]
    }
    summary = build_issue_summary(
        profile=profile,
        issue=issue,
        dataset_id=profile["source_dataset"],
        allowed_numbers=allowed_numbers(issue, state),
        allowed_ids={
            student,
            node_id,
            issue["issue_id"],
            issue["knowledge_id"],
            issue["objective_id"],
            *candidate_ids,
        },
        material_titles=titles,
    )
    problems = summary_errors(summary)
    if problems:
        raise ValueError("llm_summary 校验失败：" + "; ".join(problems[:3]))

    llm = client if client is not None else build_client(settings)
    if llm is None:
        raise ValueError(
            "LLM 未启用或缺少 API Key：请在 .env 设置 KNOWFLOW_LLM_ENABLED=true 与 "
            "KNOWFLOW_LLM_API_KEY。规则版建议请运行 `knowflow recommend`。"
        )

    first_material = next(
        (material_id for material_id in sorted(candidate_ids) if material_id.startswith("M-")),
        "对应材料",
    )
    fallback_reason = (
        f"{issue['issue_id']} 显示 {knowledge_id} 的有效评分不足时先补观测；"
        f"从 {first_material} 开始核对。"
    )
    fallback_check = f"完成 {first_material} 后按评分点自检；有效评分达到 {MIN_EVIDENCE} 次后复核。"
    reason, check, meta = ReasonWriter(llm).write(summary, fallback_reason, fallback_check)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = (
        Path(output)
        if output
        else repo_root() / "artifacts" / "explain" / f"{profile['source_dataset']}-{stamp}"
    ).resolve()
    root = repo_root().resolve()
    if target.is_relative_to(root) and not target.is_relative_to(root / "artifacts"):
        raise ValueError("repository outputs must be under artifacts/ (Git-ignored)")

    _write_json(target / "llm_summary.json", summary)
    _write_json(
        target / "explain.json",
        {
            "student_id": student,
            "node_id": node_id,
            "issue_id": issue["issue_id"],
            "knowledge_id": knowledge_id,
            "source": meta.source,
            "attempts": meta.attempts,
            "reason": reason,
            "check": check,
            "model": llm.model,
            "provider": llm.provider,
            "errors": list(meta.errors),
        },
    )
    return {
        "output": str(target),
        "student_id": student,
        "node_id": node_id,
        "issue_id": issue["issue_id"],
        "source": meta.source,
        "attempts": meta.attempts,
    }
