"""Unit and integration tests for the benchmarking engine and endpoint."""

import pytest

from cache_layer.api import create_app
from cache_layer.benchmark import BenchmarkRunner
from cache_layer.config import CacheConfig
from cache_layer.manager import CacheManager
from cache_layer.adapters.memory_adapter import MemoryAdapter


def test_benchmark_runner_memory_execution():
    cfg = CacheConfig(backend="memory")
    results = BenchmarkRunner.run_benchmark(backends=["memory"], iterations=25, config=cfg)

    assert "timestamp" in results
    assert results["iterations"] == 25
    assert "memory" in results["results"]

    mem = results["results"]["memory"]
    assert mem["available"] is True
    assert mem["status"] == "healthy"
    assert isinstance(mem["set_avg_ms"], float)
    assert isinstance(mem["get_avg_ms"], float)
    assert isinstance(mem["delete_avg_ms"], float)
    assert mem["throughput_ops_sec"] > 0
    assert mem["iterations"] == 25


def test_benchmark_runner_handles_unavailable_backend():
    # Attempt benchmark on an offline / invalid port
    cfg = CacheConfig(backend="redis", redis_port=6398, redis_timeout=0.2, redis_connect_timeout=0.2)
    results = BenchmarkRunner.run_benchmark(backends=["redis"], iterations=10, config=cfg)

    assert "redis" in results["results"]
    red = results["results"]["redis"]
    assert red["available"] is False
    assert red["status"] == "unavailable"
    assert "reason" in red
    assert red["set_avg_ms"] is None


def test_benchmark_api_endpoint():
    cfg = CacheConfig(backend="memory")
    manager = CacheManager(provider=MemoryAdapter(), config=cfg)
    app = create_app(cache_manager=manager, config=cfg)
    app.config["TESTING"] = True

    with app.test_client() as client:
        # Successful benchmark run
        res = client.post("/benchmark/run", json={"iterations": 15, "backends": ["memory"]})
        assert res.status_code == 200
        data = res.get_json()
        assert "memory" in data["results"]
        assert data["results"]["memory"]["available"] is True

        # Invalid iterations
        res2 = client.post("/benchmark/run", json={"iterations": "not_an_int"})
        assert res2.status_code == 400
        assert res2.get_json()["error"] == "Validation Error"
