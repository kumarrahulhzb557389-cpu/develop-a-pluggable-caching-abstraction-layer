"""Unit and integration tests for Phase 4: Safe backend switching, API authentication, and rate limiting."""

from unittest.mock import MagicMock
import pytest

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.memory_adapter import MemoryAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.api import create_app
from cache_layer.config import CacheConfig
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheConnectionError, CacheValidationError
from cache_layer.factory import CacheFactory
from cache_layer.manager import CacheManager
from cache_layer.security import admin_rate_limiter


# ==========================================================
# 1. CacheManager Dynamic Backend Switching Unit Tests
# ==========================================================

def test_cache_manager_switching_lifecycle():
    mem_adapter = MemoryAdapter()
    cfg = CacheConfig(backend="memory")
    manager = CacheManager(provider=mem_adapter, config=cfg)

    assert manager.provider_name == "memory"
    manager.set("k1", "val1")
    assert manager.get("k1") == "val1"

    # Register mock healthy redis creator to test switching safely
    mock_redis = MagicMock(spec=CacheProvider)
    mock_redis.provider_name = "mock_redis"
    mock_redis.health_check.return_value = {"status": "healthy", "backend": "mock_redis"}
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True


    CacheFactory.register_provider("mock_redis", lambda cfg, kw: mock_redis)

    try:
        # Switch memory -> mock_redis
        manager.switch_backend("mock_redis")
        assert manager.provider_name == "mock_redis"
        assert manager.get("any_key") is None

        # Switch back mock_redis -> memory
        manager.switch_backend("memory")
        assert manager.provider_name == "memory"
    finally:
        CacheFactory.unregister_provider("mock_redis")


def test_switch_backend_invalid_name():
    mem_adapter = MemoryAdapter()
    manager = CacheManager(provider=mem_adapter)

    with pytest.raises(CacheValidationError, match="Unsupported or unavailable backend"):
        manager.switch_backend("non_existent_engine")

    with pytest.raises(CacheValidationError, match="non-empty string"):
        manager.switch_backend("")


def test_switch_backend_unavailable_abort():
    mem_adapter = MemoryAdapter()
    manager = CacheManager(provider=mem_adapter)

    # Register mock offline provider
    mock_dead_backend = MagicMock(spec=CacheProvider)
    mock_dead_backend.provider_name = "dead_db"
    mock_dead_backend.health_check.return_value = {
        "status": "unhealthy",
        "backend": "dead_db",
        "details": {"error": "Connection refused to cluster"},
    }

    CacheFactory.register_provider("dead_db", lambda cfg, kw: mock_dead_backend)

    try:
        # Attempting switch must raise CacheConnectionError and NOT switch
        with pytest.raises(CacheConnectionError, match="Target backend 'dead_db' is unavailable"):
            manager.switch_backend("dead_db")

        # Verify active provider remained unchanged
        assert manager.provider_name == "memory"
        mock_dead_backend.close.assert_called_once()
    finally:
        CacheFactory.unregister_provider("dead_db")



# ==========================================================
# 2. REST API Backend Switching: POST /backend/switch & GET /backend
# ==========================================================

@pytest.fixture
def switching_app():
    cfg = CacheConfig(backend="memory")
    manager = CacheManager(provider=MemoryAdapter(), config=cfg)
    app = create_app(cache_manager=manager, config=cfg)
    app.config["TESTING"] = True
    return app


def test_api_switch_memory_to_mock_redis_to_memcached(switching_app):
    # Setup mock providers for reliable deterministic switching
    mock_redis = MagicMock(spec=CacheProvider)
    mock_redis.provider_name = "redis"
    mock_redis.health_check.return_value = {"status": "healthy", "backend": "redis"}
    mock_redis.get.return_value = b'"from_redis"'

    mock_memcached = MagicMock(spec=CacheProvider)
    mock_memcached.provider_name = "memcached"
    mock_memcached.health_check.return_value = {"status": "healthy", "backend": "memcached"}
    mock_memcached.get.return_value = b'"from_memcached"'

    CacheFactory.register_provider("redis", lambda cfg, kw: mock_redis)
    CacheFactory.register_provider("memcached", lambda cfg, kw: mock_memcached)

    try:
        with switching_app.test_client() as client:
            # Check initial backend
            res0 = client.get("/backend")
            assert res0.status_code == 200
            assert res0.get_json()["backend"] == "memory"

            # 1. Switch Memory -> Redis
            res1 = client.post("/backend/switch", json={"backend": "redis"})
            assert res1.status_code == 200
            assert res1.get_json()["backend"] == "redis"

            # Verify GET /backend
            res_b1 = client.get("/backend")
            assert res_b1.get_json()["backend"] == "redis"

            # 2. Switch Redis -> Memcached
            res2 = client.post("/backend/switch", json={"backend": "memcached"})
            assert res2.status_code == 200
            assert res2.get_json()["backend"] == "memcached"

            # 3. Switch Memcached -> Memory
            res3 = client.post("/backend/switch", json={"backend": "memory"})
            assert res3.status_code == 200
            assert res3.get_json()["backend"] == "memory"

            # Verify existing CRUD still works
            set_res = client.post("/cache/after_switch", json={"value": "hello_world"})
            assert set_res.status_code == 200
            get_res = client.get("/cache/after_switch")
            assert get_res.get_json()["value"] == "hello_world"
    finally:
        CacheFactory.unregister_provider("redis")
        CacheFactory.unregister_provider("memcached")


def test_api_switch_unavailable_target(switching_app):
    mock_bad = MagicMock(spec=CacheProvider)
    mock_bad.provider_name = "offline_redis"
    mock_bad.health_check.return_value = {
        "status": "unhealthy",
        "backend": "offline_redis",
        "details": {"error": "Connection timed out"},
    }
    CacheFactory.register_provider("offline_redis", lambda cfg, kw: mock_bad)

    try:
        with switching_app.test_client() as client:
            res = client.post("/backend/switch", json={"backend": "offline_redis"})
            assert res.status_code == 503
            data = res.get_json()
            assert data["error"] == "Service Unavailable"
            assert "offline_redis" in data["message"]

            # Backend must still be memory
            check_res = client.get("/backend")
            assert check_res.get_json()["backend"] == "memory"
    finally:
        CacheFactory.unregister_provider("offline_redis")



def test_api_switch_invalid_backend(switching_app):
    with switching_app.test_client() as client:
        # Invalid backend name
        res = client.post("/backend/switch", json={"backend": "cassandra"})
        assert res.status_code == 400
        assert res.get_json()["error"] == "Validation Error"

        # Empty body
        res2 = client.post("/backend/switch", json={})
        assert res2.status_code == 400
        assert res2.get_json()["error"] == "Validation Error"


# ==========================================================
# 3. API Key Security Tests
# ==========================================================

@pytest.fixture
def secured_app():
    cfg = CacheConfig(backend="memory", api_key="test-secret-key-xyz", admin_rate_limit=10)
    manager = CacheManager(provider=MemoryAdapter(), config=cfg)
    app = create_app(cache_manager=manager, config=cfg)
    app.config["TESTING"] = True
    admin_rate_limiter.reset()
    return app


def test_unauthorized_requests_to_admin_endpoints(secured_app):
    with secured_app.test_client() as client:
        # 1. Switching backend without key -> 401
        res1 = client.post("/backend/switch", json={"backend": "memory"})
        assert res1.status_code == 401
        assert res1.get_json()["error"] == "Unauthorized"
        assert "test-secret-key-xyz" not in str(res1.get_json())

        # 2. Clearing cache without key -> 401
        res2 = client.delete("/cache")
        assert res2.status_code == 401
        assert res2.get_json()["error"] == "Unauthorized"

        # 3. Diagnostics (/stats) without key -> 401
        res3 = client.get("/stats")
        assert res3.status_code == 401
        assert res3.get_json()["error"] == "Unauthorized"

        # 4. Wrong API key -> 401
        res4 = client.post(
            "/backend/switch",
            json={"backend": "memory"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert res4.status_code == 401
        assert res4.get_json()["error"] == "Unauthorized"


def test_authorized_requests_to_admin_endpoints(secured_app):
    with secured_app.test_client() as client:
        # Authorized via X-API-Key
        res1 = client.get("/stats", headers={"X-API-Key": "test-secret-key-xyz"})
        assert res1.status_code == 200
        assert "uptime_seconds" in res1.get_json()

        # Authorized via Authorization: Bearer <key>
        res2 = client.delete("/cache", headers={"Authorization": "Bearer test-secret-key-xyz"})
        assert res2.status_code == 200
        assert res2.get_json()["cleared"] is True

        # Public endpoints remain accessible without auth
        res_health = client.get("/health")
        assert res_health.status_code == 200
        res_backend = client.get("/backend")
        assert res_backend.status_code == 200
        res_crud = client.get("/cache/item")
        assert res_crud.status_code == 404  # normal key not found


# ==========================================================
# 4. Administrative Rate Limiting Tests
# ==========================================================

def test_admin_rate_limiting():
    # Setup rate limiter with limit of 3 requests
    limiter = admin_rate_limiter
    limiter._max_requests = 3
    limiter._window_seconds = 60
    limiter.reset()

    cfg = CacheConfig(backend="memory", api_key=None, admin_rate_limit=3)
    manager = CacheManager(provider=MemoryAdapter(), config=cfg)
    app = create_app(cache_manager=manager, config=cfg)
    app.config["TESTING"] = True

    with app.test_client() as client:
        # First 3 requests to admin endpoint (/stats) succeed
        for _ in range(3):
            res = client.get("/stats")
            assert res.status_code == 200

        # 4th request exceeds rate limit -> 429 Too Many Requests
        res4 = client.get("/stats")
        assert res4.status_code == 429
        data = res4.get_json()
        assert data["error"] == "Too Many Requests"
        assert "Rate limit exceeded" in data["message"]

        # Reset limiter
        limiter.reset()
        res5 = client.get("/stats")
        assert res5.status_code == 200
