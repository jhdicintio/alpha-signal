"""Flask application factory and configuration."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask
from flask_cors import CORS

from app.api import api_bp
from app.executor import CLIWorkflowExecutor
from app.jobs import JobRunner, JobStore


def create_app(config_overrides: dict | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    # Default: repo root articles.db (backend/app -> backend -> root)
    _root = Path(__file__).resolve().parent.parent.parent
    app.config["ALPHA_SIGNAL_DB_PATH"] = os.environ.get(
        "ALPHA_SIGNAL_DB_PATH",
        str(_root / "articles.db"),
    )
    if config_overrides:
        app.config.update(config_overrides)

    CORS(
        app,
        origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
        allow_headers=["Content-Type", "Authorization"],
    )

    app.register_blueprint(api_bp, url_prefix="/api")

    # Workflow executor (CLI now; swap to Flyte remote via config later)
    app.job_store = JobStore()
    app.job_executor = CLIWorkflowExecutor()
    app.job_runner = JobRunner(
        executor=app.job_executor,
        store=app.job_store,
        get_cache_path=lambda: app.config["ALPHA_SIGNAL_DB_PATH"],
    )
    app.job_runner.start()

    return app
