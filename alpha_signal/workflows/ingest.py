"""Flyte workflow for article ingestion.

Usage::

    pyflyte run alpha_signal/workflows/ingest.py ingest_wf \
        --query "solid state batteries" \
        --sources "[arxiv,openalex,europe_pmc]" \
        --max_results_per_source 20 \
        --cache_path articles.db

    # Date-only: all articles on given dates (no query):
    pyflyte run alpha_signal/workflows/ingest.py ingest_wf \
        --date_from 2024-01-01 \
        --date_to 2024-12-31

    # Single day:
    pyflyte run alpha_signal/workflows/ingest.py ingest_wf \
        --query "battery" --date_from 2024-06-15 --date_to 2024-06-15
"""

from __future__ import annotations

import logging
from datetime import date
from enum import Enum
from typing import Optional

from flytekit import task, workflow

from alpha_signal.cache.sqlite import SQLiteArticleCache
from alpha_signal.services.ingestion import deduplicate, search
from alpha_signal.sources.arxiv import ArxivSource
from alpha_signal.sources.base import BaseSource
from alpha_signal.sources.europe_pmc import EuropePMCSource
from alpha_signal.sources.openalex import OpenAlexSource
from alpha_signal.sources.semantic_scholar import SemanticScholarSource

logger = logging.getLogger(__name__)


class SourceEnum(str, Enum):
    """Article source identifier; maps to the corresponding source class."""

    arxiv = "arxiv"
    openalex = "openalex"
    semantic_scholar = "semantic_scholar"
    europe_pmc = "europe_pmc"


_SOURCE_REGISTRY: dict[SourceEnum, type[BaseSource]] = {
    SourceEnum.arxiv: ArxivSource,
    SourceEnum.openalex: OpenAlexSource,
    SourceEnum.semantic_scholar: SemanticScholarSource,
    SourceEnum.europe_pmc: EuropePMCSource,
}

_DEFAULT_SOURCES = [
    SourceEnum.arxiv,
    SourceEnum.openalex,
    SourceEnum.europe_pmc,
]


def _build_sources(source_list: list[SourceEnum]) -> list[BaseSource]:
    return [_SOURCE_REGISTRY[s]() for s in source_list]


@task
def ingest(
    query: Optional[str] = None,
    sources: Optional[list[SourceEnum]] = None,
    max_results_per_source: Optional[int | None] = None,
    cache_path: str = "articles.db",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Search article sources, deduplicate, and cache results.

    *query* is optional. If omitted, *date_from* and/or *date_to* must be
    provided to fetch all articles in that date range; otherwise an error
    is raised.

    Optional *date_from* and *date_to* are ISO dates (YYYY-MM-DD). Pass both
    for a range, or the same value for a single day. Omit for no date filter.

    Returns the number of articles now in the cache.
    """
    date_from_d: date | None = None
    date_to_d: date | None = None
    if date_from:
        try:
            date_from_d = date.fromisoformat(date_from)
        except ValueError:
            logger.warning("invalid date_from %r, ignoring", date_from)
    if date_to:
        try:
            date_to_d = date.fromisoformat(date_to)
        except ValueError:
            logger.warning("invalid date_to %r, ignoring", date_to)

    if query is None and not (date_from_d or date_to_d):
        raise ValueError("When query is omitted, at least one of date_from or date_to must be set.")

    source_list = _build_sources(sources)
    if query is not None:
        logger.info("Searching %d sources for: %r", len(source_list), query)
    else:
        logger.info("Fetching all articles from %d sources in date range", len(source_list))
    if date_from_d or date_to_d:
        logger.info("date range: %s to %s", date_from_d or "…", date_to_d or "…")

    articles = search(
        query=query,
        sources=source_list,
        max_results_per_source=max_results_per_source,
        date_from=date_from_d,
        date_to=date_to_d,
    )
    logger.info("found %d raw results", len(articles))

    articles = deduplicate(articles)
    logger.info("%d after deduplication", len(articles))

    with SQLiteArticleCache(cache_path) as cache:
        cache.put_many(articles)
        total = cache.count()

    logger.info("cache now holds %d articles (%s)", total, cache_path)
    return total


@workflow
def ingest_wf(
    query: Optional[str] = None,
    sources: Optional[list[SourceEnum]] = _DEFAULT_SOURCES,
    max_results_per_source: Optional[int | None] = None,
    cache_path: str = "articles.db",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Ingest articles from scientific sources into the local cache.

    Pass *query* to search, or omit *query* and pass *date_from* and/or
    *date_to* to fetch all articles in that date range.
    """
    return ingest(
        query=query,
        sources=sources,
        max_results_per_source=max_results_per_source,
        cache_path=cache_path,
        date_from=date_from,
        date_to=date_to,
    )
