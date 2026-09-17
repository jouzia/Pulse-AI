import pytest

from app.core.states import (
    EventStatus,
    InvalidStateTransition,
    JobStatus,
    assert_event_transition,
    assert_job_transition,
)


def test_legal_event_transition_does_not_raise():
    assert_event_transition(EventStatus.RECEIVED, EventStatus.VALIDATED)
    assert_event_transition(EventStatus.VALIDATED, EventStatus.QUEUED)
    assert_event_transition(EventStatus.QUEUED, EventStatus.PROCESSING)
    assert_event_transition(EventStatus.PROCESSING, EventStatus.DELIVERED)


def test_illegal_event_transition_raises():
    with pytest.raises(InvalidStateTransition):
        assert_event_transition(EventStatus.RECEIVED, EventStatus.DELIVERED)


def test_delivered_event_is_terminal():
    with pytest.raises(InvalidStateTransition):
        assert_event_transition(EventStatus.DELIVERED, EventStatus.QUEUED)


def test_legal_job_transition_does_not_raise():
    assert_job_transition(JobStatus.PENDING, JobStatus.QUEUED)
    assert_job_transition(JobStatus.QUEUED, JobStatus.PROCESSING)
    assert_job_transition(JobStatus.PROCESSING, JobStatus.FAILED)
    assert_job_transition(JobStatus.FAILED, JobStatus.RETRYING)
    assert_job_transition(JobStatus.RETRYING, JobStatus.QUEUED)


def test_illegal_job_transition_raises():
    with pytest.raises(InvalidStateTransition):
        assert_job_transition(JobStatus.PENDING, JobStatus.DELIVERED)


def test_dead_lettered_job_is_terminal():
    with pytest.raises(InvalidStateTransition):
        assert_job_transition(JobStatus.DEAD_LETTERED, JobStatus.QUEUED)


def test_failed_job_can_go_to_dead_lettered():
    assert_job_transition(JobStatus.FAILED, JobStatus.DEAD_LETTERED)
