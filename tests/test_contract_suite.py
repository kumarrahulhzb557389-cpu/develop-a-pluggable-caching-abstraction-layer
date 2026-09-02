"""Universal contract test suite executed identically against all cache providers."""

from unittest.mock import MagicMock
import pytest

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.service import CacheService


def create_mock_adapter(adapter_cls):
    """Create an adapter backed by a simulated memory store."""
    mock_client = MagicMock()
    store = {}

    def fake_get(key):
        return store.get(key)

    def fake_set(key, value, **kwargs):
        store[key] = value
        return True

    def fake_delete(key):
        store.pop(key, None)
        return True

    def fake_clear(*args, **kwargs):
        store.clear()
        return True

    mock_client.get.side_effect = fake_get
    mock_client.set.side_effect = fake_set
    mock_client.delete.side_effect = fake_delete
    mock_client.flushdb.side_effect = fake_clear
    mock_client.flush_all.side_effect = fake_clear
    mock_client.ping.return_value = True
    mock_client.stats.return_value = {b"version": b"1.6.9"}

    return adapter_cls(client=mock_client)


@pytest.fixture(params=[RedisAdapter, MemcachedAdapter], ids=["RedisAdapter", "MemcachedAdapter"])
def provider(request):
    adapter = create_mock_adapter(request.param)
    yield adapter
    adapter.close()


def test_contract_basic_crud(provider):
    """Verify that every provider satisfies standard CRUD contract."""
    service = CacheService(provider=provider, namespace="contract_test")

    # 1. Miss
    assert service.get("missing_key") is None

    # 2. String value
    assert service.set("str_key", "hello_world") is True
    assert service.get("str_key") == "hello_world"

    # 3. Numeric primitives
    assert service.set("int_key", 100) is True
    assert service.get("int_key") == 100
    assert type(service.get("int_key")) is int

    assert service.set("float_key", 99.99) is True
    assert service.get("float_key") == 99.99
    assert type(service.get("float_key")) is float

    # 4. Boolean (distinct from int 1/0)
    assert service.set("bool_key", True) is True
    assert service.get("bool_key") is True
    assert type(service.get("bool_key")) is bool

    # 5. Complex JSON nested structures
    nested = {
        "user": {"id": 1, "tags": ["admin", "beta"]},
        "active": True,
        "count": 42,
    }
    assert service.set("nested_key", nested) is True
    assert service.get("nested_key") == nested

    # 6. Binary payload
    raw_bytes = b"\x00\xff\x10\x20 binary test"
    assert service.set("bytes_key", raw_bytes) is True
    assert service.get("bytes_key") == raw_bytes

    # 7. Delete
    assert service.delete("str_key") is True
    assert service.get("str_key") is None

    # 8. Clear
    assert service.clear() is True
    assert service.get("nested_key") is None
    assert service.get("bytes_key") is None


def test_contract_health_check(provider):
    """Verify that every provider reports standardized health information."""
    health = provider.health_check()
    assert isinstance(health, dict)
    assert "status" in health
    assert "provider" in health
    assert health["provider"] in ("redis", "memcached")
    assert "latency_ms" in health
