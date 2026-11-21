# syntax=docker/dockerfile:1.7
# ===========================================================================
# Backend image — production
#
# Two stages so the build toolchain, the uv cache and the lockfile resolver
# never reach the runtime layer. Dependencies are installed before the source
# is copied, so a code-only change reuses the cached dependency layer.
#
# Deliberate choices:
#   * `--frozen` — the image is built from uv.lock exactly; no re-resolution.
#   * `--no-dev` — pytest/ruff/httpx stay out of production.
#   * No `.env`, no build-arg secrets. Configuration arrives at run time.
#   * Non-root runtime user (uid 10001) with a fixed uid so bind-mounted
#     volumes get predictable ownership.
# ===========================================================================

# Pinned, not `latest`: a moving base image makes builds unreproducible.
FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

# ---------------------------------------------------------------------------
# Stage 1 — resolve and install into a self-contained virtualenv
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependency layer. The project itself is excluded here so editing src/ does
# not invalidate the (slow) dependency install.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application layer. `uv sync` again installs only the project package.
COPY src ./src
COPY main.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

# PYTHONUNBUFFERED: logs reach `docker logs` immediately rather than on flush.
# PYTHONDONTWRITEBYTECODE: read-only-ish filesystem friendliness; the build
# stage already compiled the bytecode it needs.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# A fixed, high uid: predictable ownership for named volumes, and not a
# system account that could collide with something in the base image.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# The venv is built against the same interpreter, so it is portable between
# the two stages. Copying it avoids reinstalling into the runtime layer.
COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv
COPY --chown=10001:10001 main.py ./
COPY --chown=10001:10001 src ./src

# Runtime state lives on mounted volumes (see deploy/docker-compose.prod.yml).
# Creating them here with the right owner means a *named* volume inherits it;
# an empty bind mount would still need a chown on the host.
RUN mkdir -p /app/data/uploads /app/inventory-data/inventory /app/docs \
    && chown -R 10001:10001 /app/data /app/inventory-data /app/docs

USER 10001:10001

EXPOSE 8000

# Liveness only: /health touches no database, so an unhealthy Postgres must not
# make Docker restart a perfectly good application container. Readiness is
# /health/ready and is used by the deploy gate, not by Docker.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request;\nsys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]

# Exactly one worker. The application shares a single psycopg connection and an
# RLock, and keeps BM25 indexes in memory — more workers would multiply
# connections and diverge the deriving state. Scaling is vertical (API.md §14).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
