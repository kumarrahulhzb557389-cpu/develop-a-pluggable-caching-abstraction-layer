"""Interactive and automated Demo Script for the Pluggable Caching Abstraction Layer.

Demonstrates:
1. Identical cache operations on Redis.
2. Configuration-driven runtime switch to Memcached.
3. Identical cache operations on Memcached (Zero application code changes).
4. Live TTL expiration.
5. Controlled backend failure simulation & normalized error recovery.
"""

import sys
import time
from typing import Any
from unittest.mock import MagicMock

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.config import CacheConfig
from cache_layer.exceptions import (
    CacheConnectionError,
    CacheError,
    CacheTimeoutError,
    CacheValidationError,
)
from cache_layer.factory import ProviderFactory
from cache_layer.service import CacheService


def create_simulated_backend(name: str):
    """Create an in-memory simulated adapter for self-contained demonstration."""
    mock_client = MagicMock()
    store = {}
    expirations = {}

    def fake_get(k):
        if k in expirations and time.time() > expirations[k]:
            store.pop(k, None)
            expirations.pop(k, None)
            return None
        return store.get(k)

    def fake_set(k, v, **kwargs):
        ttl = kwargs.get("ex") or kwargs.get("expire")
        if ttl:
            expirations[k] = time.time() + ttl
        else:
            expirations.pop(k, None)
        store[k] = v
        return True

    def fake_delete(k):
        store.pop(k, None)
        expirations.pop(k, None)
        return True

    def fake_clear(*args, **kwargs):
        store.clear()
        expirations.clear()
        return True

    mock_client.get.side_effect = fake_get
    mock_client.set.side_effect = fake_set
    mock_client.delete.side_effect = fake_delete
    mock_client.flushdb.side_effect = fake_clear
    mock_client.flush_all.side_effect = fake_clear
    mock_client.ping.return_value = True
    mock_client.stats.return_value = {b"version": b"1.6.9"}

    if name == "redis":
        return RedisAdapter(client=mock_client)
    else:
        return MemcachedAdapter(client=mock_client)


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(step_num: int, title: str):
    print(f"\n[Step {step_num}] {title}")
    print("-" * 50)


def execute_standard_cache_workload(cache: CacheService):
    """Executes a standard set of cache operations against whatever backend is active."""
    print(f"  > Active Provider: [{cache.provider_name.upper()}] (Namespace: '{cache.namespace}')")

    # 1. Health check
    health = cache.health_check()
    print(f"  > Health Check: Status={health.get('status')}, Latency={health.get('latency_ms', 0):.2f}ms")

    # 2. Store primitive types
    print("  > Storing primitives (str, int, bool)...")
    cache.set("app:session_id", "sess_987654321")
    cache.set("app:login_attempts", 3)
    cache.set("app:is_authenticated", True)

    print(f"    - app:session_id       -> '{cache.get('app:session_id')}'")
    print(f"    - app:login_attempts   -> {cache.get('app:login_attempts')} (type: {type(cache.get('app:login_attempts')).__name__})")
    print(f"    - app:is_authenticated -> {cache.get('app:is_authenticated')} (type: {type(cache.get('app:is_authenticated')).__name__})")

    # 3. Store complex JSON document
    print("  > Storing complex nested document...")
    user_payload = {
        "user_id": 101,
        "name": "Sarah Connor",
        "roles": ["admin", "security"],
        "preferences": {"theme": "dark", "notifications": True},
    }
    cache.set("user:101:profile", user_payload)
    retrieved = cache.get("user:101:profile")
    print(f"    - Retrieved payload: {retrieved}")
    assert retrieved == user_payload, "Payload mismatch!"

    # 4. Delete operation
    print("  > Deleting 'app:session_id'...")
    cache.delete("app:session_id")
    print(f"    - Verify deletion: cache.get('app:session_id') -> {cache.get('app:session_id')}")


def run_demo(use_live_backends: bool = False):
    print_banner("PLUGGABLE CACHING ABSTRACTION LAYER - DEMO HARNESS")
    print("Zero application code changes when switching between Redis and Memcached.")

    # -------------------------------------------------------------
    # Step 1: Redis Backend
    # -------------------------------------------------------------
    print_step(1, "Executing Cache Operations on REDIS Backend")
    if use_live_backends:
        redis_provider = ProviderFactory.create_provider({"backend": "redis"})
    else:
        redis_provider = create_simulated_backend("redis")

    redis_cache = CacheService(provider=redis_provider, namespace="demo_app")
    execute_standard_cache_workload(redis_cache)

    # -------------------------------------------------------------
    # Step 2: Configuration-driven Backend Switch
    # -------------------------------------------------------------
    print_step(2, "Switching Configuration to MEMCACHED")
    print("  Configuration Change: CACHE_BACKEND = 'memcached'")
    print("  Application code remains 100% UNCHANGED.")

    if use_live_backends:
        memcached_provider = ProviderFactory.create_provider({"backend": "memcached"})
    else:
        memcached_provider = create_simulated_backend("memcached")

    memcached_cache = CacheService(provider=memcached_provider, namespace="demo_app")

    # -------------------------------------------------------------
    # Step 3: Memcached Backend (Identical Application Code)
    # -------------------------------------------------------------
    print_step(3, "Executing Identical Cache Operations on MEMCACHED")
    execute_standard_cache_workload(memcached_cache)

    # -------------------------------------------------------------
    # Step 4: TTL Expiration Demonstration
    # -------------------------------------------------------------
    print_step(4, "Demonstrating Time-To-Live (TTL) Expiration")
    ttl_seconds = 2
    key = "transient_otp_token"
    print(f"  > Setting key '{key}' with TTL = {ttl_seconds} seconds...")
    memcached_cache.set(key, "OTP-948201", ttl=ttl_seconds)

    print(f"  > Immediate read (T+0.0s): value = '{memcached_cache.get(key)}' (HIT)")
    print(f"  > Waiting {ttl_seconds + 0.5} seconds for TTL expiration...")
    time.sleep(ttl_seconds + 0.5)

    expired_val = memcached_cache.get(key)
    print(f"  > Read after expiry (T+{ttl_seconds + 0.5}s): value = {expired_val} (MISS / Expired)")
    assert expired_val is None, "Key should have expired!"

    # -------------------------------------------------------------
    # Step 5: Controlled Failure Injection & Normalized Error Handling
    # -------------------------------------------------------------
    print_step(5, "Controlled Backend Failure Simulation & Error Normalization")
    print("  > Simulating connection drop on downstream provider...")

    failing_client = MagicMock()
    failing_client.get.side_effect = ConnectionRefusedError("Connection refused by cache host:6379")
    failing_adapter = RedisAdapter(client=failing_client)
    failing_cache = CacheService(provider=failing_adapter)

    try:
        failing_cache.get("any_key")
        print("  [ERROR] Should have raised normalized exception!")
    except CacheConnectionError as exc:
        print(f"  > Caught Normalized Exception: {type(exc).__name__}")
        print(f"    Message: {exc}")
        print("  > Provider-specific exception successfully normalized! Application remains resilient.")

    # Validation Error Demonstration
    print("\n  > Simulating invalid key validation...")
    try:
        failing_cache.get("bad key with spaces\n")
    except CacheValidationError as exc:
        print(f"  > Caught Normalized Exception: {type(exc).__name__}")
        print(f"    Message: {exc}")

    # Cleanup
    redis_cache.close()
    memcached_cache.close()

    print_banner("DEMO COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    live_mode = "--live" in sys.argv
    run_demo(use_live_backends=live_mode)
