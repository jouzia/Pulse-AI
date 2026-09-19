# Pulse AI

### Event-Driven Notification Infrastructure

Pulse is an event-driven notification infrastructure service built with
FastAPI, PostgreSQL, Redis, and Celery. It accepts application events
through an authenticated REST API, persists them with database-backed
idempotency, and delivers notifications asynchronously across multiple
channels — with configurable retry/backoff, lease-based worker crash
recovery, atomic Redis rate limiting, dead-letter handling, and
Prometheus-compatible observability, all backed by an operations
dashboard for inspecting the system while it runs.

> **This has not been runtime-verified.** Every line of backend and
> frontend code here was written and statically reviewed in a sandboxed
> environment with no network access and no Postgres, Redis, or Docker
> available — not even `pytest` or `npm install` have been run. Several
> real bugs were found and fixed by re-reading the code, not by
> executing it (see [Known Limitations](#known-limitations) and
> [Testing](#testing)). A GitHub Actions workflow
> (`.github/workflows/ci.yml`) exists specifically so the first real
> execution of this test suite happens automatically, with actual
> Postgres/Redis service containers, the moment this is pushed. Read
> this whole warning before trusting anything below it.

---

## Table of contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core guarantees](#core-guarantees)
4. [Event lifecycle](#event-lifecycle)
5. [Job lifecycle](#job-lifecycle)
6. [Reliability model](#reliability-model)
7. [Rate limiting](#rate-limiting)
8. [Observability](#observability)
9. [Operations dashboard](#operations-dashboard)
10. [API](#api)
11. [Local development](#local-development)
12. [Testing](#testing)
13. [Failure scenarios](#failure-scenarios)
14. [Known limitations](#known-limitations)
15. [Engineering tradeoffs](#engineering-tradeoffs)
16. [Project structure](#project-structure)
17. [Roadmap / future work](#roadmap--future-work)

---

## Overview

Most CRUD demo projects hide the hard part of backend engineering: what
happens when a downstream call fails, twice, under concurrent load.
Pulse makes that the subject of the project rather than an afterthought.
An event comes in once; notifications go out through email, SMS, and
push; failures retry on a documented backoff schedule; permanent
failures land in a dead-letter queue an operator can inspect and retry;
a crashed worker's in-flight work gets reclaimed automatically; and the
whole thing is observable — via Prometheus-compatible metrics, structured
logs, and a dedicated dashboard — without needing to read the source to
understand what's happening.

## Architecture

```text
Client
  |
  v
FastAPI (Events API, auth, validation)
  |
  v
PostgreSQL (events, notification_jobs, deliveries, dead_letter_jobs)
  |
  |  post-commit dispatch
  v
Redis + Celery broker
  |
  +--------------+--------------+
  v              v              v
Email worker   SMS worker    Push worker
  |              |              |
  +--------------+--------------+
                 v
          Provider abstraction
                 |
                 v
     Delivery state + event aggregation
                 |
                 v
   Prometheus metrics + operations dashboard
```

Full diagrams, sequencing, and the reasoning behind each arrow:
[`docs/architecture.md`](docs/architecture.md).

**Stack**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async),
PostgreSQL, Redis, Celery (backend) · Next.js, TypeScript, React,
Tailwind CSS (dashboard) · Docker Compose (local infra).

## Core guarantees

- **Idempotency** — enforced by database unique constraints
  (`events.event_id`, `(event_id, channel)` on `notification_jobs`), not
  application-level checks alone, plus `SELECT ... FOR UPDATE SKIP LOCKED`
  job claiming so duplicate Celery task delivery never produces two
  logical deliveries.
- **At-least-once processing, not exactly-once** — stated precisely
  throughout this project, never oversold. See
  [Reliability model](#reliability-model).
- **Retries** — configurable exponential backoff with jitter, defined
  once in `app/core/retry_policy.py`, driving actual Celery re-enqueue
  delays, not a second disconnected mechanism.
- **Dead-letter handling** — jobs that exhaust `max_attempts` are
  traceable in `dead_letter_jobs` and retryable through an explicit,
  authenticated operation.
- **Delivery tracking** — every provider attempt is its own row in
  `notification_deliveries`.
- **Crash recovery** — a lease (`claimed_at`/`lease_expires_at`) plus a
  periodic sweep reclaims jobs left behind by a worker that died
  mid-processing.
- **Event aggregation** — an event's status reflects all of its jobs'
  outcomes; one dead-lettered channel marks the event `FAILED` even if
  siblings delivered.
- **Rate limiting** — Redis token bucket per channel, atomic via a Lua
  script, fails open on Redis unavailability (a documented tradeoff, not
  an oversight).
- **Observability** — Prometheus-compatible `/metrics` with
  bounded-cardinality labels, structured JSON logs, and a JSON dashboard
  summary endpoint reading the same underlying counters.

## Event lifecycle

```text
RECEIVED -> VALIDATED -> QUEUED -> PROCESSING -> DELIVERED
                                       |
                                       v
                                    FAILED -> DEAD_LETTERED
```

An event's status is an aggregate of its jobs' statuses, recomputed
after every job outcome (`app/workers/event_aggregation.py`): all jobs
`DELIVERED` -> event `DELIVERED`; any job `DEAD_LETTERED` -> event
`FAILED`; all still `QUEUED` -> event `QUEUED`; anything else in progress
-> event `PROCESSING`. See
[`docs/architecture.md`](docs/architecture.md#event-level-aggregation-partial-success)
for why this deliberately isn't modeled as a strict one-way state
machine the way the job lifecycle below is.

## Job lifecycle

```text
PENDING -> QUEUED -> PROCESSING -> DELIVERED
                          |
                          v
                       FAILED -> RETRYING -> QUEUED (loop)
                          |
                          v
                    DEAD_LETTERED
```

Enforced by an explicit transition table (`app/core/states.py`) — an
illegal transition raises `InvalidStateTransition` immediately rather
than silently writing an inconsistent state.

## Reliability model

- **Retry**: `RetryPolicy` (`app/core/retry_policy.py`) is the single
  source of truth for backoff — base delay, multiplier, max attempts,
  jitter, per channel. Celery's `countdown` parameter is populated
  directly from `policy.delay_for_attempt()`; there is no second,
  hardcoded retry schedule anywhere in the worker.
- **Crash recovery**: a lease, not a distributed lock. Claiming a job
  sets a 5-minute lease; a Celery Beat sweep every 30 seconds resets any
  job still `PROCESSING` past its lease back to `QUEUED`, and separately
  republishes `QUEUED` jobs that were committed to Postgres but never
  successfully published to Celery (the documented post-commit-enqueue
  failure window — see [Failure scenarios](#failure-scenarios)).
- **Concurrency**: `SELECT ... FOR UPDATE SKIP LOCKED` filtered to
  `status IN (QUEUED, RETRYING)`. Two concurrent claims of the same job
  resolve safely either because one wins the row lock and the other's
  `SKIP LOCKED` query returns nothing, or because the winner has already
  moved the row out of the claimable status set by the time the loser's
  query runs.
- **Delivery semantics**: **at-least-once, not exactly-once.** A task can
  be delivered more than once (Celery redelivery, or the recovery sweep
  republishing something already in flight). Correctness therefore comes
  from the database — the claim query's status filter and the outcome
  recorder's `status == PROCESSING` re-check — not from trusting a
  message is delivered exactly once.

## Rate limiting

Redis-backed token bucket, one bucket per channel
(`app/core/rate_limiter.py`), atomic via a single Lua script (`EVAL`) so
the read-refill-write cycle can't race across concurrent API/worker
processes. Chosen over a fixed window specifically to avoid the
"up to 2x the limit in a burst straddling a window boundary" problem a
naive counter-reset design has.

**Semantics**: one token = one job's provider-send attempt. Limits are
global per channel (`RATE_LIMIT_EMAIL_PER_MINUTE` etc.), not per-tenant —
Pulse has one API key today, so a tenant dimension would be unused
complexity. Checked *before* any database transaction opens (the
channel is passed as an explicit Celery task argument specifically to
make this possible). A denied job is **not** treated as a provider
failure: no attempt consumed, no delivery record, no `RetryPolicy`
involvement — the same task is rescheduled after a short fixed delay.

**Redis failure policy: fail open.** If Redis is unreachable, the
limiter allows the request rather than blocking all delivery on its own
availability. See [Engineering tradeoffs](#engineering-tradeoffs) for
why.

## Observability

`/metrics` (Prometheus text format) exposes counters for events
received, jobs processed/delivered/failed/dead-lettered/retried, and
rate-limit denials, plus histograms for provider-call duration and
end-to-end delivery latency — every one incremented at the exact point
the underlying event happens, never backfilled or estimated. The one
gauge, queue depth, is computed by a live database query at scrape time,
not maintained incrementally (which could drift after a crash-recovery
requeue).

`GET /api/v1/ops/overview` exposes the same underlying counters as JSON
for the dashboard, via `app/core/metrics.py::sum_counter()` — reading
the actual `Counter`/`Gauge` objects' current values through
`prometheus_client`'s public `.collect()` API, not a second,
independently-incremented count.

**Label cardinality** is deliberately bounded to `channel` (3 values),
`provider`, and `event_type` — never `event_id`/`job_id`/recipient,
which would make every metric series effectively unique per request.

Structured logs (`structlog`, JSON) carry `job_id`, `event_id`,
`channel`, `attempt`, `provider`, `status`, `duration_ms`, `error` — and
never an API key, credential, or full notification payload.

## Operations dashboard

A Next.js console in `frontend/` for inspecting and operating the
system — not the product, a window into it.

- **Overview** (`/`) — event/job counts by status, per-channel job
  breakdown, configured rate limits and current denial counts.
- **Events** (`/events`) — paginated, filterable (status, event type)
  event list.
- **Event detail** (`/events/[eventId]`) — the event's actual persisted
  lifecycle, its jobs, and each job's full delivery-attempt history on
  demand.
- **Dead letter** (`/dead-letter`) — paginated DLQ list with a **Retry**
  action calling `POST /api/v1/dead-letter/{id}/retry` — a deliberate,
  authenticated backend operation; the dashboard never mutates job state
  directly.
- **Observability** (`/observability`) — the same Prometheus counters
  `/metrics` exposes, as a current snapshot. No time-series chart: Pulse
  stores no historical metric data, and fabricating one would violate
  this project's honesty policy.

**Authentication boundary**: Pulse has a single static API key, no
per-user identity. The dashboard's Next.js server holds `PULSE_API_KEY`
(server-only env var, never `NEXT_PUBLIC_`) and attaches it when
proxying browser requests to the backend
(`frontend/app/api/proxy/[...path]/route.ts`) — the browser itself never
sees the key. This is an honest boundary for a single-operator internal
tool, not a multi-user auth system.

**Refresh strategy**: polling every 15 seconds, not WebSockets — the
backend's own data sources (Prometheus counters, database aggregates)
are already pull-based, so pushing updates would mean standing up an
unnecessary second distributed subsystem to broadcast data that's only
ever computed on demand.

**Every view distinguishes** loading / empty (backend reached, zero
rows) / unavailable (backend unreachable) / error (backend responded
with a 4xx/5xx) — never collapsed into a default value. See
`frontend/lib/api.ts`'s `ApiResult` type.

## API

All endpoints below require `X-API-Key: <key>` except `/health`,
`/ready`, and `/metrics`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/events` | Create an event + one job per channel, transactionally. Duplicate `event_id` returns `409`. |
| `GET` | `/api/v1/events` | Paginated, filterable (`status`, `event_type`) event list. |
| `GET` | `/api/v1/events/{event_id}` | Event detail with per-channel job summaries. |
| `GET` | `/api/v1/jobs/{job_id}` | Full job detail including delivery-attempt history. |
| `GET` | `/api/v1/dead-letter` | Paginated dead-letter list. |
| `POST` | `/api/v1/dead-letter/{id}/retry` | Resets a dead-lettered job to `QUEUED` with a fresh attempt budget and re-enqueues it. |
| `GET` | `/api/v1/ops/overview` | JSON dashboard summary — event/job counts, dead-letter count, rate-limit config and denial counts. |
| `GET` | `/metrics` | Prometheus text-format scrape endpoint. |
| `GET` | `/health` | Liveness only — no dependency checks. |
| `GET` | `/ready` | Readiness — checks Postgres and Redis. |

```bash
curl -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" -H "X-API-Key: $PULSE_API_KEY" \
  -d '{
    "event_id": "evt_01HXYZ",
    "event_type": "payment.succeeded",
    "recipient": "user@example.com",
    "channels": ["email", "push"],
    "data": {"amount": 1499, "currency": "INR", "transaction_id": "txn_123"}
  }'
# -> 201, one notification_job per channel, all QUEUED

curl http://localhost:8000/api/v1/events/evt_01HXYZ -H "X-API-Key: $PULSE_API_KEY"
# jobs[].status -> "delivered" once a worker has processed it

# Submitting the same event_id again returns 409, not a duplicate row:
curl -i -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" -H "X-API-Key: $PULSE_API_KEY" \
  -d '{"event_id": "evt_01HXYZ", "event_type": "payment.succeeded", "recipient": "user@example.com", "channels": ["email"], "data": {}}'
# -> 409 {"error": {"code": "EVENT_ALREADY_EXISTS", "message": "..."}}
```

Full request/response schemas: `/docs` (FastAPI's generated OpenAPI UI)
once the API is running.

## Local development

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local   # fill in a real key
docker compose up --build
alembic upgrade head    # inside the api container, or against DATABASE_URL locally
```

Brings up Postgres, Redis, the FastAPI API, a Celery worker consuming
`notifications.email` / `.sms` / `.push` / `.default`, Celery Beat (the
crash-recovery sweep), and the dashboard on `:3000`.

```bash
docker compose logs -f worker   # structured JSON logs per job attempt
```

**Environment variables** (`.env.example` documents every one, with
placeholders, no real secrets): `API_KEY`, `DATABASE_URL`, `REDIS_URL`,
`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`,
`RATE_LIMIT_{EMAIL,SMS,PUSH}_PER_MINUTE`, `LOG_LEVEL`. Frontend:
`PULSE_API_URL`, `PULSE_API_KEY` (server-only — see
[Operations dashboard](#operations-dashboard)).

## Testing

```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://pulse:pulse@localhost:5432/pulse_test
export REDIS_URL=redis://localhost:6379/0
export API_KEY=test-api-key
pip install -e ".[dev]"
pytest

cd ../frontend
npm install
npm run test
```

19 backend test files cover: state transitions (legal/illegal/terminal),
retry policy math, provider mocks, auth, event CRUD and validation,
transactional rollback, real-concurrency duplicate-event and
duplicate-task-execution tests (via `asyncio.gather`, not sleeps),
retry-to-success, max-attempts-to-DLQ, partial-success event
aggregation, crash recovery (stale-lease and never-enqueued cases), rate
limiter allow/deny/refill/concurrency/fail-open behavior, the ops/DLQ/
job-detail endpoints, and the generic-exception-handler's no-leak
guarantee. 3 frontend test files (Vitest + React Testing Library) cover
status rendering, the four data-state components, and the Overview
page's loading/unavailable/error/data paths.

**None of this has been executed** — see the warning at the top of this
document and `.github/workflows/ci.yml`, which exists specifically so
these tests run for real, with actual service containers, on the first
push.

## Failure scenarios

| Scenario | What happens |
|---|---|
| Duplicate `event_id` | `events.event_id` UNIQUE constraint triggers an `IntegrityError`, translated to `409 EVENT_ALREADY_EXISTS`. Not caught by an app-level check-then-insert, which would race under concurrency. |
| Concurrent duplicate submission | Same as above — only one concurrent `INSERT` can win the constraint; proven in `tests/integration/test_concurrency.py` via real `asyncio.gather`, not sleeps. |
| Worker crashes mid-processing | Job's lease (`lease_expires_at`) expires; the Beat sweep resets it to `QUEUED` within ~30s of expiry and republishes it. |
| Provider fails | Delivery attempt recorded as `FAILED`; `RetryPolicy` computes backoff; job moves to `RETRYING` then re-enqueues with a matching Celery `countdown`. |
| Provider keeps failing | Once `attempt_count >= max_attempts`, job moves to `DEAD_LETTERED` with a `dead_letter_jobs` row recording why; visible and retryable in the dashboard. |
| Redis rate limiter unreachable | Fails open — processing continues unthrottled rather than halting all delivery. |
| Post-commit Celery publish fails | Job stays `QUEUED` in Postgres with no task in flight; the recovery sweep detects unclaimed `QUEUED` jobs older than 60s and republishes them. |
| Duplicate task delivery (Celery redelivery) | `FOR UPDATE SKIP LOCKED` plus a `status == PROCESSING` re-check before recording an outcome mean a second delivery of the same attempt finds nothing left to do. |
| Partial multi-channel failure | Individual job states are never rewritten to make the aggregate look better; the event's aggregate status reflects the worst outcome (`FAILED` if any channel dead-lettered) while successful sibling jobs stay `DELIVERED`. |

## Known limitations

- **Nothing in this repository has been executed** — the overriding
  limitation, stated in full at the top of this document.
- Rate limiting fails open on Redis unavailability — documented
  tradeoff, not an oversight.
- No multi-tenancy or per-API-key rate limits — one global limit per
  channel, matching the single-API-key auth model.
- Email/SMS/push are deterministic mock providers — no real provider
  integration is implemented or claimed.
- Single environment-configured API key — no persistent key table,
  rotation, or per-client keys. The dashboard inherits this exact
  boundary.
- Event aggregation is recomputed independently per job outcome with no
  row lock — self-healing but not serialized against a rare concurrent
  race (see `docs/architecture.md`).
- No search-by-ID box on the dashboard — event/job detail is reached by
  clicking through a list.
- No performance/load numbers anywhere in this repository — none were
  measured, so none are claimed.

## Engineering tradeoffs

**Why PostgreSQL?** Transactional guarantees and row-level locking
(`SELECT ... FOR UPDATE SKIP LOCKED`) are the actual mechanism behind
this project's idempotency and concurrency claims — a NoSQL store would
mean rebuilding those guarantees at the application layer, which is
exactly the risk this project exists to avoid.

**Why Celery + Redis, not Kafka?** Kafka is a log — durable, ordered,
replayable, built for streaming and fan-out at scale. Pulse's actual
requirement is "run this job with retry/backoff and a DLQ," which is a
task queue's job description, not a log's. Celery+Redis provides that
directly; Kafka would add partition/consumer-group complexity this
system's actual scale and requirements don't call for.

**Why `SELECT ... FOR UPDATE SKIP LOCKED`?** It's the mechanism that
makes "two workers, one job" resolve correctly without a separate lock
service: one worker's transaction holds the row lock, so the other's
identical query — filtered to the same claimable statuses — either skips
the locked row or finds the status already changed. No additional
infrastructure required.

**Why two idempotency constraints instead of one?** `events.event_id`
prevents a duplicate *event*; `(event_id, channel)` on
`notification_jobs` prevents a duplicate *job* for a channel that's
already scheduled. They protect different things — the first at
ingestion, the second at job creation — and both are enforced by the
database, not application logic, because a check-then-insert has a race
window a UNIQUE constraint doesn't.

**Why at-least-once instead of exactly-once?** Exactly-once delivery
across a network boundary (worker to external provider) is not
something Celery, Redis, or Postgres can guarantee in combination — the
provider call and the database write recording its outcome are two
separate operations that can't be made atomic with each other. Claiming
exactly-once would be a claim this architecture can't back up. What
*is* achievable, and what Pulse actually implements, is idempotent
*processing*: duplicate task execution is safe because the database
state (not the message) is authoritative.

**Why a token bucket instead of a fixed window?** A fixed window
("reset a counter every 60 seconds") allows up to 2x the configured
limit in a burst straddling two adjacent windows. A continuously
refilling token bucket has no such edge case and maps directly onto
the actual requirement ("N per minute").

**Why fail-open on Redis failure for rate limiting?** A Redis outage
should not silently halt every outbound notification in the system —
that failure mode is judged worse than temporarily unbounded throughput
for a notification system specifically. A payment-authorization gate
would likely make the opposite choice; the right answer depends on
which failure mode costs more for the system in question, and that's a
deliberate call, not a default.

**Why leases instead of a distributed lock?** A full distributed lock
manager is the "unnecessary abstraction" this project's own engineering
standard warns against. A lease plus a periodic sweep is sufficient at
this scale, uses infrastructure already in place (Postgres timestamps,
Celery Beat), and fails safe: worst case, a job sits reclaimable for one
extra sweep interval.

**Why post-commit enqueue?** Publishing to Celery *before* the database
transaction commits risks a worker claiming a job whose transaction
then rolls back — a job that, from the worker's perspective, never
existed. Committing first means the only failure window is "committed
but not yet published," which the recovery sweep explicitly covers (see
[Failure scenarios](#failure-scenarios)) — a documented, bounded window,
not an unbounded one.

**What happens if the process dies between DB commit and Celery
publish?** The job sits `QUEUED` in Postgres with no task ever
published. The recovery sweep detects `QUEUED` jobs with no
`claimed_at`, older than a threshold, and republishes them.

**What happens if a provider succeeds but the worker crashes before
recording success?** The job's lease expires; the recovery sweep resets
it to `QUEUED`; a healthy worker reprocesses it — calling the provider
again. This is the concrete shape of "at-least-once, not exactly-once":
a real (non-mock, non-idempotent) provider could send a notification
twice in this exact scenario. Pulse's database-side idempotency prevents
duplicate *logical processing*; it cannot prevent a duplicate *external
side effect* from a provider that isn't itself idempotent. This
boundary is stated here rather than hidden.

**Can the same notification be delivered twice?** At the *processing*
level, no — the claim query and outcome-recording re-check make
duplicate task execution a no-op. At the *external delivery* level, in
the crash-after-success scenario above, yes, in principle, with a
non-idempotent real provider. Mock providers in this repository are
deterministic and don't have external side effects, so this can't be
observed with the current implementation, but the architectural
possibility is real and stated plainly rather than glossed over.

## Project structure

```text
pulse/
├── backend/
│   ├── app/
│   │   ├── api/v1/        # HTTP routes: events, jobs, dead-letter, ops
│   │   ├── core/          # config, state machines, retry policy, rate
│   │   │                  #   limiter, metrics, logging, auth, exceptions
│   │   ├── db/            # async engine/session setup
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── services/      # event/job/ops/dead-letter business logic
│   │   ├── workers/       # Celery app, tasks, dispatch, recovery,
│   │   │                  #   event aggregation
│   │   ├── providers/     # provider abstraction + deterministic mocks
│   │   └── main.py
│   ├── tests/             # unit / api / integration
│   ├── alembic/           # migrations (0001-0003)
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/                # Next.js App Router pages + server proxy
│   ├── components/          # shared UI (status badges, state blocks, ...)
│   ├── lib/                 # typed API client, shared types, polling hook
│   └── Dockerfile
├── docs/
│   └── architecture.md      # full design rationale and diagrams
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
└── README.md
```

## Roadmap / future work

Deliberately out of scope for this project, not overlooked:

- Real email/SMS/push provider integrations (the abstraction in
  `app/providers/` is built to support this without touching worker
  logic).
- Multi-tenant / per-API-key rate limits and a persistent, rotatable
  API key table.
- Multi-operator dashboard authentication (a real session/identity layer
  in front of the current server-side proxy).
- A deployed Prometheus + Grafana stack consuming `/metrics` for actual
  historical graphs (Pulse ships the instrumentation, not the
  monitoring stack).
- Kafka, Kubernetes, service mesh, distributed tracing, or horizontal
  autoscaling — none of these are called for by this project's actual
  scale or requirements; adding them would be technology accumulation,
  not engineering improvement, which is precisely what this project's
  own standard argues against.
