import os
import shutil
from pathlib import Path

import pytest

from agentic_chatbot.config import Settings
from agentic_chatbot.container import ChatbotContainer
from agentic_chatbot.inventory.data_access import InventoryStore
from agentic_chatbot.inventory.service import InventoryService
from tests.pg import connect, create_schema, drop_schema, dsn_for_schema

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
def schema():
    """A disposable PostgreSQL schema, dropped after the test.

    One server serves the whole suite; a schema per test keeps tests isolated
    without creating a database per test. See ``tests/pg.py`` and
    ``TEST_POSTGRES_DSN``.
    """
    from tests.pg import application_tables_in_public

    before = application_tables_in_public()
    name = create_schema()

    try:
        yield name
    finally:
        # A test that connected without calling `init_schema` writes its tables
        # into the shared `public` schema instead, where they leak into other
        # tests. Catch that here rather than letting it pass silently.
        leaked = application_tables_in_public() - before
        drop_schema(name)

        if leaked:
            raise AssertionError(
                "test wrote to the shared `public` schema instead of its own: "
                f"{sorted(leaked)}. Call init_schema() on the connection."
            )


@pytest.fixture
def dsn(schema) -> str:
    """The DSN the application should use, scoped to this test's schema."""
    return dsn_for_schema(schema)


@pytest.fixture
def connection(schema):
    """An initialised application schema in this test's isolated schema."""
    from agentic_chatbot.postgres import init_schema

    instance = connect(schema)
    init_schema(instance, embedding_dimensions=8)

    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def settings(tmp_path, dsn) -> Settings:
    inventory_copy = tmp_path / "container-inventory" / "inventory_data.json"
    inventory_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INVENTORY_DATASET, inventory_copy)

    return Settings(
        # PostgreSQL is the only backend; the DSN points at this test's schema.
        postgres_dsn=dsn,
        inventory_data_path=str(inventory_copy),
        openai_api_key="test-key",
        embedding_dimensions=8,
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


API_KEYS = "alice=alice-secret,bob=bob-secret"
JWT_SECRET = "a-real-secret-used-only-by-tests-and-long-enough-for-hs256"


@pytest.fixture
def api_settings(settings, tmp_path) -> Settings:
    """API settings over the same isolated database and a temporary upload dir."""
    return settings.model_copy(
        update={
            "openai_api_key": "test-key",
            "api_keys": API_KEYS,
            "jwt_secret_key": JWT_SECRET,
            "cors_origins": "http://localhost:3000",
            "api_upload_path": str(tmp_path / "uploads"),
        }
    )


@pytest.fixture
def api_client(api_settings):
    """A started TestClient; the lifespan builds and closes the container.

    Embeddings are replaced with the deterministic double from ``tests.fakes`` so
    document tests never reach the network.
    """
    from fastapi.testclient import TestClient

    from agentic_chatbot.api.main import create_app
    from tests.fakes import FakeEmbeddings

    app = create_app(settings=api_settings)

    with TestClient(app) as client:
        container = app.state.container
        container.document_service._embeddings = FakeEmbeddings(
            dimensions=api_settings.embedding_dimensions
        )
        yield client


@pytest.fixture
def auth_headers(api_client):
    """Authorization headers for the default operator."""

    def headers(api_key: str = "alice-secret") -> dict[str, str]:
        response = api_client.post(
            "/api/v1/auth/token", json={"api_key": api_key}
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return headers


@pytest.fixture
def inventory_store(inventory_data_path):
    return InventoryStore(inventory_data_path)


@pytest.fixture
def inventory_service(inventory_store):
    return InventoryService(inventory_store)
