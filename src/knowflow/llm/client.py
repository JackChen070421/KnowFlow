"""Minimal chat-completions client with a lazy SDK import.

Only the summary produced by :mod:`knowflow.llm.summary` is sent.  The client is
injectable so tests never touch the network and CI needs no key.
"""

from __future__ import annotations

from typing import Protocol

from knowflow.config import Settings


class ChatClient(Protocol):
    """Anything that can turn (system, user) into a text completion."""

    provider: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


class OpenAICompatClient:
    """OpenAI-compatible endpoint (DeepSeek by default).

    The SDK is imported lazily: core installs stay small and ``llm.enabled=false``
    never imports it.  A missing extra raises a readable error that the caller
    degrades to templates.
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float,
        timeout: float,
    ) -> None:
        self.provider = provider
        self.model = model
        self._base_url = base_url
        self._api_key = api_key
        self._temperature = temperature
        self._timeout = timeout
        self._client = None

    def _sdk(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - depends on install extras
                raise RuntimeError(
                    "LLM 依赖未安装：请执行 pip install -e '.[llm]' 或 uv sync --extra llm"
                ) from exc
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    def complete(self, system: str, user: str) -> str:
        response = self._sdk().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self._temperature,
            timeout=self._timeout,
        )
        return response.choices[0].message.content or ""


def build_client(settings: Settings) -> ChatClient | None:
    """Return a client only when a call may actually be attempted."""

    if not settings.llm_ready:
        return None
    return OpenAICompatClient(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
    )
