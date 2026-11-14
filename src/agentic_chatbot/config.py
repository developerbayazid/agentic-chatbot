"""Application configuration loaded from environment variables and .env."""

import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None
    database_path: str = "chatbot_memory.db"
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
    rag_index_path: str = "data/faiss"

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
    langsmith_project: str = "agentic-chatbot"
    langsmith_endpoint: str | None = None


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


def get_settings() -> Settings:
    settings = Settings()
    export_langsmith_env(settings)
    return settings
