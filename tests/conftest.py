import os
import shutil
from pathlib import Path

import pytest

from agentic_chatbot.config import Settings
from agentic_chatbot.container import ChatbotContainer
from agentic_chatbot.inventory.data_access import InventoryStore
from agentic_chatbot.inventory.service import InventoryService

REPO_ROOT = Path(__file__).resolve().parents[1]
# Tests always start from the pristine seed. The working inventory_data.json is
# the live demo state and may legitimately change while the CLI is in use.
INVENTORY_DATASET = (
    REPO_ROOT / "inventory-data" / "inventory" / "inventory_data.seed.json"
)

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
    inventory_copy = tmp_path / "container-inventory" / "inventory_data.json"
    inventory_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INVENTORY_DATASET, inventory_copy)

    return Settings(
        database_path=str(tmp_path / "chatbot_memory.db"),
        rag_index_path=str(tmp_path / "faiss"),
        inventory_data_path=str(inventory_copy),
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


@pytest.fixture
def inventory_data_path(tmp_path) -> Path:
    """A writable copy of the demo dataset, so tests never touch the original."""
    target = tmp_path / "inventory" / "inventory_data.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INVENTORY_DATASET, target)
    return target


@pytest.fixture
def inventory_store(inventory_data_path):
    return InventoryStore(inventory_data_path)


@pytest.fixture
def inventory_service(inventory_store):
    return InventoryService(inventory_store)
