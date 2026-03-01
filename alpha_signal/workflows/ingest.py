"""Flyte workflows for article ingestion.

Provides three entry points:

* **ingest_wf** — ingest articles for a single date window (or query).
  Sources run in parallel via a dynamic workflow; results are merged,
  deduplicated, and cached in a single downstream task.

* **backfill_wf** — historical backfill from *start_year* to *end_year*,
  chunked month-by-month.  Each month is a separate ``ingest_wf`` execution.

* **daily_lp** — a Flyte :class:`LaunchPlan` with a daily cron schedule
  that performs incremental ingestion using the high-water-mark strategy.

Usage::

    # Single window
    pyflyte run alpha_signal/workflows/ingest.py ingest_wf \
        --query "solid state batteries" --date_from 2024-01-01 --date_to 2024-12-31

    # Backfill 2015-present
    pyflyte run alpha_signal/workflows/ingest.py backfill_wf \
        --start_year 2015 --end_year 2025

    # Daily incremental (runs via cron or manually)
    pyflyte run alpha_signal/workflows/ingest.py daily_ingest_wf \
        --cache_path articles.db
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from enum import Enum
from typing import Optional

from flytekit import LaunchPlan, CronSchedule, dynamic, task, workflow

from alpha_signal.cache.sqlite import SQLiteArticleCache
from alpha_signal.models.articles import Article
from alpha_signal.services.ingestion import deduplicate, incremental_ingest
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


def _build_source(source_enum: SourceEnum) -> BaseSource:
    return _SOURCE_REGISTRY[source_enum]()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@task
def ingest_source(
    source: SourceEnum,
    query: Optional[str] = None,
    max_results_per_source: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[Article]:
    """Fetch articles from a single source. Meant to run in parallel."""
    src = _build_source(source)
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

    try:
        articles = src.search(
            query=query,
            max_results=max_results_per_source,
            date_from=date_from_d,
            date_to=date_to_d,
        )
    except Exception:
        logger.exception("ingest_source failed for %s", source.value)
        return []
    finally:
        src.close()

    logger.info("%s: fetched %d articles", source.value, len(articles))
    return articles


@task
def deduplicate_and_cache(
    batches: list[list[Article]],
    cache_path: str = "articles.db",
) -> int:
    """Merge per-source batches, deduplicate, and write to cache.

    Returns the total number of articles now in the cache.
    """
    all_articles: list[Article] = []
    for batch in batches:
        all_articles.extend(batch)
    logger.info("collected %d raw articles from %d sources", len(all_articles), len(batches))

    unique = deduplicate(all_articles)
    logger.info("%d after deduplication", len(unique))

    with SQLiteArticleCache(cache_path) as cache:
        existing_count_before = cache.count()
        new_articles = [
            a for a in unique if not cache.contains(a.source, a.source_id)
        ]
        if new_articles:
            cache.put_many(new_articles)
        total = cache.count()

    logger.info(
        "cache: %d new articles added (%d -> %d total)",
        len(new_articles),
        existing_count_before,
        total,
    )
    return total


@task
def daily_ingest_task(
    cache_path: str = "articles.db",
    sources: Optional[list[SourceEnum]] = None,
    query: Optional[str] = None,
) -> int:
    """Incremental ingest using the high-water-mark strategy.

    For each source, fetches only articles newer than what is already cached
    (minus a small overlap window), deduplicates, and writes new ones.
    """
    source_list = sources if sources else _DEFAULT_SOURCES

    with SQLiteArticleCache(cache_path) as cache:
        all_new: list[Article] = []
        for source_enum in source_list:
            src = _build_source(source_enum)
            try:
                new = incremental_ingest(src, cache, query=query)
                all_new.extend(new)
            finally:
                src.close()

        unique = deduplicate(all_new)
        if unique:
            cache.put_many(unique)

        total = cache.count()

    logger.info(
        "daily ingest: %d new articles added, cache now holds %d",
        len(unique),
        total,
    )
    return total


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------


@dynamic
def ingest_wf(
    query: Optional[str] = None,
    sources: Optional[list[SourceEnum]] = None,
    max_results_per_source: Optional[int] = None,
    cache_path: str = "articles.db",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> int:
    """Ingest articles from scientific sources into the local cache.

    Sources run as parallel tasks; results are merged and deduplicated in a
    single downstream task.
    """
    source_list = sources if sources else _DEFAULT_SOURCES

    if query is None and not (date_from or date_to):
        raise ValueError("When query is omitted, at least one of date_from or date_to must be set.")

    batches: list[list[Article]] = []
    for source_enum in source_list:
        batch = ingest_source(
            source=source_enum,
            query=query,
            max_results_per_source=max_results_per_source,
            date_from=date_from,
            date_to=date_to,
        )
        batches.append(batch)

    return deduplicate_and_cache(batches=batches, cache_path=cache_path)


@dynamic
def backfill_wf(
    start_year: int = 2015,
    end_year: int = 2025,
    sources: Optional[list[SourceEnum]] = None,
    cache_path: str = "articles.db",
    query: Optional[str] = None,
) -> int:
    """Historical backfill, chunked month-by-month.

    Iterates from *start_year*-01 through *end_year*-12 and runs
    ``ingest_wf`` for each month.  Each month is checkpointed independently
    so a failure mid-way can be resumed.
    """
    total = 0
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            if date(year, month, 1) > date.today():
                break
            last_day = calendar.monthrange(year, month)[1]
            df = date(year, month, 1).isoformat()
            dt = date(year, month, last_day).isoformat()
            total = ingest_wf(
                query=query,
                sources=sources,
                max_results_per_source=None,
                cache_path=cache_path,
                date_from=df,
                date_to=dt,
            )
    return total


@workflow
def daily_ingest_wf(
    cache_path: str = "articles.db",
    sources: Optional[list[SourceEnum]] = None,
    query: Optional[str] = None,
) -> int:
    """Thin workflow wrapper around the daily incremental ingest task."""
    return daily_ingest_task(
        cache_path=cache_path,
        sources=sources,
        query=query,
    )


# ---------------------------------------------------------------------------
# Launch Plan (daily cron)
# ---------------------------------------------------------------------------

daily_lp = LaunchPlan.get_or_create(
    workflow=daily_ingest_wf,
    name="daily_ingest",
    schedule=CronSchedule(schedule="0 6 * * *"),
    default_inputs={"cache_path": "articles.db"},
)
