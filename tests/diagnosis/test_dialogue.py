"""多轮对话：历史不是事实来源（任务 D）。

Three sources must stay apart:

* **当前事实** — 本轮事实卡，唯一可用的事实依据；
* **用户补充** — 用户自己统计到的，可以带归属引用，但不是数据库更新；
* **历史模型回答** — 只提供语境与指代，数字不得进入白名单。

The old behaviour (history numbers joined the whitelist) let a wrong number from
turn 1 be restated as a verified fact in turn 3; these tests pin the new rule and
the three required regressions.
"""

from __future__ import annotations

import pytest
from chat_fixtures import build_chat_run
from test_llm import SequenceClient

from knowflow.llm.chat import answer_question, build_facts, rules_answer
from knowflow.web.data import load_dashboard, read_json


@pytest.fixture()
def chat_run(tmp_path, bundle):
    return build_chat_run(tmp_path, bundle, name="dialogue-run")


@pytest.fixture()
def snapshot(chat_run):
    return load_dashboard(chat_run)


@pytest.fixture()
def knowledge(chat_run):
    return read_json(chat_run / "knowledge_base.json")


def ask(snapshot, knowledge, message, client, history=None):
    return answer_question(
        snapshot=snapshot,
        message=message,
        context={"node_id": "N02"},
        client=client,
        history=history,
        knowledge=knowledge,
    )


class RecordingClient:
    """Accepts a multi-turn request and keeps what the model actually received."""

    provider = "fake"
    model = "fake-model"

    def __init__(self, reply: str = "好的。") -> None:
        self.reply = reply
        self.system = ""
        self.messages: list[dict] = []

    def complete_messages(self, system: str, messages: list[dict]) -> str:
        self.system = system
        self.messages = list(messages)
        return self.reply


class SingleTurnClient:
    """Only implements ``complete``: exercises the fallback prompt path."""

    provider = "fake"
    model = "fake-model"

    def __init__(self, reply: str = "好的。") -> None:
        self.reply = reply
        self.user = ""

    def complete(self, system: str, user: str) -> str:
        self.user = user
        return self.reply


# --- 测试 A：历史错误数字不能污染当前事实 ---------------------------------


def test_history_numbers_do_not_enter_the_whitelist(snapshot, knowledge):
    client = SequenceClient(["刚才那 37 人先补观测。"])
    result = ask(
        snapshot,
        knowledge,
        "再说说他们",
        client,
        history=[{"role": "assistant", "text": "这个班还有 37 人证据不足"}],
    )
    assert result["source"] == "rules"
    assert result["trace"]["guard"]["failure_kind"] == "number"
    assert "37" not in result["answer"]


def test_a_wrong_number_in_history_is_corrected_not_repeated(snapshot, knowledge):
    history = [
        {"role": "user", "text": "K-02 怎么样"},
        {"role": "assistant", "text": "K-02 有 17 人薄弱"},
    ]
    facts = build_facts(snapshot, "这 17 个人应该怎么安排？", {"node_id": "N02"}, knowledge, history=history)
    conflicts = facts["dialogue"]["conflicts"]
    assert conflicts and conflicts[0]["said"] == 17
    assert conflicts[0]["knowledge_id"] == "K-02"

    answer = rules_answer(facts)
    assert "对不上" in answer
    assert "17 人薄弱" not in answer

    # The model repeating the number as a fact is rejected…
    rejected = ask(
        snapshot, knowledge, "这 17 个人应该怎么安排？", SequenceClient(["这 17 人可以直接小练。"]),
        history=history,
    )
    assert rejected["source"] == "rules"
    assert rejected["trace"]["guard"]["failure_kind"] == "number"

    # …but quoting it *with attribution* is allowed, because that is the user's claim.
    accepted = ask(
        snapshot,
        knowledge,
        "这 17 个人应该怎么安排？",
        SequenceClient(["你说的 17 人和记录对不上：K-02 目前有 1 人证据不足、3 人没有作答记录。"]),
        history=history,
    )
    assert accepted["source"] == "llm"


# --- 测试 B：正确的历史指代仍然可用 ---------------------------------------


def test_a_correct_reference_uses_the_fact_row(snapshot, knowledge):
    history = [
        {"role": "user", "text": "K-02 怎么样"},
        {"role": "assistant", "text": "K-02 有 1 人证据不足"},
    ]
    facts = build_facts(snapshot, "这 1 个人应该怎么安排？", {"node_id": "N02"}, knowledge, history=history)
    assert facts["dialogue"]["referenced"]["knowledge_id"] == "K-02"
    assert not facts["dialogue"].get("conflicts")
    assert any(item["id"] == "K-02" for item in facts["focus"]["knowledge"])

    answer = rules_answer(facts)
    assert "一元一次方程" in answer
    # PR #33 重新划分了稀疏评分：K-02 这一行现在是 1 较好 / 1 较差 / 3 无作答记录 / 1 已掌握。
    # 断言的是"数字来自该行本身"，所以不沿用旧回答里的"1 人证据不足"。
    assert "1 人较好" in answer
    assert "3 人没有作答记录" in answer
    # Numbers come from the row, not from the old answer's wording.
    assert facts["lookup"] is None or facts["lookup"].get("value") is not None

    accepted = ask(
        snapshot,
        knowledge,
        "这 1 个人应该怎么安排？",
        SequenceClient(["K-02 目前 1 人证据不足，先补一次完整作答。"]),
        history=history,
    )
    assert accepted["source"] == "llm"


# --- 测试 C：用户补充信息是独立来源 ---------------------------------------


def test_user_supplement_is_its_own_source(snapshot, knowledge):
    history = [{"role": "user", "text": "我刚刚又统计到 17 名学生已经完成补测"}]
    facts = build_facts(snapshot, "现在情况如何？", {"node_id": "N02"}, knowledge, history=history)
    supplement = facts["dialogue"]["supplement"]
    assert supplement["numbers"] == [17.0]

    answer = rules_answer(facts)
    assert "还没有进入统计" in answer

    # Repeating the user's number without attribution would turn it into a fact.
    rejected = ask(
        snapshot, knowledge, "现在情况如何？", SequenceClient(["现在有 17 人完成补测。"]),
        history=history,
    )
    assert rejected["source"] == "rules"

    # With attribution it is the user's statement, not a database update.
    accepted = ask(
        snapshot, knowledge, "现在情况如何？", SequenceClient(["你补充的 17 名补测学生还没有进入统计。"]),
        history=history,
    )
    assert accepted["source"] == "llm"


# --- 指代不清时先问，不猜 -------------------------------------------------


def test_an_unresolved_reference_is_clarified(snapshot, knowledge, monkeypatch):
    monkeypatch.setattr("knowflow.llm.chat.build_client", lambda settings, **kwargs: None)
    facts = build_facts(snapshot, "这个知识点呢？", {"node_id": "N02"}, knowledge)
    assert facts["dialogue"]["clarify"] is True
    answer = rules_answer(facts)
    assert "哪个知识点" in answer

    result = ask(snapshot, knowledge, "这个知识点呢？", None)
    assert result["source"] == "rules"
    assert "哪个知识点" in result["answer"]


# --- 约束必须真正到达模型 -------------------------------------------------


def test_the_history_rule_reaches_the_real_client(snapshot, knowledge):
    client = RecordingClient()
    ask(
        snapshot,
        knowledge,
        "再说说他们",
        client,
        history=[{"role": "assistant", "text": "K-02 有 1 人证据不足"}],
    )
    assert "不是事实来源" in client.system
    assert "旧回答里的数字" in client.system
    assert len(client.messages) == 2  # the history turn + this question


def test_the_history_warning_also_reaches_the_single_turn_client(snapshot, knowledge):
    client = SingleTurnClient()
    ask(
        snapshot,
        knowledge,
        "再说说他们",
        client,
        history=[{"role": "assistant", "text": "K-02 有 1 人证据不足"}],
    )
    assert "对话上文" in client.user
    assert "不要当成新事实" in client.user


def test_the_history_rule_is_not_added_without_history(snapshot, knowledge):
    client = RecordingClient()
    ask(snapshot, knowledge, "这个班学情如何？", client)
    assert "不是事实来源" not in client.system
