"""Root entry point for ``fastapi dev`` / ``fastapi run`` / ``uvicorn main:app``.

The application lives in ``agentic_chatbot.api.main``; this file exists only
because the FastAPI CLI auto-discovers ``main.py``, ``app.py`` or ``api.py`` in
the current directory and expects a module-level ``FastAPI`` instance there.

Importing this module builds the ``FastAPI`` object but opens no database and
compiles no graph: the container is created by the lifespan, so this stays cheap
and has no side effects.

Run it with:

    uv run fastapi dev            # auto-discovers this file
    uv run fastapi run
    uv run uvicorn main:app --reload
"""

from agentic_chatbot.api.main import create_app

app = create_app()

__all__ = ["app"]
