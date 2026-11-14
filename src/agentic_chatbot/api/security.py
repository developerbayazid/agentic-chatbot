"""Authentication and the approval handle.

Two unrelated secrets live here:

* the **access token** — an API key is exchanged for a short-lived HS256 JWT;
* the **approval id** — an HMAC over the exact pending proposal, so a client can
  name an approval without holding (or forging) any graph internals.

Nothing reads a secret from a default: the key comes from configuration.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any

import jwt

from agentic_chatbot.config import Settings, parse_api_keys

PLACEHOLDER_SECRETS = {"", "replace_with_a_long_random_secret", "change-me"}


class CredentialsError(Exception):
    """The API key is unknown, or the token is missing/invalid/expired."""


class ApprovalHandleError(Exception):
    """The approval handle is not ours, or no longer matches the proposal."""


@dataclass(frozen=True)
class CurrentUser:
    subject: str


def verify_api_key(settings: Settings, api_key: str) -> CurrentUser:
    """Return the operator named by ``api_key``, or raise ``CredentialsError``.

    ``compare_digest`` keeps the comparison constant time, and the loop never
    short-circuits on the first name, so a caller cannot learn which entry
    matched by timing.
    """
    supplied = (api_key or "").encode("utf-8")
    matched: str | None = None

    for name, secret in parse_api_keys(settings.api_keys).items():
        if hmac.compare_digest(supplied, secret.encode("utf-8")):
            matched = name

    if matched is None:
        raise CredentialsError("Invalid API key.")

    return CurrentUser(subject=matched)


def signing_secret(settings: Settings) -> str:
    secret = (settings.jwt_secret_key or "").strip()

    if secret in PLACEHOLDER_SECRETS:
        raise CredentialsError(
            "JWT_SECRET_KEY is not configured; token issuance is disabled."
        )

    return secret


def issue_access_token(settings: Settings, subject: str) -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)``."""
    expires_in = max(1, settings.jwt_access_token_expire_minutes) * 60
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
    }

    token = jwt.encode(
        payload, signing_secret(settings), algorithm=settings.jwt_algorithm
    )

    return token, expires_in


def decode_access_token(settings: Settings, token: str) -> CurrentUser:
    """Validate signature and expiry, then return the subject."""
    if not token:
        raise CredentialsError("Missing access token.")

    try:
        payload = jwt.decode(
            token,
            signing_secret(settings),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as error:
        raise CredentialsError("Access token has expired.") from error
    except jwt.InvalidTokenError as error:
        raise CredentialsError("Invalid access token.") from error

    subject = payload.get("sub")

    if not isinstance(subject, str) or not subject:
        raise CredentialsError("Invalid access token.")

    return CurrentUser(subject=subject)


def make_approval_id(
    settings: Settings,
    subject: str,
    thread_id: str,
    interrupt_id: str | None,
    approval_token: str,
) -> str:
    """Sign the exact proposal an approval refers to.

    Deterministic, so listing and deciding agree, and unambiguous, so a decision
    cannot be replayed against a different thread or a different proposal.
    """
    message = "\x1f".join(
        (subject, thread_id, interrupt_id or "", approval_token)
    ).encode("utf-8")
    digest = hmac.new(
        signing_secret(settings).encode("utf-8"), message, hashlib.sha256
    ).digest()

    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def parse_approval_id(approval_id: str) -> str:
    """Reject anything that is not a well-formed handle before verifying."""
    if not approval_id or len(approval_id) > 64:
        raise ApprovalHandleError("Malformed approval id.")

    for character in approval_id:
        if not (character.isalnum() or character in "-_"):
            raise ApprovalHandleError("Malformed approval id.")

    return approval_id


def handle_for(
    settings: Settings,
    subject: str,
    thread_id: str,
    pending: dict | None,
) -> str | None:
    """Sign the interrupt a thread is actually waiting on.

    Derived from ``get_pending_interrupt`` rather than from a streamed event, so
    the handle issued by ``POST /chat``, listed by ``GET /approvals``, and
    verified by ``POST /approvals/{id}/decision`` are the same value.
    """
    if not pending:
        return None

    payload = pending.get("value")

    if not isinstance(payload, dict):
        return None

    return make_approval_id(
        settings,
        subject,
        thread_id,
        pending.get("interrupt_id"),
        payload.get("approval_token", ""),
    )


def verify_handle(
    settings: Settings,
    subject: str,
    thread_id: str,
    pending: dict,
    approval_id: str,
) -> None:
    """Raise unless ``approval_id`` names exactly this subject's live interrupt."""
    expected = handle_for(settings, subject, thread_id, pending)

    if expected is None or not hmac.compare_digest(expected, approval_id):
        raise ApprovalHandleError(
            "This approval no longer matches the pending action."
        )
