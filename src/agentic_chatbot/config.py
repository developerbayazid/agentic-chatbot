"""Application configuration loaded from environment variables and .env."""

import os
from typing import Literal
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None

    # PostgreSQL is the only storage backend: it holds relational rows,
    # embeddings (pgvector), and LangGraph checkpoints on one connection.
    #
    # Supplied through the environment or `.env`. It is deliberately empty by
    # default: a connection string embeds credentials, and a credential
    # committed to source is a credential leaked to everyone who can read the
    # repository. `build_container` refuses to start rather than guessing a
    # localhost default.
    postgres_dsn: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    system_prompt: str = "You are a helpful AI assistant."

    # Retrieval-augmented generation
    embeddings_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 120
    rag_top_k: int = 4
    rag_min_score: float = 0.15
    rag_search_mode: Literal["hybrid", "vector", "bm25"] = "hybrid"
    rag_vector_candidates: int = 10
    rag_bm25_candidates: int = 10
    rag_rrf_k: int = 60
    docs_path: str = "docs"

    # Inventory demo dataset (JSON persistence, no ORM)
    inventory_data_path: str = "inventory-data/inventory/inventory_data.json"
    inventory_operator_id: str = "EMP-006"
    inventory_operation_log_limit: int = 500
    inventory_audit_log_limit: int = 1000
    rag_max_text_bytes: int = 2_000_000
    rag_max_pdf_bytes: int = 20_000_000
    rag_max_pdf_pages: int = 200

    # LangSmith Observability
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "agentic-chatbot-dev"
    langsmith_endpoint: str | None = None

    # REST API
    api_env: Literal["development", "production"] = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_upload_path: str = "data/uploads"
    api_max_upload_bytes: int = 20_000_000
    api_keys: str = ""
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    cors_origins: str = "http://localhost:3000"


def export_langsmith_env(settings: Settings) -> None:
    """Propagate LangSmith settings to the process environment.

    LangChain and LangSmith read tracing configuration directly from
    ``os.environ``; values loaded from ``.env`` into this Settings object are
    otherwise invisible to them.
    """
    if settings.langsmith_tracing:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    if settings.langsmith_project:
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    if settings.langsmith_endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)


def redacted_dsn_label(dsn: str) -> str:
    """Return a display-safe label for a DSN: host, port and database only.

    The connection string embeds the password, and the CLI `/status` line is
    rendered to a terminal that may be shared or recorded. Only the parts that
    identify *which* database is in use are kept.
    """
    if not dsn:
        return "not configured"

    parts = urlsplit(dsn)
    host = parts.hostname or "unknown-host"
    port = f":{parts.port}" if parts.port else ""
    database = parts.path.lstrip("/") or "unknown-db"

    return f"postgresql://{host}{port}/{database}"


def parse_api_keys(raw: str) -> dict[str, str]:
    """Parse ``name=secret,name=secret`` into a mapping.

    Blank entries are ignored; an entry without ``=`` is skipped rather than
    crashing startup, because an empty ``API_KEYS`` must simply mean "no keys".
    """
    keys: dict[str, str] = {}

    for entry in raw.split(","):
        name, separator, secret = entry.partition("=")
        name = name.strip()
        secret = secret.strip()

        if separator and name and secret:
            keys[name] = secret

    return keys


def parse_cors_origins(raw: str) -> list[str]:
    """Parse a comma-separated origin list into explicit origins."""
    origins: list[str] = []

    for entry in raw.split(","):
        origin = entry.strip()

        if origin and origin not in origins:
            origins.append(origin)

    return origins


def get_settings() -> Settings:
    settings = Settings()
    export_langsmith_env(settings)
    return settings
