from app.core.retry_policy import RetryPolicy, get_retry_policy


def test_first_retry_is_immediate():
    policy = RetryPolicy()
    assert policy.delay_for_attempt(1) == 0.0


def test_delay_grows_with_attempt():
    policy = RetryPolicy(jitter_ratio=0.0)
    d2 = policy.delay_for_attempt(2)
    d3 = policy.delay_for_attempt(3)
    d4 = policy.delay_for_attempt(4)
    assert d2 < d3 < d4


def test_delay_is_capped_at_max_delay():
    policy = RetryPolicy(max_delay_seconds=60.0, jitter_ratio=0.0)
    assert policy.delay_for_attempt(10) <= 60.0


def test_is_exhausted_boundary():
    policy = RetryPolicy(max_attempts=3)
    assert not policy.is_exhausted(2)
    assert policy.is_exhausted(3)
    assert policy.is_exhausted(4)


def test_get_retry_policy_known_channel():
    assert get_retry_policy("sms") is not None


def test_get_retry_policy_falls_back_to_default_for_unknown_channel():
    default = get_retry_policy("unknown-channel")
    assert default is not None
    assert default.max_attempts == RetryPolicy().max_attempts
