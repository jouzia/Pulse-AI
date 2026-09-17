import uuid

import pytest
from sqlalchemy import select

from app.core.states import EventStatus, JobStatus, NotificationChannel
from app.models.dead_letter_job import DeadLetterJob
from app.models.event import Event
from app.models.notification_delivery import NotificationDelivery
from app.models.notification_job import NotificationJob
from app.providers.mock import MockEmailProvider, MockSMSProvider
from app.schemas.event import EventCreateRequest
from app.services import event_service
from app.workers.tasks import _process_notification_job

pytestmark = pytest.mark.asyncio


async def _create_event_and_jobs(db_session, channels):
    payload = EventCreateRequest(
        event_id=f"evt_{uuid.uuid4().hex[:10]}",
        event_type="payment.succeeded",
        recipient="user@example.com",
        channels=list(channels),
        data={},
    )
    response = await event_service.create_event(db_session, payload)

    event_row = (
        await db_session.execute(select(Event).where(Event.event_id == response.event_id))
    ).scalar_one()
    jobs = (
        (
            await db_session.execute(
                select(NotificationJob).where(NotificationJob.event_id == event_row.id)
            )
        )
        .scalars()
        .all()
    )
    return event_row, jobs


async def test_successful_job_processing_marks_delivered(db_session, set_provider):
    set_provider(NotificationChannel.EMAIL, MockEmailProvider(failure_mode="always_succeed"))

    _, jobs = await _create_event_and_jobs(db_session, ["email"])
    job = jobs[0]

    await _process_notification_job(job.id, job.channel)

    await db_session.refresh(job)
    assert job.status == JobStatus.DELIVERED
    assert job.attempt_count == 1
    assert job.claimed_at is None

    deliveries = (
        (
            await db_session.execute(
                select(NotificationDelivery).where(NotificationDelivery.job_id == job.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(deliveries) == 1
    assert deliveries[0].status.value == "delivered"


async def test_failed_job_transitions_to_retrying(db_session, set_provider):
    set_provider(NotificationChannel.EMAIL, MockEmailProvider(failure_mode="always_fail"))

    _, jobs = await _create_event_and_jobs(db_session, ["email"])
    job = jobs[0]
    job.max_attempts = 5
    await db_session.commit()

    await _process_notification_job(job.id, job.channel)

    await db_session.refresh(job)
    assert job.status == JobStatus.RETRYING
    assert job.attempt_count == 1
    assert job.scheduled_at is not None
    assert job.last_error is not None


async def test_max_attempts_exhausted_dead_letters_job(db_session, set_provider):
    set_provider(NotificationChannel.EMAIL, MockEmailProvider(failure_mode="always_fail"))

    _, jobs = await _create_event_and_jobs(db_session, ["email"])
    job = jobs[0]
    job.max_attempts = 1
    await db_session.commit()

    await _process_notification_job(job.id, job.channel)

    await db_session.refresh(job)
    assert job.status == JobStatus.DEAD_LETTERED

    dlq_rows = (
        (
            await db_session.execute(
                select(DeadLetterJob).where(DeadLetterJob.original_job_id == job.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(dlq_rows) == 1
    assert dlq_rows[0].reason


async def test_eventual_success_after_retries(db_session, set_provider):
    set_provider(
        NotificationChannel.EMAIL,
        MockEmailProvider(failure_mode="fail_n_then_succeed", fail_count=2),
    )

    _, jobs = await _create_event_and_jobs(db_session, ["email"])
    job = jobs[0]
    job.max_attempts = 5
    await db_session.commit()

    # Same provider instance persists across calls (module-level registry),
    # so three claims of the same job model "fails twice, then succeeds"
    # without needing real Celery countdown scheduling in the test.
    await _process_notification_job(job.id, job.channel)
    await db_session.refresh(job)
    assert job.status == JobStatus.RETRYING

    await _process_notification_job(job.id, job.channel)
    await db_session.refresh(job)
    assert job.status == JobStatus.RETRYING

    await _process_notification_job(job.id, job.channel)
    await db_session.refresh(job)
    assert job.status == JobStatus.DELIVERED
    assert job.attempt_count == 3


async def test_partial_success_preserves_individual_job_states_and_aggregates_correctly(
    db_session, set_provider
):
    set_provider(NotificationChannel.EMAIL, MockEmailProvider(failure_mode="always_succeed"))
    set_provider(NotificationChannel.SMS, MockSMSProvider(failure_mode="always_fail"))

    event_row, jobs = await _create_event_and_jobs(db_session, ["email", "sms"])
    for job in jobs:
        job.max_attempts = 1
    await db_session.commit()

    for job in jobs:
        await _process_notification_job(job.id, job.channel)
        await db_session.refresh(job)

    by_channel = {job.channel: job.status for job in jobs}
    assert by_channel[NotificationChannel.EMAIL] == JobStatus.DELIVERED
    assert by_channel[NotificationChannel.SMS] == JobStatus.DEAD_LETTERED

    await db_session.refresh(event_row)
    assert event_row.status == EventStatus.FAILED, (
        "event must not become DELIVERED when any channel permanently failed"
    )
