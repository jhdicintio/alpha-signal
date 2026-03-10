"""Health and stats endpoints."""

from flask import Blueprint, current_app, jsonify

from app.cache import get_cache

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health():
    """Simple health check."""
    return jsonify({"status": "ok"})


@health_bp.route("/stats", methods=["GET"])
def stats():
    """Return article and extraction counts."""
    try:
        with get_cache(current_app) as cache:
            article_count = cache.count()
            extraction_count = cache.extraction_count()
        return jsonify({
            "articles": article_count,
            "extractions": extraction_count,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
