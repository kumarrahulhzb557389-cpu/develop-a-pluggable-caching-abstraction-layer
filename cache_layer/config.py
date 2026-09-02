"""Configuration models and environment parser for the cache layer."""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from cache_layer.exceptions import CacheConfigurationError

DEFAULT_SUPPORTED_BACKENDS = {"redis", "memcached"}
_registered_backends: Set[str] = set(DEFAULT_SUPPORTED_BACKENDS)


def register_backend_name(name: str) -> None:
    """Register a backend name as valid in config validation."""
    _registered_backends.add(name.lower().strip())


@dataclass
class RedisConfig:
    """Configuration parameters for Redis backend."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    socket_timeout: float = 2.0
    socket_connect_timeout: float = 2.0
    max_connections: int = 50

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RedisConfig":
        return cls(
            host=str(data.get("host", "localhost")),
            port=int(data.get("port", 6379)),
            db=int(data.get("db", 0)),
            password=data.get("password"),
            socket_timeout=float(data.get("socket_timeout", 2.0)),
            socket_connect_timeout=float(data.get("socket_connect_timeout", 2.0)),
            max_connections=int(data.get("max_connections", 50)),
        )


@dataclass
class MemcachedConfig:
    """Configuration parameters for Memcached backend."""

    host: str = "localhost"
    port: int = 11211
    connect_timeout: float = 2.0
    timeout: float = 2.0
    max_pool_size: int = 50

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemcachedConfig":
        return cls(
            host=str(data.get("host", "localhost")),
            port=int(data.get("port", 11211)),
            connect_timeout=float(data.get("connect_timeout", 2.0)),
            timeout=float(data.get("timeout", 2.0)),
            max_pool_size=int(data.get("max_pool_size", 50)),
        )


@dataclass
class CacheConfig:
    """Top-level caching configuration."""

    backend: str = "redis"
    namespace: Optional[str] = None
    redis: RedisConfig = field(default_factory=RedisConfig)
    memcached: MemcachedConfig = field(default_factory=MemcachedConfig)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate configuration settings.

        Raises:
            CacheConfigurationError: If any configuration value is invalid.
        """
        if not self.backend or not self.backend.strip():
            raise CacheConfigurationError("Cache backend must be specified ('redis' or 'memcached').")

        backend_lower = self.backend.lower().strip()
        if backend_lower not in _registered_backends:
            raise CacheConfigurationError(
                f"Unsupported cache backend '{self.backend}'. Supported backends: {sorted(list(_registered_backends))}"
            )
        self.backend = backend_lower

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheConfig":
        """Load configuration from a Python dictionary."""
        backend = data.get("backend", "redis")
        namespace = data.get("namespace")

        redis_data = data.get("redis", {})
        memcached_data = data.get("memcached", {})

        redis_cfg = RedisConfig.from_dict(redis_data) if isinstance(redis_data, dict) else RedisConfig()
        memcached_cfg = MemcachedConfig.from_dict(memcached_data) if isinstance(memcached_data, dict) else MemcachedConfig()

        return cls(
            backend=backend,
            namespace=namespace,
            redis=redis_cfg,
            memcached=memcached_cfg,
        )

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "CacheConfig":
        """Load configuration from environment variables."""
        if env is None:
            env = os.environ

        backend = env.get("CACHE_BACKEND", "redis").lower().strip()
        namespace = env.get("CACHE_NAMESPACE")

        # Redis environment overrides
        redis_host = env.get("REDIS_HOST", "localhost")
        redis_port = int(env.get("REDIS_PORT", "6379"))
        redis_db = int(env.get("REDIS_DB", "0"))
        redis_password = env.get("REDIS_PASSWORD")
        redis_timeout = float(env.get("REDIS_SOCKET_TIMEOUT", "2.0"))
        redis_conn_timeout = float(env.get("REDIS_SOCKET_CONNECT_TIMEOUT", "2.0"))
        redis_max_conns = int(env.get("REDIS_MAX_CONNECTIONS", "50"))

        redis_cfg = RedisConfig(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            socket_timeout=redis_timeout,
            socket_connect_timeout=redis_conn_timeout,
            max_connections=redis_max_conns,
        )

        # Memcached environment overrides
        memcached_host = env.get("MEMCACHED_HOST", "localhost")
        memcached_port = int(env.get("MEMCACHED_PORT", "11211"))
        memcached_conn_timeout = float(env.get("MEMCACHED_CONNECT_TIMEOUT", "2.0"))
        memcached_timeout = float(env.get("MEMCACHED_TIMEOUT", "2.0"))
        memcached_max_pool = int(env.get("MEMCACHED_MAX_POOL_SIZE", "50"))

        memcached_cfg = MemcachedConfig(
            host=memcached_host,
            port=memcached_port,
            connect_timeout=memcached_conn_timeout,
            timeout=memcached_timeout,
            max_pool_size=memcached_max_pool,
        )

        return cls(
            backend=backend,
            namespace=namespace,
            redis=redis_cfg,
            memcached=memcached_cfg,
        )
