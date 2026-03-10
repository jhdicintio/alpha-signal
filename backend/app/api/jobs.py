"""Jobs API: trigger ingest, extract, pipeline and poll status."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.jobs.store import JobType

jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("/default-prompt", methods=["GET"])
def get_default_prompt():
    """Return the default extraction system prompt so users can view or copy it."""
    from alpha_signal.extractors.base import SYSTEM_PROMPT

    return jsonify({"system_prompt": SYSTEM_PROMPT})


def _get_store():
    return getattr(current_app, "job_store", None)


def _require_store():
    store = _get_store()
    if store is None:
        raise RuntimeError("Job store not configured")
    return store


# ---- Ingest ----

@jobs_bp.route("/ingest", methods=["POST"])
def start_ingest():
    """Start an ingest job. Returns 202 with job_id."""
    store = _require_store()
    body = request.get_json(silent=True) or {}
    query = body.get("query")
    date_from = body.get("date_from")
    date_to = body.get("date_to")
    if not query and not date_from and not date_to:
        return jsonify({"error": "At least one of query, date_from, or date_to is required"}), 400
    params = {
        "query": query,
        "date_from": date_from,
        "date_to": date_to,
        "sources": body.get("sources"),
        "max_results_per_source": body.get("max_results_per_source"),
    }
    params = {k: v for k, v in params.items() if v is not None}
    record = store.create(JobType.INGEST, params=params)
    return jsonify({"job_id": record.job_id}), 202


# ---- Extract ----

@jobs_bp.route("/extract", methods=["POST"])
def start_extract():
    """Start an extract job. Returns 202 with job_id.

    Optional body: model, budget_usd, skip_existing, provider, system_prompt.
    Pass system_prompt to use a custom extraction prompt for iteration.
    """
    store = _require_store()
    body = request.get_json(silent=True) or {}
    params = {
        "model": body.get("model", "gpt-4o-mini"),
        "budget_usd": body.get("budget_usd", 1.0),
        "skip_existing": body.get("skip_existing", True),
        "provider": body.get("provider"),
        "system_prompt": body.get("system_prompt"),
    }
    params = {k: v for k, v in params.items() if v is not None}
    record = store.create(JobType.EXTRACT, params=params)
    return jsonify({"job_id": record.job_id}), 202


# ---- Pipeline ----

@jobs_bp.route("/pipeline", methods=["POST"])
def start_pipeline():
    """Start a full pipeline (ingest then extract) job. Returns 202 with job_id.

    Optional body: system_prompt for custom extraction prompt.
    """
    store = _require_store()
    body = request.get_json(silent=True) or {}
    query = body.get("query")
    date_from = body.get("date_from")
    date_to = body.get("date_to")
    if not query and not date_from and not date_to:
        return jsonify({"error": "At least one of query, date_from, or date_to is required"}), 400
    params = {
        "query": query,
        "date_from": date_from,
        "date_to": date_to,
        "sources": body.get("sources"),
        "max_results_per_source": body.get("max_results_per_source"),
        "model": body.get("model", "gpt-4o-mini"),
        "budget_usd": body.get("budget_usd", 1.0),
        "system_prompt": body.get("system_prompt"),
    }
    params = {k: v for k, v in params.items() if v is not None}
    record = store.create(JobType.PIPELINE, params=params)
    return jsonify({"job_id": record.job_id}), 202


# ---- Status ----

@jobs_bp.route("/<job_id>", methods=["GET"])
def get_job(job_id: str):
    """Return job status and result/error."""
    store = _require_store()
    record = store.get(job_id)
    if record is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(record.to_dict())


@jobs_bp.route("", methods=["GET"])
def list_jobs():
    """List recent jobs with optional type filter and pagination."""
    store = _require_store()
    limit = request.args.get("limit", type=int, default=50)
    offset = request.args.get("offset", type=int, default=0)
    job_type_str = request.args.get("type", type=str, default=None)
    limit = min(max(1, limit), 200)
    offset = max(0, offset)
    job_type = None
    if job_type_str:
        try:
            job_type = JobType(job_type_str)
        except ValueError:
            return jsonify({"error": f"Invalid type: {job_type_str}"}), 400
    records = store.list_jobs(limit=limit, offset=offset, job_type=job_type)
    return jsonify({
        "items": [r.to_dict() for r in records],
        "limit": limit,
        "offset": offset,
    })
