"""In-memory cache adapter implementing CacheProvider contract with TTL and LRU eviction."""

import threading
import time
from typing import Any, Dict, Optional, Tuple

from cache_layer.contract import CacheProvider


class MemoryAdapter(CacheProvider):
    """Thread-safe, in-process in-memory cache adapter.

    Features:
    - Thread-safe access protected by RLock.
    - Automatic TTL expiration (lazy and on-demand).
    - LRU eviction when capacity exceeds max_size.
    - Direct binary payload storage conforming to the unified CacheProvider contract.
    """

    def __init__(self, max_size: int = 10000):
        self._max_size = max_size
        # Store mapping: key -> (value_bytes, expiry_timestamp, last_accessed_timestamp)
        self._store: Dict[str, Tuple[bytes, Optional[float], float]] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._deletes = 0
        self._created_at = time.time()

    @property
    def provider_name(self) -> str:
        return "memory"

    def _evict_if_needed(self) -> None:
        """Evict expired items first, or the least recently accessed item if full."""
        now = time.time()
        # Step 1: Evict expired keys
        expired_keys = [
            k for k, (_, expiry, _) in self._store.items()
            if expiry is not None and now >= expiry
        ]
        for k in expired_keys:
            del self._store[k]

        # Step 2: If still at or over max_size, evict least recently accessed
        if len(self._store) >= self._max_size and self._store:
            oldest_key = min(self._store.keys(), key=lambda k: self._store[k][2])
            del self._store[oldest_key]

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            val, expiry, _ = entry
            now = time.time()
            if expiry is not None and now >= expiry:
                del self._store[key]
                self._misses += 1
                return None

            # Update last accessed time
            self._store[key] = (val, expiry, now)
            self._hits += 1
            return val

    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        with self._lock:
            if ttl == 0:
                self._store.pop(key, None)
                self._sets += 1
                return True

            if key not in self._store and len(self._store) >= self._max_size:
                self._evict_if_needed()

            now = time.time()
            expiry = (now + ttl) if (ttl is not None and ttl > 0) else None
            self._store[key] = (bytes(value), expiry, now)
            self._sets += 1
            return True

    def delete(self, key: str) -> bool:
        with self._lock:
            self._store.pop(key, None)
            self._deletes += 1
            return True

    def get_many(self, keys: list) -> Dict[str, Optional[bytes]]:
        with self._lock:
            return {k: self.get(k) for k in keys}

    def set_many(self, mapping: Dict[str, bytes], ttl: Optional[int] = None) -> bool:
        with self._lock:
            for k, v in mapping.items():
                self.set(k, v, ttl=ttl)
            return True

    def delete_many(self, keys: list) -> bool:
        with self._lock:
            for k in keys:
                self.delete(k)
            return True

    def clear(self) -> bool:
        with self._lock:
            self._store.clear()
            return True


    def stats(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            # Clean up expired items during stats inspection
            expired = [
                k for k, (_, exp, _) in self._store.items()
                if exp is not None and now >= exp
            ]
            for k in expired:
                del self._store[k]

            total_items = len(self._store)
            bytes_used = sum(len(v[0]) for v in self._store.values())
            return {
                "provider": self.provider_name,
                "items_count": total_items,
                "bytes_used": bytes_used,
                "hits": self._hits,
                "misses": self._misses,
                "sets": self._sets,
                "deletes": self._deletes,
                "uptime_seconds": round(now - self._created_at, 2),
            }

    def health_check(self) -> Dict[str, Any]:
        with self._lock:
            bytes_used = sum(len(v[0]) for v in self._store.values())
            return {
                "status": "healthy",
                "backend": self.provider_name,
                "provider": self.provider_name,
                "latency_ms": 0.01,
                "details": {
                    "items_count": len(self._store),
                    "bytes_used": bytes_used,
                    "max_size": self._max_size,
                },
            }


    def close(self) -> None:
        with self._lock:
            self._store.clear()
