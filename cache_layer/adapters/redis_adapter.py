"""Redis backend adapter implementing CacheProvider contract with connection pooling."""

import time
from typing import Any, Dict, Optional

try:
    import redis  # type: ignore
    from redis.exceptions import (  # type: ignore
        BusyLoadingError,
        ConnectionError as RedisConnectionError,
        RedisError,
        TimeoutError as RedisTimeoutError,
    )
except ImportError:

    redis = None
    RedisConnectionError = Exception
    RedisTimeoutError = Exception
    BusyLoadingError = Exception
    RedisError = Exception

from cache_layer.contract import CacheProvider
from cache_layer.exceptions import (
    CacheBackendError,
    CacheConfigurationError,
    CacheConnectionError,
    CacheTimeoutError,
)


class RedisAdapter(CacheProvider):
    """Production-grade Redis adapter with connection pooling and normalized error mapping."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 2.0,
        socket_connect_timeout: float = 2.0,
        max_connections: int = 50,
        client: Optional[Any] = None,
    ):
        if redis is None and client is None:
            raise CacheConfigurationError("The 'redis' package is not installed.")

        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._max_connections = max_connections

        if client is not None:
            self._client = client
            self._pool = getattr(client, "connection_pool", None)
        else:
            self._pool = redis.ConnectionPool(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                socket_timeout=self._socket_timeout,
                socket_connect_timeout=self._socket_connect_timeout,
                max_connections=self._max_connections,
                decode_responses=False,  # Contract requires raw bytes
            )
            self._client = redis.Redis(connection_pool=self._pool)

    @property
    def provider_name(self) -> str:
        return "redis"

    def _handle_error(self, err: Exception, op_name: str) -> None:
        if isinstance(err, (RedisConnectionError, BusyLoadingError)):
            raise CacheConnectionError(
                f"Redis connection failed during {op_name}: {err}", original_error=err
            ) from err
        if isinstance(err, RedisTimeoutError):
            raise CacheTimeoutError(
                f"Redis operation timed out during {op_name}: {err}", original_error=err
            ) from err
        if isinstance(err, RedisError):
            raise CacheBackendError(
                f"Redis backend error during {op_name}: {err}", original_error=err
            ) from err
        raise CacheBackendError(
            f"Unexpected error in Redis adapter during {op_name}: {err}", original_error=err
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
            if ttl is not None and ttl > 0:
                result = self._client.set(key, value, ex=ttl)
            elif ttl == 0:
                # TTL 0 means immediate expiration
                self._client.delete(key)
                return True
            else:
                result = self._client.set(key, value)
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
            raw_values = self._client.mget(keys)
            result = {}
            for k, val in zip(keys, raw_values):
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
                self._client.delete(*mapping.keys())
                return True
            if ttl is not None and ttl > 0:
                pipe = self._client.pipeline()
                for k, v in mapping.items():
                    pipe.set(k, v, ex=ttl)
                pipe.execute()
            else:
                self._client.mset(mapping)
            return True
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "set_many")

    def delete_many(self, keys: list) -> bool:
        if not keys:
            return True
        try:
            self._client.delete(*keys)
            return True
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "delete_many")


    def clear(self) -> bool:
        try:
            self._client.flushdb()
            return True
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
    def stats(self) -> Dict[str, Any]:
        try:
            info = self._client.info()
            return {
                "provider": self.provider_name,
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "bytes_used": info.get("used_memory", 0),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "total_commands": info.get("total_commands_processed", 0),
                "raw": info,
            }
        except (CacheConnectionError, CacheTimeoutError, CacheBackendError):
            raise
        except Exception as err:
            self._handle_error(err, "stats")

    def health_check(self) -> Dict[str, Any]:
        start = time.perf_counter()
        try:
            ping_ok = self._client.ping()
            latency_ms = (time.perf_counter() - start) * 1000.0
            if ping_ok:
                server_version = "unknown"
                try:
                    info = self._client.info("server")
                    server_version = info.get("redis_version", "unknown")
                except Exception:
                    pass

                return {
                    "status": "healthy",
                    "backend": self.provider_name,
                    "provider": self.provider_name,
                    "latency_ms": round(latency_ms, 3),
                    "details": {
                        "host": self._host,
                        "port": self._port,
                        "db": self._db,
                        "server_version": server_version,
                    },
                }
            return {
                "status": "unhealthy",
                "backend": self.provider_name,
                "provider": self.provider_name,
                "latency_ms": round(latency_ms, 3),
                "details": {"error": "Ping returned False"},
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
            if self._pool is not None and hasattr(self._pool, "disconnect"):
                self._pool.disconnect()
        except Exception:
            pass
