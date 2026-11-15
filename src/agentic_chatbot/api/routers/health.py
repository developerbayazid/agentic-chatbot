"""Health endpoints.

Readiness is deliberately cheap: no model call, no embedding, no index read. It
answers "can this process serve traffic right now", and it never discloses a
path, key, or DSN — only booleans and a status.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

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
    try:
        container.connection.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        logger.debug("readiness: database check failed", exc_info=True)
        return False


def _graph_ready(container) -> bool:
    return getattr(container, "chatbot", None) is not None


def _storage_ready(container) -> bool:
    """Whether the vector store is usable.

    The two backends store vectors differently — FAISS writes a directory,
    ``PgVectorStore`` writes rows — so this asks each for a cheap, side-effect-free
    answer rather than assuming a filesystem path exists. Probe generators are
    preferred; bulk ``stats()`` is not, because readiness must stay cheap.
    """
    store = getattr(container, "vector_store", None)

    if store is None:
        return False

    try:
        probe = getattr(store, "probe", None)

        if callable(probe):
            return bool(probe())

        # FAISS: the index directory must exist and be writable.
        directory = Path(store.path_for("default")).parent
        return directory.is_dir()
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
