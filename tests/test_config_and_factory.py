"""Unit tests for configuration parsing and ProviderFactory."""

from unittest.mock import patch
import pytest

from cache_layer.adapters.memcached_adapter import MemcachedAdapter
from cache_layer.adapters.redis_adapter import RedisAdapter
from cache_layer.config import CacheConfig, MemcachedConfig, RedisConfig
from cache_layer.contract import CacheProvider
from cache_layer.exceptions import CacheConfigurationError
from cache_layer.factory import ProviderFactory
from cache_layer.service import CacheService


def test_cache_config_from_dict():
    cfg = CacheConfig.from_dict({
        "backend": "redis",
        "namespace": "my_app",
        "redis": {
            "host": "redis.internal",
            "port": 6380,
            "db": 2,
            "password": "secret_password",
            "socket_timeout": 1.5,
            "max_connections": 100,
        },
        "memcached": {
            "host": "memcached.internal",
            "port": 11212,
            "connect_timeout": 3.0,
            "timeout": 3.0,
            "max_pool_size": 25,
        },
    })

    assert cfg.backend == "redis"
    assert cfg.namespace == "my_app"
    assert cfg.redis.host == "redis.internal"
    assert cfg.redis.port == 6380
    assert cfg.redis.db == 2
    assert cfg.redis.password == "secret_password"
    assert cfg.redis.socket_timeout == 1.5
    assert cfg.redis.max_connections == 100
    assert cfg.memcached.host == "memcached.internal"
    assert cfg.memcached.port == 11212
    assert cfg.memcached.max_pool_size == 25


def test_cache_config_from_env():
    env = {
        "CACHE_BACKEND": "memcached",
        "CACHE_NAMESPACE": "env_ns",
        "MEMCACHED_HOST": "10.0.0.5",
        "MEMCACHED_PORT": "11222",
        "REDIS_HOST": "10.0.0.6",
        "REDIS_PORT": "6399",
        "REDIS_DB": "1",
    }

    cfg = CacheConfig.from_env(env)
    assert cfg.backend == "memcached"
    assert cfg.namespace == "env_ns"
    assert cfg.memcached.host == "10.0.0.5"
    assert cfg.memcached.port == 11222
    assert cfg.redis.host == "10.0.0.6"
    assert cfg.redis.port == 6399
    assert cfg.redis.db == 1


def test_cache_config_invalid_backend():
    with pytest.raises(CacheConfigurationError, match="Unsupported cache backend"):
        CacheConfig.from_dict({"backend": "unsupported_backend"})

    with pytest.raises(CacheConfigurationError, match="Cache backend must be specified"):
        CacheConfig(backend="")


def test_provider_factory_create_redis():
    cfg = CacheConfig(backend="redis", redis=RedisConfig(host="127.0.0.1", port=6379))
    provider = ProviderFactory.create_provider(cfg)
    assert isinstance(provider, RedisAdapter)
    assert provider.provider_name == "redis"
    provider.close()


def test_provider_factory_create_memcached():
    cfg = CacheConfig(backend="memcached", memcached=MemcachedConfig(host="127.0.0.1", port=11211))
    provider = ProviderFactory.create_provider(cfg)
    assert isinstance(provider, MemcachedAdapter)
    assert provider.provider_name == "memcached"
    provider.close()


def test_provider_factory_create_service():
    cfg = {
        "backend": "redis",
        "namespace": "svc_test",
        "redis": {"host": "127.0.0.1", "port": 6379},
    }
    service = ProviderFactory.create_service(cfg)
    assert isinstance(service, CacheService)
    assert service.namespace == "svc_test"
    assert service.provider_name == "redis"
    service.close()


def test_provider_factory_custom_adapter_registration():
    class DummyCustomProvider(CacheProvider):
        @property
        def provider_name(self) -> str:
            return "dummy"

        def get(self, key: str):
            return None

        def set(self, key: str, value: bytes, ttl=None):
            return True

        def delete(self, key: str):
            return True

        def clear(self):
            return True

        def health_check(self):
            return {"status": "healthy", "provider": "dummy"}

        def close(self):
            pass

    ProviderFactory.register_provider("dummy", DummyCustomProvider)
    
    # Custom provider registration must require subclass of CacheProvider
    with pytest.raises(TypeError):
        ProviderFactory.register_provider("invalid", object)

    provider = ProviderFactory.create_provider({"backend": "dummy"})
    assert isinstance(provider, DummyCustomProvider)
    assert provider.provider_name == "dummy"
