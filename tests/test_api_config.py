"""REST API configuration: defaults stay inert, parsers normalize env strings."""

from agentic_chatbot.config import Settings, parse_api_keys, parse_cors_origins


def test_api_defaults_are_inert(monkeypatch):
    for key in (
        "API_ENV",
        "API_HOST",
        "API_PORT",
        "API_KEYS",
        "JWT_SECRET_KEY",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.api_env == "development"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.api_upload_path == "data/uploads"
    assert settings.api_max_upload_bytes == 20_000_000
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes == 30
    assert settings.api_keys == ""
    assert settings.jwt_secret_key is None
    assert parse_cors_origins(settings.cors_origins) == ["http://localhost:3000"]


def test_api_settings_read_environment(monkeypatch):
    monkeypatch.setenv("API_ENV", "production")
    monkeypatch.setenv("API_PORT", "9100")
    monkeypatch.setenv("API_KEYS", "alice=s1,bob=s2")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-real-looking-secret")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://example.test")

    settings = Settings(_env_file=None)

    assert settings.api_env == "production"
    assert settings.api_port == 9100
    assert parse_api_keys(settings.api_keys) == {"alice": "s1", "bob": "s2"}
    assert settings.jwt_secret_key == "a-real-looking-secret"
    assert parse_cors_origins(settings.cors_origins) == [
        "http://localhost:3000",
        "http://example.test",
    ]


def test_invalid_api_env_is_rejected(monkeypatch):
    monkeypatch.setenv("API_ENV", "staging")

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_parse_api_keys_ignores_blank_and_malformed_entries():
    assert parse_api_keys("") == {}
    assert parse_api_keys("   ") == {}
    assert parse_api_keys("alice=secret") == {"alice": "secret"}
    assert parse_api_keys(" alice = secret ") == {"alice": "secret"}
    assert parse_api_keys("alice=a,bob=b") == {"alice": "a", "bob": "b"}
    assert parse_api_keys("malformed,alice=a") == {"alice": "a"}
    assert parse_api_keys("alice=") == {}


def test_parse_cors_origins_deduplicates_and_strips():
    assert parse_cors_origins("") == []
    assert parse_cors_origins(" http://a , http://b ,, ") == [
        "http://a",
        "http://b",
    ]
    assert parse_cors_origins("http://a,http://a") == ["http://a"]
