"""Read and update the local LLM block of ``.env`` from the dashboard.

The file is Git-ignored and is the same one the CLI reads, so saving here is
equivalent to editing backend configuration.  The API never returns the key.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

from knowflow.config import get_settings
from knowflow.contracts import repo_root

PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "qwen": {
        "label": "通义千问（百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "custom": {"label": "自定义（OpenAI 兼容）", "base_url": "", "model": ""},
}

MANAGED_KEYS = (
    "KNOWFLOW_LLM_ENABLED",
    "KNOWFLOW_LLM_PROVIDER",
    "KNOWFLOW_LLM_BASE_URL",
    "KNOWFLOW_LLM_MODEL",
    "KNOWFLOW_LLM_API_KEY",
)
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-/]{0,99}$")
_HEADER = "# KnowFlow local settings (Git-ignored). Written by the web settings page."
_LOCK = threading.RLock()


def env_path() -> Path:
    """Return the repository ``.env`` that both the CLI and the dashboard read."""

    return repo_root() / ".env"


def _presets() -> list[dict[str, str]]:
    return [{"value": key, **value} for key, value in PROVIDERS.items()]


def read_llm_settings() -> dict:
    """Return the effective settings with the key reduced to a boolean."""

    settings = get_settings()
    return {
        "enabled": settings.llm_enabled,
        "ready": settings.llm_ready,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "api_key_set": bool(settings.llm_api_key.strip()),
        "providers": _presets(),
        "env_file": str(env_path()),
    }


def _validate(payload: dict, existing_key: str) -> tuple[dict[str, str], str]:
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")
    enabled = payload.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("enabled 必须是布尔值")
    provider = str(payload.get("provider") or "").strip()
    if provider not in PROVIDERS:
        raise ValueError("未知的模型厂商")
    preset = PROVIDERS[provider]
    model = str(payload.get("model") or "").strip() or preset["model"]
    base_url = str(payload.get("base_url") or "").strip() or preset["base_url"]
    if provider == "custom" and (not model or not base_url):
        raise ValueError("自定义厂商需要填写 Base URL 与模型")
    if not MODEL_RE.fullmatch(model):
        raise ValueError("模型名不合法")
    parsed = urlparse(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or any(character.isspace() for character in base_url)
    ):
        raise ValueError("Base URL 必须是 http(s) 地址")
    api_key = str(payload.get("api_key") or "").strip()
    if len(api_key) > 200 or any(character in api_key for character in "\r\n"):
        raise ValueError("API Key 不合法")
    if enabled and not (api_key or existing_key):
        raise ValueError("启用 LLM 需要填写 API Key")
    updates = {
        "KNOWFLOW_LLM_ENABLED": "true" if enabled else "false",
        "KNOWFLOW_LLM_PROVIDER": provider,
        "KNOWFLOW_LLM_BASE_URL": base_url,
        "KNOWFLOW_LLM_MODEL": model,
    }
    return updates, api_key


def _write_env(target: Path, updates: dict[str, str], api_key: str) -> None:
    values = dict(updates)
    if api_key:
        values["KNOWFLOW_LLM_API_KEY"] = api_key
    lines = (
        target.read_text(encoding="utf-8").splitlines()
        if target.is_file()
        else [_HEADER, ""]
    )
    seen: set[str] = set()
    merged: list[str] = []
    for line in lines:
        match = re.match(r"^\s*([A-Z0-9_]+)\s*=", line)
        key = match.group(1) if match else None
        if key in values:
            merged.append(f"{key}={values[key]}")
            seen.add(key or "")
        else:
            merged.append(line)
    for key, value in values.items():
        if key not in seen:
            merged.append(f"{key}={value}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text("\n".join(merged).rstrip("\n") + "\n", encoding="utf-8")
    os.replace(temporary, target)


def save_llm_settings(payload: dict, path: Path | None = None) -> dict:
    """Validate, persist and apply one settings change; never echo the key."""

    with _LOCK:
        existing_key = get_settings().llm_api_key.strip()
        updates, api_key = _validate(payload, existing_key)
        _write_env(Path(path) if path else env_path(), updates, api_key)
        for key, value in updates.items():
            os.environ[key] = value
        if api_key:
            os.environ["KNOWFLOW_LLM_API_KEY"] = api_key
        return read_llm_settings()
