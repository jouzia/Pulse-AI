import structlog
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import func, select, text

from app.api.v1.dead_letter import router as dead_letter_router
from app.api.v1.events import router as events_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.ops import router as ops_router
from app.core import metrics
from app.core.config import get_settings
from app.core.exceptions import PulseError
from app.core.logging import configure_logging
from app.core.states import JobStatus, NotificationChannel
from app.db.session import AsyncSessionLocal
from app.models.notification_job import NotificationJob

# Bug found in Phase 6 audit: configure_logging() was previously only ever
# invoked for Celery workers (via the worker_process_init signal in
# app/workers/celery_app.py). The API process never called it, so every
# structlog.get_logger() call made from request-handling code (e.g.
# app/services/event_service.py's enqueue-failure logging) used
# structlog's out-of-the-box default renderer, not the JSON format this
# project documents everywhere as "structured logging." Calling it here,
# at API startup, is the fix.
configure_logging()

settings = get_settings()
logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Pulse",
    description="Event-driven notification infrastructure.",
    version="0.2.0",
)

app.include_router(events_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(dead_letter_router, prefix="/api/v1")
app.include_router(ops_router, prefix="/api/v1")


# --- Consistent error envelope -----------------------------------------
# One shape for every error the API returns: {"error": {"code", "message"}}.
# Never leak SQL, stack traces, or connection details to the client.


@app.exception_handler(PulseError)
async def pulse_error_handler(request: Request, exc: PulseError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # The response is deliberately generic: no exception message, type,
    # or traceback reaches the client. The full detail -- including the
    # traceback -- goes to structured logs instead, via exc_info=True,
    # which app/core/logging.py's format_exc_info processor renders into
    # a plain string field before JSON-encoding. Never log request
    # headers or body here: that's exactly where an X-API-Key or a
    # notification payload would end up in the log stream.
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
            }
        },
    )


# --- Health / readiness --------------------------------------------------


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness only — must stay cheap, never checks dependencies."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready", tags=["ops"])
async def ready() -> JSONResponse:
    """Readiness — lightweight checks against Postgres and Redis."""
    checks = {"postgres": False, "redis": False}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        checks["postgres"] = False

    try:
        redis_client = Redis.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.aclose()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    all_ok = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ok" if all_ok else "unavailable", "checks": checks},
    )


@app.get("/metrics", tags=["ops"])
async def metrics_endpoint() -> Response:
    """
    Prometheus scrape endpoint. All counters/histograms in app/core/metrics
    are updated in place as the underlying events happen (see
    app/services/event_service.py and app/workers/tasks.py). The one
    gauge, queue depth, is different: it's computed fresh from the
    database on every scrape, right here, rather than maintained
    incrementally -- an incrementally-updated "queue depth" counter could
    silently drift from reality (e.g. after a crash-recovery requeue);
    querying it live cannot.
    """
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(NotificationJob.channel, func.count())
            .where(NotificationJob.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]))
            .group_by(NotificationJob.channel)
        )
        counts = {channel: 0 for channel in NotificationChannel}
        for channel, count in rows.all():
            counts[channel] = count

    for channel, count in counts.items():
        metrics.queue_depth.labels(channel=channel.value).set(count)

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

