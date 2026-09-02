"""Provider factory for configuration-driven cache backend instantiation."""

from typing import Any, Dict, Optional, Type, Union

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.config import CacheConfig, register_backend_name
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheConfigurationError
from cache_layer.serializer import Serializer
from cache_layer.service import CacheService


class ProviderFactory:
    """Factory for creating cache providers and services based on configuration."""

    _registry: Dict[str, Type[CacheProvider]] = {
        "redis": RedisAdapter,
        "memcached": MemcachedAdapter,
    }

    @classmethod
    def register_provider(cls, name: str, adapter_cls: Type[CacheProvider]) -> None:
        """Register a custom cache provider adapter.

        Args:
            name: Backend identifier string.
            adapter_cls: CacheProvider subclass.
        """
        if not isinstance(adapter_cls, type) or not issubclass(adapter_cls, CacheProvider):
            raise TypeError(f"Adapter class must inherit from CacheProvider, got {adapter_cls}")
        cleaned_name = name.lower().strip()
        cls._registry[cleaned_name] = adapter_cls
        register_backend_name(cleaned_name)

    @classmethod
    def get_registered_providers(cls) -> Dict[str, Type[CacheProvider]]:
        """Return a copy of all registered provider classes."""
        return dict(cls._registry)

    @classmethod
    def create_provider(
        cls,
        config: Optional[Union[CacheConfig, Dict[str, Any]]] = None,
    ) -> CacheProvider:
        """Instantiate a CacheProvider according to the provided configuration.

        Args:
            config: CacheConfig instance, dictionary configuration, or None (loads from environment).

        Returns:
            An instantiated CacheProvider.

        Raises:
            CacheConfigurationError: If configuration is invalid or provider is unknown.
        """
        if config is None:
            resolved_config = CacheConfig.from_env()
        elif isinstance(config, dict):
            resolved_config = CacheConfig.from_dict(config)
        elif isinstance(config, CacheConfig):
            resolved_config = config
        else:
            raise CacheConfigurationError(
                f"Config must be CacheConfig, dict, or None, got {type(config).__name__}"
            )

        backend = resolved_config.backend.lower().strip()
        if backend not in cls._registry:
            raise CacheConfigurationError(
                f"Unknown or unsupported cache backend '{backend}'. Registered backends: {list(cls._registry.keys())}"
            )

        if backend == "redis":
            rc = resolved_config.redis
            return RedisAdapter(
                host=rc.host,
                port=rc.port,
                db=rc.db,
                password=rc.password,
                socket_timeout=rc.socket_timeout,
                socket_connect_timeout=rc.socket_connect_timeout,
                max_connections=rc.max_connections,
            )
        elif backend == "memcached":
            mc = resolved_config.memcached
            return MemcachedAdapter(
                host=mc.host,
                port=mc.port,
                connect_timeout=mc.connect_timeout,
                timeout=mc.timeout,
                max_pool_size=mc.max_pool_size,
            )
        else:
            adapter_cls = cls._registry[backend]
            return adapter_cls()

    @classmethod
    def create_service(
        cls,
        config: Optional[Union[CacheConfig, Dict[str, Any]]] = None,
        serializer: Optional[Serializer] = None,
    ) -> CacheService:
        """Create a fully configured CacheService based on configuration.

        Args:
            config: CacheConfig instance, dictionary configuration, or None (loads from environment).
            serializer: Optional custom serializer.

        Returns:
            An instantiated CacheService ready for application use.
        """
        if config is None:
            resolved_config = CacheConfig.from_env()
        elif isinstance(config, dict):
            resolved_config = CacheConfig.from_dict(config)
        elif isinstance(config, CacheConfig):
            resolved_config = config
        else:
            raise CacheConfigurationError(
                f"Config must be CacheConfig, dict, or None, got {type(config).__name__}"
            )

        provider = cls.create_provider(resolved_config)
        return CacheService(
            provider=provider,
            serializer=serializer,
            namespace=resolved_config.namespace,
        )
