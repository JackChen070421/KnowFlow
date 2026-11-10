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


class Settings(BaseSettings):
    """Runtime configuration; see ``.env.example`` for the full list."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
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
    llm_timeout_seconds: float = Field(default=30.0, gt=0.0)

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
