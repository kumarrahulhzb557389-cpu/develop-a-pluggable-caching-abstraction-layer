# Pluggable Caching Abstraction Layer

A production-grade, configuration-driven caching abstraction layer in Python providing a unified, portable contract over interchangeable cache backends (**Redis** and **Memcached**).

---

## 🚀 Value Proposition

Applications often suffer from vendor lock-in when calling backend-specific cache APIs directly. Switching from Redis to Memcached (or vice versa) frequently demands widespread code rewrites, error handling changes, and serialization adjustments.

This library solves the problem by providing:
- **One Stable Contract**: Application code interacts with a single `CacheService` / `CacheProvider` interface (`get`, `set`, `delete`, `clear`, `health_check`).
- **Zero Application Code Changes**: Switch between Redis and Memcached via configuration without changing application-facing cache calls.
- **Normalized Reliability Layer**: Unified exception hierarchy (`CacheConnectionError`, `CacheTimeoutError`, `CacheValidationError`, etc.) mapping backend-specific errors into predictable domain exceptions.
- **Portable Serialization**: Type-preserving, vendor-neutral serialization handling primitives (`str`, `int`, `float`, `bool`, `None`, `bytes`) and JSON-serializable complex data structures.
- **Connection Pooling & Health Checks**: Production-ready connection pooling and latency-aware health checks for both backends.
- **Configuration-Driven Factory**: Easily instantiate providers and services via environment variables (`CACHE_BACKEND`, `REDIS_HOST`, `MEMCACHED_HOST`, etc.) or dictionary configs.
- **REST API & Interactive Demo**: Built-in FastAPI server and rich interactive CLI demo harness.

---

## 🏛️ Architecture & System Flow

```mermaid
flowchart TD
    A[Application / API Client] --> B[Unified Cache Service]
    B --> C[Validate Request]
    C -->|Invalid| E[Return Validation Error]
    C -->|Valid| D[CacheProvider Contract]
    D --> F[Provider Factory / Configuration]
    F -->|Redis| G[Redis Adapter]
    F -->|Memcached| H[Memcached Adapter]
    G --> I[Redis Connection Pool]
    H --> J[Memcached Connection Pool]
    I --> K[Redis Backend]
    J --> L[Memcached Backend]
    K --> M[Normalize Result / Error]
    L --> M
    M --> N[Common Response]
    G -. connection/timeout .-> O[Normalized Cache Error]
    H -. connection/timeout .-> O
    O --> N
```

---

## 📁 Repository Structure

```text
├── cache_layer/
│   ├── __init__.py           # Public exports
│   ├── api.py                # FastAPI REST API endpoints
│   ├── config.py             # CacheConfig, RedisConfig, MemcachedConfig
│   ├── contract.py           # CacheProvider ABC interface
│   ├── exceptions.py         # Normalized exception hierarchy
│   ├── factory.py            # ProviderFactory (config-driven instantiation)
│   ├── serializer.py         # PortableJsonSerializer with type preservation
│   ├── validation.py         # Key, TTL, and namespace validation engine
│   ├── service.py            # CacheService coordinator
│   └── adapters/
│       ├── __init__.py
│       ├── redis_adapter.py      # Pooled Redis client adapter
│       └── memcached_adapter.py  # Pooled pymemcache adapter
├── tests/
│   ├── test_api.py               # REST API endpoint tests (TestClient)
│   ├── test_cache_service.py     # End-to-end integration & interchangeability tests
│   ├── test_config_and_factory.py# Configuration & ProviderFactory tests
│   ├── test_contract_suite.py    # Universal contract test suite for all adapters
│   ├── test_exceptions.py        # Exception hierarchy tests
│   ├── test_memcached_adapter.py # Memcached adapter unit & error injection tests
│   ├── test_redis_adapter.py     # Redis adapter unit & error injection tests
│   ├── test_serializer.py        # Portable serializer tests
│   └── test_validation.py        # Key/TTL validation tests
├── demo.py                   # Interactive Demo Script & test harness
├── ARCHITECTURE.md           # Technical baseline & architecture specifications
├── PRD.md                    # Product requirements document
├── PROGRESS.md               # Task tracking & decisions log
├── .gitignore                # Git ignore patterns
└── README.md                 # Project documentation
```

---

## 📦 Installation & Requirements

### Dependencies
Install the required dependencies:

```bash
pip install redis pymemcache fastapi uvicorn httpx pytest
```

---

## 💻 Usage Examples

### 1. Configuration-Driven Initialization via `ProviderFactory`

```python
from cache_layer import ProviderFactory, CacheConfig

# Create directly from environment variables:
# export CACHE_BACKEND=redis
# export CACHE_NAMESPACE=my_service
cache = ProviderFactory.create_service()

# Or create from explicit config dictionary:
config = {
    "backend": "memcached",
    "namespace": "my_service",
    "memcached": {"host": "localhost", "port": 11211}
}
cache = ProviderFactory.create_service(config)
```

### 2. Basic CRUD & Type Preservation

```python
with cache:
    # Store string
    cache.set("session_id", "abc-123", ttl=3600)

    # Store complex JSON dict
    cache.set("user:101:profile", {
        "name": "Sarah Connor",
        "roles": ["admin"],
        "active": True
    }, ttl=600)

    # Retrieve values
    profile = cache.get("user:101:profile")
    print(profile["name"])  # 'Sarah Connor'

    # Delete key
    cache.delete("session_id")
```

### 3. Health Checks

```python
health = cache.health_check()
print(health)
# Output:
# {
#     "status": "healthy",
#     "provider": "redis",
#     "latency_ms": 0.85,
#     "details": {"host": "localhost", "port": 6379, "db": 0}
# }
```

### 4. Normalized Error Handling

```python
from cache_layer import (
    CacheConnectionError,
    CacheTimeoutError,
    CacheValidationError,
    CacheError
)

try:
    cache.get("invalid key with spaces")
except CacheValidationError as e:
    print(f"Validation error: {e}")
except CacheConnectionError as e:
    print(f"Connection error: {e}")
except CacheTimeoutError as e:
    print(f"Timeout error: {e}")
except CacheError as e:
    print(f"General cache error: {e}")
```

---

## 🌐 Running the REST API Server

Start the FastAPI application with Uvicorn:

```bash
uvicorn cache_layer.api:app --reload --port 8000
```

### API Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Backend health check and latency report |
| `GET` | `/cache/info` | Current active backend and namespace info |
| `GET` | `/cache/{key}` | Retrieve cached value (`404` if not found) |
| `PUT` | `/cache/{key}` | Store value with optional `ttl` |
| `DELETE` | `/cache/{key}` | Delete specific key |
| `DELETE` | `/cache` | Clear entire cache store / namespace |
| `POST` | `/cache/switch` | Dynamically switch backend provider at runtime |

---

## 🎬 Running the Interactive Demo

Execute the interactive demo script:

```bash
python demo.py
```

To run against live Redis and Memcached services:
```bash
python demo.py --live
```

---

## 🧪 Running Tests

Execute the complete test suite (33 unit, integration, and contract tests):

```bash
python -m pytest -v
```

---

## 📜 License

MIT License.
