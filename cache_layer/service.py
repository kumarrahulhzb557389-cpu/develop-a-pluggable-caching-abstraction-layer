"""Unified CacheService coordinating validation, serialization, and adapter operations."""

from typing import Any, Dict, Optional

from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheError
from cache_layer.serializer import PortableJsonSerializer, Serializer
from cache_layer.validation import (
    validate_key,
    validate_keys,
    validate_mapping,
    validate_namespace,
    validate_ttl,
)



class CacheService:
    """Application-facing caching service with unified semantics across all providers."""

    def __init__(
        self,
        provider: CacheProvider,
        serializer: Optional[Serializer] = None,
        namespace: Optional[str] = None,
    ):
        if not isinstance(provider, CacheProvider):
            raise TypeError(f"Provider must implement CacheProvider, got {type(provider).__name__}")

        self._provider = provider
        self._serializer = serializer if serializer is not None else PortableJsonSerializer()
        self._namespace = validate_namespace(namespace)

    @property
    def provider(self) -> CacheProvider:
        """The underlying cache backend provider."""
        return self._provider

    @property
    def provider_name(self) -> str:
        """Name of the active provider."""
        return self._provider.provider_name

    @property
    def serializer(self) -> Serializer:
        """The active serializer."""
        return self._serializer

    @property
    def namespace(self) -> Optional[str]:
        """Configured namespace prefix."""
        return self._namespace

    def _format_key(self, key: str) -> str:
        validated_key = validate_key(key)
        if self._namespace:
            full_key = f"{self._namespace}:{validated_key}"
            validate_key(full_key)
            return full_key
        return validated_key

    def get(self, key: str) -> Any:
        """Retrieve and deserialize the value for a given key.

        Returns:
            The deserialized Python value, or None on cache miss.
        """
        full_key = self._format_key(key)
        raw_bytes = self._provider.get(full_key)
        if raw_bytes is None:
            return None
        return self._serializer.deserialize(raw_bytes)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Serialize and store a value under the given key.

        Args:
            key: Cache key.
            value: Any JSON-serializable or primitive Python value / bytes.
            ttl: Optional TTL in seconds.

        Returns:
            True if successfully stored, False otherwise.
        """
        full_key = self._format_key(key)
        validated_ttl = validate_ttl(ttl)
        raw_bytes = self._serializer.serialize(value)
        return self._provider.set(full_key, raw_bytes, ttl=validated_ttl)

    def delete(self, key: str) -> bool:
        """Delete a key from the cache.

        Returns:
            True if deletion was acknowledged.
        """
        full_key = self._format_key(key)
        return self._provider.delete(full_key)

    def get_many(self, keys: list) -> Dict[str, Any]:
        """Retrieve and deserialize values for multiple keys.

        Args:
            keys: Iterable of cache keys.

        Returns:
            Dictionary mapping original cache keys to deserialized values (or None on miss).
        """
        valid_keys = validate_keys(keys)
        key_map = {k: self._format_key(k) for k in valid_keys}
        formatted_keys = list(key_map.values())
        raw_results = self._provider.get_many(formatted_keys)

        results = {}
        for original_k, formatted_k in key_map.items():
            raw_bytes = raw_results.get(formatted_k)
            if raw_bytes is None:
                results[original_k] = None
            else:
                results[original_k] = self._serializer.deserialize(raw_bytes)
        return results

    def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Serialize and store multiple key-value pairs.

        Args:
            mapping: Dictionary of key-value pairs.
            ttl: Optional TTL in seconds for all keys.

        Returns:
            True if all stored successfully.
        """
        valid_mapping = validate_mapping(mapping)
        validated_ttl = validate_ttl(ttl)
        raw_mapping = {
            self._format_key(k): self._serializer.serialize(v)
            for k, v in valid_mapping.items()
        }
        return self._provider.set_many(raw_mapping, ttl=validated_ttl)

    def delete_many(self, keys: list) -> bool:
        """Delete multiple keys from the cache.

        Args:
            keys: Iterable of cache keys to remove.

        Returns:
            True if all deleted or acknowledged.
        """
        valid_keys = validate_keys(keys)
        formatted_keys = [self._format_key(k) for k in valid_keys]
        return self._provider.delete_many(formatted_keys)

    def clear(self) -> bool:

        """Clear all entries in the cache store/namespace.

        Returns:
            True if cleared successfully.
        """
        return self._provider.clear()

    def stats(self) -> Dict[str, Any]:
        """Retrieve cache provider statistics.

        Returns:
            Dictionary containing provider metrics.
        """
        return self._provider.stats()

    def health_check(self) -> Dict[str, Any]:
        """Check backend connectivity and health."""
        return self._provider.health_check()

    def close(self) -> None:
        """Close provider resources."""
        self._provider.close()

    def __enter__(self) -> "CacheService":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
