"""Security headers and the SPA/scroll invariants.

The header tests guard a real gap found during the Sprint 8 audit: the API
returned no security headers at all, and the frontend served a fingerprinting
`X-Powered-By`. Both are cheap to lose in a refactor, so they are asserted.
"""

from __future__ import annotations


def test_api_sets_baseline_security_headers(api_client):
    headers = api_client.get("/health").headers

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "geolocation=()" in headers["permissions-policy"]


def test_api_sets_hsts_only_over_https(api_client):
    """HSTS on a plain-HTTP dev server would poison the browser for that host."""
    plain = api_client.get("/health")
    assert "strict-transport-security" not in plain.headers

    forwarded = api_client.get(
        "/health", headers={"x-forwarded-proto": "https"}
    )
    assert "max-age=31536000" in forwarded.headers["strict-transport-security"]


def test_security_headers_survive_errors(api_client):
    """An error response must carry the same headers as a success."""
    response = api_client.get("/api/v1/threads")  # 401, no token

    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_headers_do_not_leak_server_details(api_client):
    headers = api_client.get("/health").headers

    assert "server" not in {key.lower() for key in headers}


def test_no_credentials_are_hardcoded_in_settings():
    """A connection string in source is a credential leaked to every reader.

    This existed: `postgres_dsn` defaulted to `postgres:postgres@localhost`. The
    default is now empty and the app refuses to start until it is configured.
    """
    from agentic_chatbot.config import Settings

    defaults = Settings.model_fields

    assert defaults["postgres_dsn"].default == ""

    # And nothing anywhere in the package ships a URL with an inline password.
    from pathlib import Path

    import agentic_chatbot

    package = Path(agentic_chatbot.__file__).parent
    offenders = []

    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")

        if "postgresql://" in text and "PASSWORD" not in text:
            for line in text.splitlines():
                if "postgresql://" in line and "@" in line:
                    credentials = line.split("postgresql://", 1)[1].split("@", 1)[0]
                    user, _, password = credentials.partition(":")

                    if password and password not in {"PASSWORD", "password"}:
                        offenders.append(f"{path.name}: {line.strip()[:70]}")

    assert not offenders, "hardcoded database credentials: " + "; ".join(offenders)


def test_postgres_backend_fails_clearly_without_a_dsn():
    """The first thing a fresh clone hits must be actionable, not a stack trace."""
    import pytest

    from agentic_chatbot.config import Settings
    from agentic_chatbot.container import _create_storage

    settings = Settings(
        database_backend="postgres",
        postgres_dsn="",
        openai_api_key="test-key",
        _env_file=None,
    )

    with pytest.raises(RuntimeError) as error:
        _create_storage(settings)

    message = str(error.value)
    assert "POSTGRES_DSN" in message
    assert "DATABASE_BACKEND=sqlite" in message, "must offer the SQLite escape hatch"

