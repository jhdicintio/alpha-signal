"""Articles API endpoints."""

from flask import Blueprint, current_app, jsonify, request

from app.cache import get_cache
from app.serializers import article_to_dict, extraction_to_dict

articles_bp = Blueprint("articles", __name__)


def _filter_articles_by_date_and_source(
    articles: list,
    source: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list:
    """Filter articles by source and publication date range."""
    out = articles
    if source:
        out = [a for a in out if a.source == source]
    if date_from:
        try:
            from datetime import date

            d_from = date.fromisoformat(date_from)
            out = [a for a in out if a.publication_date and a.publication_date >= d_from]
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import date

            d_to = date.fromisoformat(date_to)
            out = [a for a in out if a.publication_date and a.publication_date <= d_to]
        except ValueError:
            pass
    return out


@articles_bp.route("", methods=["GET"])
def list_articles():
    """List articles with optional pagination and filters."""
    limit = request.args.get("limit", type=int, default=50)
    offset = request.args.get("offset", type=int, default=0)
    source = request.args.get("source", type=str, default=None)
    publication_date_from = request.args.get("publication_date_from", type=str, default=None)
    publication_date_to = request.args.get("publication_date_to", type=str, default=None)

    limit = min(max(1, limit), 200)
    offset = max(0, offset)

    try:
        with get_cache(current_app) as cache:
            articles = cache.all()
            articles = _filter_articles_by_date_and_source(
                articles, source, publication_date_from, publication_date_to
            )
            total = len(articles)
            page = articles[offset : offset + limit]
            results = [article_to_dict(a) for a in page]
        return jsonify({
            "items": results,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@articles_bp.route("/<source>/<source_id>", methods=["GET"])
def get_article(source: str, source_id: str):
    """Single article, optionally with its extraction."""
    with_extraction = request.args.get("with_extraction", type=str, default="")
    with_extraction = with_extraction.lower() in ("1", "true", "yes")

    try:
        with get_cache(current_app) as cache:
            article = cache.get(source, source_id)
            if article is None:
                return jsonify({"error": "Article not found"}), 404
            payload = {"article": article_to_dict(article)}
            if with_extraction:
                extraction = cache.get_extraction(source, source_id)
                if extraction:
                    payload["extraction"] = extraction_to_dict(extraction)
                else:
                    payload["extraction"] = None
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
