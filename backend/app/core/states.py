"""
Explicit state machines for events and notification jobs.

These are the single source of truth for valid states. They are mapped to
native Postgres enum types (see app/models) rather than left as free-text
columns, so an invalid state is a type/constraint error, not a typo that
silently corrupts a report six months from now.

Do not introduce new state strings anywhere else in the codebase — extend
these enums instead.
"""

from enum import Enum


class EventStatus(str, Enum):
    """Lifecycle of an inbound event, tracked on the `events` row."""

    RECEIVED = "received"
    VALIDATED = "validated"
    QUEUED = "queued"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class JobStatus(str, Enum):
    """Lifecycle of a single notification_job (one event x one channel)."""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTERED = "dead_lettered"


class DeliveryStatus(str, Enum):
    """Result of a single provider dispatch attempt, tracked per delivery row."""

    ATTEMPTED = "attempted"
    DELIVERED = "delivered"
    FAILED = "failed"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


# Transition tables double as validation: a worker calling
# `assert_transition(current, next_)` gets a hard failure on any move that
# isn't listed here, instead of a silent bad write.

EVENT_TRANSITIONS: dict[EventStatus, set[EventStatus]] = {
    EventStatus.RECEIVED: {EventStatus.VALIDATED, EventStatus.FAILED},
    EventStatus.VALIDATED: {EventStatus.QUEUED, EventStatus.FAILED},
    EventStatus.QUEUED: {EventStatus.PROCESSING},
    EventStatus.PROCESSING: {EventStatus.DELIVERED, EventStatus.FAILED},
    EventStatus.FAILED: {EventStatus.QUEUED, EventStatus.DEAD_LETTERED},
    EventStatus.DELIVERED: set(),
    EventStatus.DEAD_LETTERED: set(),
}

JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.QUEUED},
    JobStatus.QUEUED: {JobStatus.PROCESSING},
    JobStatus.PROCESSING: {JobStatus.DELIVERED, JobStatus.FAILED},
    JobStatus.FAILED: {JobStatus.RETRYING, JobStatus.DEAD_LETTERED},
    JobStatus.RETRYING: {JobStatus.QUEUED},
    JobStatus.DELIVERED: set(),
    JobStatus.DEAD_LETTERED: set(),
}


class InvalidStateTransition(Exception):
    def __init__(self, current: Enum, target: Enum):
        super().__init__(f"Cannot transition from {current} to {target}")
        self.current = current
        self.target = target


def assert_job_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in JOB_TRANSITIONS.get(current, set()):
        raise InvalidStateTransition(current, target)


def assert_event_transition(current: EventStatus, target: EventStatus) -> None:
    if target not in EVENT_TRANSITIONS.get(current, set()):
        raise InvalidStateTransition(current, target)


def enum_values(enum_cls: type[Enum]) -> list[str]:
    """
    Pass as `values_callable` to SQLAlchemy's Enum column type.

    Without this, SQLAlchemy stores a Python Enum member's *name*
    (e.g. "RECEIVED") to the database by default -- not its `.value`
    ("received"). The Alembic migration's native Postgres enum type only
    permits the lowercase `.value` strings, so omitting this causes every
    insert to fail with an invalid-enum-value error at runtime.
    """
    return [member.value for member in enum_cls]
