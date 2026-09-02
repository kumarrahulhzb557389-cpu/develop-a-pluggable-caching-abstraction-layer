"""Normalized validation engine for cache keys, TTL values, and namespaces."""

import re
from typing import Any, Dict, List, Optional


from cache_layer.exceptions import CacheValidationError

# Memcached protocol limits keys to 250 ASCII characters without whitespace/control chars
MAX_KEY_LENGTH = 250
KEY_DISALLOWED_PATTERN = re.compile(r"[\s\x00-\x1f\x7f]")


def validate_key(key: str, max_length: int = MAX_KEY_LENGTH) -> str:
    """Validate a cache key according to the unified portable standard.

    Args:
        key: The key string to validate.
        max_length: Maximum allowed character length (defaults to 250).

    Returns:
        The validated key.

    Raises:
        CacheValidationError: If key is invalid.
    """
    if not isinstance(key, str):
        raise CacheValidationError(f"Cache key must be a string, got {type(key).__name__}")

    if not key:
        raise CacheValidationError("Cache key cannot be empty")

    if len(key) > max_length:
        raise CacheValidationError(
            f"Cache key length ({len(key)}) exceeds maximum allowed length of {max_length} characters"
        )

    if KEY_DISALLOWED_PATTERN.search(key):
        raise CacheValidationError(
            "Cache key contains invalid characters (whitespace or control characters are not permitted)"
        )

    return key


def validate_ttl(ttl: Optional[int]) -> Optional[int]:
    """Validate TTL parameter.

    Args:
        ttl: Time to live in seconds, or None for non-expiring keys.

    Returns:
        The validated TTL integer or None.

    Raises:
        CacheValidationError: If TTL is invalid, negative, boolean, or not an integer.
    """
    if ttl is None:
        return None

    if isinstance(ttl, bool) or not isinstance(ttl, int):
        raise CacheValidationError(f"TTL must be an integer (seconds) or None, got {type(ttl).__name__}")

    if ttl < 0:
        raise CacheValidationError(f"TTL cannot be negative: {ttl}")

    return ttl



def validate_keys(keys: Any) -> list:
    """Validate an iterable collection of cache keys.

    Args:
        keys: Iterable of keys.

    Returns:
        List of validated keys.

    Raises:
        CacheValidationError: If keys is not a collection, is empty, or contains invalid keys.
    """
    if not isinstance(keys, (list, tuple, set)):
        raise CacheValidationError(f"Keys collection must be a list, tuple or set, got {type(keys).__name__}")
    if not keys:
        raise CacheValidationError("Keys collection cannot be empty")
    return [validate_key(k) for k in keys]


def validate_mapping(mapping: Any) -> dict:
    """Validate a key-value dictionary for batch operations.

    Args:
        mapping: Dictionary of key-value pairs.

    Returns:
        Validated dictionary.

    Raises:
        CacheValidationError: If mapping is not a dict, is empty, or contains invalid keys.
    """
    if not isinstance(mapping, dict):
        raise CacheValidationError(f"Batch mapping must be a dict, got {type(mapping).__name__}")
    if not mapping:
        raise CacheValidationError("Batch mapping cannot be empty")
    for k in mapping.keys():
        validate_key(k)
    return mapping



def validate_namespace(namespace: Optional[str]) -> Optional[str]:
    """Validate a namespace prefix string.

    Args:
        namespace: Optional namespace prefix.

    Returns:
        Validated namespace or None.

    Raises:
        CacheValidationError: If namespace contains invalid characters.
    """
    if namespace is None or namespace == "":
        return None

    if not isinstance(namespace, str):
        raise CacheValidationError(
            f"Namespace must be a string, got {type(namespace).__name__}"
        )

    if KEY_DISALLOWED_PATTERN.search(namespace):
        raise CacheValidationError(
            "Namespace contains invalid characters (whitespace or control characters are not permitted)"
        )

    return namespace
