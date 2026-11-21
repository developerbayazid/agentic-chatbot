# AWS Deployment Runbook — BAYAZID AI

Operational guide for running this application on AWS at the lowest practical
cost. This document is built up sprint by sprint; sections marked **pending**
are filled in when the sprint that produces their artefacts completes.

The plan itself, with the full audit, cost tables, decisions, and risk register,
is [`aws-deployment-ci-cd-plan.md`](./aws-deployment-ci-cd-plan.md).

> **Nothing here is free.** The AWS Free plan for accounts created on or after
> 15 July 2025 is a **credit-based** plan ($100 + up to $100, expiring after six
> months). This stack needs 2–4 GiB of RAM, which is above the free-eligible
> 1 GiB instance class, so it runs on credits and then on real money. The
> realistic figure is **≈ $38/month**; see
> [§ Cost](#20-estimated-monthly-cost).

---

## Contents

| § | Section | State |
|---|---|---|
| 1 | [Architecture](#1-architecture) | pending (Sprint 3, 6) |
| 2 | [AWS account prerequisites](#2-aws-account-prerequisites) | pending (Sprint 6) |
| 3 | [Free Tier eligibility](#3-free-tier-eligibility) | **done** |
| 4 | [Docker setup](#4-docker-setup) | pending (Sprint 1–3) |
| 5 | [Docker Hub repositories](#5-docker-hub-repositories) | pending (Sprint 5) |
| 6 | [GitHub secrets and variables](#6-github-secrets-and-variables) | pending (Sprint 5, 7) |
| 7 | [GitHub OIDC configuration](#7-github-oidc-configuration) | pending (Sprint 6) |
| 8 | [IAM policy](#8-iam-policy) | pending (Sprint 6) |
| 9 | [EC2 setup](#9-ec2-setup) | pending (Sprint 6) |
| 10 | [Docker Compose configuration](#10-docker-compose-configuration) | pending (Sprint 3, 7) |
| 11 | [PostgreSQL + pgvector](#11-postgresql--pgvector) | pending (Sprint 3) |
| 12 | [Environment variables](#12-environment-variables) | pending (Sprint 7) |
| 13 | [Initial deployment](#13-initial-deployment) | pending (Sprint 7) |
| 14 | [Automated deployments](#14-automated-deployments) | pending (Sprint 7) |
| 15 | [Database backup](#15-database-backup) | pending (Sprint 8) |
| 16 | [Database restore](#16-database-restore) | pending (Sprint 8) |
| 17 | [Rollback](#17-rollback) | pending (Sprint 7–8) |
| 18 | [Monitoring](#18-monitoring) | pending (Sprint 8) |
| 19 | [Troubleshooting](#19-troubleshooting) | pending (Sprint 8) |
| 20 | [Estimated monthly cost](#20-estimated-monthly-cost) | **done** |

---

## 1. Architecture

*Pending — produced by Sprints 3 (local replica) and 6 (AWS resources).*

The target shape, in short: one EC2 host running four containers (Caddy →
Next.js → FastAPI → PostgreSQL/pgvector) behind a single TLS entrypoint. Only
ports 443 and 80 are reachable from the internet; the backend and database live
on the compose network only.

---

## 2. AWS account prerequisites

*Pending — Sprint 6.*

---

## 3. Free Tier eligibility

Verified November 2026 against the AWS Free Tier FAQ and public pricing pages.
Re-check before spending anything.

### Which plan the account is on

| Account created | What you get |
| --- | --- |
| **On or after 15 July 2025** | Credit-based **Free plan**: $100 at sign-up, plus up to $100 for onboarding activities. Credits expire **6 months** after account creation, or when spent — whichever comes first. |
| **Before 15 July 2025** | The legacy 12-month offers: 750 h/month of `t2`/`t3.micro`, 750 h of `db.t3.micro`, 5 GB S3, and the always-free services. |

Either way, the Free plan is **not** a permanent free tier. When it expires the
account is suspended, data is kept for 90 days, and is then deleted.

### The instance-size problem

Free-plan-eligible instance types are the **1 GiB** class (`t3.micro`,
`t4g.micro`). This application needs more than that:

| Component | Approx. resident memory |
| --- | --- |
| PostgreSQL + pgvector | ~250–400 MB |
| FastAPI + LangChain + numpy + faiss | ~500 MB – 1 GB peak |
| Next.js standalone runtime | ~150–250 MB |
| Caddy | ~20 MB |

That is why the plan targets `t3.small` (2 GiB, the floor, with swap) or
`t3.medium` (4 GiB, the realistic default).

### Charges that apply even on the Free plan

- **Public IPv4: $0.005 per hour, ≈ $3.65 per month**, whether the address is in
  use or idle. This is billed even while the Free plan is active.
- An **Elastic IP** that is allocated but not attached keeps billing. Release it
  when you are finished.
- **EBS storage and snapshots** beyond any allowance, and **data transfer out**
  beyond the monthly allowance.

### What you must confirm yourself

These are account-specific and cannot be verified from the repository:

1. Account creation date and whether the plan is **Free** or **Paid**
   (Console → Settings → Billing).
2. Credits remaining and their expiry date (Console → Billing → Credits, or the
   `GetAccountPlanState` API).
3. On-demand instance quota for `t3.small`/`t3.medium` in the chosen region
   (Service Quotas → Amazon EC2).
4. Whether Elastic IP allocation is permitted on your plan.

### Services this plan uses

| Service | Purpose | Cost |
| --- | --- | --- |
| EC2 (`t3.small`/`t3.medium`) | Application host | $15–30/month |
| EBS gp3, 30 GB | OS, images, database volume | $2.40/month |
| EBS snapshots | Weekly backup | ≈ $1.50/month |
| Public IPv4 | Reachability | $3.65/month |
| SSM Session Manager / `SendCommand` | Deployment and shell | always free |
| SSM Parameter Store (Standard) | Secrets | always free |
| CloudWatch alarms | Availability and CPU | within the free allotment |
| Docker Hub (public repos) | Image registry | free |
| Let's Encrypt via Caddy | TLS certificates | free |

**Deliberately not used**, because the cost is not justified at this size:
Application Load Balancer (≈ $16–18/month plus LCUs), NAT Gateway (≈ $32/month),
Route 53 hosted zone ($0.50/month — use the registrar's DNS), Secrets Manager
($0.40/secret/month — Parameter Store is free), and Amazon ECR.

> ACM certificates cannot be attached to a standalone EC2 instance; they deploy
> only to ALB, CloudFront, or API Gateway. That is why TLS is handled by Caddy
> and Let's Encrypt.

---

## 4. Docker setup

*Pending — Sprints 1–3.*

---

## 5. Docker Hub repositories

*Pending — Sprint 5.*

---

## 6. GitHub secrets and variables

*Pending — Sprints 5 and 7.*

---

## 7. GitHub OIDC configuration

*Pending — Sprint 6.*

---

## 8. IAM policy

*Pending — Sprint 6.*

---

## 9. EC2 setup

*Pending — Sprint 6.*

---

## 10. Docker Compose configuration

*Pending — Sprints 3 and 7.*

---

## 11. PostgreSQL + pgvector

*Pending — Sprint 3.*

The existing logical design is preserved unchanged: PostgreSQL 18 with the
`vector` extension, 1536-dimension embeddings, an HNSW cosine index, and
LangGraph checkpoints in the same database. See [`POSTGRES.md`](./POSTGRES.md)
for the background.

---

## 12. Environment variables

*Pending — Sprint 7.*

The application reads its configuration from `.env` in the working directory.
[`.env.example`](./.env.example) is the authoritative list.

---

## 13. Initial deployment

*Pending — Sprint 7.*

---

## 14. Automated deployments

*Pending — Sprint 7.*

---

## 15. Database backup

*Pending — Sprint 8.*

---

## 16. Database restore

*Pending — Sprint 8.*

---

## 17. Rollback

*Pending — Sprints 7 and 8.*

---

## 18. Monitoring

*Pending — Sprint 8.*

---

## 19. Troubleshooting

*Pending — Sprint 8.*

---

## 20. Estimated monthly cost

Figures are **us-east-1, on-demand, 730 hours**, and exclude OpenAI and
LangSmith usage. Verify in your own region — prices differ.

| Line item | `t3.small` (2 GiB) | `t3.medium` (4 GiB) |
| --- | --- | --- |
| EC2 compute | $15.18 | $30.37 |
| Public IPv4 | $3.65 | $3.65 |
| EBS gp3, 30 GB | $2.40 | $2.40 |
| EBS snapshots | $1.50 | $1.50 |
| SSM, Parameter Store, Docker Hub, Let's Encrypt | $0.00 | $0.00 |
| **Total** | **≈ $22.73 / month** | **≈ $37.92 / month** |

**$200 of Free-plan credits covers roughly 5.3 months at the `t3.medium` level** —
which is why the plan keeps the default there and treats `t3.small` as a
fallback: the credits run out at about the same time the plan expires.

### Warnings

- **Never describe this as free.** Both figures are billed, first against
  credits and then against your card.
- When the Free plan ends, the account is **suspended** unless upgraded. Data is
  retained for 90 days, then permanently erased.
- The largest avoidable charges are an idle Elastic IP ($3.65/month), a load
  balancer (≈ $16–18/month), a NAT Gateway (≈ $32/month), and CloudWatch Logs
  ingestion. The plan avoids all four.
- Set a billing alarm before creating any resource. On a Paid plan, a monthly
  spend limit with early cost controls is available.
