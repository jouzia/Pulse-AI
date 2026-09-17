from app.providers.mock import MockEmailProvider


def test_always_succeed_provider_returns_success():
    provider = MockEmailProvider(failure_mode="always_succeed")
    result = provider.send(recipient="a@b.com", job_id="job-1")
    assert result.success
    assert result.provider_message_id is not None
    assert result.error_message is None


def test_always_fail_provider_returns_failure():
    provider = MockEmailProvider(failure_mode="always_fail")
    result = provider.send(recipient="a@b.com", job_id="job-1")
    assert not result.success
    assert result.error_message is not None
    assert result.provider_message_id is None


def test_fail_n_then_succeed_is_deterministic_per_instance():
    provider = MockEmailProvider(failure_mode="fail_n_then_succeed", fail_count=2)
    r1 = provider.send(recipient="a@b.com", job_id="job-1")
    r2 = provider.send(recipient="a@b.com", job_id="job-1")
    r3 = provider.send(recipient="a@b.com", job_id="job-1")
    assert not r1.success
    assert not r2.success
    assert r3.success


def test_always_fail_is_never_random():
    provider = MockEmailProvider(failure_mode="always_fail")
    results = [provider.send(recipient="a@b.com", job_id="job-1") for _ in range(10)]
    assert all(not r.success for r in results)


def test_fresh_instance_resets_the_failure_counter():
    provider_a = MockEmailProvider(failure_mode="fail_n_then_succeed", fail_count=1)
    provider_a.send(recipient="a@b.com", job_id="job-1")

    provider_b = MockEmailProvider(failure_mode="fail_n_then_succeed", fail_count=1)
    result = provider_b.send(recipient="a@b.com", job_id="job-2")
    assert not result.success
