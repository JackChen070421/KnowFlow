"""Settings store: preserve .env, mask the key, reject unsafe input."""

from __future__ import annotations

import json

import pytest

from knowflow.llm.client import LLMError
from knowflow.llm.settings_store import (
    MANAGED_KEYS,
    read_llm_settings,
    save_llm_settings,
)
from knowflow.llm.settings_store import (
    test_llm_connection as probe_llm_connection,
)


def baseline(monkeypatch) -> None:
    """Pin every managed key so a local .env cannot leak into the test."""

    for key in MANAGED_KEYS:
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("KNOWFLOW_LLM_ENABLED", "false")


def test_save_preserves_other_lines_and_masks_the_key(tmp_path, monkeypatch):
    baseline(monkeypatch)
    target = tmp_path / ".env"
    target.write_text(
        "# keep this comment\nOTHER_SETTING=1\nKNOWFLOW_LLM_PROVIDER=deepseek\n",
        encoding="utf-8",
    )
    saved = save_llm_settings(
        {
            "enabled": True,
            "provider": "qwen",
            "model": "",
            "base_url": "",
            "api_key": "sk-test-123",
        },
        path=target,
    )
    text = target.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert "OTHER_SETTING=1" in text
    assert "KNOWFLOW_LLM_ENABLED=true" in text
    assert "KNOWFLOW_LLM_PROVIDER=qwen" in text
    assert "KNOWFLOW_LLM_MODEL=qwen-plus" in text
    assert text.count("KNOWFLOW_LLM_PROVIDER=") == 1
    assert "KNOWFLOW_LLM_API_KEY=sk-test-123" in text

    assert saved["enabled"] is True
    assert saved["ready"] is True
    assert saved["provider"] == "qwen"
    assert saved["api_key_set"] is True
    assert "sk-test-123" not in json.dumps(saved, ensure_ascii=False)


def test_blank_key_keeps_the_previous_key(tmp_path, monkeypatch):
    baseline(monkeypatch)
    target = tmp_path / ".env"
    save_llm_settings(
        {"enabled": True, "provider": "deepseek", "api_key": "sk-keep-me"},
        path=target,
    )
    save_llm_settings(
        {"enabled": True, "provider": "deepseek", "api_key": "", "model": "deepseek-reasoner"},
        path=target,
    )
    text = target.read_text(encoding="utf-8")
    assert "KNOWFLOW_LLM_API_KEY=sk-keep-me" in text
    assert "KNOWFLOW_LLM_MODEL=deepseek-reasoner" in text


def test_enabling_without_any_key_is_rejected(tmp_path, monkeypatch):
    baseline(monkeypatch)
    with pytest.raises(ValueError, match="API Key"):
        save_llm_settings({"enabled": True, "provider": "deepseek"}, path=tmp_path / ".env")
    assert not (tmp_path / ".env").exists()


def test_custom_provider_requires_url_and_model(tmp_path, monkeypatch):
    baseline(monkeypatch)
    with pytest.raises(ValueError, match="自定义"):
        save_llm_settings(
            {"enabled": False, "provider": "custom", "model": "", "base_url": ""},
            path=tmp_path / ".env",
        )
    with pytest.raises(ValueError, match="Base URL"):
        save_llm_settings(
            {
                "enabled": False,
                "provider": "custom",
                "model": "local-model",
                "base_url": "ftp://example.com",
            },
            path=tmp_path / ".env",
        )


def test_unknown_provider_and_bad_key_are_rejected(tmp_path, monkeypatch):
    baseline(monkeypatch)
    with pytest.raises(ValueError, match="厂商"):
        save_llm_settings({"enabled": False, "provider": "unknown"}, path=tmp_path / ".env")
    with pytest.raises(ValueError, match="API Key"):
        save_llm_settings(
            {"enabled": False, "provider": "deepseek", "api_key": "a\nb"},
            path=tmp_path / ".env",
        )


def test_settings_are_readable_without_the_key(monkeypatch):
    baseline(monkeypatch)
    monkeypatch.setenv("KNOWFLOW_LLM_PROVIDER", "openai")
    monkeypatch.setenv("KNOWFLOW_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("KNOWFLOW_LLM_API_KEY", "sk-hidden")
    state = read_llm_settings()
    assert state["api_key_set"] is True
    assert "sk-hidden" not in json.dumps(state, ensure_ascii=False)
    assert {item["value"] for item in state["providers"]} >= {"deepseek", "openai", "qwen", "custom"}


def test_probe_without_a_key_is_a_config_error(monkeypatch):
    baseline(monkeypatch)
    result = probe_llm_connection({})
    assert result["ok"] is False
    assert result["kind"] == "config"
    assert "API Key" in result["error"]


def test_probe_reports_the_classified_failure(monkeypatch):
    baseline(monkeypatch)
    monkeypatch.setenv("KNOWFLOW_LLM_API_KEY", "sk-probe-secret")

    class Failing:
        def __init__(self, **kwargs: object) -> None:
            pass

        def complete(self, system: str, user: str) -> str:
            raise LLMError("auth", "HTTP 401：Authentication Fails")

    monkeypatch.setattr("knowflow.llm.settings_store.OpenAICompatClient", Failing)
    result = probe_llm_connection({})
    assert result["ok"] is False
    assert result["kind"] == "auth"
    assert "401" in result["error"]
    assert "sk-probe-secret" not in json.dumps(result, ensure_ascii=False)


def test_probe_reports_latency_on_success(monkeypatch):
    baseline(monkeypatch)
    monkeypatch.setenv("KNOWFLOW_LLM_API_KEY", "sk-probe-secret")

    class Working:
        def __init__(self, **kwargs: object) -> None:
            pass

        def complete(self, system: str, user: str) -> str:
            return "正常"

    monkeypatch.setattr("knowflow.llm.settings_store.OpenAICompatClient", Working)
    result = probe_llm_connection({})
    assert result["ok"] is True
    assert result["reply"] == "正常"
    assert isinstance(result["elapsed_ms"], int)


