"""Service functions for article ingestion.

These functions orchestrate across one or more :class:`BaseSource` instances
and are the primary public API for the ingestion layer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date

from alpha_signal.models.articles import Article
from alpha_signal.sources.base import BaseSource

logger = logging.getLogger(__name__)


def search(
    sources: Iterable[BaseSource],
    *,
    query: str | None = None,
    max_results_per_source: int | None = 10,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Article]:
    """Search every *source* and return a flat list of results.

    Either *query* or at least one of *date_from* / *date_to* must be set.
    When *query* is None and dates are set, sources return all articles
    in that date range (subject to *max_results_per_source*).

    When *max_results_per_source* is None, each source returns all matching
    results (paginates until exhausted). When it is an int, each source
    returns at most that many.

    If *date_from* or *date_to* are set, they are passed to each source to
    restrict results to that publication/submission date range (single day:
    set both to the same date; full year: e.g. date_from=date(2024,1,1),
    date_to=date(2024,12,31)). Sources that do not support date filtering
    ignore the range.

    Sources that raise are logged and skipped so one flaky API doesn't
    take down the whole pipeline.
    """
    if query is None and not (date_from or date_to):
        raise ValueError("Either query or at least one of date_from/date_to must be set.")
    articles: list[Article] = []
    for source in sources:
        try:
            hits = source.search(
                query=query,
                max_results=max_results_per_source,
                date_from=date_from,
                date_to=date_to,
            )
            logger.info(
                "%s returned %d results%s",
                source.name,
                len(hits),
                f" for {query!r}" if query else " (date range)",
            )
            articles.extend(hits)
        except Exception:
            logger.exception("search failed for source %s", source.name)
    return articles


def fetch(identifier: str, source: BaseSource) -> Article | None:
    """Fetch a single article by its source-specific *identifier*."""
    try:
        return source.fetch_by_id(identifier)
    except Exception:
        logger.exception("fetch failed for %s on source %s", identifier, source.name)
        return None


def deduplicate(articles: list[Article]) -> list[Article]:
    """Remove duplicate articles based on DOI, falling back to title matching.

    When two articles share a DOI, the one from the source with higher
    metadata quality (more fields populated) is kept.
    """
    by_doi: dict[str, Article] = {}
    by_title: dict[str, Article] = {}
    unique: list[Article] = []

    for article in articles:
        if article.doi:
            key = article.doi.lower()
            if key in by_doi:
                existing = by_doi[key]
                if _richness(article) > _richness(existing):
                    unique.remove(existing)
                    by_doi[key] = article
                    unique.append(article)
                continue
            by_doi[key] = article

        title_key = _normalise_title(article.title)
        if title_key and title_key in by_title:
            existing = by_title[title_key]
            if _richness(article) > _richness(existing):
                unique.remove(existing)
                by_title[title_key] = article
                unique.append(article)
            continue
        if title_key:
            by_title[title_key] = article

        unique.append(article)

    return unique


def _richness(article: Article) -> int:
    """Score how many optional fields are populated — used for dedup tiebreaks."""
    score = 0
    if article.abstract:
        score += 2
    if article.doi:
        score += 1
    if article.publication_date:
        score += 1
    if article.citation_count is not None:
        score += 1
    if article.authors:
        score += 1
    if article.categories:
        score += 1
    return score


def _normalise_title(title: str) -> str:
    return " ".join(title.lower().split())
