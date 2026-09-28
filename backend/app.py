"""Flask application factory and entry point."""
import os
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, request, send_from_directory

from .config import Config
from .database import healthcheck, init_db
from .routes import ALL_BLUEPRINTS
from .utils.errors import ApiError, RateLimited


# --------------------------------------------------------------------------
# Naive in-memory rate limiter (per IP, sliding 60s window).
# Production: use Redis + flask-limiter so the limit is shared across pods.
# --------------------------------------------------------------------------
_HITS: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str, limit: int) -> bool:
    now = time.time()
    window = _HITS[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        return True
    window.append(now)
    return False


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    app.config["BOOTSTRAP_KEY"] = Config.BOOTSTRAP_KEY

    # --- database ---------------------------------------------------------
    init_db()

    # --- blueprints -------------------------------------------------------
    for blueprint in ALL_BLUEPRINTS:
        app.register_blueprint(blueprint)

    # ---------------------------------------------------------------------
    # Cross-cutting middleware
    # ---------------------------------------------------------------------
    @app.before_request
    def _limit_and_log():
        if request.path.startswith("/api/"):
            ip = request.headers.get("X-Forwarded-For", request.remote_addr or "?")
            ip = ip.split(",")[0].strip()
            if _rate_limited(ip, Config.RATE_LIMIT_PER_MINUTE):
                raise RateLimited("Too many requests - please slow down")

    @app.after_request
    def _security_headers(response):
        response.headers["Access-Control-Allow-Origin"] = Config.CORS_ORIGINS
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Bootstrap-Key"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.method == "OPTIONS":
            response.status_code = 204
        return response

    # ---------------------------------------------------------------------
    # Error handling — always JSON, never leak stack traces
    # ---------------------------------------------------------------------
    @app.errorhandler(ApiError)
    def _handle_api_error(err: ApiError):
        return jsonify(err.to_dict()), err.status

    @app.errorhandler(404)
    def _handle_404(_err):
        if request.path.startswith("/api/"):
            return jsonify(error="Endpoint not found"), 404
        return send_from_directory(Config.FRONTEND_DIR, "index.html")

    @app.errorhandler(405)
    def _handle_405(_err):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(Exception)
    def _handle_unexpected(err: Exception):
        app.logger.exception("Unhandled error: %s", err)
        return jsonify(error="Internal server error"), 500

    # ---------------------------------------------------------------------
    # Health / readiness probes (used by load balancers and CI)
    # ---------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        db_ok = healthcheck()
        return jsonify(
            status="ok" if db_ok else "degraded",
            database="up" if db_ok else "down",
            version="1.0.0",
        ), (200 if db_ok else 503)

    # ---------------------------------------------------------------------
    # Static frontend (SPA)
    # ---------------------------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(Config.FRONTEND_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename: str):
        full_path = os.path.join(Config.FRONTEND_DIR, filename)
        if os.path.isfile(full_path):
            return send_from_directory(Config.FRONTEND_DIR, filename)
        # SPA fallback
        return send_from_directory(Config.FRONTEND_DIR, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    # threaded=True is REQUIRED so SSE streams do not block normal requests.
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)