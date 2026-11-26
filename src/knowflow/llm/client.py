"""Chat-completions client on the standard library.

No SDK on purpose.  A competition laptop may have no network access to PyPI, and
a missing ``openai`` package used to surface as "the model is unreachable" — the
single most confusing failure in the dashboard.  Standard library only means the
dialog works on any machine that can already run the app.

Every failure is classified (:class:`LLMError`) so the caller can tell auth from
timeout from a bad base URL, and retry only what is worth retrying.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Protocol

from knowflow.config import Settings

LOGGER = logging.getLogger(__name__)

MAX_DETAIL = 240
_SECRET = re.compile(r"sk-[A-Za-z0-9._\-]{4,}")
_PROXY_ENV = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")


def redact(text: str) -> str:
    """Strip key-shaped tokens before an error reaches a log, note or artifact."""

    return _SECRET.sub("sk-***", text or "")


class ChatClient(Protocol):
    """Anything that can turn (system, user) into a text completion."""

    provider: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


class LLMError(RuntimeError):
    """One classified model-call failure.

    ``kind`` is stable and machine readable, so the UI decides the wording and
    the retry policy instead of collapsing every cause into "调用不通".
    """

    RETRYABLE = frozenset({"network", "timeout", "server", "rate_limit"})

    def __init__(self, kind: str, detail: str, *, status: int | None = None) -> None:
        self.kind = kind
        self.status = status
        self.detail = redact(detail).strip()[:MAX_DETAIL]
        super().__init__(f"{kind}: {self.detail}")

    @property
    def retryable(self) -> bool:
        return self.kind in self.RETRYABLE


def _classify_http(status: int, body: str) -> LLMError:
    detail = f"HTTP {status}：{body.strip()[:MAX_DETAIL]}" if body.strip() else f"HTTP {status}"
    if status in (401, 403):
        return LLMError("auth", detail, status=status)
    if status == 402:
        return LLMError("billing", detail, status=status)
    if status == 404:
        return LLMError("model", detail, status=status)
    if status == 429:
        return LLMError("rate_limit", detail, status=status)
    if status >= 500:
        return LLMError("server", detail, status=status)
    return LLMError("request", detail, status=status)


@lru_cache(maxsize=1)
def _opener() -> urllib.request.OpenerDirector:
    """Honour proxy environment variables, ignore a stale Windows registry proxy.

    ``httpx`` (used by the SDK this replaces) only reads the environment, so the
    behaviour stays the same instead of silently picking up a machine-wide proxy.
    """

    if any(os.environ.get(name) for name in _PROXY_ENV):
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OpenAICompatClient:
    """OpenAI-compatible chat-completions endpoint (DeepSeek by default)."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float,
        timeout: float,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> None:
        self.provider = provider
        self.model = model
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key
        self._temperature = temperature
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._json_mode = json_mode

    @property
    def endpoint(self) -> str:
        return f"{self._base_url}/chat/completions"

    def complete(self, system: str, user: str) -> str:
        return self.complete_messages(system, [{"role": "user", "content": user}])

    def complete_messages(self, system: str, messages: list[dict]) -> str:
        """One multi-turn request: system + the validated turns + the question."""

        turns = [
            {"role": item["role"], "content": item["content"]}
            for item in messages
            if isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ]
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *turns],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        started = time.monotonic()
        try:
            with _opener().open(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:  # a body we cannot read is not worth another failure
                body = ""
            raise _classify_http(exc.code, body) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise LLMError("timeout", f"连接 {self._base_url} 超时（{self._timeout:g}s）") from None
            raise LLMError("network", f"{type(reason).__name__}: {reason}") from None
        except TimeoutError:
            raise LLMError("timeout", f"读取 {self._base_url} 超时（{self._timeout:g}s）") from None
        except ValueError as exc:  # e.g. "unknown url type" from a bad Base URL
            raise LLMError("request", f"Base URL 不合法：{exc}") from None
        except OSError as exc:
            raise LLMError("network", f"{type(exc).__name__}: {exc}") from None

        try:
            data = json.loads(raw)
        except ValueError:
            raise LLMError("bad_response", f"响应不是 JSON：{raw[:120]}") from None
        if not isinstance(data, dict):
            raise LLMError("bad_response", "响应不是 JSON 对象")
        if data.get("error") and not data.get("choices"):
            # Some compatible gateways answer 200 with an error body.
            message = data["error"]
            if isinstance(message, dict):
                message = message.get("message") or message.get("code") or message
            raise LLMError("request", f"接口返回错误：{message}")
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("bad_response", f"缺少 choices[0].message.content：{raw[:120]}") from None
        text = (content or "").strip()
        if not text:
            raise LLMError("empty", "模型返回空内容（可能触发了 max_tokens 或内容过滤）")
        LOGGER.debug(
            "llm ok provider=%s model=%s elapsed=%.2fs chars=%d",
            self.provider,
            self.model,
            time.monotonic() - started,
            len(text),
        )
        return text


def build_client(
    settings: Settings,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatClient | None:
    """Return a client only when a call may actually be attempted.

    ``temperature``/``max_tokens`` let the chat path run warmer than the
    reason/check rewriter without another settings object.
    """

    if not settings.llm_ready:
        return None
    return OpenAICompatClient(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature if temperature is None else temperature,
        timeout=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens if max_tokens is None else max_tokens,
    )
