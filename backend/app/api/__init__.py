"""API blueprint and route registration."""

from flask import Blueprint

from app.api.health import health_bp
from app.api.extractions import extractions_bp
from app.api.articles import articles_bp
from app.api.jobs import jobs_bp

api_bp = Blueprint("api", __name__)

api_bp.register_blueprint(health_bp)
api_bp.register_blueprint(extractions_bp, url_prefix="/extractions")
api_bp.register_blueprint(articles_bp, url_prefix="/articles")
api_bp.register_blueprint(jobs_bp, url_prefix="/jobs")
