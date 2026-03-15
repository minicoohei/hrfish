"""
MiroFish Backend - Flask application factory
"""

import hmac
import os
import warnings

# Suppress multiprocessing resource_tracker warnings (from third-party libs)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, jsonify, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask application factory"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # JSON encoding: ensure Unicode displays directly
    # Flask >= 2.3 uses app.json.ensure_ascii, older versions use JSON_AS_ASCII
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # Setup logging
    logger = setup_logger('mirofish')
    
    # Only print startup info in reloader subprocess (avoid double printing in debug)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend starting...")
        logger.info("=" * 50)
    
    # Enable CORS
    cors_origins = app.config.get('CORS_ORIGINS', ['http://localhost:3000'])
    CORS(app, resources={r"/api/*": {"origins": cors_origins, "supports_credentials": True}})

    # Rate limiting
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        rate_hour = os.environ.get('RATE_LIMIT_HOUR', '200 per hour')
        rate_minute = os.environ.get('RATE_LIMIT_MINUTE', '50 per minute')
        limiter = Limiter(
            get_remote_address,
            app=app,
            default_limits=[rate_hour, rate_minute],
            storage_uri="memory://",
        )
        app.limiter = limiter
        if should_log_startup:
            logger.info(f"Rate limiting enabled ({rate_hour}, {rate_minute})")
    except ImportError:
        if should_log_startup:
            logger.warning("flask-limiter not installed, rate limiting disabled")
    except Exception as e:
        if should_log_startup:
            logger.warning(f"Rate limiting config error (check RATE_LIMIT_* env vars): {e}")
    
    # Register simulation process cleanup (ensure termination on server shutdown)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Simulation process cleanup registered")
    
    # API key authentication middleware
    @app.before_request
    def check_api_key():
        if request.path == '/health' or request.method == 'OPTIONS':
            return None
        if not request.path.startswith('/api/'):
            return None
        api_key = app.config.get('API_KEY')
        if not api_key:
            return None  # Auth disabled in dev mode
        provided = request.headers.get('X-API-Key')
        if not provided or not hmac.compare_digest(provided, api_key):
            return jsonify({"success": False, "error": "Invalid or missing API key"}), 401

    # Request logging middleware
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Request: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            body = request.get_json(silent=True)
            if body:
                safe_keys = list(body.keys())
                logger.debug(f"Request body keys: {safe_keys}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"Response: {response.status_code}")
        return response
    
    # Register blueprints
    from .api import graph_bp, simulation_bp, report_bp, knowledge_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(knowledge_bp, url_prefix='/api/knowledge')
    
    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}
    
    # Global error handlers
    @app.errorhandler(500)
    def internal_error(e):
        from .utils.error_handler import error_response
        return error_response("Internal server error")

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "error": "Not found"}), 404

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"success": False, "error": "Bad request"}), 400

    if should_log_startup:
        logger.info("MiroFish Backend started")

    return app

