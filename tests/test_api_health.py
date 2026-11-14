"""API foundation: lifespan, health, readiness, and the error envelope."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from agentic_chatbot.api.main import create_app


class FakeContainer:
    """Minimal container double, so lifecycle tests need no LLM or embeddings."""

    def __init__(self):
        from types import SimpleNamespace

        self.closed = False
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.execute("CREATE TABLE t (id INTEGER)")
        self.chatbot = SimpleNamespace()
        self.vector_store = SimpleNamespace(
            path_for=lambda namespace: __import__("pathlib").Path(
                _storage_dir
            ) / f"{namespace}.faiss"
        )

    def close(self):
        self.closed = True
        self.connection.close()


_storage_dir = None


@pytest.fixture
def fake_factory(tmp_path, monkeypatch):
    global _storage_dir
    _storage_dir = tmp_path
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

    assert api_settings.database_path not in text
    assert api_settings.rag_index_path not in text
    assert api_settings.jwt_secret_key not in text
    assert "faiss" not in text
    assert "sqlite" not in text.replace("checks", "")


def test_readiness_fails_when_the_database_is_closed(api_client):
    container = api_client.app.state.container
    container.connection.close()

    response = api_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] is False
    assert response.json()["status"] == "not_ready"


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
    real chatbot_memory.db instead of the temporary one.
    """
    app = create_app(settings=api_settings)

    with TestClient(app) as client:
        container = app.state.container

        assert client.get("/health").status_code == 200
        assert container.settings is api_settings
        assert container.settings.database_path == api_settings.database_path


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
