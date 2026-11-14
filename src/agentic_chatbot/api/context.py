"""Request correlation ID, shared by the error envelope and the logs."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str | None = None) -> str:
    request_id = (value or "").strip()[:64] or new_request_id()
    _request_id.set(request_id)
    return request_id


def get_request_id() -> str | None:
    return _request_id.get()
