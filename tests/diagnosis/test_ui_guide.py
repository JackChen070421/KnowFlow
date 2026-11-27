"""The WebUI map must describe the interface that actually ships.

``llm/ui_guide.py`` is the only place the companion learns page/tab/button names.
These tests read the shipped front end and fail when a label is added, renamed or
removed without updating the guide — that is the sync mechanism, not a snapshot
of today's wording.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from knowflow.llm import audit, ui_guide

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src" / "knowflow" / "web" / "static"


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def _labels(pattern: str, text: str) -> tuple[str, ...]:
    return tuple(match.group(1) for match in re.finditer(pattern, text))


APP = _read("app.js")
LEARNING = _read("learning.js")
TRAINING = _read("training.js")
EXPLORE = _read("explore-labs.mjs")
MORE = _read("explore-more.mjs")


def _nav() -> tuple[tuple[str, ...], tuple[str, ...]]:
    block = _slice(APP, "function navItems()", "function shell()")
    teacher, student = block.split("] : [", 1)
    pattern = r"\['[a-z]+', '([^']+)'"
    return _labels(pattern, teacher), _labels(pattern, student)


def _reports() -> tuple[str, ...]:
    block = _slice(APP, "const REPORTS = [", "];")
    return _labels(r"\{id:'[a-z]+', label:'([^']+)'", block)


def _profile_tabs() -> tuple[str, ...]:
    block = _slice(APP, "const profileTabs = [", "const sections = {")
    return _labels(r"\['(?:analysis|knowledge|records|history|plans|feedback)',\s*'([^']+)'", block)


def _settings_tabs() -> tuple[str, ...]:
    block = _slice(APP, "const SETTINGS_TABS = [", "];")
    return _labels(r"\['[a-z]+', '([^']+)'", block)


def _course_tabs() -> tuple[str, ...]:
    block = _slice(APP, "const sections=[", "];")
    return _labels(r"\['(?:map|list|sources)','([^']+)'", block)


def _learning_tabs() -> tuple[str, ...]:
    return _labels(r"\['(?:cards|mistakes|favorites)',\s*'([^']+)'", LEARNING)


def _explore_tabs() -> tuple[str, ...]:
    block = _slice(APP, "const EXPLORE_TABS = [", "];")
    return _labels(r"\['(?:analysis|model|task|quiz)',\s*'([^']+)'", block)


def _training_tabs() -> tuple[str, ...]:
    match = re.search(r"labels=\[([^\]]+)\]", TRAINING)
    assert match is not None
    return tuple(re.findall(r"'([^']+)'", match.group(1)))


def _themes() -> tuple[str, ...]:
    block = _slice(APP, "const THEMES = [", "];")
    return _labels(r"\{id: '[a-z]+', label: '([^']+)'", block)


def _explore_labs() -> tuple[str, ...]:
    pattern = r"id: '(?:mirror|budget|rental|window)',\s*index:.*?field:.*?title: '([^']+)'"
    return _labels(pattern, EXPLORE.replace("\n", " "))


def _explore_more() -> tuple[str, ...]:
    return _labels(r"\{ id: '(?:tasks|links|reads)', title: '([^']+)'", MORE)


def test_teacher_nav_matches_the_shipped_shell():
    teacher, _ = _nav()
    assert ui_guide.TEACHER_NAV == teacher


def test_student_nav_matches_the_shipped_shell():
    _, student = _nav()
    assert ui_guide.STUDENT_NAV == student


def test_class_report_tabs_match():
    assert ui_guide.TEACHER_REPORTS == _reports()


def test_profile_tabs_match():
    shipped = _profile_tabs()
    assert ui_guide.PROFILE_TABS == shipped[:-1]
    assert ui_guide.TEACHER_PROFILE_TABS == shipped


def test_settings_tabs_match():
    shipped = _settings_tabs()
    assert ui_guide.SETTINGS_TABS == shipped
    assert ui_guide.STUDENT_SETTINGS_TABS == (shipped[0], shipped[2])


def test_course_learning_explore_and_training_tabs_match():
    assert ui_guide.COURSE_TABS == _course_tabs()
    assert ui_guide.LEARNING_TABS == _learning_tabs()
    assert ui_guide.EXPLORE_TABS == _explore_tabs()
    assert ui_guide.TRAINING_TABS == _training_tabs()
    assert ui_guide.THEMES == _themes()
    assert ui_guide.EXPLORE_LABS == _explore_labs()
    assert ui_guide.EXPLORE_MORE == _explore_more()


def test_teacher_guide_names_every_teacher_entry():
    text = ui_guide.webui_guide("teacher")
    labels = (
        *ui_guide.TEACHER_NAV,
        *ui_guide.TEACHER_REPORTS,
        *ui_guide.TEACHER_PROFILE_TABS,
        *ui_guide.SETTINGS_TABS,
        *ui_guide.COURSE_TABS,
        *ui_guide.TRAINING_TABS,
        *ui_guide.THEMES,
    )
    missing = [label for label in labels if label not in text]
    assert not missing, missing


def test_student_guide_names_every_student_entry_and_hides_teacher_tools():
    text = ui_guide.webui_guide("student")
    labels = (
        *ui_guide.STUDENT_NAV,
        *ui_guide.PROFILE_TABS,
        *ui_guide.STUDENT_SETTINGS_TABS,
        *ui_guide.COURSE_TABS,
        *ui_guide.LEARNING_TABS,
        *ui_guide.EXPLORE_TABS,
        *ui_guide.EXPLORE_LABS,
        *ui_guide.EXPLORE_MORE,
    )
    missing = [label for label in labels if label not in text]
    assert not missing, missing
    assert "变式训练" not in text
    assert "教学与 AI" not in text
    assert "数据分析" not in text


def test_current_page_hint_is_audience_checked():
    assert "对方此刻在「学生明细」页" in ui_guide.webui_guide("teacher", "students")
    assert "对方此刻在「学习空间」页" in ui_guide.webui_guide("student", "plan")
    # A teacher-only page is not a student's page: ignore the hint instead of
    # telling a student they are somewhere the interface does not have.
    assert "对方此刻在" not in ui_guide.webui_guide("student", "students")
    assert "对方此刻在" not in ui_guide.webui_guide("teacher", "plan")


def test_unknown_audience_gets_the_student_map():
    text = ui_guide.webui_guide("admin", "students")
    assert "学习空间" in text
    assert "变式训练" not in text
    assert "对方此刻在" not in text


def test_guide_is_versioned_for_sync():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", ui_guide.UI_GUIDE_VERSION)


@pytest.mark.parametrize("audience", ["teacher", "student"])
def test_guide_numbers_read_as_teaching_not_learner_claims(audience):
    """A label like “两个人的共同空闲” must not fail the number lock.

    Every number that survives in the guide has to be understood by the chat
    audit as a teaching/advisory quantity (or be absent); otherwise quoting the
    interface would fall back to the rule answer.
    """

    report = audit.number_audit(
        ui_guide.webui_guide(audience), set(), set(), names=ui_guide.NUMERIC_LABELS
    )
    assert report["unverified"] == [], report["unverified"]


def test_numeric_labels_are_declared_for_the_audit():
    labels = {
        *ui_guide.TEACHER_NAV,
        *ui_guide.STUDENT_NAV,
        *ui_guide.TEACHER_REPORTS,
        *ui_guide.TEACHER_PROFILE_TABS,
        *ui_guide.SETTINGS_TABS,
        *ui_guide.COURSE_TABS,
        *ui_guide.LEARNING_TABS,
        *ui_guide.EXPLORE_TABS,
        *ui_guide.EXPLORE_LABS,
        *ui_guide.EXPLORE_MORE,
        *ui_guide.TRAINING_TABS,
        *ui_guide.THEMES,
    }
    # Only labels the audit would otherwise read as a learner count need the
    # exemption; “活动预算的两个方案” already classifies 两 as a teaching amount.
    numeric = {
        label
        for label in labels
        if any(not item["verified"] for item in audit.audit_numbers(label, set(), set()))
    }
    assert numeric == set(ui_guide.NUMERIC_LABELS)


def test_a_numeric_ui_name_is_not_treated_as_a_learner_claim():
    name = ui_guide.NUMERIC_LABELS[0]
    assert (
        audit.validate_answer(
            f"在「跨域探索」的「{name}」里。", set(), set(), names=ui_guide.NUMERIC_LABELS
        )
        == []
    )
    # The exemption is per occurrence, not a licence for a real count.
    assert audit.validate_answer("只有 2 人掌握。", set(), set(), names=ui_guide.NUMERIC_LABELS)
