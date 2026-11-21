"""Health endpoints.

Readiness is deliberately cheap: no model call, no embedding, no index read. It
answers "can this process serve traffic right now", and it never discloses a
path, key, or DSN — only booleans and a status.
"""

from __future__ import annotations

import logging

import psycopg
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from agentic_chatbot.api.dependencies import ContainerDep, SettingsDep
from agentic_chatbot.api.security import PLACEHOLDER_SECRETS
from agentic_chatbot.config import parse_api_keys

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

APPLICATION = "BAYAZID AI"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "application": APPLICATION}


def _database_ready(container) -> bool:
    """Whether the database answers ``SELECT 1``.

    A Postgres outage must become a clean 503 rather than an escaped 500: a
    load balancer that sees a 500 cannot distinguish an unhealthy dependency from
    a bug in the application.
    """
    try:
        container.connection.execute("SELECT 1").fetchone()
        return True
    except psycopg.Error:
        logger.debug("readiness: database check failed", exc_info=True)
        return False


def _graph_ready(container) -> bool:
    return getattr(container, "chatbot", None) is not None


def _storage_ready(container) -> bool:
    """Whether the vector store is usable.

    ``PgVectorStore`` exposes ``probe()``, a cheap side-effect-free check; bulk
    ``stats()`` is not used because readiness must stay cheap.
    """
    store = getattr(container, "vector_store", None)

    if store is None:
        return False

    try:
        probe = getattr(store, "probe", None)

        if callable(probe):
            return bool(probe())

        return False
    except Exception:  # noqa: BLE001 - an unusable store is simply not ready
        logger.debug("readiness: vector store check failed", exc_info=True)
        return False


def _configuration_ready(settings) -> bool:
    secret = (settings.jwt_secret_key or "").strip()

    return (
        bool(parse_api_keys(settings.api_keys))
        and secret not in PLACEHOLDER_SECRETS
        and settings.openai_api_key is not None
    )


@router.get("/health/ready")
def readiness(
    container: ContainerDep,
    settings: SettingsDep,
) -> JSONResponse:
    checks = {
        "database": _database_ready(container),
        "graph": _graph_ready(container),
        "storage": _storage_ready(container),
        "configuration": _configuration_ready(settings),
    }
    ready = all(checks.values())
    payload = {
        "status": "ready" if ready else "not_ready",
        "application": APPLICATION,
        "checks": checks,
    }

    return JSONResponse(
        status_code=(
            status.HTTP_200_OK
            if ready
            else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content=payload,
    )
