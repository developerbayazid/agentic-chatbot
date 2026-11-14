"""Application factory and lifespan.

The container is created once on startup (the same composition root the CLI
uses) and closed on shutdown. Nothing opens a database or a graph at import
time, so importing this module from a test is free.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager

import anyio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agentic_chatbot.api.context import HEADER, set_request_id
from agentic_chatbot.api.errors import install_error_handlers
from agentic_chatbot.api.routers import (
    approvals,
    auth,
    chat,
    documents,
    health,
    threads,
)
from agentic_chatbot.config import Settings, get_settings, parse_cors_origins
from agentic_chatbot.container import ChatbotContainer, build_container

logger = logging.getLogger(__name__)

WILDCARD_ORIGINS = {"*"}


def _configure_logging() -> None:
    root = logging.getLogger()

    if root.handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _validate_settings(settings: Settings) -> None:
    """Fail loudly on a configuration that would silently serve insecure traffic."""
    origins = parse_cors_origins(settings.cors_origins)

    if WILDCARD_ORIGINS & set(origins):
        raise RuntimeError(
            "CORS_ORIGINS must list explicit origins; a wildcard cannot be "
            "combined with credentials."
        )

    from agentic_chatbot.api.security import PLACEHOLDER_SECRETS

    secret = (settings.jwt_secret_key or "").strip()

    if settings.api_env == "production" and secret in PLACEHOLDER_SECRETS:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set to a strong value when API_ENV=production."
        )

    if secret and secret not in PLACEHOLDER_SECRETS and len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be at least 32 characters for HS256."
        )


def create_app(
    settings: Settings | None = None,
    container_factory: Callable[[ChatbotContainer], ChatbotContainer] | None = None,
) -> FastAPI:
    _configure_logging()
    settings = settings or get_settings()
    _validate_settings(settings)

    # Default to the project's composition root *with these settings*. Passing
    # no factory must never fall back to get_settings(), or a caller-supplied
    # configuration (and every test) would quietly use the real database.
    factory = container_factory or build_container

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("starting the API; building the container")
        container = await anyio.to_thread.run_sync(factory, settings)
        app.state.container = container

        try:
            yield
        finally:
            logger.info("shutting down the API; closing the container")
            await anyio.to_thread.run_sync(container.close)

    development = settings.api_env != "production"

    app = FastAPI(
        title="BAYAZID AI",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if development else None,
        redoc_url="/redoc" if development else None,
        openapi_url="/openapi.json" if development else None,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=parse_cors_origins(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", HEADER],
    )

    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        request_id = set_request_id(request.headers.get(HEADER))
        response = await call_next(request)
        response.headers[HEADER] = request_id
        return response

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(threads.router)
    app.include_router(chat.router)
    app.include_router(approvals.router)
    app.include_router(documents.router)

    return app


def main() -> None:
    """Console entry point: ``agentic-chatbot-api``."""
    settings = get_settings()

    uvicorn.run(
        create_app(settings=settings),
        host=settings.api_host,
        port=settings.api_port,
    )
