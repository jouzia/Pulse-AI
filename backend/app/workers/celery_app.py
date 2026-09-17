"""
Celery application, deliberately kept separate from the FastAPI app in
app/main.py. The API process only ever needs to enqueue tasks (via
app.workers.dispatch); it should never need Celery's worker runtime
configuration in scope. Keeping all Celery config in exactly one module
means broker settings, concurrency, and queue behavior can change without
touching API code.
"""

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery(
    "pulse",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Ack after the task returns, not on receipt: if a worker process
    # dies mid-task, Redis redelivers the message instead of silently
    # dropping it. This is what makes "at-least-once" actually true here
    # rather than aspirational -- the cost is possible duplicate delivery,
    # which is exactly why job claiming (app/workers/tasks.py) is built to
    # be idempotent regardless of how many times a message is delivered.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # 1: a worker process holds at most one unacked task at a time. With
    # task_acks_late, a higher prefetch would let a crashed worker take
    # several jobs down with it before Redis notices and redelivers them.
    # This costs some throughput; correctness wins that tradeoff here.
    worker_prefetch_multiplier=1,
    task_default_queue="notifications.default",
    # No time limit today would mean a hung provider call (irrelevant for
    # the current instant, synchronous mock providers, but a real risk
    # once an actual HTTP-based provider is plugged in) could occupy a
    # worker process indefinitely. Both limits sit well under the
    # 5-minute job lease (app/workers/tasks.py's LEASE_DURATION_SECONDS)
    # so a killed task's job still gets reclaimed promptly by the
    # recovery sweep either way -- these limits protect worker
    # throughput, the lease protects job correctness; neither depends on
    # the other to be right.
    task_soft_time_limit=120,
    task_time_limit=150,
    # The recovery sweep (app/workers/recovery.py) runs every 30s under
    # Celery Beat -- frequent enough that a crashed worker's jobs don't
    # sit stuck for long, infrequent enough not to be a real load source.
    beat_schedule={
        "recover-stale-jobs": {
            "task": "app.workers.recovery.recover_stale_jobs",
            "schedule": 30.0,
        },
    },
)


@worker_process_init.connect
def _init_worker_logging(**kwargs) -> None:
    configure_logging()


# Imported at the bottom (after `celery_app` is assigned) so their
# @celery_app.task decorators register against this app. tasks.py and
# recovery.py both import `celery_app` from this module -- safe here
# because that name is already bound by the time these imports run.
from app.workers import recovery as _recovery  # noqa: E402,F401
from app.workers import tasks as _tasks  # noqa: E402,F401
