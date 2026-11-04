"""Application settings for the FastAPI web layer.

Settings are loaded from the environment and an optional ``.env`` file via
``pydantic-settings``. The web layer is the only place that reads process-wide
configuration; the engine (``mad/``) and persistence (``app/db/``) layers take
their inputs explicitly so they stay headless and testable (Req 12.2).

Configuration surface (all overridable via env, prefix ``MAD_``):

* ``MAD_DATABASE_URL`` — SQLAlchemy URL for the SQLite datastore. Defaults to
  :data:`app.db.session.DEFAULT_DATABASE_URL`.
* ``MAD_SECRET_KEY`` — operator server secret used to derive the Fernet key for
  credential encryption (consumed by :mod:`app.security`). Surfaced here for
  completeness/validation; the security layer reads it directly.
* ``MAD_CORS_ORIGINS`` — comma-separated list (or JSON array) of allowed
  frontend origins for CORS. Defaults to the common Vite dev origins.
* ``MAD_DATASET_STORAGE_PATH`` — directory where uploaded dataset CSVs are
  stored. Defaults to ``data/datasets`` under the backend working directory.
* ``MAD_API_TITLE`` / ``MAD_API_DESCRIPTION`` — OpenAPI metadata overrides.

Nothing here imports FastAPI, so the module is safe to import from the CLI and
tests as well.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.db.session import DEFAULT_DATABASE_URL

# Default directory (relative to the backend working directory) where uploaded
# dataset CSV files are stored. Overridable via ``MAD_DATASET_STORAGE_PATH``.
DEFAULT_DATASET_STORAGE_PATH: str = "data/datasets"

# Default frontend origins (Vite dev server over http) allowed through CORS.
DEFAULT_CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


class Settings(BaseSettings):
    """Typed application settings, loaded from env / ``.env``.

    The ``MAD_`` env prefix keeps the web layer's configuration namespaced and
    avoids clashes with provider API keys (``OPENAI_API_KEY`` etc.) that live in
    the same ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_prefix="MAD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Persistence
    database_url: str = Field(default=DEFAULT_DATABASE_URL)

    # Credential encryption server secret (consumed by app.security). Optional
    # here so the app can boot for read-only/metadata use without a secret; the
    # security layer raises a clear error if a credential operation needs it.
    secret_key: str | None = Field(default=None)

    # CORS — allowed frontend origins.
    cors_origins: list[str] = Field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))

    # Dataset storage — directory where uploaded CSV files are written. Relative
    # paths resolve against the backend working directory; created on first use.
    dataset_storage_path: str = Field(default=DEFAULT_DATASET_STORAGE_PATH)

    @property
    def dataset_storage_dir(self) -> Path:
        """The dataset storage directory as a :class:`~pathlib.Path`."""
        return Path(self.dataset_storage_path)

    # OpenAPI metadata
    api_title: str = Field(default="MADLab API")
    api_description: str = Field(
        default=(
            "REST API for the Multi-Agent Debate (MAD) platform: taxonomy, "
            "configurations, providers, datasets, and debate executions."
        )
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string as well as a list/JSON array.

        ``MAD_CORS_ORIGINS=http://a.com,http://b.com`` is a convenient shape for
        ``.env`` files; pydantic-settings otherwise expects a JSON array. An
        empty string yields an empty list (CORS effectively disabled).
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            # Leave JSON arrays for pydantic to parse natively.
            if stripped.startswith("["):
                return value
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance."""
    return Settings()


__all__ = [
    "Settings",
    "get_settings",
    "DEFAULT_CORS_ORIGINS",
    "DEFAULT_DATASET_STORAGE_PATH",
]
