"""Integration tests for Flask caching REST API endpoints."""

from unittest.mock import MagicMock
import pytest

from cache_layer.contract import CacheProvider
from cache_layer.adapters.memory_adapter import MemoryAdapter
from cache_layer.api import create_app
from cache_layer.exceptions import CacheConnectionError
from cache_layer.manager import CacheManager



@pytest.fixture
def client():
    provider = MemoryAdapter()
    manager = CacheManager(provider=provider, namespace="api_test")
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert data["service"] == "Universal-Cache-Manager"
    assert "endpoints" in data


def test_crud_endpoints(client):
    # 1. Miss
    res = client.get("/cache/user123")
    assert res.status_code == 404
    assert res.get_json()["error"] == "Key not found"

    # 2. Put / Post
    payload = {"value": {"name": "Alice", "age": 28}, "ttl": 300}
    res = client.put("/cache/user123", json=payload)
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"

    # 3. Get Hit
    res = client.get("/cache/user123")
    assert res.status_code == 200
    assert res.get_json()["value"] == {"name": "Alice", "age": 28}

    # 4. Delete Key
    res = client.delete("/cache/user123")
    assert res.status_code == 200
    assert res.get_json()["deleted"] is True

    # 5. Verify deleted
    res = client.get("/cache/user123")
    assert res.status_code == 404


def test_clear_endpoint(client):
    client.put("/cache/k1", json={"value": "val1"})
    client.put("/cache/k2", json={"value": "val2"})

    res = client.delete("/cache")
    assert res.status_code == 200
    assert res.get_json()["cleared"] is True

    assert client.get("/cache/k1").status_code == 404
    assert client.get("/cache/k2").status_code == 404


def test_stats_and_health_endpoints(client):
    # Generate some hits and misses
    client.put("/cache/counter", json={"value": 42})
    client.get("/cache/counter")
    client.get("/cache/nonexistent")

    # Stats
    res = client.get("/stats")
    assert res.status_code == 200
    stats = res.get_json()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    assert stats["provider"] == "memory"
    assert "hit_ratio_percent" in stats

    # Health
    res = client.get("/health")
    assert res.status_code == 200
    health = res.get_json()
    assert health["status"] == "healthy"
    assert health["provider"] == "memory"


def test_error_handling_validation(client):
    # Invalid key with spaces
    res = client.get("/cache/key%20with%20spaces")
    assert res.status_code == 400
    assert res.get_json()["error"] == "Validation Error"

    # Negative TTL
    res = client.put("/cache/key_with_neg_ttl", json={"value": "foo", "ttl": -10})
    assert res.status_code == 400
    assert res.get_json()["error"] == "Validation Error"


def test_error_handling_connection_error():
    mock_provider = MagicMock(spec=CacheProvider)
    mock_provider.provider_name = "failing_redis"
    mock_provider.get.side_effect = CacheConnectionError("Connection refused")
    manager = CacheManager(provider=mock_provider)
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True

    with app.test_client() as c:
        res = c.get("/cache/test_key")
        assert res.status_code == 503
        data = res.get_json()
        assert data["error"] == "Service Unavailable"

