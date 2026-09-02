"""Unit tests for MemoryAdapter."""

import concurrent.futures
import time
import pytest

from cache_layer.adapters.memory_adapter import MemoryAdapter


def test_memory_adapter_crud():
    adapter = MemoryAdapter()
    assert adapter.provider_name == "memory"

    # Set and Get
    assert adapter.set("key1", b"val1") is True
    assert adapter.get("key1") == b"val1"

    # Miss
    assert adapter.get("missing") is None

    # Delete
    assert adapter.delete("key1") is True
    assert adapter.get("key1") == b"val1" or adapter.get("key1") is None
    assert adapter.get("key1") is None

    # Clear
    adapter.set("k1", b"v1")
    adapter.set("k2", b"v2")
    assert adapter.clear() is True
    assert adapter.get("k1") is None
    assert adapter.get("k2") is None


def test_memory_adapter_ttl():
    adapter = MemoryAdapter()

    # Immediate expiry
    adapter.set("immediate", b"temp", ttl=0)
    assert adapter.get("immediate") is None

    # Short TTL expiry
    adapter.set("short_lived", b"data", ttl=1)
    assert adapter.get("short_lived") == b"data"

    time.sleep(1.1)
    assert adapter.get("short_lived") is None


def test_memory_adapter_lru_eviction():
    # Adapter with max_size 2
    adapter = MemoryAdapter(max_size=2)

    adapter.set("k1", b"v1")
    adapter.set("k2", b"v2")

    # Access k1 to make k2 least recently used
    assert adapter.get("k1") == b"v1"

    # Insert third key, which should trigger eviction of k2
    adapter.set("k3", b"v3")

    assert adapter.get("k1") == b"v1"
    assert adapter.get("k2") is None  # evicted
    assert adapter.get("k3") == b"v3"


def test_memory_adapter_stats_and_health():
    adapter = MemoryAdapter()
    adapter.set("alpha", b"12345")
    adapter.get("alpha")
    adapter.get("missing_key")

    stats = adapter.stats()
    assert stats["provider"] == "memory"
    assert stats["items_count"] == 1
    assert stats["bytes_used"] == 5
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    assert "uptime_seconds" in stats

    health = adapter.health_check()
    assert health["status"] == "healthy"
    assert health["provider"] == "memory"
    assert health["details"]["items_count"] == 1

    adapter.close()
    assert adapter.get("alpha") is None


def test_memory_adapter_concurrency():
    adapter = MemoryAdapter()

    def worker(worker_id):
        for i in range(50):
            key = f"thread_key_{worker_id}_{i}"
            adapter.set(key, f"val_{i}".encode("utf-8"), ttl=60)
            val = adapter.get(key)
            assert val == f"val_{i}".encode("utf-8")
            if i % 2 == 0:
                adapter.delete(key)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, w) for w in range(8)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert adapter.health_check()["status"] == "healthy"
