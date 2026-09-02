"""Real multi-backend benchmarking engine for Universal-Cache-Manager."""

import time
from typing import Any, Dict, List, Optional

from cache_layer.config import CacheConfig
from cache_layer.factory import CacheFactory


class BenchmarkRunner:
    """Executes real performance benchmarks measuring latency and throughput across cache backends."""

    DEFAULT_BACKENDS = ["memory", "redis", "memcached"]

    @classmethod
    def run_benchmark(
        cls,
        backends: Optional[List[str]] = None,
        iterations: int = 50,
        config: Optional[CacheConfig] = None,
    ) -> Dict[str, Any]:
        """Run real, un-faked benchmark measuring SET, GET, and DELETE performance.

        Args:
            backends: List of backend names to benchmark (default: ['memory', 'redis', 'memcached']).
            iterations: Number of operations per stage (clamped between 10 and 1000).
            config: Optional CacheConfig instance.

        Returns:
            Dictionary containing real measured results, throughput, and status per backend.
        """
        # Clamp iterations to safe boundaries
        iterations = max(10, min(int(iterations), 1000))
        target_backends = backends or cls.DEFAULT_BACKENDS

        results: Dict[str, Any] = {}
        benchmark_timestamp = time.time()

        for backend_name in target_backends:
            clean_name = backend_name.lower().strip()
            results[clean_name] = cls._benchmark_single_backend(clean_name, iterations, config)

        return {
            "timestamp": benchmark_timestamp,
            "iterations": iterations,
            "results": results,
        }

    @classmethod
    def _benchmark_single_backend(
        cls,
        backend: str,
        iterations: int,
        config: Optional[CacheConfig] = None,
    ) -> Dict[str, Any]:
        """Execute real benchmark against a single backend."""
        provider = None
        try:
            cfg = config or CacheConfig.from_env()
            provider = CacheFactory.create_provider(backend=backend, config=cfg)
        except Exception as err:
            return {
                "available": False,
                "status": "unavailable",
                "backend": backend,
                "reason": f"Configuration / initialization failed: {str(err)}",
                "set_avg_ms": None,
                "get_avg_ms": None,
                "delete_avg_ms": None,
                "throughput_ops_sec": None,
            }

        # Step 1: Pre-flight health check
        health = provider.health_check()
        if health.get("status") != "healthy":
            try:
                provider.close()
            except Exception:
                pass
            return {
                "available": False,
                "status": "unavailable",
                "backend": backend,
                "reason": health.get("details", {}).get("error", "Backend health check failed"),
                "ping_latency_ms": health.get("latency_ms"),
                "set_avg_ms": None,
                "get_avg_ms": None,
                "delete_avg_ms": None,
                "throughput_ops_sec": None,
            }

        # Step 2: Real measured operations
        try:
            # 1. SET stage
            set_start = time.perf_counter()
            for i in range(iterations):
                provider.set(f"__bench__:{i}", f"payload_{i}".encode("utf-8"))
            set_duration = time.perf_counter() - set_start
            set_avg_ms = round((set_duration / iterations) * 1000.0, 4)

            # 2. GET stage
            get_start = time.perf_counter()
            for i in range(iterations):
                provider.get(f"__bench__:{i}")
            get_duration = time.perf_counter() - get_start
            get_avg_ms = round((get_duration / iterations) * 1000.0, 4)

            # 3. DELETE stage
            del_start = time.perf_counter()
            for i in range(iterations):
                provider.delete(f"__bench__:{i}")
            del_duration = time.perf_counter() - del_start
            del_avg_ms = round((del_duration / iterations) * 1000.0, 4)

            total_ops = iterations * 3
            total_duration = set_duration + get_duration + del_duration
            throughput = round(total_ops / total_duration, 2) if total_duration > 0 else 0.0

            return {
                "available": True,
                "status": "healthy",
                "backend": backend,
                "iterations": iterations,
                "ping_latency_ms": health.get("latency_ms", 0.0),
                "set_avg_ms": set_avg_ms,
                "get_avg_ms": get_avg_ms,
                "delete_avg_ms": del_avg_ms,
                "throughput_ops_sec": throughput,
                "total_time_ms": round(total_duration * 1000.0, 2),
            }
        except Exception as err:
            return {
                "available": False,
                "status": "error",
                "backend": backend,
                "reason": f"Benchmark execution error: {str(err)}",
                "set_avg_ms": None,
                "get_avg_ms": None,
                "delete_avg_ms": None,
                "throughput_ops_sec": None,
            }
        finally:
            try:
                # Cleanup any remaining keys
                for i in range(iterations):
                    provider.delete(f"__bench__:{i}")
                provider.close()
            except Exception:
                pass
