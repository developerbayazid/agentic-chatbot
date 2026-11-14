"""Token issuance.

An operator exchanges a configured API key for a short-lived JWT. This is the
only unauthenticated write endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from agentic_chatbot.api.dependencies import SettingsDep
from agentic_chatbot.api.errors import APIError
from agentic_chatbot.api.schemas import TokenRequest, TokenResponse
from agentic_chatbot.api.security import (
    CredentialsError,
    issue_access_token,
    verify_api_key,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
def create_token(body: TokenRequest, settings: SettingsDep) -> TokenResponse:
    try:
        user = verify_api_key(settings, body.api_key)
        token, expires_in = issue_access_token(settings, user.subject)
    except CredentialsError as error:
        # One code for every credential failure: the client learns nothing about
        # which half of the pair was wrong.
        raise APIError(
            "INVALID_CREDENTIALS",
            "The supplied API key is not valid.",
            status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    return TokenResponse(access_token=token, expires_in=expires_in)
