import pytest

from agentic_chatbot.config import Settings
from agentic_chatbot.container import ChatbotContainer


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "chatbot_memory.db"),
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
