"""Memcached backend adapter implementing CacheProvider contract with connection pooling."""

import socket
import time
from typing import Any, Dict, Optional

try:
    import pymemcache  # type: ignore
    from pymemcache.client.base import PooledClient  # type: ignore
    from pymemcache.exceptions import (  # type: ignore
        MemcacheClientError,
        MemcacheError,
        MemcacheServerError,
        MemcacheUnknownError,
    )
except ImportError:

    pymemcache = None
    PooledClient = None
    MemcacheError = Exception
    MemcacheClientError = Exception
    MemcacheServerError = Exception
    MemcacheUnknownError = Exception

from cache_layer.contract import CacheProvider
from cache_layer.exceptions import (
    CacheBackendError,
    CacheConfigurationError,
    CacheConnectionError,
    CacheTimeoutError,
)


class MemcachedAdapter(CacheProvider):
    """Production-grade Memcached adapter with connection pooling and normalized error mapping."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11211,
        connect_timeout: float = 2.0,
        timeout: float = 2.0,
        max_pool_size: int = 50,
        client: Optional[Any] = None,
    ):
        if pymemcache is None and client is None:
            raise CacheConfigurationError("The 'pymemcache' package is not installed.")

        self._host = host
        self._port = port
        self._connect_timeout = connect_timeout
        self._timeout = timeout
        self._max_pool_size = max_pool_size

        if client is not None:
            self._client = client
        else:
            self._client = PooledClient(
                server=(self._host, self._port),
                connect_timeout=self._connect_timeout,
                timeout=self._timeout,
                max_pool_size=self._max_pool_size,
                no_delay=True,
                ignore_exc=False,
                default_noreply=False,
            )

    @property
    def provider_name(self) -> str:
        return "memcached"

    def _handle_error(self, err: Exception, op_name: str) -> None:
        if isinstance(err, (socket.timeout, TimeoutError)):
            raise CacheTimeoutError(
                f"Memcached operation timed out during {op_name}: {err}", original_error=err
            ) from err

        if isinstance(err, (ConnectionRefusedError, ConnectionResetError, ConnectionError)):
            raise CacheConnectionError(
                f"Memcached connection failed during {op_name}: {err}", original_error=err
            ) from err

        if isinstance(err, MemcacheError):
            err_msg = str(err).lower()
            if "connection" in err_msg or "refused" in err_msg or "closed" in err_msg or "reset" in err_msg:
                raise CacheConnectionError(
                    f"Memcached connection error during {op_name}: {err}", original_error=err
                ) from err
            if "timeout" in err_msg or "timed out" in err_msg:
                raise CacheTimeoutError(
                    f"Memcached timeout during {op_name}: {err}", original_error=err
                ) from err
            raise CacheBackendError(
                f"Memcached error during {op_name}: {err}", original_error=err
            ) from err

        if isinstance(err, OSError):
            raise CacheConnectionError(
                f"Socket/OS error during Memcached {op_name}: {err}", original_error=err
            ) from err

        raise CacheBackendError(
            f"Unexpected error in Memcached adapter during {op_name}: {err}", original_error=err
        ) from err

    def get(self, key: str) -> Optional[bytes]:
        try:
            val = self._client.get(key)
            if val is None:
                return None
            if isinstance(val, memoryview):
                return val.tobytes()
            if isinstance(val, (bytes, bytearray)):
                return bytes(val)
            if isinstance(val, str):
                return val.encode("utf-8")
            return bytes(val)
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "get")

    def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        try:
            expire = ttl if ttl is not None else 0
            if ttl == 0:
                self._client.delete(key)
                return True
            result = self._client.set(key, value, expire=expire)
            return bool(result)
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "set")

    def delete(self, key: str) -> bool:
        try:
            self._client.delete(key)
            return True
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "delete")

    def get_many(self, keys: list) -> Dict[str, Optional[bytes]]:
        if not keys:
            return {}
        try:
            raw_map = self._client.get_many(keys)
            result = {}
            for k in keys:
                val = raw_map.get(k) if isinstance(raw_map, dict) else None
                if val is None:
                    result[k] = None
                elif isinstance(val, memoryview):
                    result[k] = val.tobytes()
                elif isinstance(val, (bytes, bytearray)):
                    result[k] = bytes(val)
                elif isinstance(val, str):
                    result[k] = val.encode("utf-8")
                else:
                    result[k] = bytes(val)
            return result
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "get_many")

    def set_many(self, mapping: Dict[str, bytes], ttl: Optional[int] = None) -> bool:
        if not mapping:
            return True
        try:
            if ttl == 0:
                for k in mapping.keys():
                    self._client.delete(k)
                return True
            expire = ttl if ttl is not None else 0
            failed_keys = self._client.set_many(mapping, expire=expire)
            return len(failed_keys) == 0 if isinstance(failed_keys, list) else True
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "set_many")

    def delete_many(self, keys: list) -> bool:
        if not keys:
            return True
        try:
            if hasattr(self._client, "delete_many"):
                self._client.delete_many(keys)
            else:
                for k in keys:
                    self._client.delete(k)
            return True
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "delete_many")


    def clear(self) -> bool:
        try:
            self._client.flush_all()
            return True
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "clear")

    def stats(self) -> Dict[str, Any]:
        try:
            raw_stats = self._client.stats()
            normalized = {}
            if isinstance(raw_stats, dict):
                for k, v in raw_stats.items():
                    key_str = k.decode("utf-8", errors="replace") if isinstance(k, (bytes, bytearray)) else str(k)
                    val_str = v.decode("utf-8", errors="replace") if isinstance(v, (bytes, bytearray)) else v
                    try:
                        normalized[key_str] = int(val_str)
                    except (ValueError, TypeError):
                        try:
                            normalized[key_str] = float(val_str)
                        except (ValueError, TypeError):
                            normalized[key_str] = val_str

            return {
                "provider": self.provider_name,
                "hits": normalized.get("get_hits", 0),
                "misses": normalized.get("get_misses", 0),
                "items_count": normalized.get("curr_items", 0),
                "bytes_used": normalized.get("bytes", 0),
                "uptime_seconds": normalized.get("uptime", 0),
                "total_commands": normalized.get("cmd_get", 0) + normalized.get("cmd_set", 0),
                "raw": normalized,
            }
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "stats")

    def health_check(self) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            stats = self._client.stats()
            latency_ms = (time.perf_counter() - start) * 1000.0
            return {
                "status": "healthy",
                "backend": self.provider_name,
                "provider": self.provider_name,
                "latency_ms": round(latency_ms, 3),
                "details": {
                    "host": self._host,
                    "port": self._port,
                    "server_version": (
                        stats.get(b"version", b"").decode("utf-8", errors="replace")
                        if isinstance(stats, dict)
                        else "unknown"
                    ),
                },
            }
        except Exception as err:
            latency_ms = (time.perf_counter() - start) * 1000.0
            return {
                "status": "unhealthy",
                "backend": self.provider_name,
                "provider": self.provider_name,
                "latency_ms": round(latency_ms, 3),
                "details": {
                    "host": self._host,
                    "port": self._port,
                    "error": str(err),
                    "error_type": type(err).__name__,
                },
            }


    def close(self) -> None:
        try:
            if hasattr(self._client, "close"):
                self._client.close()
        except Exception:
            pass
