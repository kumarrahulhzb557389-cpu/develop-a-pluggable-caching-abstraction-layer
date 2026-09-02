"""Pluggable Caching Abstraction Layer."""

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.memory_adapter import MemoryAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.config import CacheConfig
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import (
    CacheBackendError,
    CacheConfigurationError,
    CacheConnectionError,
    CacheError,
    CacheSerializationError,
    CacheTimeoutError,
    CacheValidationError,
)
from cache_layer.factory import CacheFactory
from cache_layer.manager import CacheManager
from cache_layer.serializer import PortableJsonSerializer, Serializer
from cache_layer.service import CacheService
from cache_layer.validation import validate_key, validate_namespace, validate_ttl

__all__ = [
    "CacheProvider",
    "CacheService",
    "CacheManager",
    "CacheFactory",
    "CacheConfig",
    "MemoryAdapter",
    "RedisAdapter",
    "MemcachedAdapter",
    "Serializer",
    "PortableJsonSerializer",
    "validate_key",
    "validate_ttl",
    "validate_namespace",
    "CacheError",
    "CacheConnectionError",
    "CacheTimeoutError",
    "CacheValidationError",
    "CacheSerializationError",
    "CacheConfigurationError",
    "CacheBackendError",
]

