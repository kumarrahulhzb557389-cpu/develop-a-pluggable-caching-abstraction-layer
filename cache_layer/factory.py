"""Provider and CacheManager factory for configuration-driven instantiation."""

from typing import Any, Callable, Dict, Optional, Type

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.memory_adapter import MemoryAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.config import CacheConfig
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheConfigurationError
from cache_layer.manager import CacheManager
from cache_layer.serializer import Serializer


class CacheFactory:
    """Factory supporting configuration-driven provider creation and custom registration."""

    _registry: Dict[str, Callable[[CacheConfig, Dict[str, Any]], CacheProvider]] = {}

    @classmethod
    def register_provider(
        cls,
        backend_name: str,
        creator_or_class: Any,
    ) -> None:
        """Register a new or custom cache provider backend.

        Args:
            backend_name: The lowercase identifier (e.g. 'valkey', 'dynamodb').
            creator_or_class: A callable taking (config, kwargs) and returning CacheProvider,
                              or a CacheProvider class.
        """
        backend_name = backend_name.lower().strip()
        if isinstance(creator_or_class, type) and issubclass(creator_or_class, CacheProvider):
            cls._registry[backend_name] = lambda cfg, kw: creator_or_class(**kw)
        elif callable(creator_or_class):
            cls._registry[backend_name] = creator_or_class
        else:
            raise CacheConfigurationError(
                f"Provider creator must be callable or CacheProvider subclass: {creator_or_class}"
            )

    @classmethod
    def unregister_provider(cls, backend_name: str) -> None:
        """Unregister a custom provider from the registry."""
        cls._registry.pop(backend_name.lower().strip(), None)

    @classmethod
    def get_available_backends(cls) -> list:

        """Return list of all available and registered cache backends."""
        standard = ["memory", "redis", "memcached"]
        custom = [k for k in cls._registry.keys() if k not in standard]
        return standard + sorted(custom)

    @classmethod
    def create_provider(

        cls,
        backend: Optional[str] = None,
        config: Optional[CacheConfig] = None,
        **kwargs: Any,
    ) -> CacheProvider:
        """Instantiate a CacheProvider according to configuration.

        Args:
            backend: Optional override for the backend type.
            config: Optional CacheConfig instance. If None, loaded from env.
            **kwargs: Extra parameters passed to the provider constructor.

        Returns:
            An instantiated CacheProvider.
        """
        cfg = config if config is not None else CacheConfig.from_env()
        target_backend = (backend or cfg.backend).lower().strip()

        # Check user-registered providers first
        if target_backend in cls._registry:
            return cls._registry[target_backend](cfg, kwargs)

        if target_backend == "memory":
            max_size = kwargs.get("max_size", cfg.memory_max_size)
            return MemoryAdapter(max_size=max_size)

        elif target_backend == "redis":
            redis_kwargs = {
                "host": kwargs.get("host", cfg.redis_host),
                "port": kwargs.get("port", cfg.redis_port),
                "db": kwargs.get("db", cfg.redis_db),
                "password": kwargs.get("password", cfg.redis_password),
                "socket_timeout": kwargs.get("socket_timeout", cfg.redis_timeout),
                "socket_connect_timeout": kwargs.get("socket_connect_timeout", cfg.redis_connect_timeout),
                "max_connections": kwargs.get("max_connections", cfg.redis_max_connections),
            }
            if "client" in kwargs:
                redis_kwargs["client"] = kwargs["client"]
            return RedisAdapter(**redis_kwargs)

        elif target_backend == "memcached":
            memcached_kwargs = {
                "host": kwargs.get("host", cfg.memcached_host),
                "port": kwargs.get("port", cfg.memcached_port),
                "timeout": kwargs.get("timeout", cfg.memcached_timeout),
                "connect_timeout": kwargs.get("connect_timeout", cfg.memcached_connect_timeout),
                "max_pool_size": kwargs.get("max_pool_size", cfg.memcached_max_pool_size),
            }
            if "client" in kwargs:
                memcached_kwargs["client"] = kwargs["client"]
            return MemcachedAdapter(**memcached_kwargs)

        else:
            raise CacheConfigurationError(f"Unsupported cache backend: '{target_backend}'")

    @classmethod
    def create_cache_manager(
        cls,
        config: Optional[CacheConfig] = None,
        serializer: Optional[Serializer] = None,
        provider: Optional[CacheProvider] = None,
        **kwargs: Any,
    ) -> CacheManager:
        """Create a complete CacheManager instance configured from environment or config.

        Args:
            config: Optional CacheConfig instance.
            serializer: Optional custom serializer.
            provider: Optional pre-created CacheProvider instance.
            **kwargs: Extra parameters passed to create_provider.

        Returns:
            A ready-to-use CacheManager.
        """
        cfg = config if config is not None else CacheConfig.from_env()
        active_provider = provider if provider is not None else cls.create_provider(config=cfg, **kwargs)
        return CacheManager(
            provider=active_provider,
            serializer=serializer,
            namespace=cfg.namespace,
            default_ttl=cfg.default_ttl,
            config=cfg,
        )

