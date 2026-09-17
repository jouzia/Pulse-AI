"""
Domain-level exceptions. Each carries the HTTP status code and stable,
machine-readable error code it should surface as — the exception handler
in app/main.py translates these into the single consistent error envelope
{"error": {"code": ..., "message": ...}} without leaking internals (SQL,
stack traces, connection strings) to the client.

Route handlers and the service layer raise these directly; they never
construct an HTTP response themselves. That keeps error formatting in
exactly one place.
"""


class PulseError(Exception):
    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class EventAlreadyExistsError(PulseError):
    """events.event_id UNIQUE constraint violation."""

    status_code = 409
    code = "EVENT_ALREADY_EXISTS"


class JobAlreadyExistsError(PulseError):
    """notification_jobs (event_id, channel) UNIQUE constraint violation."""

    status_code = 409
    code = "JOB_ALREADY_EXISTS"


class EventNotFoundError(PulseError):
    status_code = 404
    code = "EVENT_NOT_FOUND"


class JobNotFoundError(PulseError):
    status_code = 404
    code = "JOB_NOT_FOUND"


class DeadLetterJobNotFoundError(PulseError):
    status_code = 404
    code = "DEAD_LETTER_JOB_NOT_FOUND"


class DeadLetterJobAlreadyResolvedError(PulseError):
    """A retry was requested for a dead-letter entry that was already retried."""

    status_code = 409
    code = "DEAD_LETTER_JOB_ALREADY_RESOLVED"


class InvalidCredentialsError(PulseError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
