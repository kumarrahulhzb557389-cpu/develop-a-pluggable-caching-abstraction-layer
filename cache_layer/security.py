"""Security utilities for Universal-Cache-Manager: API Key authentication and rate limiting."""

from functools import wraps
import hmac
import threading
import time
from typing import Callable, Dict, List, Optional
from flask import current_app, jsonify, request


class RateLimiter:
    """Thread-safe in-memory sliding-window rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is within allowed limits for the client."""
        now = time.time()
        cutoff = now - self._window_seconds

        with self._lock:
            timestamps = self._requests.get(client_id, [])
            # Filter timestamps within current window
            valid_timestamps = [ts for ts in timestamps if ts > cutoff]

            if len(valid_timestamps) >= self._max_requests:
                self._requests[client_id] = valid_timestamps
                return False

            valid_timestamps.append(now)
            self._requests[client_id] = valid_timestamps
            return True

    def reset(self) -> None:
        """Clear all recorded rate limit timestamps."""
        with self._lock:
            self._requests.clear()


# Global rate limiter instance for administrative endpoints
admin_rate_limiter = RateLimiter(max_requests=60, window_seconds=60)


def extract_api_key(req) -> Optional[str]:
    """Extract API key from X-API-Key header or Authorization Bearer header."""
    header_key = req.headers.get("X-API-Key")
    if header_key:
        return header_key.strip()

    auth_header = req.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None


def require_api_key(f: Callable) -> Callable:
    """Decorator to enforce API key authentication on sensitive administrative endpoints.

    If CACHE_API_KEY is configured in current_app.config['CACHE_CONFIG'] or CACHE_API_KEY env,
    the request must provide a matching key. If not configured, access is permitted.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Retrieve configured API key
        expected_key = None
        cfg = current_app.config.get("CACHE_CONFIG")
        if cfg is not None and getattr(cfg, "api_key", None):
            expected_key = cfg.api_key
        elif current_app.config.get("CACHE_API_KEY"):
            expected_key = current_app.config["CACHE_API_KEY"]

        if expected_key:
            provided_key = extract_api_key(request)
            if not provided_key or not hmac.compare_digest(provided_key, expected_key):
                return jsonify({
                    "error": "Unauthorized",
                    "message": "Invalid or missing API key",
                }), 401

        return f(*args, **kwargs)

    return decorated_function


def rate_limit_admin(f: Callable) -> Callable:
    """Decorator to apply rate limiting on administrative endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr or "127.0.0.1"
        if not admin_rate_limiter.is_allowed(client_ip):
            return jsonify({
                "error": "Too Many Requests",
                "message": "Rate limit exceeded for administrative operations. Please try again later.",
            }), 429

        return f(*args, **kwargs)

    return decorated_function
