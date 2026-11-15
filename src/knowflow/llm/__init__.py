"""Optional LLM edge layer: summary-only input, guarded text, template fallback.

The layer is deliberately small and replaceable: it can rewrite Task-3
``reason``/``check`` wording, never a number or an ID.  When it is disabled, the
rule templates remain the only writer, so every other layer stays deterministic.

Owner: R3.
"""

from __future__ import annotations

from .client import ChatClient, OpenAICompatClient, build_client
from .service import PROMPT_VERSION, ReasonWriter, WriteMeta
from .summary import build_issue_summary

__all__ = [
    "ChatClient",
    "OpenAICompatClient",
    "PROMPT_VERSION",
    "ReasonWriter",
    "WriteMeta",
    "build_client",
    "build_issue_summary",
]
