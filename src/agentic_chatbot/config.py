"""Application configuration loaded from environment variables and .env."""

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


def get_settings() -> Settings:
    return Settings()
