"""Entrypoint for the Universal-Cache-Manager Flask REST application."""

import os

from cache_layer.api import create_app
from cache_layer.config import CacheConfig

config = CacheConfig.from_env()
app = create_app(config=config)

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true")
    print(f"Starting Universal-Cache-Manager [Backend: {config.backend}] on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
