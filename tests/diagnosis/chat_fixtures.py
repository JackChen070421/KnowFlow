"""Shared builder for a validated synthetic dashboard run (chat tests).

``test_web`` and ``test_chat_teaching`` each carry their own copy of this setup;
new chat suites import this helper so a fourth copy does not appear.
"""

from __future__ import annotations

from pathlib import Path

from test_recommend import knowledge_base

from knowflow.diagnosis.pipeline import run_diagnosis
from knowflow.knowledge.pipeline import write_knowledge_base
from knowflow.recommend.pipeline import recommend_run


def build_chat_run(tmp_path: Path, bundle: dict, name: str = "chat-run") -> Path:
    run = tmp_path / name
    knowledge = knowledge_base(bundle)
    for objective in knowledge["objectives"]:
        objective["unit"] = "synthetic unit"
    write_knowledge_base(knowledge, run / "knowledge_base.json")
    run_diagnosis(bundle, run / "diagnosis", node_id="all")
    report = recommend_run(
        run=str(run / "diagnosis"),
        knowledge=str(run / "knowledge_base.json"),
        node="all",
        output=str(run / "recommendations"),
    )
    assert report["gate"] == "pass"
    return run
