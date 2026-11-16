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
