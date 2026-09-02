import os
from typing import Optional

from flask import Blueprint, Flask, current_app, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from cache_layer.benchmark import BenchmarkRunner
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
from cache_layer.factory import CacheFactory
from cache_layer.manager import CacheManager
from cache_layer.security import admin_rate_limiter, rate_limit_admin, require_api_key


def create_cache_blueprint(cache_manager: CacheManager) -> Blueprint:
    """Create a Flask Blueprint bound to the provided CacheManager instance."""
    bp = Blueprint("cache_api", __name__)

    @bp.route("/", methods=["GET"])
    def root_info():
        return jsonify({
            "service": "Universal-Cache-Manager",
            "backend": cache_manager.provider_name,
            "provider": cache_manager.provider_name,
            "endpoints": {
                "GET /cache/<key>": "Retrieve cached value",
                "POST|PUT /cache/<key>": "Store value with optional TTL",
                "DELETE /cache/<key>": "Delete a specific key",
                "DELETE /cache": "Clear the cache store/namespace (admin)",
                "POST /cache/batch/set": "Batch store key-value pairs with optional TTL",
                "POST /cache/batch/get": "Batch retrieve values for keys",
                "POST /cache/batch/delete": "Batch delete keys",
                "GET /stats": "Retrieve operational and backend statistics (admin)",
                "GET /health": "Inspect service and backend health",
                "GET /backends": "List active and available cache backends",
                "POST /backend/switch": "Switch active cache backend provider (admin)",
                "GET /backend": "Retrieve active backend and health status",
                "POST /benchmark/run": "Execute real comparative multi-backend performance benchmarks",
                "GET /dashboard": "Access web management dashboard",
            },
        }), 200




    @bp.route("/cache/batch/set", methods=["POST", "PUT"])
    def batch_set():
        if not request.is_json:
            raise CacheValidationError("Batch set requires application/json payload")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise CacheValidationError("Batch set payload must be a JSON object")

        raw_ttl = body.get("ttl")
        if raw_ttl is None and "ttl" in request.args:
            raw_ttl = request.args.get("ttl")

        if raw_ttl is not None:
            if isinstance(raw_ttl, bool):
                raise CacheValidationError(f"TTL cannot be a boolean value: {raw_ttl}")
            try:
                ttl = int(raw_ttl)
            except (ValueError, TypeError) as err:
                raise CacheValidationError(f"TTL must be an integer (seconds), got '{raw_ttl}'") from err
        else:
            ttl = None


        if "items" in body:
            raw_items = body["items"]
            if isinstance(raw_items, dict):
                mapping = raw_items
            elif isinstance(raw_items, list):
                mapping = {}
                for item in raw_items:
                    if not isinstance(item, dict) or "key" not in item or "value" not in item:
                        raise CacheValidationError("Each item in list must have 'key' and 'value'")
                    mapping[item["key"]] = item["value"]
            else:
                raise CacheValidationError("'items' must be a dictionary or list of key-value objects")
        else:
            mapping = {k: v for k, v in body.items() if k != "ttl"}

        if not mapping:
            raise CacheValidationError("No items provided for batch set")

        cache_manager.set_many(mapping, ttl=ttl)
        return jsonify({
            "status": "success",
            "count": len(mapping),
            "ttl": ttl,
        }), 200

    @bp.route("/cache/batch/get", methods=["POST", "GET"])
    def batch_get():
        keys = None
        if request.method == "POST" and request.is_json:
            body = request.get_json(silent=True)
            if isinstance(body, dict) and "keys" in body:
                keys = body["keys"]
            elif isinstance(body, list):
                keys = body
        elif "keys" in request.args:
            keys = [k.strip() for k in request.args.get("keys", "").split(",") if k.strip()]

        if keys is None:
            raise CacheValidationError("Batch get requires 'keys' in JSON body or query parameter")

        results = cache_manager.get_many(keys)
        return jsonify({
            "values": results,
            "count": len(results),
        }), 200

    @bp.route("/cache/batch/delete", methods=["POST", "DELETE"])
    @bp.route("/cache/batch", methods=["DELETE"])
    def batch_delete():
        keys = None
        if request.is_json:
            body = request.get_json(silent=True)
            if isinstance(body, dict) and "keys" in body:
                keys = body["keys"]
            elif isinstance(body, list):
                keys = body
        elif "keys" in request.args:
            keys = [k.strip() for k in request.args.get("keys", "").split(",") if k.strip()]

        if keys is None:
            raise CacheValidationError("Batch delete requires 'keys' in JSON body or query parameter")

        cache_manager.delete_many(keys)
        return jsonify({
            "status": "success",
            "deleted_count": len(keys),
        }), 200

    @bp.route("/cache/<key>", methods=["GET"])
    def get_key(key: str):

        val = cache_manager.get(key)
        if val is None:
            return jsonify({
                "error": "Key not found",
                "key": key,
            }), 404
        return jsonify({
            "key": key,
            "value": val,
        }), 200

    @bp.route("/cache/<key>", methods=["POST", "PUT"])
    def set_key(key: str):
        raw_ttl = None
        if request.is_json:
            body = request.get_json(silent=True)
            if isinstance(body, dict) and "value" in body:
                val = body["value"]
                raw_ttl = body.get("ttl")
            else:
                val = body
                raw_ttl = request.args.get("ttl")
        else:
            raw_text = request.get_data(as_text=True)
            val = raw_text if raw_text else None
            raw_ttl = request.args.get("ttl")

        if raw_ttl is None and "ttl" in request.args:
            raw_ttl = request.args.get("ttl")

        if raw_ttl is not None:
            if isinstance(raw_ttl, bool):
                raise CacheValidationError(f"TTL cannot be a boolean value: {raw_ttl}")
            try:
                ttl = int(raw_ttl)
            except (ValueError, TypeError) as err:
                raise CacheValidationError(f"TTL must be an integer (seconds), got '{raw_ttl}'") from err
        else:
            ttl = None


        cache_manager.set(key, val, ttl=ttl)
        return jsonify({
            "status": "success",
            "key": key,
            "ttl": ttl,
        }), 200

    @bp.route("/cache/<key>", methods=["DELETE"])
    def delete_key(key: str):
        cache_manager.delete(key)
        return jsonify({
            "status": "success",
            "deleted": True,
            "key": key,
        }), 200

    @bp.route("/cache", methods=["DELETE"])
    @rate_limit_admin
    @require_api_key
    def clear_cache():
        cache_manager.clear()
        return jsonify({
            "status": "success",
            "cleared": True,
        }), 200

    @bp.route("/stats", methods=["GET"])
    @rate_limit_admin
    @require_api_key
    def get_stats():
        stats_data = cache_manager.stats()
        return jsonify(stats_data), 200

    @bp.route("/health", methods=["GET"])
    def health_check():
        health = cache_manager.health_check()
        if "backend" not in health:
            health["backend"] = health.get("provider", cache_manager.provider_name)
        status_code = 200 if health.get("status") == "healthy" else 503
        return jsonify(health), status_code

    @bp.route("/backends", methods=["GET"])
    def list_backends():
        return jsonify({
            "active": cache_manager.provider_name,
            "available": CacheFactory.get_available_backends(),
        }), 200

    @bp.route("/backend", methods=["GET"])
    def get_current_backend():
        health = cache_manager.health_check()
        return jsonify({
            "backend": cache_manager.provider_name,
            "status": health.get("status", "healthy"),
        }), 200

    @bp.route("/backend/switch", methods=["POST"])
    @rate_limit_admin
    @require_api_key
    def switch_backend():
        if not request.is_json:
            raise CacheValidationError("Backend switch requires application/json payload")
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or "backend" not in body:
            raise CacheValidationError("Missing 'backend' field in request body")

        target_backend = body["backend"]
        new_provider = cache_manager.switch_backend(target_backend)

        return jsonify({
            "status": "success",
            "backend": new_provider.provider_name,
            "message": f"Successfully switched cache backend to {new_provider.provider_name}",
        }), 200

    @bp.route("/benchmark/run", methods=["POST"])
    def run_benchmark():
        iterations = 50
        backends = None
        if request.is_json:
            body = request.get_json(silent=True) or {}
            if "iterations" in body:
                try:
                    iterations = int(body["iterations"])
                except (ValueError, TypeError):
                    raise CacheValidationError("iterations must be an integer")
            if "backends" in body and isinstance(body["backends"], list):
                backends = body["backends"]

        cfg = current_app.config.get("CACHE_CONFIG") or cache_manager.config
        results = BenchmarkRunner.run_benchmark(backends=backends, iterations=iterations, config=cfg)
        return jsonify(results), 200

    @bp.route("/dashboard", methods=["GET"])
    def serve_dashboard():
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dist_dir = os.path.join(base_dir, "frontend", "dist")
        index_file = os.path.join(dist_dir, "index.html")
        if os.path.exists(index_file):
            return send_from_directory(dist_dir, "index.html")
        return jsonify({
            "status": "frontend_not_built",
            "message": "Frontend production build not found in frontend/dist. Run 'npm run build' inside frontend/ directory or visit Vite dev server at http://localhost:5173",
        }), 200

    @bp.route("/assets/<path:path>", methods=["GET"])
    def serve_dashboard_assets(path):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assets_dir = os.path.join(base_dir, "frontend", "dist", "assets")
        if os.path.exists(os.path.join(assets_dir, path)):
            return send_from_directory(assets_dir, path)
        return jsonify({"error": "Asset not found"}), 404

    return bp



def create_app(
    cache_manager: Optional[CacheManager] = None,
    config: Optional[CacheConfig] = None,
) -> Flask:
    """Application factory for Flask caching API.

    Args:
        cache_manager: Optional existing CacheManager. If omitted, built via CacheFactory.
        config: Optional CacheConfig instance.
    """
    app = Flask(__name__)

    cfg = config if config is not None else CacheConfig.from_env()
    manager = cache_manager if cache_manager is not None else CacheFactory.create_cache_manager(config=cfg)
    app.config["CACHE_MANAGER"] = manager
    app.config["CACHE_CONFIG"] = cfg
    if cfg.api_key:
        app.config["CACHE_API_KEY"] = cfg.api_key
    admin_rate_limiter._max_requests = cfg.admin_rate_limit

    blueprint = create_cache_blueprint(manager)
    app.register_blueprint(blueprint)


    # Register normalized exception handlers
    @app.errorhandler(CacheValidationError)
    def handle_validation_error(err: CacheValidationError):
        return jsonify({"error": "Validation Error", "message": str(err)}), 400

    @app.errorhandler(CacheSerializationError)
    def handle_serialization_error(err: CacheSerializationError):
        return jsonify({"error": "Serialization Error", "message": str(err)}), 400

    @app.errorhandler(CacheTimeoutError)
    def handle_timeout_error(err: CacheTimeoutError):
        return jsonify({"error": "Gateway Timeout", "message": str(err)}), 504

    @app.errorhandler(CacheConnectionError)
    def handle_connection_error(err: CacheConnectionError):
        return jsonify({"error": "Service Unavailable", "message": str(err)}), 503

    @app.errorhandler(CacheBackendError)
    def handle_backend_error(err: CacheBackendError):
        return jsonify({"error": "Bad Gateway", "message": str(err)}), 502

    @app.errorhandler(CacheConfigurationError)
    def handle_configuration_error(err: CacheConfigurationError):
        return jsonify({"error": "Configuration Error", "message": str(err)}), 500

    @app.errorhandler(CacheError)
    def handle_general_cache_error(err: CacheError):
        return jsonify({"error": "Internal Cache Error", "message": str(err)}), 500

    @app.errorhandler(Exception)
    def handle_unexpected_exception(err: Exception):
        # Handle standard HTTPExceptions (like 404, 405) gracefully
        if isinstance(err, HTTPException):
            return jsonify({
                "error": err.name,
                "message": err.description,
            }), err.code
        # Never leak raw Python tracebacks or internal paths to users
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected error occurred while processing your request.",
        }), 500

    return app

