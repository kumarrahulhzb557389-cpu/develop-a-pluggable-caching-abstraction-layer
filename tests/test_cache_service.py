"""Unit and integration tests for CacheService."""

from unittest.mock import MagicMock
import pytest

from cache_layer.contract import CacheProvider
from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.exceptions import (
    CacheConnectionError,
    CacheError,
    CacheValidationError,
)
from cache_layer.service import CacheService


class InMemoryMockProvider(CacheProvider):
    """In-memory mock provider conforming to CacheProvider contract."""

    def __init__(self, name="mock"):
        self._store = {}
        self._name = name
        self.closed = False

    @property
    def provider_name(self) -> str:
        return self._name

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: bytes, ttl=None):
        if ttl == 0:
            self._store.pop(key, None)
        else:
            self._store[key] = value
        return True

    def delete(self, key: str):
        self._store.pop(key, None)
        return True

    def clear(self):
        self._store.clear()
        return True

    def health_check(self):
        return {"status": "healthy", "provider": self._name}

    def close(self):
        self.closed = True


@pytest.mark.parametrize("provider_class", [RedisAdapter, MemcachedAdapter])
def test_cache_service_interchangeability(provider_class):
    mock_client = MagicMock()
    mock_store = {}

    def fake_get(k):
        return mock_store.get(k)

    def fake_set(k, v, **kwargs):
        mock_store[k] = v
        return True

    def fake_delete(k):
        mock_store.pop(k, None)
        return True

    def fake_clear(*args, **kwargs):
        mock_store.clear()
        return True

    mock_client.get.side_effect = fake_get
    mock_client.set.side_effect = fake_set
    mock_client.delete.side_effect = fake_delete
    mock_client.flushdb.side_effect = fake_clear
    mock_client.flush_all.side_effect = fake_clear
    mock_client.ping.return_value = True
    mock_client.stats.return_value = {}

    adapter = provider_class(client=mock_client)
    service = CacheService(provider=adapter, namespace="test_app")

    # Set and Get string
    assert service.set("user:1", "Alice") is True
    assert service.get("user:1") == "Alice"

    # Set and Get dict
    profile = {"age": 30, "roles": ["admin"]}
    assert service.set("user:1:profile", profile, ttl=300) is True
    assert service.get("user:1:profile") == profile

    # Miss
    assert service.get("user:999") is None

    # Delete
    assert service.delete("user:1") is True
    assert service.get("user:1") is None

    # Clear
    assert service.clear() is True
    assert service.get("user:1:profile") is None

    service.close()


def test_cache_service_validation():
    provider = InMemoryMockProvider()
    service = CacheService(provider=provider, namespace="app")

    # Invalid key with spaces
    with pytest.raises(CacheValidationError):
        service.get("invalid key")

    # Invalid TTL
    with pytest.raises(CacheValidationError):
        service.set("valid_key", "val", ttl=-10)

    # Empty key
    with pytest.raises(CacheValidationError):
        service.delete("")


def test_cache_service_context_manager():
    provider = InMemoryMockProvider()
    with CacheService(provider=provider) as service:
        service.set("k", 123)
        assert service.get("k") == 123
    assert provider.closed is True


def test_cache_service_stats():
    provider = InMemoryMockProvider()
    service = CacheService(provider=provider)
    stats = service.stats()
    assert stats["provider"] == "mock"

