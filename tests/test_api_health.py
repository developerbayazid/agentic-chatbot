"""API foundation: lifespan, health, readiness, and the error envelope."""

import pytest
from fastapi.testclient import TestClient

from agentic_chatbot.api.main import create_app


class FakeContainer:
    """Minimal container double, so lifecycle tests need no LLM or embeddings."""

    def __init__(self):
        from types import SimpleNamespace

        self.closed = False
        self.connection = SimpleNamespace()
        self.chatbot = SimpleNamespace()
        self.vector_store = SimpleNamespace(probe=lambda: True)

    def close(self):
        self.closed = True


@pytest.fixture
def fake_factory():
    created = []

    def factory(_settings):
        container = FakeContainer()
        created.append(container)
        return container

    return factory, created


def test_health_is_public_and_minimal(api_client):
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "application": "BAYAZID AI"}
    assert "database_path" not in response.text


def test_readiness_reports_named_checks(api_client):
    response = api_client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {
        "database": True,
        "graph": True,
        "storage": True,
        "configuration": True,
    }


def test_readiness_exposes_no_paths_or_secrets(api_client, api_settings):
    text = api_client.get("/health/ready").text

    assert api_settings.postgres_dsn not in text
    assert api_settings.jwt_secret_key not in text
    assert "faiss" not in text
    assert "password" not in text.lower()


def test_storage_check_accepts_a_store_without_filesystem_paths(api_client):
    """The vector store must not be assumed to be FAISS.

    ``PgVectorStore`` has no ``path_for`` at all, so a readiness check written
    against the FAISS API reported ``storage: False`` on Postgres and made every
    deployment look unready. Stores may expose a ``probe`` instead.
    """
    container = api_client.app.state.container

    class RowStore:
        def probe(self):
            return True

    original = container.vector_store
    container.vector_store = RowStore()

    try:
        body = api_client.get("/health/ready").json()
        assert body["checks"]["storage"] is True
        assert body["status"] == "ready"
    finally:
        container.vector_store = original


def test_storage_check_reports_an_unusable_store(api_client):
    container = api_client.app.state.container

    class BrokenStore:
        def probe(self):
            return False

    original = container.vector_store
    container.vector_store = BrokenStore()

    try:
        body = api_client.get("/health/ready").json()
        assert body["checks"]["storage"] is False
        assert body["status"] == "not_ready"
    finally:
        container.vector_store = original


def test_readiness_fails_when_the_database_is_closed(api_client):
    container = api_client.app.state.container
    container.connection.close()

    response = api_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] is False
    assert response.json()["status"] == "not_ready"


def test_readiness_fails_on_a_postgres_error(api_client):
    """A Postgres outage must be a 503, not an escaped 500.

    ``_database_ready`` originally caught only ``sqlite3.Error``. On the Postgres
    backend psycopg raises ``psycopg.Error``, so a dropped connection escaped the
    handler and broke every container health check.
    """
    import psycopg

    container = api_client.app.state.container

    class BrokenConnection:
        def execute(self, *_args, **_kwargs):
            raise psycopg.OperationalError("connection lost")

    original = container.connection
    container.connection = BrokenConnection()

    try:
        response = api_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["database"] is False
        assert response.json()["status"] == "not_ready"
    finally:
        container.connection = original


def test_readiness_fails_with_placeholder_configuration(api_settings, tmp_path):
    from tests.conftest import JWT_SECRET

    broken = api_settings.model_copy(
        update={"jwt_secret_key": "replace_with_a_long_random_secret"}
    )
    assert broken.jwt_secret_key != JWT_SECRET

    with TestClient(create_app(settings=broken)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["configuration"] is False


def test_container_is_built_once_and_closed_on_shutdown(
    api_settings, fake_factory
):
    factory, created = fake_factory

    app = create_app(settings=api_settings, container_factory=factory)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert len(created) == 1
        assert app.state.container is created[0]
        assert created[0].closed is False

    assert created[0].closed is True


def test_startup_failure_is_loud(api_settings):
    def factory(_settings):
        raise RuntimeError("cannot build the container")

    app = create_app(settings=api_settings, container_factory=factory)

    with pytest.raises(RuntimeError, match="cannot build the container"):
        with TestClient(app):
            pass


def test_the_default_factory_uses_the_supplied_settings(api_settings):
    """A regression guard: create_app must never fall back to get_settings().

    An earlier version ignored the argument, so every API test quietly opened the
    real database instead of the test one.
    """
    app = create_app(settings=api_settings)

    with TestClient(app) as client:
        container = app.state.container

        assert client.get("/health").status_code == 200
        assert container.settings is api_settings
        assert container.settings.postgres_dsn == api_settings.postgres_dsn


def test_wildcard_cors_is_rejected(api_settings):
    broken = api_settings.model_copy(update={"cors_origins": "*"})

    with pytest.raises(RuntimeError, match="wildcard"):
        create_app(settings=broken)


def test_production_requires_a_real_secret(api_settings):
    broken = api_settings.model_copy(
        update={
            "api_env": "production",
            "jwt_secret_key": "replace_with_a_long_random_secret",
        }
    )

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_app(settings=broken)


def test_production_disables_documentation(api_settings):
    production = api_settings.model_copy(
        update={"api_env": "production"}
    )

    app = create_app(settings=production)

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_development_serves_documentation(api_client):
    assert api_client.get("/docs").status_code == 200
    assert api_client.get("/openapi.json").status_code == 200


def test_request_id_is_echoed_and_honoured(api_client):
    generated = api_client.get("/health")
    supplied = api_client.get("/health", headers={"X-Request-ID": "caller-123"})

    assert generated.headers["X-Request-ID"]
    assert supplied.headers["X-Request-ID"] == "caller-123"


def test_unknown_route_uses_the_error_envelope(api_client):
    response = api_client.get("/api/v1/does-not-exist")

    assert response.status_code == 404


def test_validation_error_lists_fields_without_echoing_values(api_settings):
    from agentic_chatbot.api.schemas import TokenRequest

    app = create_app(settings=api_settings)

    @app.post("/validate")
    def validate(body: TokenRequest):
        return {"ok": True}

    with TestClient(app) as client:
        response = client.post(
            "/validate", json={"api_key": "", "unexpected": "sensitive-value"}
        )

    assert response.status_code == 422
    validation = response.json()["error"]
    assert validation["code"] == "VALIDATION_ERROR"
    assert "request_id" in validation
    assert "unexpected" in validation["message"]
    assert "sensitive-value" not in response.text


def test_unhandled_exception_is_not_leaked(api_settings):
    app = create_app(settings=api_settings)

    @app.get("/boom")
    def boom():
        raise ValueError("internal detail that must not escape")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "INTERNAL_ERROR"
    assert "internal detail" not in response.text
