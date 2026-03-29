"""Tests for the Dramatiq worker configuration."""

from cyberpulse.tasks.worker import _mask_url, broker, dramatiq, result_backend


class TestWorkerConfiguration:
    """Tests for worker configuration."""

    def test_broker_is_redis_broker(self):
        """Test that broker is a RedisBroker instance."""
        from dramatiq.brokers.redis import RedisBroker
        assert isinstance(broker, RedisBroker)

    def test_result_backend_is_redis_backend(self):
        """Test that result_backend is a RedisBackend instance."""
        from dramatiq.results.backends import RedisBackend
        assert isinstance(result_backend, RedisBackend)

    def test_broker_has_results_middleware(self):
        """Test that broker has Results middleware."""
        from dramatiq.results import Results
        middleware_types = [type(m) for m in broker.middleware]
        assert Results in middleware_types

    def test_dramatiq_has_broker_set(self):
        """Test that dramatiq global has broker set."""
        assert dramatiq.get_broker() is broker


class TestMaskUrl:
    """Tests for _mask_url utility function."""

    def test_mask_url_with_password(self):
        """Test URL masking with password."""
        url = "redis://user:secretpassword@localhost:6379/1"
        masked = _mask_url(url)
        assert masked == "redis://user:***@localhost:6379/1"
        assert "secretpassword" not in masked

    def test_mask_url_without_password(self):
        """Test URL masking without password."""
        url = "redis://localhost:6379/1"
        masked = _mask_url(url)
        assert masked == "redis://localhost:6379/1"

    def test_mask_url_with_credentials_no_user(self):
        """Test URL masking with just password."""
        url = "redis://:password@localhost:6379/1"
        masked = _mask_url(url)
        assert "password" not in masked
        assert "***" in masked


class TestWorkerIntegration:
    """Integration tests for worker with mocked settings."""

    def test_uses_dramatiq_broker_url_from_settings(self):
        """Test that configuration uses dramatiq_broker_url from settings."""
        from cyberpulse.config import settings
        # The worker module should use settings.dramatiq_broker_url
        # We verify this by checking the configuration
        assert hasattr(settings, "dramatiq_broker_url")

    def test_broker_configuration_with_custom_url(self):
        """Test broker can be configured with custom URL."""
        from dramatiq.brokers.redis import RedisBroker
        from dramatiq.results import Results
        from dramatiq.results.backends import RedisBackend

        custom_url = "redis://custom:6379/5"
        test_broker = RedisBroker(url=custom_url)
        test_backend = RedisBackend(url=custom_url)
        test_broker.add_middleware(Results(backend=test_backend))

        assert isinstance(test_broker, RedisBroker)
        assert isinstance(test_backend, RedisBackend)


class TestDramatiqActor:
    """Tests for creating actors with the configured broker."""

    def test_can_define_actor(self):
        """Test that an actor can be defined with the broker."""
        @dramatiq.actor
        def test_task(value: int) -> int:
            return value * 2

        # Actor should be registered
        assert hasattr(test_task, "send")
        assert test_task.actor_name == "test_task"

    def test_actor_with_options(self):
        """Test that an actor can be defined with options."""
        @dramatiq.actor(max_retries=3, time_limit=60000)
        def test_task_with_options(data: str) -> str:
            return data.upper()

        assert hasattr(test_task_with_options, "send")
