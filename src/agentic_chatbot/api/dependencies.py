"""FastAPI dependency providers.

Services are read off ``app.state.container`` — the composition root built by the
lifespan — so the API never constructs a second container, never opens a second
SQLite connection, and never compiles a second graph.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agentic_chatbot.api.errors import APIError
from agentic_chatbot.api.security import (
    CredentialsError,
    CurrentUser,
    decode_access_token,
)
from agentic_chatbot.config import Settings
from agentic_chatbot.container import ChatbotContainer
from agentic_chatbot.services import (
    ChatService,
    DocumentService,
    ThreadService,
)

bearer_scheme = HTTPBearer(auto_error=False)


def get_container(request: Request) -> ChatbotContainer:
    container = getattr(request.app.state, "container", None)

    if container is None:  # pragma: no cover - the lifespan always sets this
        raise APIError(
            "NOT_READY",
            "The application is still starting.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return container


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_chat_service(
    container: Annotated[ChatbotContainer, Depends(get_container)],
) -> ChatService:
    return container.chat_service


def get_thread_service(
    container: Annotated[ChatbotContainer, Depends(get_container)],
) -> ThreadService:
    return container.thread_service


def get_document_service(
    container: Annotated[ChatbotContainer, Depends(get_container)],
) -> DocumentService:
    return container.document_service


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> CurrentUser:
    """Authenticate the bearer token.

    Every status is 401 with the same code shape, so a caller cannot tell
    "missing" from "expired" from "wrong signature" by the error code alone —
    only by the message intended for a human.
    """
    if credentials is None or not credentials.credentials:
        raise APIError(
            "UNAUTHORIZED",
            "A bearer token is required.",
            status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return decode_access_token(settings, credentials.credentials)
    except CredentialsError as error:
        raise APIError(
            "UNAUTHORIZED",
            str(error),
            status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
ThreadServiceDep = Annotated[ThreadService, Depends(get_thread_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[ChatbotContainer, Depends(get_container)]
