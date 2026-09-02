"""Unit tests for CacheManager, CacheFactory, and CacheConfig."""

import os
from unittest.mock import MagicMock
import pytest

from cache_layer.adapters.memory_adapter import MemoryAdapter
from cache_layer.config import CacheConfig
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheConfigurationError
from cache_layer.factory import CacheFactory
from cache_layer.manager import CacheManager


def test_cache_config_defaults_and_validation():
    cfg = CacheConfig()
    assert cfg.backend == "memory"
    assert cfg.redis_port == 6379
    assert cfg.memcached_port == 11211

    # Invalid backend
    with pytest.raises(CacheConfigurationError, match="Unsupported cache backend"):
        CacheConfig(backend="unsupported_db")

    # Invalid port
    with pytest.raises(CacheConfigurationError, match="Invalid redis_port"):
        CacheConfig(redis_port=99999)

    # Invalid timeout
    with pytest.raises(CacheConfigurationError, match="timeout must be > 0"):
        CacheConfig(redis_timeout=-1.0)


def test_cache_config_from_env(monkeypatch):
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    monkeypatch.setenv("CACHE_REDIS_PORT", "6380")
    monkeypatch.setenv("CACHE_NAMESPACE", "myapp")

    cfg = CacheConfig.from_env()
    assert cfg.backend == "redis"
    assert cfg.redis_port == 6380
    assert cfg.namespace == "myapp"


def test_cache_factory_create_providers():
    # Memory
    mem_provider = CacheFactory.create_provider("memory")
    assert isinstance(mem_provider, MemoryAdapter)

    # Redis with mock
    mock_redis_client = MagicMock()
    redis_provider = CacheFactory.create_provider("redis", client=mock_redis_client)
    assert redis_provider.provider_name == "redis"

    # Memcached with mock
    mock_mc_client = MagicMock()
    mc_provider = CacheFactory.create_provider("memcached", client=mock_mc_client)
    assert mc_provider.provider_name == "memcached"

    # Unsupported
    with pytest.raises(CacheConfigurationError):
        CacheFactory.create_provider("unknown_backend")


def test_cache_factory_custom_registration():
    class DummyProvider(CacheProvider):
        @property
        def provider_name(self):
            return "dummy"

        def get(self, key):
            return None

        def set(self, key, value, ttl=None):
            return True

        def delete(self, key):
            return True

        def clear(self):
            return True

        def health_check(self):
            return {"status": "healthy", "provider": "dummy"}

        def close(self):
            pass

    CacheFactory.register_provider("dummy", DummyProvider)
    provider = CacheFactory.create_provider("dummy")
    assert provider.provider_name == "dummy"


def test_cache_manager_crud_and_metrics():
    provider = MemoryAdapter()
    manager = CacheManager(provider=provider, namespace="test", default_ttl=300)

    assert manager.hits == 0
    assert manager.misses == 0
    assert manager.hit_ratio == 0.0

    # Set items
    assert manager.set("user:1", {"name": "Bob"}) is True
    assert manager.set("user:2", "Alice") is True

    # Get hits
    assert manager.get("user:1") == {"name": "Bob"}
    assert manager.hits == 1
    assert manager.misses == 0
    assert manager.hit_ratio == 100.0

    # Get miss
    assert manager.get("missing") is None
    assert manager.hits == 1
    assert manager.misses == 1
    assert manager.hit_ratio == 50.0

    # Delete
    assert manager.delete("user:1") is True
    assert manager.get("user:1") is None
    assert manager.misses == 2

    # Stats
    stats = manager.stats()
    assert stats["provider"] == "memory"
    assert stats["namespace"] == "test"
    assert stats["hits"] == 1
    assert stats["misses"] == 2
    assert stats["total_reads"] == 3
    assert stats["sets"] == 2
    assert stats["deletes"] == 1
    assert "backend_stats" in stats

    # Clear
    assert manager.clear() is True
    assert manager.get("user:2") is None


def test_cache_manager_context_manager():
    provider = MemoryAdapter()
    with CacheManager(provider=provider) as manager:
        manager.set("k", "v")
        assert manager.get("k") == "v"
