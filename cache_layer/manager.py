import copy
import threading
import time
from typing import Any, Dict, Optional

from cache_layer.config import CacheConfig
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheConnectionError, CacheValidationError
from cache_layer.serializer import Serializer
from cache_layer.service import CacheService
from cache_layer.validation import validate_ttl


class CacheManager(CacheService):
    """Unified application-facing cache manager.

    Extends CacheService by tracking operational metrics:
    - hits, misses, hit ratio percentage
    - total reads, sets, deletes, clears
    - default TTL handling
    - unified stats() merging manager metrics with provider metrics
    """

    def __init__(
        self,
        provider: CacheProvider,
        serializer: Optional[Serializer] = None,
        namespace: Optional[str] = None,
        default_ttl: Optional[int] = None,
        config: Optional[CacheConfig] = None,
    ):
        super().__init__(provider=provider, serializer=serializer, namespace=namespace)
        self._default_ttl = validate_ttl(default_ttl)
        self._config = config
        self._lock = threading.RLock()

        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._deletes = 0
        self._clears = 0
        self._started_at = time.time()

    @property
    def default_ttl(self) -> Optional[int]:
        """Default TTL in seconds when none is provided to set()."""
        return self._default_ttl

    @property
    def hits(self) -> int:
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        with self._lock:
            return self._misses

    @property
    def hit_ratio(self) -> float:
        with self._lock:
            total = self._hits + self._misses
            return round((self._hits / total) * 100.0, 2) if total > 0 else 0.0

    def get(self, key: str) -> Any:
        val = super().get(key)
        with self._lock:
            if val is not None:
                self._hits += 1
            else:
                self._misses += 1
        return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        success = super().set(key, value, ttl=effective_ttl)
        if success:
            with self._lock:
                self._sets += 1
        return success

    def delete(self, key: str) -> bool:
        success = super().delete(key)
        if success:
            with self._lock:
                self._deletes += 1
        return success

    def get_many(self, keys: list) -> Dict[str, Any]:
        results = super().get_many(keys)
        with self._lock:
            for val in results.values():
                if val is not None:
                    self._hits += 1
                else:
                    self._misses += 1
        return results

    def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        success = super().set_many(mapping, ttl=effective_ttl)
        if success:
            with self._lock:
                self._sets += len(mapping)
        return success

    def delete_many(self, keys: list) -> bool:
        success = super().delete_many(keys)
        if success:
            with self._lock:
                self._deletes += len(keys)
        return success


    def clear(self) -> bool:
        success = super().clear()
        if success:
            with self._lock:
                self._clears += 1
        return success

    def stats(self) -> Dict[str, Any]:
        """Return aggregated cache statistics."""
        with self._lock:
            total_reads = self._hits + self._misses
            hit_ratio = round((self._hits / total_reads) * 100.0, 2) if total_reads > 0 else 0.0
            uptime = round(time.time() - self._started_at, 2)

            backend_stats = {}
            try:
                backend_stats = self._provider.stats()
            except Exception:
                backend_stats = {"provider": self.provider_name}

            return {
                "provider": self.provider_name,
                "namespace": self.namespace,
                "uptime_seconds": uptime,
                "hits": self._hits,
                "misses": self._misses,
                "total_reads": total_reads,
                "hit_ratio_percent": hit_ratio,
                "sets": self._sets,
                "deletes": self._deletes,
                "clears": self._clears,
                "backend_stats": backend_stats,
            }

    @property
    def config(self) -> Optional[CacheConfig]:
        """The configuration associated with this CacheManager."""
        return self._config

    def switch_backend(self, backend: str, config: Optional[CacheConfig] = None) -> CacheProvider:
        """Dynamically switch the underlying cache provider backend.

        Args:
            backend: Target backend name ('memory', 'redis', 'memcached', or custom registered).
            config: Optional configuration overrides.

        Returns:
            The newly active CacheProvider.

        Raises:
            CacheValidationError: If backend name is invalid.
            CacheConnectionError: If target backend is unavailable / fails health check.
        """
        if not isinstance(backend, str) or not backend.strip():
            raise CacheValidationError("Backend name must be a non-empty string")

        backend_clean = backend.lower().strip()
        from cache_layer.factory import CacheFactory
        available = CacheFactory.get_available_backends()
        if backend_clean not in available:
            raise CacheValidationError(
                f"Unsupported or unavailable backend: '{backend}'. Available backends: {available}"
            )

        cfg = config or self._config
        if cfg is not None:
            cfg_clone = copy.copy(cfg)
            cfg_clone.backend = backend_clean
        else:
            cfg_clone = None

        candidate = CacheFactory.create_provider(backend=backend_clean, config=cfg_clone)

        # Pre-flight health check before making any switch
        health = candidate.health_check()
        if health.get("status") != "healthy":
            try:
                candidate.close()
            except Exception:
                pass
            error_msg = health.get("details", {}).get("error", "Target backend health check failed")
            raise CacheConnectionError(f"Target backend '{backend_clean}' is unavailable: {error_msg}")

        # Hot-swap provider safely under lock
        with self._lock:
            old_provider = self._provider
            self._provider = candidate
            if cfg_clone is not None:
                self._config = cfg_clone
            try:
                old_provider.close()
            except Exception:
                pass

        return candidate

