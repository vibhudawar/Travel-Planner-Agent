"""Centralized, validated application settings (WIN 1).

All configuration and secrets live here. Importing this module performs no I/O:
settings are loaded and validated lazily on the first ``get_settings()`` call,
which fails fast with a clear message if a required key is missing. Secrets are
``SecretStr`` so they never leak into logs or reprs.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor paths to the project root (this file's directory) so config, the cache
# directory, and the SQLite DB resolve regardless of the CWD the app is launched
# from.
_PROJECT_ROOT = Path(__file__).resolve().parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Typed application settings, populated from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Secrets (required; a missing one fails fast at startup) ---
    openai_api_key: SecretStr = Field(..., description="OpenAI API key")
    serpapi_api_key: SecretStr = Field(..., description="SerpAPI key (flights, hotels, maps, YouTube)")
    openweather_api_key: SecretStr = Field(..., description="OpenWeather API key")

    # --- LLM configuration (pinned for reproducibility; override via env) ---
    # Pinned so evals measure a fixed target. Change OPENAI_MODEL in the env to
    # swap models rather than editing code.
    openai_model: str = Field("gpt-4o", description="Pinned chat model id")
    # Eval judge model — intentionally different from openai_model so the generator
    # never grades its own output (judge ≠ generator). Override via JUDGE_MODEL.
    judge_model: str = Field("gpt-4o-mini", description="Model used by eval LLM judges")
    temperature: float = Field(0.0, ge=0.0, le=2.0, description="Sampling temperature; 0 = most reproducible")
    max_tokens: int = Field(1500, gt=0, description="Max output tokens per LLM call")
    request_timeout: float = Field(60.0, gt=0, description="Per-request LLM timeout (seconds)")
    max_retries: int = Field(2, ge=0, description="LLM client retry count on transient errors")

    # --- Infrastructure ---
    # Defaults are absolute (anchored to the project root) so they don't depend
    # on the launch directory; override with an absolute path via env if desired.
    cache_dir: str = Field(
        default_factory=lambda: str(_PROJECT_ROOT / "cache"),
        description="diskcache directory for tool-result caching",
    )
    sqlite_db_path: str = Field(
        default_factory=lambda: str(_PROJECT_ROOT / "chatbot.db"),
        description="LangGraph SqliteSaver database path",
    )


    def resolved_cache_dir(self) -> str:
        """cache_dir as an absolute path (relative values anchored to project root)."""
        return str(_resolve_path(self.cache_dir))

    def resolved_sqlite_path(self) -> str:
        """sqlite_db_path as an absolute path (relative values anchored to project root)."""
        return str(_resolve_path(self.sqlite_db_path))


def _resolve_path(path_str: str) -> Path:
    """Resolve a possibly-relative path against the project root, expanding ~."""
    p = Path(path_str).expanduser()
    return p if p.is_absolute() else _PROJECT_ROOT / p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the validated settings singleton (constructed and validated once).

    Raises a clear ``RuntimeError`` naming the missing keys instead of a raw
    pydantic ``ValidationError``, so a misconfigured environment fails fast and
    legibly at startup rather than as an opaque error mid-conversation.
    """
    try:
        return Settings()  # type: ignore[call-arg]  # values come from env / .env
    except ValidationError as exc:
        missing = sorted(
            {
                str(err["loc"][0]).upper()
                for err in exc.errors()
                if err.get("type") == "missing" and err.get("loc")
            }
        )
        if missing:
            raise RuntimeError(
                "Missing required configuration: "
                + ", ".join(missing)
                + f". Set them in your environment or {_ENV_FILE.name} (see .env.example)."
            ) from exc
        raise
