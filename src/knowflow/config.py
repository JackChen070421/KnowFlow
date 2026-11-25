"""Typed runtime configuration loaded from the environment (and ``.env`` locally).

This is the only module that reads environment variables; everything else takes a
``Settings`` instance. Precedence: real environment > ``.env`` > defaults, which
keeps CI and containers working without a ``.env`` file.

Boundary note (AGENT.md §9–§10): these settings configure *where* the aggregated
``llm_summary`` may be sent. They never carry raw records, names or free text.

Owner: R3.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environment variables mirror .env.example with the KNOWFLOW_ prefix stripped:
#   KNOWFLOW_LLM_API_KEY -> llm_api_key, KNOWFLOW_DATA_DIR -> data_dir, ...
ENV_PREFIX = "KNOWFLOW_"


def _env_file() -> str:
    """Prefer the repository ``.env`` even when the process starts elsewhere.

    The web settings page writes this file, so the server and a later CLI run
    must resolve the same path regardless of the current directory.
    """

    root = Path(__file__).resolve().parents[2]
    return str(root / ".env") if (root / "pyproject.toml").is_file() else ".env"


class Settings(BaseSettings):
    """Runtime configuration; see ``.env.example`` for the full list."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM edge layer -------------------------------------------------
    llm_enabled: bool = False
    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = Field(default="", repr=False)
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    # A chat answer is a conversation, not a rewritten reason/check line: warmer,
    # and short enough to stay readable in the bubble.
    llm_chat_temperature: float = Field(default=0.6, ge=0.0, le=2.0)
    llm_chat_max_tokens: int = Field(default=700, ge=16, le=8192)
    # One call must not block the chat bubble for half a minute: the interactive
    # path retries a timeout once, so the worst case is ~2 x this value.
    llm_timeout_seconds: float = Field(default=20.0, gt=0.0)
    llm_max_tokens: int = Field(default=1024, ge=16, le=8192)

    # --- paths ----------------------------------------------------------
    data_dir: Path = Path("./data")
    artifact_dir: Path = Path("./artifacts")

    # --- runtime --------------------------------------------------------
    log_level: str = "INFO"
    random_seed: int = 20261108

    @property
    def llm_ready(self) -> bool:
        """True only when a call may actually be attempted.

        ``enabled`` alone is not enough: an empty key must degrade to templates
        instead of producing a 401 at runtime (AGENT.md §9).
        """

        return self.llm_enabled and bool(self.llm_api_key.strip())


def get_settings(**overrides: object) -> Settings:
    """Build settings, optionally overriding fields (handy in tests)."""

    return Settings(**overrides)  # type: ignore[arg-type]
