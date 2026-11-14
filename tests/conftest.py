import os

import pytest

from agentic_chatbot.config import Settings
from agentic_chatbot.container import ChatbotContainer

LANGSMITH_ENV_KEYS = (
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_PROJECT",
    "LANGCHAIN_ENDPOINT",
)


@pytest.fixture(autouse=True)
def isolate_langsmith_env():
    saved = {key: os.environ.get(key) for key in LANGSMITH_ENV_KEYS}

    for key in LANGSMITH_ENV_KEYS:
        os.environ.pop(key, None)

    yield

    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "chatbot_memory.db"),
        rag_index_path=str(tmp_path / "faiss"),
        openai_api_key="test-key",
        _env_file=None,
    )


@pytest.fixture
def container(settings):
    instance = ChatbotContainer(settings)
    try:
        yield instance
    finally:
        instance.close()
