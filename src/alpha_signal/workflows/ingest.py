"""Flyte workflow for article ingestion.

Usage::

    pyflyte run src/alpha_signal/workflows/ingest.py ingest_wf \
        --query "solid state batteries" \
        --sources "arxiv,openalex,europe_pmc" \
        --max_results_per_source 20 \
        --cache_path articles.db

    # Restrict to a date range (optional):
    pyflyte run src/alpha_signal/workflows/ingest.py ingest_wf \
        --query "quantum computing" \
        --date_from 2024-01-01 \
        --date_to 2024-12-31

    # Single day:
    pyflyte run src/alpha_signal/workflows/ingest.py ingest_wf \
        --query "battery" --date_from 2024-06-15 --date_to 2024-06-15
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from flytekit import task, workflow

from alpha_signal.cache.sqlite import SQLiteArticleCache
from alpha_signal.services.ingestion import deduplicate, search
from alpha_signal.sources.arxiv import ArxivSource
from alpha_signal.sources.base import BaseSource
from alpha_signal.sources.europe_pmc import EuropePMCSource
from alpha_signal.sources.openalex import OpenAlexSource
from alpha_signal.sources.semantic_scholar import SemanticScholarSource

_SOURCE_REGISTRY: dict[str, type[BaseSource]] = {
    "arxiv": ArxivSource,
    "openalex": OpenAlexSource,
    "semantic_scholar": SemanticScholarSource,
    "europe_pmc": EuropePMCSource,
}


def _build_sources(source_names: str) -> list[BaseSource]:
    names = [s.strip() for s in source_names.split(",") if s.strip()]
    sources = []
    for name in names:
        cls = _SOURCE_REGISTRY.get(name)
        if cls is None:
            print(f"  [warn] unknown source {name!r}, skipping")
            continue
        sources.append(cls())
    return sources


@task
def ingest(
    query: str,
    sources: str = "arxiv,openalex,europe_pmc",
    max_results_per_source: int = 20,
    cache_path: str = "articles.db",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Search article sources, deduplicate, and cache results.

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
            print(f"  [warn] invalid date_from {date_from!r}, ignoring")
    if date_to:
        try:
            date_to_d = date.fromisoformat(date_to)
        except ValueError:
            print(f"  [warn] invalid date_to {date_to!r}, ignoring")

    source_list = _build_sources(sources)
    print(f"Searching {len(source_list)} sources for: {query!r}")
    if date_from_d or date_to_d:
        print(f"  date range: {date_from_d or '…'} to {date_to_d or '…'}")

    articles = search(
        query,
        source_list,
        max_results_per_source=max_results_per_source,
        date_from=date_from_d,
        date_to=date_to_d,
    )
    print(f"  found {len(articles)} raw results")

    articles = deduplicate(articles)
    print(f"  {len(articles)} after deduplication")

    with SQLiteArticleCache(cache_path) as cache:
        cache.put_many(articles)
        total = cache.count()

    print(f"  cache now holds {total} articles ({cache_path})")
    return total


@workflow
def ingest_wf(
    query: str,
    sources: str = "arxiv,openalex,europe_pmc",
    max_results_per_source: int = 20,
    cache_path: str = "articles.db",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Ingest articles from scientific sources into the local cache."""
    return ingest(
        query=query,
        sources=sources,
        max_results_per_source=max_results_per_source,
        cache_path=cache_path,
        date_from=date_from,
        date_to=date_to,
    )
