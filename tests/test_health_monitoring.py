"""Unit and integration tests for Phase 3: Reliable backend health monitoring, discovery, and safety."""

from unittest.mock import MagicMock
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.memory_adapter import MemoryAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.api import create_app
from cache_layer.config import CacheConfig
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheConfigurationError, CacheConnectionError

from cache_layer.factory import CacheFactory
from cache_layer.manager import CacheManager



# =======================================================
# 1. Health Checks across All 3 Backends (Unit Level)
# =======================================================

def test_memory_health_check_details():
    adapter = MemoryAdapter(max_size=500)
    adapter.set("k1", b"hello")
    health = adapter.health_check()

    assert health["status"] == "healthy"
    assert health["backend"] == "memory"
    assert health["provider"] == "memory"
    assert "latency_ms" in health
    assert health["details"]["items_count"] == 1
    assert health["details"]["bytes_used"] == 5
    assert health["details"]["max_size"] == 500


def test_redis_healthy_check():
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.info.return_value = {"redis_version": "7.2.4"}

    adapter = RedisAdapter(
        host="redis.internal",
        port=6379,
        db=2,
        password="secret_password_123",
        client=mock_client,
    )
    health = adapter.health_check()

    assert health["status"] == "healthy"
    assert health["backend"] == "redis"
    assert health["provider"] == "redis"
    assert health["details"]["host"] == "redis.internal"
    assert health["details"]["port"] == 6379
    assert health["details"]["db"] == 2
    assert health["details"]["server_version"] == "7.2.4"
    # Verify password is strictly redacted / omitted from health output
    assert "password" not in health["details"]
    assert "secret_password_123" not in str(health)


def test_redis_unavailable_health_check():
    mock_client = MagicMock()
    mock_client.ping.side_effect = RedisConnectionError("Connection refused by target machine")

    adapter = RedisAdapter(host="10.0.0.1", port=6379, client=mock_client)
    health = adapter.health_check()

    assert health["status"] == "unhealthy"
    assert health["backend"] == "redis"
    assert health["provider"] == "redis"
    assert "Connection refused" in health["details"]["error"]
    assert health["details"]["error_type"] == "ConnectionError"
    # Ensure no raw internal traceback in health payload
    assert "Traceback" not in str(health)


def test_memcached_healthy_check():
    mock_client = MagicMock()
    mock_client.stats.return_value = {b"version": b"1.6.22"}

    adapter = MemcachedAdapter(host="memcached.internal", port=11211, client=mock_client)
    health = adapter.health_check()

    assert health["status"] == "healthy"
    assert health["backend"] == "memcached"
    assert health["provider"] == "memcached"
    assert health["details"]["host"] == "memcached.internal"
    assert health["details"]["port"] == 11211
    assert health["details"]["server_version"] == "1.6.22"


def test_memcached_unavailable_health_check():
    mock_client = MagicMock()
    mock_client.stats.side_effect = ConnectionRefusedError("Connection refused on 11211")

    adapter = MemcachedAdapter(host="10.0.0.2", port=11211, client=mock_client)
    health = adapter.health_check()

    assert health["status"] == "unhealthy"
    assert health["backend"] == "memcached"
    assert health["provider"] == "memcached"
    assert "Connection refused" in health["details"]["error"]
    assert health["details"]["error_type"] == "ConnectionRefusedError"
    assert "Traceback" not in str(health)


# =======================================================
# 2. HTTP Endpoints: GET /health and GET /backends
# =======================================================

def test_http_health_endpoint_healthy():
    provider = MemoryAdapter()
    manager = CacheManager(provider=provider)
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True

    with app.test_client() as client:
        res = client.get("/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "healthy"
        assert data["backend"] == "memory"
        assert data["provider"] == "memory"
        assert "latency_ms" in data


def test_http_health_endpoint_unhealthy():
    mock_provider = MagicMock(spec=CacheProvider)
    mock_provider.provider_name = "redis"
    mock_provider.health_check.return_value = {
        "status": "unhealthy",
        "backend": "redis",
        "provider": "redis",
        "latency_ms": 15.2,
        "details": {"error": "Connection timed out", "error_type": "TimeoutError"},
    }

    manager = CacheManager(provider=mock_provider)
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True

    with app.test_client() as client:
        res = client.get("/health")
        # Must return HTTP 503 when backend is unhealthy
        assert res.status_code == 503
        data = res.get_json()
        assert data["status"] == "unhealthy"
        assert data["backend"] == "redis"
        assert data["details"]["error"] == "Connection timed out"


def test_http_backends_discovery_endpoint():
    provider = MemoryAdapter()
    manager = CacheManager(provider=provider)
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True

    with app.test_client() as client:
        res = client.get("/backends")
        assert res.status_code == 200
        data = res.get_json()
        assert data["active"] == "memory"
        assert "memory" in data["available"]
        assert "redis" in data["available"]
        assert "memcached" in data["available"]


def test_http_backends_custom_registered():
    class ValkeyProvider(CacheProvider):
        @property
        def provider_name(self):
            return "valkey"
        def get(self, key): return None
        def set(self, key, value, ttl=None): return True
        def delete(self, key): return True
        def clear(self): return True
        def health_check(self): return {"status": "healthy", "backend": "valkey"}
        def close(self): pass

    CacheFactory.register_provider("valkey", ValkeyProvider)

    provider = CacheFactory.create_provider("valkey")
    manager = CacheManager(provider=provider)
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True

    with app.test_client() as client:
        res = client.get("/backends")
        assert res.status_code == 200
        data = res.get_json()
        assert data["active"] == "valkey"
        assert "valkey" in data["available"]


def test_no_stack_traces_on_unexpected_exception():
    mock_provider = MagicMock(spec=CacheProvider)
    mock_provider.provider_name = "crash_backend"
    # Simulate an unexpected critical crash inside the backend
    mock_provider.get.side_effect = RuntimeError("Fatal hardware memory fault")

    manager = CacheManager(provider=mock_provider)
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True

    with app.test_client() as client:
        res = client.get("/cache/some_key")
        # Must return HTTP 500
        assert res.status_code == 500
        data = res.get_json()
        assert data["error"] == "Internal Server Error"
        # Must NOT expose Python traceback, code lines, or internal exception message
        assert "Fatal hardware memory fault" not in data["message"]
        assert "Traceback" not in res.get_data(as_text=True)
        assert "File " not in res.get_data(as_text=True)


def test_invalid_backend_configuration():
    # Attempting to configure an unsupported backend
    with pytest.raises(CacheConfigurationError, match="Unsupported cache backend"):
        CacheConfig(backend="couchbase")

    # Creating provider with unknown backend raises CacheConfigurationError
    with pytest.raises(CacheConfigurationError):
        CacheFactory.create_provider(backend="couchbase")


def test_api_stability_under_repeated_failures():
    mock_provider = MagicMock(spec=CacheProvider)
    mock_provider.provider_name = "flaky_redis"
    mock_provider.get.side_effect = CacheConnectionError("Network connection reset")
    mock_provider.health_check.return_value = {

        "status": "unhealthy",
        "backend": "flaky_redis",
        "provider": "flaky_redis",
        "latency_ms": 5.0,
        "details": {"error": "Connection reset", "error_type": "ConnectionError"},
    }

    manager = CacheManager(provider=mock_provider)
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True

    with app.test_client() as client:
        # Multiple requests during outage
        for _ in range(5):
            res = client.get("/cache/item")
            assert res.status_code == 503
            assert res.get_json()["error"] == "Service Unavailable"

        # Health endpoint during outage returns 503
        health_res = client.get("/health")
        assert health_res.status_code == 503
        assert health_res.get_json()["status"] == "unhealthy"

        # Discovery endpoint remains operational
        backends_res = client.get("/backends")
        assert backends_res.status_code == 200
        assert backends_res.get_json()["active"] == "flaky_redis"

