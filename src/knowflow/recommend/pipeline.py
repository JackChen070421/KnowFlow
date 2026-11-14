"""Task-3 ``recommend`` / ``verify-recommend`` commands.

The input is a completed Task-2 run plus the frozen Task-1 knowledge base.  The
output is a set of per-student, per-node recommendation JSON files and a
validation report; no raw answer text is read or written.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from knowflow.contracts import repo_root
from knowflow.diagnosis.pipeline import latest_run_dir
from knowflow.recommend.catalog import build_catalog, load_knowledge_base
from knowflow.recommend.rules import POLICY_VERSION, recommend_profile
from knowflow.recommend.validation import SCHEMA_ID, validate_saved_recommendations

RUN_SCHEMA_VERSION = "1.1.0"


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def default_knowledge_path() -> Path:
    root = repo_root() / "artifacts" / "knowledge"
    preferred = root / "official-v1-frozen" / "knowledge_base.json"
    if preferred.is_file():
        return preferred
    candidates = sorted(root.glob("*/knowledge_base.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise ValueError(
            "knowledge base not found; run `knowflow knowledge --dataset official-v1` first"
        )
    return candidates[-1]


def _resolve_run(value: str | None) -> Path:
    if value in (None, "", "latest"):
        return latest_run_dir()
    path = Path(value)
    if not (path / "run_manifest.json").is_file():
        raise ValueError(f"not a completed Task-2 run: {path}")
    return path


def _protect_output(output: Path) -> Path:
    root = repo_root().resolve()
    target = output.resolve()
    if target.is_relative_to(root) and not target.is_relative_to(root / "artifacts"):
        raise ValueError("repository outputs must be under artifacts/ (Git-ignored)")
    if target.exists():
        raise ValueError(f"output already exists; choose a new directory: {target}")
    return target


def _nodes(bundle: dict) -> dict[str, dict]:
    return {node["node_id"]: node for node in bundle["nodes"]}


def _resolve_nodes(bundle: dict, node: str | None) -> list[str]:
    nodes = _nodes(bundle)
    if node in (None, "", "latest"):
        latest = max(nodes.values(), key=lambda item: (item["date"], item["node_id"]))
        return [latest["node_id"]]
    if node == "all":
        return sorted(nodes, key=lambda node_id: (nodes[node_id]["date"], node_id))
    if node not in nodes:
        raise ValueError(f"unknown node: {node}")
    return [node]


def _profiles(run: Path, node_id: str) -> list[tuple[Path, dict]]:
    directory = run / "nodes" / node_id / "students"
    paths = sorted(directory.glob("S*.json"))
    if not paths:
        raise ValueError(f"no student profiles under {directory}")
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]


def _index_entry(rec: dict, path: str, scope_known: bool) -> dict:
    return {
        "student_id": rec["student_id"],
        "node_id": rec["node_id"],
        "path": path,
        "scope_known": scope_known,
        "plan_items": len(rec["plan"]),
        "probe_needed": rec["probe_plan"]["needed"],
        "probe_items": rec["probe_plan"]["items"],
        "issue_ids": [item["issue_id"] for item in rec["plan"]],
    }


def _summary_text(manifest: dict, index: dict) -> list[str]:
    policy = manifest["policy"]
    counts = manifest["counts"]
    return [
        "# 任务3运行结果",
        "",
        f"数据集：{manifest['dataset_id']}；节点：{', '.join(manifest['nodes'])}。",
        f"生成{counts['students']}份个人学习建议，计划项{counts['plan_items']}条，"
        f"{counts['probe_needed_students']}名学生需要补充观测。",
        "",
        "## 规则与边界",
        "",
        f"- 规则版本：{policy['version']}；LLM：关闭（模板生成，可复算）。",
        "- 每条建议都绑定 issue_id；材料只来自任务1知识底座，测评题优先节点内材料。",
        "- 证据不足不推断“未掌握”：只给补充观测题，并在 probe_plan 中说明。",
        "- difficulty 与 est_minutes 为规则推算值：官方材料没有这两个字段，"
        "按题型/认知类型估算，不能当作官方难度或精确用时。",
        "- 表现较好的知识点不强行加练；未知参与范围的学生只提示先确认范围。",
        "",
        "## 产物",
        "",
        "```text",
        "nodes/<节点>/students/<学生>.json   个人建议",
        "index.json                          学生/计划索引",
        "knowledge_base.json                 本次使用的任务1知识底座",
        "inputs/                             画像与诊断输入快照（用于复核）",
        "validation_report.json              门禁结果",
        "run_manifest.json                   哈希与策略",
        "```",
        "",
        "## 复核",
        "",
        "```powershell",
        "python -m knowflow.cli verify-recommend --run artifacts/recommend/<目录>",
        "```",
        "",
        "## 学生索引",
        "",
    ] + [
        f"- {entry['student_id']} / {entry['node_id']}：计划 {entry['plan_items']} 条，"
        f"补充观测 {'是' if entry['probe_needed'] else '否'}"
        for entry in index["students"]
    ]


def recommend_run(
    run: str | None = None,
    knowledge: str | None = None,
    node: str | None = "latest",
    output: str | None = None,
    generated_at: str | None = None,
) -> dict:
    run_dir = _resolve_run(run)
    knowledge_path = Path(knowledge) if knowledge else default_knowledge_path()
    if not knowledge_path.is_file():
        raise ValueError(f"knowledge base not found: {knowledge_path}")
    knowledge_base = load_knowledge_base(knowledge_path)
    catalog = build_catalog(knowledge_base)

    run_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    bundle = json.loads((run_dir / "diagnosis_input.json").read_text(encoding="utf-8"))
    node_ids = _resolve_nodes(bundle, node)
    timestamp = generated_at or now_iso()
    target = (
        Path(output)
        if output
        else repo_root()
        / "artifacts"
        / "recommend"
        / f"{bundle['dataset_id']}-{datetime.now():%Y%m%d-%H%M%S-%f}"
    )
    target = _protect_output(target)
    target.mkdir(parents=True)
    shutil.copy2(knowledge_path, target / "knowledge_base.json")
    (target / "inputs").mkdir()
    shutil.copy2(run_dir / "diagnosis_input.json", target / "inputs" / "diagnosis_input.json")

    recs: list[tuple[Path, dict]] = []
    index_students = []
    for node_id in node_ids:
        node_available = set(_nodes(bundle)[node_id]["material_ids"])
        local_profiles = target / "inputs" / "nodes" / node_id / "students"
        local_profiles.mkdir(parents=True)
        for profile_path, profile in _profiles(run_dir, node_id):
            shutil.copy2(profile_path, local_profiles / profile_path.name)
            profile_sha = hashlib.sha256(profile_path.read_bytes()).hexdigest()
            rec = recommend_profile(
                profile,
                catalog,
                node_available,
                bundle["records"],
                timestamp,
                profile_sha,
            )
            relative = Path("nodes") / node_id / "students" / profile_path.name
            write_json(target / relative, rec)
            recs.append((target / relative, rec))
            index_students.append(
                _index_entry(rec, relative.as_posix(), profile["coverage"]["scope_known"])
            )

    index = {
        "schema_version": RUN_SCHEMA_VERSION,
        "dataset_id": bundle["dataset_id"],
        "nodes": node_ids,
        "generated_at": timestamp,
        "students": index_students,
        "counts": {
            "students": len(index_students),
            "plan_items": sum(entry["plan_items"] for entry in index_students),
            "probe_needed_students": sum(entry["probe_needed"] for entry in index_students),
            "scope_unknown_students": sum(
                1 for entry in index_students if not entry["scope_known"]
            ),
        },
    }
    write_json(target / "index.json", index)

    targets = [
        {
            "path": path.relative_to(target).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "schema_id": SCHEMA_ID,
        }
        for path, _ in recs
    ]
    counts = index["counts"]
    manifest = {
        "schema_version": RUN_SCHEMA_VERSION,
        "dataset_id": bundle["dataset_id"],
        "run_id": target.name,
        "generated_at": timestamp,
        "scope": "task3_only",
        "nodes": node_ids,
        "source_run": {
            "path": str(run_dir.resolve()),
            "generated_at": run_manifest.get("generated_at"),
            "nodes": run_manifest.get("nodes", []),
        },
        "source_knowledge": {
            "path": "knowledge_base.json",
            "original_path": str(knowledge_path.resolve()),
            "sha256": hashlib.sha256(knowledge_path.read_bytes()).hexdigest(),
        },
        "policy": {
            "name": "rule-template",
            "version": POLICY_VERSION,
            "llm_enabled": False,
            "difficulty": "heuristic",
            "time": "heuristic",
            "material_scope": "catalog_prefer_node",
            "max_plan_items": 3,
        },
        "targets": targets,
        "auxiliary_files": {
            "index.json": hashlib.sha256((target / "index.json").read_bytes()).hexdigest()
        },
        "counts": counts,
    }
    write_json(target / "run_manifest.json", manifest)
    (target / "运行说明.md").write_text(
        "\n".join(_summary_text(manifest, index)) + "\n", encoding="utf-8"
    )

    report = validate_saved_recommendations(target)
    write_json(target / "validation_report.json", report)
    return {
        "run": str(target),
        "nodes": node_ids,
        "students": counts["students"],
        "plan_items": counts["plan_items"],
        "probe_needed_students": counts["probe_needed_students"],
        "gate": report["gate"],
        "validation_report": str(target / "validation_report.json"),
    }


def latest_recommend_dir(base: Path | None = None) -> Path:
    root = Path(base) if base is not None else repo_root() / "artifacts" / "recommend"
    if not root.is_dir():
        raise ValueError(f"no recommendation runs yet: {root} does not exist")
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "run_manifest.json").is_file()
    ]
    if not candidates:
        raise ValueError(f"no completed recommendation runs under {root}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def verify_recommend(run: str | None = None) -> dict:
    run_dir = latest_recommend_dir() if run in (None, "", "latest") else Path(run)
    return validate_saved_recommendations(run_dir)
