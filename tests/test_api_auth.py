"""Authentication: token issuance, expiry, and rejection paths."""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from agentic_chatbot.api.dependencies import CurrentUserDep
from agentic_chatbot.api.main import create_app


def test_valid_api_key_returns_a_token(api_client):
    response = api_client.post(
        "/api/v1/auth/token", json={"api_key": "alice-secret"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1800
    assert body["access_token"]


def test_unknown_api_key_is_rejected(api_client):
    response = api_client.post(
        "/api/v1/auth/token", json={"api_key": "not-a-key"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "not-a-key" not in response.text


def test_api_key_is_required(api_client):
    assert (
        api_client.post("/api/v1/auth/token", json={}).status_code == 422
    )


def test_token_subject_is_the_operator_name(api_client, api_settings):
    token = api_client.post(
        "/api/v1/auth/token", json={"api_key": "bob-secret"}
    ).json()["access_token"]

    payload = jwt.decode(
        token, api_settings.jwt_secret_key, algorithms=[api_settings.jwt_algorithm]
    )

    assert payload["sub"] == "bob"
    assert payload["exp"] - payload["iat"] == 1800


def test_issuance_is_disabled_without_a_signing_secret(api_settings):
    broken = api_settings.model_copy(update={"jwt_secret_key": None})

    with TestClient(create_app(settings=broken)) as client:
        response = client.post(
            "/api/v1/auth/token", json={"api_key": "alice-secret"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.fixture
def protected_app(api_settings):
    """The app plus a protected route, since resource routers arrive later."""
    app = create_app(settings=api_settings)
    router = APIRouter()

    @router.get("/protected")
    def protected(user: CurrentUserDep):
        return {"subject": user.subject}

    app.include_router(router)
    return app


def test_protected_route_requires_a_token(protected_app):
    with TestClient(protected_app) as client:
        response = client.get("/protected")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.headers.get("www-authenticate") == "Bearer"


def test_protected_route_accepts_a_valid_token(protected_app):
    with TestClient(protected_app) as client:
        token = client.post(
            "/api/v1/auth/token", json={"api_key": "alice-secret"}
        ).json()["access_token"]
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json() == {"subject": "alice"}


def test_invalid_signature_is_rejected(protected_app, api_settings):
    forged = jwt.encode(
        {"sub": "alice", "exp": int(time.time()) + 60},
        "a-different-secret-that-is-also-long-enough-for-hs256",
        algorithm=api_settings.jwt_algorithm,
    )

    with TestClient(protected_app) as client:
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {forged}"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_token_is_rejected(protected_app, api_settings):
    now = int(time.time())
    expired = jwt.encode(
        {"sub": "alice", "iat": now - 100, "exp": now - 10},
        api_settings.jwt_secret_key,
        algorithm=api_settings.jwt_algorithm,
    )

    with TestClient(protected_app) as client:
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {expired}"}
        )

    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


def test_token_without_a_subject_is_rejected(protected_app, api_settings):
    now = int(time.time())
    anonymous = jwt.encode(
        {"iat": now, "exp": now + 60},
        api_settings.jwt_secret_key,
        algorithm=api_settings.jwt_algorithm,
    )

    with TestClient(protected_app) as client:
        response = client.get(
            "/protected", headers={"Authorization": f"Bearer {anonymous}"}
        )

    assert response.status_code == 401


def test_malformed_authorization_header_is_rejected(protected_app):
    with TestClient(protected_app) as client:
        response = client.get(
            "/protected", headers={"Authorization": "Bearer"}
        )

    assert response.status_code == 401


def test_a_callers_token_cannot_claim_another_subject(protected_app, api_settings):
    """The subject comes from the signed token, never from the request body."""
    stolen_claims = jwt.encode(
        {"sub": "bob", "exp": int(time.time()) + 60},
        api_settings.jwt_secret_key,
        algorithm=api_settings.jwt_algorithm,
    )

    with TestClient(protected_app) as client:
        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {stolen_claims}"},
        )

    # A valid token does authenticate as its own subject; what it cannot do is
    # carry an ``owner_id`` override, because that is not an input at all.
    assert response.status_code == 200
    assert response.json()["subject"] == "bob"
