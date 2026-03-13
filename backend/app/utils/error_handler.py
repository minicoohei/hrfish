"""Centralized error response helper."""

import traceback
from flask import current_app, jsonify
from .logger import get_logger


def error_response(message: str, status_code: int = 500, error_id: str = None):
    """Return a safe error response. Include traceback only in DEBUG mode."""
    logger = get_logger('mirofish.error')
    logger.error(f"{message}\n{traceback.format_exc()}")

    body = {"success": False, "error": message}
    if error_id:
        body["error_id"] = error_id
    if current_app.config.get('DEBUG'):
        body["traceback"] = traceback.format_exc()

    return jsonify(body), status_code
