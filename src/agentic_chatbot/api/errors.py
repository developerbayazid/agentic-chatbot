"""Consistent API error envelope.

Every failure leaves the process as one shape::

    {"error": {"code": "THREAD_NOT_FOUND", "message": "...", "request_id": "..."}}

Stack traces are logged, never returned. Validation errors report field paths
only, so a rejected payload cannot echo a secret back to the client.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agentic_chatbot.api.context import get_request_id

logger = logging.getLogger(__name__)

_INTERNAL_MESSAGE = "The server failed to process the request."


class APIError(Exception):
    """A failure the router anticipated and can name."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        *,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(),
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            logger.warning("api error %s: %s", exc.code, exc.message)

        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            ".".join(str(part) for part in error.get("loc", ()) if part != "body")
            for error in exc.errors()
        ]

        return JSONResponse(
            status_code=422,
            content=error_body(
                "VALIDATION_ERROR",
                "Invalid request: " + ", ".join(filter(None, fields)),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled error on %s %s", request.method, request.url.path
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("INTERNAL_ERROR", _INTERNAL_MESSAGE),
        )
