"""Retry/fallback service that turns one summary into guarded reason/check text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .client import ChatClient
from .guard import parse_json, response_errors
from .prompt import SYSTEM_PROMPT, user_prompt

PROMPT_VERSION = "llm-reason-1"
_SECRET = re.compile(r"sk-[A-Za-z0-9._\-]{4,}")


def redact(text: str) -> str:
    """Remove key-shaped tokens before an error reaches any artifact."""

    return _SECRET.sub("sk-***", text)


@dataclass(frozen=True)
class WriteMeta:
    """What happened for one plan item; recorded, never hidden."""

    source: str
    attempts: int
    errors: tuple[str, ...] = ()


class ReasonWriter:
    """Rewrite ``reason``/``check``; fall back to the rule template on any doubt.

    ``max_attempts`` is the initial call plus retries (default 1 + 2).  Network
    errors, invalid JSON and guard rejections all consume an attempt, so a broken
    provider can never block a run.
    """

    def __init__(self, client: ChatClient, max_attempts: int = 3) -> None:
        self.client = client
        self.max_attempts = max(1, max_attempts)

    @property
    def provider(self) -> str:
        return getattr(self.client, "provider", "unknown")

    @property
    def model(self) -> str:
        return getattr(self.client, "model", "unknown")

    def write(
        self, summary: dict, fallback_reason: str, fallback_check: str
    ) -> tuple[str, str, WriteMeta]:
        errors: list[str] = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = self.client.complete(SYSTEM_PROMPT, user_prompt(summary))
            except Exception as exc:  # network/SDK errors degrade, never abort the run
                errors.append(redact(f"{type(exc).__name__}: {exc}")[:200])
                continue
            try:
                response = parse_json(raw)
            except (ValueError, TypeError) as exc:
                errors.append(redact(f"invalid_json: {exc}")[:160])
                continue
            problems = response_errors(response, summary)
            if not problems:
                return (
                    response["reason"].strip(),
                    response["check"].strip(),
                    WriteMeta("llm", attempt),
                )
            errors.extend(problems[:3])
        return (
            fallback_reason,
            fallback_check,
            WriteMeta("template", self.max_attempts, tuple(errors[-3:])),
        )
