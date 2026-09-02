"""REST API server exposing unified caching endpoints and dynamic runtime backend switching."""

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cache_layer.config import CacheConfig
from cache_layer.exceptions import (
    CacheBackendError,
    CacheConfigurationError,
    CacheConnectionError,
    CacheError,
    CacheSerializationError,
    CacheTimeoutError,
    CacheValidationError,
)
from cache_layer.factory import ProviderFactory
from cache_layer.service import CacheService

# Shared global CacheService instance
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get or initialize the active global CacheService."""
    global _cache_service
    if _cache_service is None:
        _cache_service = ProviderFactory.create_service()
    return _cache_service


def set_cache_service(service: CacheService) -> None:
    """Set the active global CacheService."""
    global _cache_service
    if _cache_service is not None and _cache_service is not service:
        _cache_service.close()
    _cache_service = service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure service is initialized
    get_cache_service()
    yield
    # Shutdown: close open connections
    global _cache_service
    if _cache_service is not None:
        _cache_service.close()
        _cache_service = None


app = FastAPI(
    title="Pluggable Caching Abstraction API",
    description="Unified, configuration-driven caching service supporting interchangeable Redis and Memcached backends.",
    version="1.0.0",
    lifespan=lifespan,
)


class CachePutRequest(BaseModel):
    value: Any = Field(..., description="Value to store in cache (JSON-serializable, primitive, or string).")
    ttl: Optional[int] = Field(None, ge=0, description="Optional Time-to-Live in seconds.")


class CacheSwitchRequest(BaseModel):
    backend: str = Field(..., description="Target backend provider ('redis' or 'memcached').")
    namespace: Optional[str] = Field(None, description="Optional namespace prefix.")
    redis: Optional[Dict[str, Any]] = Field(None, description="Optional Redis backend configuration.")
    memcached: Optional[Dict[str, Any]] = Field(None, description="Optional Memcached backend configuration.")


# Exception Handlers
@app.exception_handler(CacheValidationError)
async def validation_error_handler(request: Request, exc: CacheValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "ValidationError", "detail": str(exc)},
    )


@app.exception_handler(CacheConnectionError)
async def connection_error_handler(request: Request, exc: CacheConnectionError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "ConnectionError", "detail": str(exc)},
    )


@app.exception_handler(CacheTimeoutError)
async def timeout_error_handler(request: Request, exc: CacheTimeoutError):
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={"error": "TimeoutError", "detail": str(exc)},
    )


@app.exception_handler(CacheConfigurationError)
async def config_error_handler(request: Request, exc: CacheConfigurationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "ConfigurationError", "detail": str(exc)},
    )


@app.exception_handler(CacheError)
async def generic_cache_error_handler(request: Request, exc: CacheError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "CacheError", "detail": str(exc)},
    )


# API Endpoints
@app.get("/health", summary="Health check", tags=["System"])
def health_check():
    """Report abstraction and backend health status."""
    service = get_cache_service()
    health = service.health_check()
    status_code = status.HTTP_200_OK if health.get("status") == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=health)


@app.get("/cache/info", summary="Cache info", tags=["System"])
def cache_info():
    """Retrieve current cache provider configuration and status."""
    service = get_cache_service()
    return {
        "provider": service.provider_name,
        "namespace": service.namespace,
    }


@app.get("/cache/{key}", summary="Retrieve cached value", tags=["Cache Operations"])
def get_cache(key: str):
    """Retrieve a value by key. Returns 404 on cache miss."""
    service = get_cache_service()
    val = service.get(key)
    if val is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Key '{key}' not found in cache",
        )
    return {
        "key": key,
        "value": val,
        "cached": True,
        "provider": service.provider_name,
    }


@app.put("/cache/{key}", summary="Store value in cache", tags=["Cache Operations"])
def set_cache(key: str, req: CachePutRequest):
    """Store a value under the given key with optional TTL."""
    service = get_cache_service()
    success = service.set(key, req.value, ttl=req.ttl)
    return {
        "key": key,
        "stored": success,
        "ttl": req.ttl,
        "provider": service.provider_name,
    }


@app.delete("/cache/{key}", summary="Delete key from cache", tags=["Cache Operations"])
def delete_cache(key: str):
    """Delete a specific key from the cache."""
    service = get_cache_service()
    success = service.delete(key)
    return {
        "key": key,
        "deleted": success,
        "provider": service.provider_name,
    }


@app.delete("/cache", summary="Clear cache store", tags=["Cache Operations"])
def clear_cache():
    """Clear all entries in the configured cache store or namespace."""
    service = get_cache_service()
    success = service.clear()
    return {
        "cleared": success,
        "provider": service.provider_name,
    }


@app.post("/cache/switch", summary="Switch backend at runtime", tags=["System"])
def switch_backend(req: CacheSwitchRequest):
    """Dynamically switch the active cache backend (e.g. from Redis to Memcached) at runtime."""
    data = req.model_dump(exclude_none=True)
    new_service = ProviderFactory.create_service(data)
    set_cache_service(new_service)
    return {
        "status": "switched",
        "provider": new_service.provider_name,
        "namespace": new_service.namespace,
    }
