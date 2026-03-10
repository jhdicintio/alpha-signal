"""Extractions API endpoints."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from flask import Blueprint, current_app, jsonify, request

from app.cache import get_cache
from app.serializers import extraction_with_article_to_dict

extractions_bp = Blueprint("extractions", __name__)


def _filter_by_sector(items: list, sector: str) -> list:
    """Filter (source, source_id, extraction) triples by extraction.technologies[].sector."""
    if not sector or not sector.strip():
        return items
    sector_lower = sector.strip().lower()
    out = []
    for source, source_id, extraction in items:
        for tech in extraction.technologies:
            if (tech.sector or "").lower() == sector_lower:
                out.append((source, source_id, extraction))
                break
    return out


def _filter_by_maturity(items: list, maturity: str) -> list:
    """Filter to extractions that have at least one technology with the given maturity."""
    if not maturity or not maturity.strip():
        return items
    mat_lower = maturity.strip().lower()
    out = []
    for source, source_id, extraction in items:
        for tech in extraction.technologies:
            if (tech.maturity or "").lower() == mat_lower:
                out.append((source, source_id, extraction))
                break
    return out


def _filter_by_sentiment(items: list, sentiment: str) -> list:
    """Filter by extraction-level sentiment."""
    if not sentiment or not sentiment.strip():
        return items
    sent_lower = sentiment.strip().lower()
    return [(s, sid, ext) for s, sid, ext in items if (ext.sentiment or "").lower() == sent_lower]


def _filter_by_novelty(items: list, novelty: str) -> list:
    """Filter by extraction-level novelty."""
    if not novelty or not novelty.strip():
        return items
    nov_lower = novelty.strip().lower()
    return [(s, sid, ext) for s, sid, ext in items if (ext.novelty or "").lower() == nov_lower]


def _filter_by_technology(items: list, technology: str) -> list:
    """Filter to extractions that mention a technology matching the substring (case-insensitive)."""
    if not technology or not technology.strip():
        return items
    tech_lower = technology.strip().lower()
    out = []
    for source, source_id, extraction in items:
        for tech in extraction.technologies:
            if tech_lower in (tech.technology or "").lower():
                out.append((source, source_id, extraction))
                break
    return out


def _filter_by_quantitative_claims(items: list, value: bool) -> list:
    """Filter to extractions that have at least one claim with quantitative=True."""
    if not value:
        return items
    return [(s, sid, ext) for s, sid, ext in items if any(c.quantitative for c in (ext.claims or []))]


def _sort_items_by_publication_date(items: list, cache, order: str) -> list:
    """Sort (source, source_id, extraction) triples by article publication_date. order is 'asc' or 'desc'."""
    with_dates = []
    for s, sid, ext in items:
        article = cache.get(s, sid)
        pub = article.publication_date if article else None
        with_dates.append((pub, s, sid, ext))
    reverse = order.lower() == "desc"
    with_dates.sort(key=lambda x: (x[0] is None, x[0] if x[0] else date.min), reverse=reverse)
    return [(s, sid, ext) for _, s, sid, ext in with_dates]


@extractions_bp.route("", methods=["GET"])
def list_extractions():
    """List extractions with optional pagination, filters, and sort."""
    limit = request.args.get("limit", type=int, default=50)
    offset = request.args.get("offset", type=int, default=0)
    source = request.args.get("source", type=str, default=None)
    extraction_model = request.args.get("extraction_model", type=str, default=None)
    sector = request.args.get("sector", type=str, default=None)
    maturity = request.args.get("maturity", type=str, default=None)
    sentiment = request.args.get("sentiment", type=str, default=None)
    novelty = request.args.get("novelty", type=str, default=None)
    technology = request.args.get("technology", type=str, default=None)
    quantitative_claims = request.args.get("quantitative_claims", type=str, default="")
    quantitative_claims = quantitative_claims.lower() in ("1", "true", "yes")
    sort = request.args.get("sort", type=str, default=None)
    order = request.args.get("order", type=str, default="desc")

    limit = min(max(1, limit), 200)
    offset = max(0, offset)

    try:
        with get_cache(current_app) as cache:
            items = cache.all_extractions(model=extraction_model)
            if source:
                items = [(s, sid, ext) for s, sid, ext in items if s == source]
            if sector:
                items = _filter_by_sector(items, sector)
            if maturity:
                items = _filter_by_maturity(items, maturity)
            if sentiment:
                items = _filter_by_sentiment(items, sentiment)
            if novelty:
                items = _filter_by_novelty(items, novelty)
            if technology:
                items = _filter_by_technology(items, technology)
            if quantitative_claims:
                items = _filter_by_quantitative_claims(items, True)
            if sort and sort.lower() == "publication_date":
                items = _sort_items_by_publication_date(items, cache, order or "desc")
            total = len(items)
            page = items[offset : offset + limit]
            results = []
            for s, sid, extraction in page:
                article = cache.get(s, sid)
                results.append(extraction_with_article_to_dict(s, sid, article, extraction))
        return jsonify({
            "items": results,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@extractions_bp.route("/aggregates", methods=["GET"])
def get_aggregates():
    """Return aggregated counts for sectors, maturity, sentiment, novelty, and top N sectors/technologies."""
    sector_filter = request.args.get("sector", type=str, default=None)
    top_n = request.args.get("top", type=int, default=50)
    top_n = min(max(1, top_n), 200)

    try:
        with get_cache(current_app) as cache:
            items = cache.all_extractions(model=None)
            if sector_filter:
                items = _filter_by_sector(items, sector_filter)

            by_sector = defaultdict(int)
            by_sector_maturity = defaultdict(lambda: defaultdict(int))
            by_sector_sentiment = defaultdict(lambda: defaultdict(int))
            by_maturity = defaultdict(int)
            by_sentiment = defaultdict(int)
            by_novelty = defaultdict(int)
            technology_counts = defaultdict(lambda: defaultdict(int))  # technology -> sector -> count

            for _s, _sid, ext in items:
                sent = (ext.sentiment or "neutral").lower()
                nov = (ext.novelty or "incremental").lower()
                by_sentiment[sent] += 1
                by_novelty[nov] += 1
                sectors_in_ext = set()
                for tech in ext.technologies or []:
                    sec = (tech.sector or "Unknown").strip() or "Unknown"
                    mat = (tech.maturity or "theoretical").lower()
                    tech_name = (tech.technology or "Unknown").strip() or "Unknown"
                    by_sector[sec] += 1
                    by_sector_maturity[sec][mat] += 1
                    by_maturity[mat] += 1
                    sectors_in_ext.add(sec)
                    technology_counts[tech_name][sec] = technology_counts[tech_name][sec] + 1
                for sec in sectors_in_ext:
                    by_sector_sentiment[sec][sent] += 1

            top_sectors = sorted(by_sector.items(), key=lambda x: -x[1])[:top_n]
            top_technologies_flat = []
            for tech_name, sec_counts in technology_counts.items():
                total = sum(sec_counts.values())
                primary_sector = max(sec_counts.items(), key=lambda x: x[1])[0]
                top_technologies_flat.append({"technology": tech_name, "sector": primary_sector, "count": total})
            top_technologies = sorted(top_technologies_flat, key=lambda x: -x["count"])[:top_n]

        return jsonify({
            "by_sector": dict(by_sector),
            "by_sector_maturity": {k: dict(v) for k, v in by_sector_maturity.items()},
            "by_sector_sentiment": {k: dict(v) for k, v in by_sector_sentiment.items()},
            "by_maturity": dict(by_maturity),
            "by_sentiment": dict(by_sentiment),
            "by_novelty": dict(by_novelty),
            "top_sectors": [{"sector": s, "count": c} for s, c in top_sectors],
            "top_technologies": top_technologies,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@extractions_bp.route("/trends", methods=["GET"])
def get_trends():
    """Return time-bucketed extraction counts (by month). Optional filters: from, to, sector."""
    from_date_str = request.args.get("from", type=str, default=None)
    to_date_str = request.args.get("to", type=str, default=None)
    sector_filter = request.args.get("sector", type=str, default=None)
    group_by = request.args.get("group_by", type=str, default="month")

    try:
        from_date = date.fromisoformat(from_date_str) if from_date_str else None
    except ValueError:
        from_date = None
    try:
        to_date = date.fromisoformat(to_date_str) if to_date_str else None
    except ValueError:
        to_date = None

    if group_by != "month":
        return jsonify({"error": "Only group_by=month is supported"}), 400

    try:
        with get_cache(current_app) as cache:
            items = cache.all_extractions(model=None)
            if sector_filter:
                items = _filter_by_sector(items, sector_filter)

            buckets = defaultdict(int)
            for s, sid, ext in items:
                article = cache.get(s, sid)
                pub = article.publication_date if article else None
                if pub is None:
                    continue
                if from_date and pub < from_date:
                    continue
                if to_date and pub > to_date:
                    continue
                key = pub.replace(day=1).isoformat()[:7]
                buckets[key] += 1

            points = [{"period": k, "count": v} for k, v in sorted(buckets.items())]
        return jsonify({"group_by": "month", "points": points})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@extractions_bp.route("/<source>/<source_id>", methods=["GET"])
def get_extraction(source: str, source_id: str):
    """Single extraction with article."""
    extraction_model = request.args.get("extraction_model", type=str, default=None)
    try:
        with get_cache(current_app) as cache:
            extraction = cache.get_extraction(source, source_id, model=extraction_model)
            if extraction is None:
                return jsonify({"error": "Extraction not found"}), 404
            article = cache.get(source, source_id)
            payload = extraction_with_article_to_dict(source, source_id, article, extraction)
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
