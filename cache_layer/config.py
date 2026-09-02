"""Configuration model and environment loader for the cache layer."""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from cache_layer.exceptions import CacheConfigurationError


SUPPORTED_BACKENDS = {"memory", "redis", "memcached"}


@dataclass
class CacheConfig:
    """Configuration settings for cache providers and cache service."""

    backend: str = "memory"
    # Redis specific settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_timeout: float = 2.0
    redis_connect_timeout: float = 2.0
    redis_max_connections: int = 50

    # Memcached specific settings
    memcached_host: str = "localhost"
    memcached_port: int = 11211
    memcached_timeout: float = 2.0
    memcached_connect_timeout: float = 2.0
    memcached_max_pool_size: int = 50

    # Memory specific settings
    memory_max_size: int = 10000

    # General cache settings
    namespace: Optional[str] = None
    default_ttl: Optional[int] = None

    # Security settings
    api_key: Optional[str] = None
    admin_rate_limit: int = 60

    def __post_init__(self) -> None:
        self.validate()


    def validate(self) -> None:
        """Validate configuration parameters.

        Raises:
            CacheConfigurationError: If any configuration value is invalid.
        """
        if not isinstance(self.backend, str):
            raise CacheConfigurationError(f"Backend must be a string, got {type(self.backend).__name__}")

        backend_lower = self.backend.lower().strip()
        if backend_lower not in SUPPORTED_BACKENDS:
            raise CacheConfigurationError(
                f"Unsupported cache backend: '{self.backend}'. Supported backends: {sorted(SUPPORTED_BACKENDS)}"
            )
        self.backend = backend_lower

        if not (1 <= self.redis_port <= 65535):
            raise CacheConfigurationError(f"Invalid redis_port: {self.redis_port}")

        if not (1 <= self.memcached_port <= 65535):
            raise CacheConfigurationError(f"Invalid memcached_port: {self.memcached_port}")

        if self.redis_timeout <= 0:
            raise CacheConfigurationError(f"redis_timeout must be > 0, got {self.redis_timeout}")

        if self.memcached_timeout <= 0:
            raise CacheConfigurationError(f"memcached_timeout must be > 0, got {self.memcached_timeout}")

        if self.memory_max_size <= 0:
            raise CacheConfigurationError(f"memory_max_size must be > 0, got {self.memory_max_size}")

        if self.default_ttl is not None and self.default_ttl < 0:
            raise CacheConfigurationError(f"default_ttl cannot be negative: {self.default_ttl}")

    @classmethod
    def from_env(cls) -> "CacheConfig":
        """Construct CacheConfig from environment variables."""
        backend = os.getenv("CACHE_BACKEND", "memory")

        redis_host = os.getenv("CACHE_REDIS_HOST", "localhost")
        try:
            redis_port = int(os.getenv("CACHE_REDIS_PORT", "6379"))
        except ValueError as err:
            raise CacheConfigurationError(f"CACHE_REDIS_PORT must be an integer: {err}") from err

        try:
            redis_db = int(os.getenv("CACHE_REDIS_DB", "0"))
        except ValueError as err:
            raise CacheConfigurationError(f"CACHE_REDIS_DB must be an integer: {err}") from err

        redis_password = os.getenv("CACHE_REDIS_PASSWORD") or None

        try:
            redis_timeout = float(os.getenv("CACHE_REDIS_TIMEOUT", "2.0"))
        except ValueError as err:
            raise CacheConfigurationError(f"CACHE_REDIS_TIMEOUT must be a float: {err}") from err

        memcached_host = os.getenv("CACHE_MEMCACHED_HOST", "localhost")
        try:
            memcached_port = int(os.getenv("CACHE_MEMCACHED_PORT", "11211"))
        except ValueError as err:
            raise CacheConfigurationError(f"CACHE_MEMCACHED_PORT must be an integer: {err}") from err

        try:
            memcached_timeout = float(os.getenv("CACHE_MEMCACHED_TIMEOUT", "2.0"))
        except ValueError as err:
            raise CacheConfigurationError(f"CACHE_MEMCACHED_TIMEOUT must be a float: {err}") from err

        try:
            memory_max_size = int(os.getenv("CACHE_MEMORY_MAX_SIZE", "10000"))
        except ValueError as err:
            raise CacheConfigurationError(f"CACHE_MEMORY_MAX_SIZE must be an integer: {err}") from err

        namespace = os.getenv("CACHE_NAMESPACE") or None

        default_ttl_env = os.getenv("CACHE_DEFAULT_TTL")
        default_ttl = int(default_ttl_env) if default_ttl_env is not None else None

        api_key = os.getenv("CACHE_API_KEY") or None
        try:
            admin_rate_limit = int(os.getenv("CACHE_ADMIN_RATE_LIMIT", "60"))
        except ValueError as err:
            raise CacheConfigurationError(f"CACHE_ADMIN_RATE_LIMIT must be an integer: {err}") from err

        return cls(
            backend=backend,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            redis_password=redis_password,
            redis_timeout=redis_timeout,
            memcached_host=memcached_host,
            memcached_port=memcached_port,
            memcached_timeout=memcached_timeout,
            memory_max_size=memory_max_size,
            namespace=namespace,
            default_ttl=default_ttl,
            api_key=api_key,
            admin_rate_limit=admin_rate_limit,
        )


    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheConfig":
        """Construct CacheConfig from a dictionary."""
        return cls(**data)
