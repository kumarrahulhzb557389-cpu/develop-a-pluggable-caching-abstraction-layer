"""Tests for Phase 2: Advanced TTL expiration and batch operations across all backends."""

import time
from unittest.mock import MagicMock
import pytest

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.memory_adapter import MemoryAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.api import create_app
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheValidationError
from cache_layer.manager import CacheManager
from cache_layer.validation import validate_ttl


# ==========================================
# 1. TTL Validation Tests
# ==========================================

def test_ttl_validation_graceful_and_errors():
    # Valid TTLs
    assert validate_ttl(None) is None
    assert validate_ttl(0) == 0
    assert validate_ttl(60) == 60

    # Invalid TTLs
    with pytest.raises(CacheValidationError, match="must be an integer"):
        validate_ttl(True)

    with pytest.raises(CacheValidationError, match="must be an integer"):
        validate_ttl(False)

    with pytest.raises(CacheValidationError, match="cannot be negative"):
        validate_ttl(-10)

    with pytest.raises(CacheValidationError, match="must be an integer"):
        validate_ttl("-5")

    with pytest.raises(CacheValidationError, match="must be an integer"):
        validate_ttl("not_a_number")

    with pytest.raises(CacheValidationError, match="must be an integer"):
        validate_ttl(15.75)



# ==========================================
# 2. Memory Backend TTL & Batch Tests
# ==========================================

def test_memory_ttl_expiration_and_persistence():
    adapter = MemoryAdapter()

    # Normal SET without TTL (must persist)
    assert adapter.set("persistent", b"data1", ttl=None) is True
    assert adapter.get("persistent") == b"data1"

    # SET with TTL
    assert adapter.set("ephemeral", b"data2", ttl=1) is True
    assert adapter.get("ephemeral") == b"data2"

    # Expire after 1.1s
    time.sleep(1.1)
    assert adapter.get("ephemeral") is None
    # Persistent key still exists
    assert adapter.get("persistent") == b"data1"


def test_memory_batch_operations():
    adapter = MemoryAdapter()

    # Batch SET
    mapping = {"item:1": b"v1", "item:2": b"v2", "item:3": b"v3"}
    assert adapter.set_many(mapping, ttl=60) is True

    # Batch GET
    res = adapter.get_many(["item:1", "item:2", "item:3", "missing"])
    assert res["item:1"] == b"v1"
    assert res["item:2"] == b"v2"
    assert res["item:3"] == b"v3"
    assert res["missing"] is None

    # Batch DELETE
    assert adapter.delete_many(["item:1", "item:2"]) is True
    res2 = adapter.get_many(["item:1", "item:2", "item:3"])
    assert res2["item:1"] is None
    assert res2["item:2"] is None
    assert res2["item:3"] == b"v3"


# ==========================================
# 3. Redis Backend TTL & Batch Tests
# ==========================================

def test_redis_ttl_and_batch_mock():
    mock_client = MagicMock()
    mock_pipe = MagicMock()
    mock_client.pipeline.return_value = mock_pipe
    mock_client.mget.return_value = [b"v1", b"v2", None]

    adapter = RedisAdapter(client=mock_client)

    # SET with TTL (calls client.set with ex=60)
    adapter.set("k_ttl", b"v", ttl=60)
    mock_client.set.assert_called_once_with("k_ttl", b"v", ex=60)

    # SET without TTL (calls client.set without ex)
    mock_client.set.reset_mock()
    adapter.set("k_no_ttl", b"v", ttl=None)
    mock_client.set.assert_called_once_with("k_no_ttl", b"v")

    # Batch SET with TTL (uses pipeline)
    adapter.set_many({"a": b"1", "b": b"2"}, ttl=120)
    mock_client.pipeline.assert_called_once()
    assert mock_pipe.set.call_count == 2
    mock_pipe.execute.assert_called_once()

    # Batch SET without TTL (uses mset)
    mock_client.mset.reset_mock()
    adapter.set_many({"x": b"1", "y": b"2"}, ttl=None)
    mock_client.mset.assert_called_once_with({"x": b"1", "y": b"2"})

    # Batch GET
    res = adapter.get_many(["k1", "k2", "k3"])
    mock_client.mget.assert_called_once_with(["k1", "k2", "k3"])
    assert res == {"k1": b"v1", "k2": b"v2", "k3": None}

    # Batch DELETE
    adapter.delete_many(["k1", "k2"])
    mock_client.delete.assert_called_once_with("k1", "k2")


# ==========================================
# 4. Memcached Backend TTL & Batch Tests
# ==========================================

def test_memcached_ttl_and_batch_mock():
    mock_client = MagicMock()
    mock_client.get_many.return_value = {"k1": b"v1", "k2": b"v2"}
    mock_client.set_many.return_value = []

    adapter = MemcachedAdapter(client=mock_client)

    # SET with TTL (expire=60)
    adapter.set("k_ttl", b"v", ttl=60)
    mock_client.set.assert_called_once_with("k_ttl", b"v", expire=60)

    # SET without TTL (expire=0)
    mock_client.set.reset_mock()
    adapter.set("k_no_ttl", b"v", ttl=None)
    mock_client.set.assert_called_once_with("k_no_ttl", b"v", expire=0)

    # Batch SET with TTL
    adapter.set_many({"k1": b"v1", "k2": b"v2"}, ttl=90)
    mock_client.set_many.assert_called_once_with({"k1": b"v1", "k2": b"v2"}, expire=90)

    # Batch GET
    res = adapter.get_many(["k1", "k2", "missing"])
    mock_client.get_many.assert_called_once_with(["k1", "k2", "missing"])
    assert res["k1"] == b"v1"
    assert res["k2"] == b"v2"
    assert res["missing"] is None

    # Batch DELETE
    adapter.delete_many(["k1", "k2"])
    mock_client.delete_many.assert_called_once_with(["k1", "k2"])


# ==========================================
# 5. CacheManager Batch & Telemetry Tests
# ==========================================

def test_cache_manager_batch_metrics():
    provider = MemoryAdapter()
    manager = CacheManager(provider=provider, namespace="batch_test", default_ttl=300)

    # Batch SET with default TTL
    items = {"u1": {"name": "Alice"}, "u2": {"name": "Bob"}}
    assert manager.set_many(items) is True
    assert manager.stats()["sets"] == 2

    # Batch GET
    res = manager.get_many(["u1", "u2", "u3"])
    assert res["u1"] == {"name": "Alice"}
    assert res["u2"] == {"name": "Bob"}
    assert res["u3"] is None

    stats = manager.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["total_reads"] == 3
    assert stats["hit_ratio_percent"] == 66.67

    # Batch DELETE
    assert manager.delete_many(["u1", "u2"]) is True
    assert manager.stats()["deletes"] == 2


# ==========================================
# 6. Flask REST API Batch & TTL Tests
# ==========================================

@pytest.fixture
def api_client():
    provider = MemoryAdapter()
    manager = CacheManager(provider=provider, namespace="flask_test")
    app = create_app(cache_manager=manager)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_flask_single_key_ttl_example(api_client):
    # Example from prompt: POST /cache/user with value "Rahul" and ttl 60
    res = api_client.post("/cache/user", json={"value": "Rahul", "ttl": 60})
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"

    # Fetch
    get_res = api_client.get("/cache/user")
    assert get_res.status_code == 200
    assert get_res.get_json()["value"] == "Rahul"


def test_flask_invalid_ttl_handling(api_client):
    # Invalid TTL in body
    res1 = api_client.post("/cache/k1", json={"value": "foo", "ttl": "invalid_ttl"})
    assert res1.status_code == 400
    assert res1.get_json()["error"] == "Validation Error"

    # Negative TTL
    res2 = api_client.post("/cache/k2", json={"value": "foo", "ttl": -30})
    assert res2.status_code == 400
    assert res2.get_json()["error"] == "Validation Error"

    # Boolean TTL
    res3 = api_client.post("/cache/k3", json={"value": "foo", "ttl": True})
    assert res3.status_code == 400
    assert res3.get_json()["error"] == "Validation Error"


def test_flask_batch_endpoints(api_client):
    # Batch SET
    batch_payload = {
        "items": {
            "p1": {"name": "Laptop", "stock": 10},
            "p2": {"name": "Mouse", "stock": 50},
        },
        "ttl": 300,
    }
    set_res = api_client.post("/cache/batch/set", json=batch_payload)
    assert set_res.status_code == 200
    assert set_res.get_json()["count"] == 2

    # Batch GET
    get_res = api_client.post("/cache/batch/get", json={"keys": ["p1", "p2", "p3"]})
    assert get_res.status_code == 200
    vals = get_res.get_json()["values"]
    assert vals["p1"] == {"name": "Laptop", "stock": 10}
    assert vals["p2"] == {"name": "Mouse", "stock": 50}
    assert vals["p3"] is None

    # Batch DELETE
    del_res = api_client.post("/cache/batch/delete", json={"keys": ["p1", "p2"]})
    assert del_res.status_code == 200
    assert del_res.get_json()["deleted_count"] == 2

    # Verify deleted
    get_res2 = api_client.post("/cache/batch/get", json={"keys": ["p1", "p2"]})
    assert get_res2.get_json()["values"]["p1"] is None
    assert get_res2.get_json()["values"]["p2"] is None
