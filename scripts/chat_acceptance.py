"""Run the six acceptance questions against the local validated snapshot.

This is a *local* check, not part of CI: the snapshot is built from the official
data, which never enters the repository.  It reuses exactly the code path the
dashboard uses (``web.data.load_dashboard`` → ``llm.chat.answer_question``), so a
pass here means the chat behaved the same way the teacher would see it.

Usage (from the repo root, with the web snapshot already built):

    python scripts/chat_acceptance.py                 # deterministic fallback
    python scripts/chat_acceptance.py --path live     # configured model
    python scripts/chat_acceptance.py --student S002  # student wording

``--path rules`` forces the rule fallback (no model call, no API cost) and
``--path live`` uses whatever model the local ``.env`` configures; when the model
is unreachable the output says which failure was classified.

Checks are deliberately coarse: they assert the *shape* the task asked for (a
count question stays a count, evidence gaps are not called "not mastered", no
internal material IDs in a class answer), not exact wording — wording is the
model's job and must be free to change.

Owner: R3.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from knowflow.contracts import repo_root
from knowflow.llm import chat
from knowflow.web.data import load_dashboard, read_json

CASES = (
    ("A 整体学情", "这个班学情如何？"),
    ("B 知识点", "这个班哪些知识点最薄弱？"),
    ("C 教学建议", "下一节课应该怎么安排？"),
    ("D 学生分层", "这个班需要分层教学吗？"),
    ("E 简单查询", "全班有多少人？"),
    ("F 不确定性", "K-06 是不是全班都没掌握？"),
)


def _snapshot_path(root: Path) -> Path:
    cache = root / "artifacts/web/latest.json"
    if not cache.is_file():
        raise SystemExit(
            "没有找到 artifacts/web/latest.json；请先启动一次 dashboard 或运行 "
            "`python -m knowflow.web` 生成本机快照。"
        )
    return root / read_json(cache)["run"]


def _run(question: str, snapshot: dict, knowledge: dict, path: str) -> dict:
    client = None
    patched = False
    if path == "rules":
        original = chat.build_client
        chat.build_client = lambda settings, **kwargs: None  # noqa: ARG005 - mirrors signature
        patched = True
    try:
        return chat.answer_question(
            snapshot=snapshot,
            message=question,
            context={"node_id": "N02"},
            client=client,
            knowledge=knowledge,
        )
    finally:
        if patched:
            chat.build_client = original


def _checks(case: str, result: dict, snapshot: dict) -> list[str]:
    """Coarse shape checks; an empty list means "looks like the brief asked"."""

    answer = result["answer"]
    failures: list[str] = []
    if not answer.strip():
        failures.append("空回答")
    if "http://" in answer or "https://" in answer or "```" in answer:
        failures.append("出现了 URL 或代码块")
    if case.startswith("E"):
        classes = snapshot["classes"]["N02"]
        count = (classes.get("ALL") or classes.get("G1"))["student_count"]
        # "全班40人" and "全班 40 人" are the same answer; spacing is not the point.
        if f"{count}人" not in answer.replace(" ", ""):
            failures.append(f"没有直接给出人数 {count}")
        if len(answer) > 40:
            failures.append("数据查询附带了长篇分析")
    else:
        # Only the *section header* form is a template residue; "这个知识点上，有 6 人…"
        # is ordinary Chinese.
        if "建议教学动作" in answer or re.search(r"(?m)^\s*知识点上[，,]", answer):
            failures.append("仍然使用旧报告的固定段落")
    if case.startswith(("A", "B", "C", "D")):
        if "M-" in answer:
            failures.append("在班级分析里直接抛出了题目编号")
    if case.startswith("F"):
        if "不是" not in answer[:12]:
            failures.append("没有正面回答“是不是”")
        gap_words = ("证据不足", "缺证据", "证据不够", "没测到", "待观察")
        gap_fences = ("不等于", "不能算", "不是", "不能判", "并非")
        if not any(word in answer for word in gap_words):
            failures.append("没有说明证据不够")
        if not any(word in answer for word in gap_fences):
            failures.append("没有把证据不够与没掌握分开")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="六条验收问题的本机检查")
    parser.add_argument("--path", default="rules", choices=["rules", "live"])
    parser.add_argument("--student", default=None, help="以某个学生视角提问（可选）")
    parser.add_argument("--out", default=None, help="把结果写到 JSON（默认 artifacts/web/）")
    args = parser.parse_args(argv)

    root = repo_root()
    run = _snapshot_path(root)
    snapshot = load_dashboard(run)
    snapshot["meta"]["viewer"] = {
        "username": "local",
        "role": "student" if args.student else "teacher",
        "student_id": args.student,
    }
    knowledge = read_json(run / "knowledge_base.json")

    results = []
    failed = 0
    for case, question in CASES:
        result = _run(question, snapshot, knowledge, args.path)
        problems = _checks(case, result, snapshot)
        failed += len(problems) > 0
        guard = result["trace"]["guard"]
        results.append(
            {
                "case": case,
                "question": question,
                "source": result["source"],
                "intent": guard.get("intent"),
                "failure_kind": guard.get("failure_kind"),
                "problems": guard.get("problems"),
                "answer": result["answer"],
                "checks": problems,
            }
        )
        print(f"===== {case} | {question}")
        print(f"[source={result['source']} intent={guard.get('intent')} "
              f"failure={guard.get('failure_kind') or '-'}]")
        print(result["answer"])
        if result.get("note"):
            print(f"[note] {result['note']}")
        print("[检查] " + ("通过" if not problems else "；".join(problems)))
        print()

    out = (
        Path(args.out)
        if args.out
        else root / f"artifacts/web/chat-acceptance-{args.path}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"path": args.path, "student": args.student, "cases": results},
                   ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"结果已写入 {out}")
    print(f"未通过 {failed}/{len(CASES)} 条")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
