"""
Prometheus metrics. Every counter/histogram here is incremented at the
exact point the underlying event actually happens (a job is claimed,
delivered, failed, dead-lettered, retried, or rate-limited) — never
backfilled, periodically invented, or estimated. The one gauge
(`pulse_queue_depth`) is computed by querying the database at scrape
time in the `/metrics` handler in app/main.py, not maintained as a
running counter that could silently drift from reality.

Label cardinality: labels are limited to `channel` (3 fixed values),
`provider` (one mock provider name per channel, so also effectively
bounded by channel), and `event_type` on the one events-received counter.
Deliberately excluded: event_id, job_id, recipient, or any other
per-request value — each would make that metric's series count grow
without bound as the system runs, which is the classic Prometheus
cardinality mistake this project is deliberately avoiding. `event_type`
is included on `events_received_total` on the assumption that a real
system emits a bounded set of event type strings (e.g.
"payment.succeeded", "user.signup") rather than one per request; if that
assumption stops holding for a given deployment, that label should be
dropped.
"""

from prometheus_client import Counter, Gauge, Histogram

events_received_total = Counter(
    "pulse_events_received_total",
    "Events successfully persisted via POST /events.",
    ["event_type"],
)

notifications_processed_total = Counter(
    "pulse_notifications_processed_total",
    "Notification job processing attempts started (successfully claimed by a worker).",
    ["channel"],
)

notifications_delivered_total = Counter(
    "pulse_notifications_delivered_total",
    "Notification jobs that reached DELIVERED.",
    ["channel", "provider"],
)

notifications_failed_total = Counter(
    "pulse_notifications_failed_total",
    "Individual provider send attempts that failed (includes attempts that go on to retry).",
    ["channel", "provider"],
)

notifications_dead_lettered_total = Counter(
    "pulse_notifications_dead_lettered_total",
    "Notification jobs that exhausted max_attempts and were dead-lettered.",
    ["channel"],
)

notification_retries_total = Counter(
    "pulse_notification_retries_total",
    "Notification jobs scheduled for a retry after a failed attempt.",
    ["channel"],
)

rate_limit_denied_total = Counter(
    "pulse_rate_limit_denied_total",
    "Job processing attempts deferred by the rate limiter (not counted as provider failures).",
    ["channel"],
)

notification_processing_duration_seconds = Histogram(
    "pulse_notification_processing_duration_seconds",
    "Duration of a single provider send call (one attempt).",
    ["channel", "provider"],
)

notification_delivery_duration_seconds = Histogram(
    "pulse_notification_delivery_duration_seconds",
    "End-to-end time from job creation to final DELIVERED, including any retries.",
    ["channel"],
)

queue_depth = Gauge(
    "pulse_queue_depth",
    "Notification jobs currently QUEUED or RETRYING (waiting to be processed), per channel.",
    ["channel"],
)


def sum_counter(counter: Counter, **label_filter: str) -> float:
    """
    Reads the CURRENT value already held by a prometheus_client Counter,
    optionally filtered to matching labels. Exists so the dashboard's
    JSON ops endpoint (app/services/ops_service.py) can surface the exact
    same in-process counters /metrics exposes, in JSON form, rather than
    maintaining a second, separately-incremented count that could drift
    from the real one. Uses the public `.collect()` API rather than
    reaching into the Counter's private internals.

    Note: like any in-process Prometheus counter, this resets to zero
    when the API process restarts — it is not a durable, historical
    total. The dashboard must not present it as one.
    """
    total = 0.0
    for metric in counter.collect():
        for sample in metric.samples:
            if not sample.name.endswith("_total"):
                continue
            if all(sample.labels.get(k) == v for k, v in label_filter.items()):
                total += sample.value
    return total
