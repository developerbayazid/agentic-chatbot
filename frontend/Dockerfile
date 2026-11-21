# syntax=docker/dockerfile:1.7
# ===========================================================================
# Frontend image — production (Next.js standalone)
#
# Three stages: dependencies → build → runtime. The runtime image carries the
# standalone server bundle and its traced node_modules only — no pnpm, no
# TypeScript, no dev dependencies, no source tree.
#
# The BFF design means this is the only public-facing container: the browser
# talks to Next, and Next proxies to the backend over the compose network.
# There are no NEXT_PUBLIC_* variables, and none may be added: `connect-src
# 'self'` in the CSP depends on the browser never addressing the backend.
# ===========================================================================

# ---------------------------------------------------------------------------
# Stage 1 — dependencies
# ---------------------------------------------------------------------------
FROM node:22-slim AS deps

WORKDIR /app

# corepack pins pnpm to the version in `packageManager`, so the lockfile is
# honoured exactly. CI uses the same version.
RUN corepack enable && corepack prepare pnpm@12.18.0 --activate

# Only the manifests: a source-only change must not invalidate the install.
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# ---------------------------------------------------------------------------
# Stage 2 — build
# ---------------------------------------------------------------------------
FROM node:22-slim AS builder

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@12.18.0 --activate

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# `next build` needs egress: `next/font/google` downloads fonts at build time.
# They are then served from the image, so the runtime needs no egress.
#
# `typescript.ignoreBuildErrors` is set in next.config.ts, so this build does
# NOT type-check. `pnpm typecheck` is the type gate and belongs in CI (Sprint 4)
# — a green image is not evidence that the types are sound.
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# ---------------------------------------------------------------------------
# Stage 3 — runtime
# ---------------------------------------------------------------------------
FROM node:22-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN groupadd --gid 10001 nextjs \
    && useradd --uid 10001 --gid 10001 --shell /usr/sbin/nologin nextjs

# The standalone bundle is rooted at `.next/standalone` and expects to run from
# there. `server.js` is its entry point.
COPY --from=builder --chown=10001:10001 /app/.next/standalone ./
# Static assets and the client-side chunks are NOT part of the standalone
# trace; Next serves them from these two paths, so they must be copied beside it.
COPY --from=builder --chown=10001:10001 /app/.next/static ./.next/static
COPY --from=builder --chown=10001:10001 /app/public ./public

USER 10001:10001

EXPOSE 3000

# /login renders without the backend, so this stays a genuine liveness check:
# a dead API must not make Docker restart a healthy frontend.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

CMD ["node", "server.js"]
