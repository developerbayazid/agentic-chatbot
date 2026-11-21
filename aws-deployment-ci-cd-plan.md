# AWS Deployment & GitHub Actions CI/CD — Sprint-by-Sprint Plan

**Project:** BAYAZID AI / Agentic Chatbot (`D:\ai-engineering\agentic-chatbot-main`)
**Brief:** `aws.md`
**Status:** implementation in progress — Sprint 0 complete, awaiting verification.

---

## 0. Sprint status ledger

Legend: **DONE** · **IN PROGRESS** · **AWAITING VERIFY** · **PENDING** · **BLOCKED**

| Sprint | Scope | State | Gate |
|---|---|---|---|
| 0 | Baseline hardening | **DONE** — awaiting your verification | ruff clean, 719 passed / 28 skipped |
| 1 | Backend image | **PENDING** | needs Sprint 0 sign-off |
| 2 | Frontend image | **PENDING** | needs Sprint 1 |
| 3 | Local full-stack compose | **PENDING** | needs Sprint 2 |
| 4 | CI workflow | **PENDING** | needs Sprint 3 |
| 5 | Publish to Docker Hub | **PENDING** | needs Sprint 4 green on `main` |
| 6 | AWS foundation (**billable**) | **PENDING** | needs explicit approval + §8 inputs |
| 7 | Automated deployment | **PENDING** | needs Sprint 6 |
| 8 | Backup, monitoring, runbook | **PENDING** | needs Sprint 7 |

### Sprint 0 — completion record

**State: DONE.** No AWS resource created. Cost: $0.

Files created:
- `.dockerignore` — root build context. Excludes `.env*`, `.venv`, `frontend/`,
  `tests/`, `notebooks/`, `data/`, `inventory-data/`, `docs/`, `deploy/`, `.git`.
  Note `.gitignore` has no effect on Docker build context, so this had to be explicit.
- `frontend/.dockerignore` — `node_modules`, `.next`, `.env*`, test output.
- `AWS-DEPLOYMENT.md` — runbook skeleton; §3 (Free Tier) and §20 (cost) are
  complete, the remaining 18 sections are marked pending per sprint.

Files modified:
- `src/agentic_chatbot/api/routers/health.py` — `_database_ready` now catches
  `(sqlite3.Error, psycopg.Error)`. Previously a Postgres outage escaped as a
  500 instead of a 503, breaking every container health check.
- `src/agentic_chatbot/postgres.py` — added the missing `from typing import Any`.
  `Any` was used in `run_outside_transaction`'s signature but never imported;
  it only "worked" because `from __future__ import annotations` made the
  annotation a string. A real latent bug that ruff's `F821` caught.
- `pyproject.toml` — added `ruff` to the dev group and a `[tool.ruff]` block:
  `line-length = 100`, `target-version = "py314"`, `select = ["E","F","I","B","UP"]`,
  plus documented per-file ignores (see below).
- `.env.example` — added `POSTGRES_PASSWORD` (compose only, not read by the app)
  and a commented `SYSTEM_PROMPT` (a `Settings` field that had no example entry).
- `frontend/.env.example` — documented `BACKEND_API_URL` for the compose network.
- `README.md` — added a pointer to the plan and runbook from `## Deploying`.
- `tests/test_api_health.py` — added `test_readiness_fails_on_a_postgres_error`.
- `tests/test_cli_commands.py`, `tests/test_cli_picker.py`, `tests/fakes.py`,
  `tests/test_cli_chat.py` — small lint fixes (`E731`, `F841`, `UP028`).
- `src/agentic_chatbot/{bm25_store,vector_store,pg_vector_store,migrate_to_postgres}.py`
  — explicit `strict=False` on `zip()` (behaviour unchanged).
- 71 auto-fixes across the tree from `ruff check --fix`: import ordering,
  unused imports, `datetime.timezone.utc` → `datetime.UTC`, deprecated typing imports.

**Deliberate lint exceptions** (each documented in `pyproject.toml`):
- `E501` in `inventory/validation.py`, `inventory/service.py`, `cli/commands.py`,
  `cli/console.py` — 39 pre-existing long lines in ERP business logic. Reformatting
  them would bury this sprint's real diff; they remain covered by tests.
- `B008` in `api/routers/**` — `file: UploadFile = File(...)` is FastAPI's
  required dependency-injection idiom, not a defect.
- one `# noqa: UP028` in `api/routers/chat.py` — `yield from` inside that `try`
  would hand `GeneratorExit` handling to the sub-generator and break the clean
  close-on-disconnect path.

**Decision taken during the sprint:** CI will gate on `ruff check` only, **not**
`ruff format --check`. `ruff format` would rewrite 84 of 139 files; a
whitespace-only sweep of that size is not something to slip into a hardening
sprint. Formatting can be adopted later as its own isolated commit.

**Verification performed:**
- `uv run ruff check src tests` → *All checks passed!*
- `uv run python -m compileall -q src/agentic_chatbot` → clean
- `uv run pytest -q` → **719 passed, 28 skipped** (was 718/28; the new
  regression test makes 719). The 28 skips are the Postgres-gated tests, which
  need `TEST_POSTGRES_DSN`.
- Runtime probe: a real `psycopg.OperationalError` now yields
  `_database_ready() -> False` instead of propagating.

**Still outstanding from this sprint — needs a decision from you:**
1. **Rotate the credentials in `.env`.** `OPENAI_API_KEY`, `LANGSMITH_API_KEY`,
   `JWT_SECRET_KEY`, and the `API_KEYS` values look live. The file is gitignored,
   but treat them as compromised before any cloud deployment.
2. **`LICENSE`.** There is none in the repo, which blocks publishing images to a
   public Docker Hub repository — which Decision D3 depends on.

---

## 1. Verified baseline (audited, not assumed)

| Area | Actual state | Deployment consequence |
|---|---|---|
| Backend entry | `main.py` → `create_app()` in `src/agentic_chatbot/api/main.py` | CMD = `uvicorn main:app` |
| Python | `requires-python >=3.14`, `.python-version` 3.14, `uv_build` | `python:3.14-slim`, `uv` only, **no `requirements.txt`** |
| Deps | `uv.lock` present, 23 runtime deps (`faiss-cpu`, `psycopg[binary]`, `langgraph-checkpoint-postgres`, `uvicorn[standard]`) | 2-stage `uv sync --frozen --no-dev` |
| Dead dep | `streamlit>=1.67.0` declared, **zero imports** | ~150 MB image bloat — separate approved change only |
| Frontend | Next.js **16.4.6**, React 19.3.0, App Router, pnpm **12.18.0** (`pnpm-lock.yaml`) | `node:22-slim` + corepack |
| Frontend arch | **BFF proxy**: browser → `/api/backend/*` → `BACKEND_API_URL`. CSP `connect-src 'self'`. **Zero `NEXT_PUBLIC_*` vars** | Only Next.js is exposed; backend/DB stay on the internal network |
| Frontend build | `output: 'standalone'` **not set**; `typescript.ignoreBuildErrors: true` | Add standalone; CI must run `pnpm typecheck` |
| Concurrency | **One uvicorn worker, hard requirement** (`API.md §14`): one shared `psycopg` connection + `RLock`, in-memory BM25, single-writer inventory JSON | No horizontal scaling — vertical sizing only |
| DB | PostgreSQL **18.7** (dev), pgvector **0.8.7**, `vector(1536)`, **HNSW** cosine, `POSTGRES_DSN` has **no default** | pgvector must be PG 18-class; `CREATE EXTENSION` is manual |
| Schema | No Alembic, no `.sql`. Idempotent `init_schema()` + `PostgresSaver.setup()` **at startup** | "Migrations" are startup DDL, all `IF NOT EXISTS`, non-destructive |
| Retrieval | BM25 = `rank_bm25` in memory; RRF in `rrf.py`; hybrid via `ThreadPoolExecutor(2)` | BM25 rebuilds on every start (first-query latency) |
| Checkpoints | `PostgresSaver` on the **shared** connection | Same DB, same volume |
| Uploads | `data/uploads/<subject>/<sha256[:16]><ext>` | **Named volume required** |
| Inventory | `inventory-data/inventory/inventory_data.json` (~512 KB) is **mutable runtime state** | **Volume**, never baked into the image; keep seed file for restore |
| Health | `/health` (liveness), `/health/ready` (db/graph/storage/config → 200/503) | Ready for container healthchecks |
| **Health bug** | `_database_ready` catches **only `sqlite3.Error`** (`routers/health.py:33-39`) but the call raises `psycopg.Error` | DB outage → **500 + traceback** instead of 503. Must fix |
| Tests | pytest 9.2, **668 tests / 52 files**, fully offline (SQLite in `tmp_path`, `FakeEmbeddings`, scripted LLM); 3 Postgres files skip without `TEST_POSTGRES_DSN` | CI needs no secrets |
| Linting | **No ruff/black/mypy/pre-commit config** anywhere. Frontend has ESLint 9 + `tsc --noEmit` + vitest | "Python linting" impossible until tooling is added |
| Docker / CI | `Dockerfile`, `docker-compose*`, `.dockerignore`, `.github/` — **all absent** | Everything net-new |
| Secrets | `.env` gitignored but holds **live-looking** `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, real 64-char `JWT_SECRET_KEY` | Rotate before any cloud deploy |
| Legal | **No `LICENSE`** | Blocks public Docker Hub distribution |

---

## 2. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Single EC2 host running all four containers** (Option A) | Postgres and backend are coupled by design (single connection, single worker); inventory/uploads are local state; RDS costs more than the compute it replaces. Option B documented as scale-up only |
| D2 | **Caddy on the host for TLS** | Let's Encrypt is free and automatic. **ACM certs cannot be attached to a standalone EC2 instance**; ALB ≈ $16–18/mo and NAT ≈ $32/mo are avoidable |
| D3 | **Two *public* Docker Hub repos** | Personal plan = unlimited public, only **1 private**; two private repos force Pro ($9/mo). Requires a `LICENSE` |
| D4 | **Immutable `sha-<short>` tags in production**; `latest` published but never used by the server | Rollback integrity |
| D5 | **GitHub OIDC → SSM `SendCommand`**, no SSH, no static AWS keys | Satisfies `aws.md §7/§8/§13`; SSM agent is pre-installed on AL2023; port 22 closed entirely |
| D6 | **SSM Parameter Store Standard `SecureString`**, not Secrets Manager | Std tier + `alias/aws/ssm` = $0; Secrets Manager is $0.40/secret/mo |
| D7 | **`t3.medium` (2 vCPU/4 GiB) realistic; `t3.small` (2 GiB) floor with swap.** **x86_64 first** | 4 GiB fits Postgres + FastAPI/LangChain/numpy/faiss + Next.js + Caddy. cp314 **aarch64** wheels for `faiss-cpu`/`psycopg[binary]` are unverified → ARM (`t4g`) only after a proven `linux/arm64` build |
| D8 | **Region chosen once** — `ap-south-1` recommended; all prices below are **us-east-1** | Latency from Dhaka/Kathmandu; verify in-region |
| D9 | **Three named volumes** — `pgdata`, `uploads`, `inventory`; `docs/` mounted read-only | Assets never live in images |
| D10 | **No destructive automation** — startup DDL is `IF NOT EXISTS`; `pg_dump` before every swap; no `image prune -a` | `aws.md §9/§15/§18` |

---

## 3. Free Tier and cost reality (verified Nov 2026)

### 3.1 What the account actually gets

- **Accounts created on/after 15 Jul 2025:** credit-based **Free plan** — $100 at sign-up + up to $100 for onboarding tasks = **≤ $200**, expiring **6 months** after account creation or when credits run out.
- **Older accounts:** legacy 12-month offers (750 h/mo `t2/t3.micro`, 750 h `db.t3.micro`, 5 GB S3, …).
- Free-plan-eligible instances are the **1 GiB** class (`t3.micro`, `t4g.micro`) — **not enough** for this stack. This app runs on **credits**, not a free instance.
- On Free-plan expiry: account **suspended**, data retained 90 days, then erased.
- **Public IPv4: $0.005/h = $3.65/mo, charged even under Free Tier.** A stopped instance with an Elastic IP keeps billing.
- **Docker Hub:** unauthenticated 100 pulls/6 h per IP; **Personal 200 pulls/6 h**; unlimited public repos, 1 private.

### 3.2 Service table

| Service | Purpose | Free Tier | Limits | Potential extra cost |
|---|---|---|---|---|
| EC2 `t3.medium` | App host | Only `.micro` is free-eligible; otherwise covered by credits | 750 h legacy / credits | $30.37/mo |
| EC2 `t3.small` | Minimum viable floor | same | same | $15.18/mo |
| EBS gp3 30 GB | OS + images + pgdata | Credits / legacy 30 GB | — | $2.40/mo |
| EBS snapshots | Weekly backup | Credits | — | ≈$1.50/mo |
| Public IPv4 | Reachable address | **No** | — | **$3.65/mo** |
| Elastic IP | Stable address | **No** | — | $3.65/mo (billed even detached) |
| SSM Session Manager / SendCommand | Deploy + shell | **Yes (always free)** | — | $0 |
| SSM Parameter Store Standard | Secrets | **Yes** (std ≤10k params) | — | $0 |
| Secrets Manager | *rejected* | No | — | $0.40/secret/mo |
| CloudWatch | Alarms, basic metrics | Limited always-free allotment | 10 alarms/metrics, 5 GB logs | Only if log ingestion enabled |
| Route 53 | DNS | No | — | $0.50/mo — **use registrar DNS** |
| ALB | *rejected* | No | — | ≈$16–18/mo + LCU |
| NAT Gateway | *rejected* | No | — | ≈$32/mo |
| ACM | *unsuitable* | — | — | Let's Encrypt, $0 |
| Docker Hub (public) | Registry | **Yes** | 200 pulls/6 h authenticated | $0 |
| OpenAI / LangSmith | App runtime | n/a | — | usage-based, unchanged |

### 3.3 Monthly estimate (us-east-1, 730 h, excl. OpenAI/LangSmith)

| Line | `t3.small` | `t3.medium` |
|---|---|---|
| EC2 compute | $15.18 | $30.37 |
| Public IPv4 | $3.65 | $3.65 |
| EBS gp3 30 GB | $2.40 | $2.40 |
| EBS snapshots | $1.50 | $1.50 |
| SSM / Parameter Store / Docker Hub / Let's Encrypt | $0 | $0 |
| **Total** | **≈ $22.73/mo** | **≈ $37.92/mo** |

**$200 of credits ≈ 5.3 months at the realistic tier** — deliberately inside the 6-month Free-plan window. **Never claim zero cost.** Both figures are credit-billed; after the Free plan ends you upgrade or lose the account.

**Only you can verify** (Console → Billing → Free Tier / Credits): account creation date and plan type, credits remaining + expiry, on-demand `t3.medium` quota in your region, and whether Elastic IP is available on your plan.

---

## 4. Target topology

```text
                      GitHub (main)
                           |
                  .github/workflows/ci.yml          lint, typecheck, 668 tests, docker build
                           |  on success
                  .github/workflows/deploy.yml
                           |
         Docker Hub (public)            AWS OIDC (no static keys)
   bayazid-ai-backend:sha-abc123               |
   bayazid-ai-frontend:sha-abc123        IAM role: ssm:SendCommand
                           \                  /
                            \                /
                        EC2 t3.medium (AL2023 + SSM agent)
                        /opt/bayazid/
                              |
                     Caddy :80/:443 (Let's Encrypt)
                              |
                      frontend :3000  (Next.js standalone + BFF)
                              |  http://backend:8000   [internal]
                      backend  :8000  (uvicorn, EXACTLY 1 worker)
                              |  postgresql://…@db:5432
                      db       :5432  (pgvector/pg18)  [internal]
                              |
              volumes: pgdata | uploads | inventory
```

**Published host ports: 443 and 80 only.** `8000` and `5432` exist solely on the compose network.

---

## 5. Files to create / modify

**Backend image & orchestration**
- create `/Dockerfile`, `/.dockerignore`, `/docker-compose.yml` (local dev), `/docker/postgres/init/01-extensions.sql`
- modify `/.env.example` (+`POSTGRES_PASSWORD`, +`SYSTEM_PROMPT` — currently a Settings field with no example), `/src/agentic_chatbot/api/routers/health.py` (catch `psycopg.Error`), `/pyproject.toml` (`[tool.ruff]`, dev group)

**Frontend image**
- create `/frontend/Dockerfile`, `/frontend/.dockerignore`
- modify `/frontend/next.config.ts` (`output: "standalone"`), `/frontend/.env.example`

**Production assets**
- create `/deploy/docker-compose.prod.yml`, `/deploy/Caddyfile`, `/deploy/render-env.sh`, `/deploy/deploy.sh`, `/deploy/rollback.sh`, `/deploy/backup.sh`, `/deploy/restore.sh`, `/deploy/systemd/bayazid.service`

**CI/CD**
- create `/.github/workflows/ci.yml`, `/.github/workflows/deploy.yml`, `/.github/workflows/rollback.yml`

**Docs**
- create `/AWS-DEPLOYMENT.md` (the 20-section guide)
- modify `/README.md` (replace the intent-only `## Deploying` with a link)

---

## 6. Sprints

Each sprint ends with a written report (files changed, commands, results, cost implication) and **stops for approval**. No sprint creates a billable resource without an explicit go-ahead.

### Sprint 0 — Baseline hardening (zero AWS, $0)
**Objective:** make the repo container/CI-ready and remove the defects that would break healthchecks or leak secrets.
**Create:** `.dockerignore`, `frontend/.dockerignore`, `AWS-DEPLOYMENT.md` skeleton.
**Modify:** `routers/health.py` (catch `psycopg.Error` → 503), `.env.example`, `frontend/.env.example`, `README.md` link, `pyproject.toml` (`[tool.ruff]`, line-length 100, py314, select `E,F,I,B,UP`).
**AWS:** none.
**Security:** **rotate `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, `JWT_SECRET_KEY`, `API_KEYS`** — live-looking values on disk. Decide on `LICENSE` (D3 depends on it).
**Cost:** $0.
**Risks:** adding ruff rewrites `uv.lock` — use `uv add --dev ruff` and commit the lock; touch no unrelated code.
**Validate:** `uv run ruff check src tests` clean (or an explicit documented ignore baseline); `compileall` clean; **668 tests still pass**; `/health/ready` returns **503 not 500** with the DB stopped.
**Output:** a repo that lints, tests, and reports readiness correctly.

### Sprint 1 — Backend image ($0)
**Objective:** a production backend image that runs the verified app.
**Create:** `/Dockerfile` (2-stage, `python:3.14-slim`, `uv sync --frozen --no-dev`, non-root uid 10001, `HEALTHCHECK` on `/health`), finish `/.dockerignore`.
**AWS:** none. **Config:** `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`; no secrets in ARG/ENV.
**Security:** non-root, no `.env` copied, no build-arg secrets.
**Risks — R1 (highest):** `faiss-cpu` / `psycopg[binary]` cp314 **aarch64** wheels. Gate: `buildx --platform linux/arm64` must succeed **before** any `t4g` choice; otherwise stay x86_64 and record why.
**Validate:** image < ~800 MB; with SQLite settings `/health` → 200; with a `pgvector/pg18` sibling `/health/ready` all-true; `docker history` leaks nothing; runs as uid 10001; startup survives `CREATE INDEX CONCURRENTLY`.
**Output:** `bayazid-ai-backend:dev` serving chat/stream/approvals/documents.

### Sprint 2 — Frontend image ($0)
**Objective:** lean Next.js standalone runtime talking to the backend over the compose network.
**Create:** `/frontend/Dockerfile` (3-stage deps→build→runtime, `node:22-slim`, corepack pnpm 12.18), `/frontend/.dockerignore`.
**Modify:** `next.config.ts` — add `output: "standalone"` only.
**Config:** `BACKEND_API_URL=http://backend:8000`, `SESSION_COOKIE_SECURE=true`, `NODE_ENV=production`, `HOSTNAME=0.0.0.0`, `PORT=3000`.
**Security:** non-root `nextjs`; **no `NEXT_PUBLIC_*`** (none exist — keep it that way); CSP stays `connect-src 'self'`.
**Risks:** `next/font/google` fetches **at build time** (needs egress); `ignoreBuildErrors` means `pnpm typecheck` in CI is the only type gate; confirm `standalone` works with `cacheComponents` + `partialPrefetching`.
**Validate:** image < ~350 MB; `/login` → 200 **with no backend running**; with the backend up: login → threads → streamed chat → approval → upload all work through the BFF; SSE not buffered.
**Output:** `bayazid-ai-frontend:dev`.

### Sprint 3 — Local full-stack compose ($0) — the rehearsal
**Objective:** the exact production topology locally, so Sprint 7 has nothing new to discover.
**Create:** `/docker-compose.yml`, `/docker/postgres/init/01-extensions.sql` (`CREATE EXTENSION IF NOT EXISTS vector;`).
**Modify:** `.env.example`.
**Config:** `DATABASE_BACKEND=postgres`, `POSTGRES_DSN=postgresql://bayazid:${POSTGRES_PASSWORD}@db:5432/bayazid`, `POSTGRES_INITDB_ARGS=--data-checksums`.
**Security:** pin the pgvector image per minor version (never `:latest`); **do not publish 5432**.
**Risks — R2:** image's bundled `vector` must be ≥0.8 and PG 18-compatible (dev = 0.8.7/18.7) — assert `SELECT extversion …` and prove the HNSW index with `SET enable_seqscan=off`. **R3:** named-volume permissions vs uid 10001. **R4:** first-query latency while BM25 rebuilds.
**Validate:** hybrid search returns fused RRF results with **both** retrievers healthy; upload → chunk → embed → HNSW search works; `down`/`up` preserves threads, documents, embeddings, checkpoints, uploads **and** inventory mutations; `docker compose config` shows only 80/443.
**Output:** one-command production replica + the dockerized-DB compatibility evidence `aws.md §9` requires.

### Sprint 4 — CI workflow ($0)
**Objective:** every PR gated; `main` always deployable.
**Create:** `/.github/workflows/ci.yml`.
**Jobs:** (1) **backend** — `uv sync --frozen`, `ruff check`, `ruff format --check`, `compileall`, `pytest -q`; (2) **backend-postgres** — `pgvector/pgvector:pg18` service, `TEST_POSTGRES_DSN=… pytest tests/test_storage_parity.py tests/test_postgres_container.py tests/test_pg_vector_store.py`; (3) **frontend** — `pnpm install --frozen-lockfile`, `lint`, `typecheck`, `test`, `build`; (4) **docker** — `buildx` no-push build of both images.
**Config:** `astral-sh/setup-uv` with lockfile cache; `pnpm/action-setup` + `actions/setup-node` pnpm cache; `concurrency` groups; path filters.
**Security:** **no secrets in the PR path**; `permissions: contents: read`; pin third-party actions (SHA-pin `docker/*`).
**Cost:** $0 on a public repo; private repo draws the 2,000 min/mo allotment.
**Risks:** Google Fonts egress at build (R5); 668 tests + Next build per PR is slow → concurrency + path filters.
**Validate:** break a test and a lint rule → red; PR → green; no secret echoed in logs.
**Output:** red/green on every push.

### Sprint 5 — Publish to Docker Hub ($0)
**Objective:** immutable SHA-tagged images from `main` only.
**Create:** build/push job in `deploy.yml` (or a dedicated `publish.yml`).
**Docker Hub:** create `bayazid-ai-backend` and `bayazid-ai-frontend` (**public**, D3).
**Config:** secrets `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` (**access token with Read/Write — never the account password**); `docker/login-action` via `password-stdin`; `docker/metadata-action` → `sha-<short>` + `latest`.
**Security:** guard the push step with `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` so **fork PRs can never publish**; never echo the token.
**Risks:** 200 pulls/6 h is a non-issue for a build-only pipeline; buildx `type=gha` cache keeps rebuilds cheap.
**Validate:** push to `main` → both images carry a tag matching `git rev-parse --short HEAD`; a PR publishes nothing.
**Output:** a registry the server can pull from.

### Sprint 6 — AWS foundation (billable — **approval gate**)
**Objective:** a hardened host reachable only via SSM + 80/443.
**Create (documented steps in `AWS-DEPLOYMENT.md`, not IaC):** IAM OIDC provider for `token.actions.githubusercontent.com`; deploy role trusting `repo:<owner>/<repo>:environment:production` with only `ssm:SendCommand` / `ssm:GetCommandInvocation` on that instance+document; instance profile (`AmazonSSMManagedInstanceCore` + `ssm:GetParametersByPath` on `/bayazid/*` + `kms:Decrypt` on `alias/aws/ssm`); Parameter Store tree `/bayazid/prod/*`; SG (inbound 80/443 from `0.0.0.0/0`, **no 22**, all egress); `t3.medium` AL2023, 30 GB gp3, Elastic IP; `user_data` installing Docker + compose plugin and creating `bayazid`.
**AWS resources:** EC2, EBS, EIP, SG, IAM role/profile/OIDC, SSM parameters.
**Security:** no key pairs; SSH off; **IMDSv2 required** (`HttpTokens=required`); EBS encrypted; least-privilege SG; 5432 never opened.
**Cost:** **≈ $37.92/mo at `t3.medium`** (§3.3). **Crosses the spend line — do not execute without explicit approval.**
**Risks — R6:** Free plan may restrict Elastic IP → fallback is auto-IP + a DNS updater, or accept an IP change on stop/start. **R7:** region price/quota differences. **R8:** `t3` CPU-credit throttling during embedding bursts.
**Validate:** SSM `SendCommand` exits 0; `curl -I https://$DOMAIN` fails *before* deploy but the SG is right; 22 is closed from the internet; `docker --version` and `docker compose version` via Session Manager.
**Output:** an empty hardened host awaiting images.

### Sprint 7 — Automated deployment ($0 additional)
**Objective:** `git push main` → live, health-verified, auto-rolling-back.
**Create:** `/deploy/docker-compose.prod.yml` (images by `${IMAGE_TAG}`, `restart: unless-stopped`, json-file logging 10m×3, 3 named volumes, `mem_limit`, healthchecks, `depends_on: service_healthy`), `/deploy/Caddyfile`, `/deploy/render-env.sh`, `/deploy/deploy.sh`, `/deploy/rollback.sh`, `/deploy/systemd/bayazid.service`, `/.github/workflows/deploy.yml` (OIDC + SSM), `/.github/workflows/rollback.yml` (`workflow_dispatch` + tag input).
**Config:** GitHub `Environment: production` with required reviewer; secrets `AWS_ROLE_ARN`, `EC2_INSTANCE_ID`; `DOMAIN` as a **variable**, not a secret.
**Security:** `id-token: write` scoped to the deploy job only; zero static AWS keys; `.env` at `0600`; deploy user outside the `docker` group (compose via `sudo`/systemd).
**Risks — R9:** "zero downtime" is unrealistic with one worker and one host — expect a few seconds of 502; mitigate with Caddy retries + health-gated swap and **say so in the docs**. **R10:** `CREATE INDEX CONCURRENTLY` at startup racing a `pg_dump`. **R11:** a corrupted `previous_tag` state file.
**`deploy.sh` sequence:** read target SHA → `render-env.sh` → `compose pull` → **`backup.sh` (abort on failure)** → write `state/previous_tag` → `compose up -d --remove-orphans` → poll `/health` then `/health/ready` for 120 s → on failure `rollback.sh` and exit 1 → on success retain the last 3 images.
**Validate:** green path works; a deliberately broken image **auto-rolls back** and the site stays up; GitHub UI approve-and-push works; `/health/ready` all-true after deploy; a document uploaded before deploy is still downloadable after.
**Output:** push-to-deploy with a rollback that has actually been exercised.

### Sprint 8 — Backup, monitoring, runbook, cost review
**Objective:** operable by someone who didn't build it.
**Create:** `/deploy/backup.sh`, `/deploy/restore.sh`, host cron entries, CloudWatch alarms (CPU >80% for 15 min, status-check-failed → SNS email), the final `AWS-DEPLOYMENT.md` sections.
**Modify:** `/README.md`.
**AWS resources:** SNS topic + email subscription; optional EBS Data Lifecycle Manager weekly snapshots.
**Config:** 7 daily + 4 weekly retention; **never auto-delete the newest**; images retained 3.
**Security:** backup dir `0700`; dumps never leave the host unencrypted; restore requires `--confirm`.
**Cost:** snapshots ≈$1.50/mo; alarms within free allotment; **skip CloudWatch Logs ingestion** — use json-file rotation + `docker compose logs`.
**Risks — R12:** an untested restore is not a backup → **perform a real restore in this sprint**. **R13:** disk fill from images + dumps → 80% alarm.
**Validate:** `restore.sh --confirm` rebuilds a working DB into a scratch container; dumps age out at the retention boundary; killing the backend container raises an alert within 15 min; `docker compose logs backend --tail 50` is the documented first diagnostic.
**Output:** complete `AWS-DEPLOYMENT.md` (all 20 sections of `aws.md §16`) + a rehearsed restore.

---

## 7. Risk register

| # | Risk | Sprint | Mitigation |
|---|---|---|---|
| R1 | cp314 **aarch64** wheels missing for `faiss-cpu`/`psycopg[binary]` | 1 | `buildx --platform linux/arm64` gate; fall back to x86_64 `t3` |
| R2 | pgvector image ≠ dev 0.8.7 / PG 18 | 3 | Pin tag, assert `extversion`, prove HNSW with `enable_seqscan=off` |
| R3 | Volume permissions vs uid 10001 | 3 | Explicit `user:`/`chown`; test on a fresh volume |
| R4 | First-query latency while BM25 rebuilds | 3, 7 | Warm via `/health/ready` + a post-deploy smoke query |
| R5 | Build-time Google Fonts egress | 2, 4 | Allow egress in CI; fonts cached in the layer |
| R6 | Free plan may restrict Elastic IP | 6 | Auto-IP + DNS updater fallback; document the trade-off |
| R7 | `streamlit` dead dependency bloats the image | 1 | Optional removal as a **separate approved change** |
| R8 | `t3` CPU-credit throttling on embedding bursts | 6 | Alarm on `CPUCreditBalance`; move to `t4g`/unlimited |
| R9 | Seconds of 502 during recreate | 7 | Caddy retries + health-gated swap; state it plainly |
| R10 | `CREATE INDEX CONCURRENTLY` vs concurrent `pg_dump` | 7 | Back up **before** recreate, never in parallel with startup |
| R11 | Broken rollback state file | 7 | Write `previous_tag` before swap; prove it by forcing a failure |
| R12 | Untested restore | 8 | Mandatory restore rehearsal |
| R13 | Disk fill (images + dumps) | 8 | 3-image / 7+4-dump retention; 80% disk alarm |
| R14 | Free-plan expiry suspends the account | — | Reminder at month 5; export data; decide upgrade |

---

## 8. Inputs needed before Sprint 6

1. **Domain name** — or "IP only for now", which forces HTTP-only until DNS exists.
2. **Region confirmation** — `ap-south-1` assumed; §3.3 prices are us-east-1.
3. **Public Docker Hub repos accepted?** — private repos need Pro ($9/mo) and make `LICENSE` optional.
4. **Account date** — pre- or post-15 Jul 2025 (legacy 12-month offers vs credit-based Free plan).

---

## 9. Definition of done

- `docker compose up` reproduces production locally, and `down`/`up` loses no threads, documents, embeddings, checkpoints, uploads, or inventory mutations.
- A failing test or lint rule turns CI red; a green `main` push publishes two SHA-tagged public images.
- `https://$DOMAIN` serves a valid Let's Encrypt certificate; **ports 22, 8000 and 5432 are unreachable from the internet**.
- `/health` 200 and `/health/ready` all-true; readiness returns **503, not 500**, when Postgres is down.
- A forced bad deploy restores the previous tag automatically and the site stays up.
- `restore.sh --confirm` rebuilds a working database from the latest dump.
- `AWS-DEPLOYMENT.md` answers all 20 items of `aws.md §16` and states monthly cost with caveats — never "free".
