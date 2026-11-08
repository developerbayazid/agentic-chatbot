"""Application configuration loaded from environment variables and .env."""

import os

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
