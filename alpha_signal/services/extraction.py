"""Service functions for LLM-powered article extraction.

These functions orchestrate extraction across batches of articles and are the
primary public API for the extraction layer.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable

from alpha_signal.extractors.base import BaseExtractor
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction
from alpha_signal.monitoring.costs import CostTracker

ResultCallback = Callable[[Article, ArticleExtraction], None]

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENCY = 30


class BudgetExceededError(Exception):
    """Raised when extraction would exceed the configured budget."""


def extract_article(
    article: Article,
    extractor: BaseExtractor,
) -> ArticleExtraction | None:
    """Extract structured data from a single *article*.

    Returns ``None`` (instead of raising) if the extraction fails so that
    callers processing batches can skip failures gracefully.
    """
    try:
        result = extractor.extract(article)
        logger.info(
            "extracted %d technologies from %r (%s)",
            len(result.technologies),
            article.title[:60],
            article.source,
        )
        return result
    except ImportError:
        # Missing optional deps (e.g. [local]) — fail fast so user sees one clear error
        raise
    except RuntimeError as e:
        # Device/setup errors (e.g. CUDA not available) — fail fast so batch stops
        msg = str(e).lower()
        if "cuda" in msg or "device" in msg or "torch not compiled" in msg:
            raise
        logger.exception("extraction failed for article %s", article.source_id)
        return None
    except Exception:
        logger.exception("extraction failed for article %s", article.source_id)
        return None


def extract_batch(
    articles: list[Article],
    extractor: BaseExtractor,
    *,
    skip_no_abstract: bool = True,
    cost_tracker: CostTracker | None = None,
    system_prompt: str | None = None,
    max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    on_result: ResultCallback | None = None,
) -> list[tuple[Article, ArticleExtraction]]:
    """Extract structured data from every article in *articles*.

    Returns a list of ``(article, extraction)`` pairs.  Articles that fail
    extraction or lack an abstract (when *skip_no_abstract* is True) are
    silently omitted from the output.

    When *max_concurrency* > 1, extractions run as concurrent async tasks
    using the extractor's ``extract_async`` method.  Set to 1 for sequential
    execution.

    *on_result*, when provided, is called immediately after each successful
    extraction with ``(article, extraction)``.  Use this to persist results
    incrementally so progress is not lost if the process is interrupted.

    When *cost_tracker* is provided with a budget, the batch will:

    1. **Pre-check**: estimate the total cost and raise
       :class:`BudgetExceededError` if the estimate exceeds the remaining
       budget.
    2. **Mid-batch check** (sequential only): after each extraction, verify
       that the running actual cost has not exceeded the budget.
    """
    eligible = [
        a for a in articles
        if not skip_no_abstract or a.abstract
    ]
    skipped = len(articles) - len(eligible)
    if skipped:
        logger.info("skipping %d articles without abstracts", skipped)

    if cost_tracker and system_prompt and eligible:
        estimate = cost_tracker.estimate_batch(eligible, system_prompt)
        logger.info("cost estimate: %s", estimate)

        if cost_tracker.would_exceed_budget(estimate.estimated_cost_usd):
            raise BudgetExceededError(
                f"Estimated cost ${estimate.estimated_cost_usd:.4f} would exceed "
                f"remaining budget ${cost_tracker.budget_remaining_usd:.4f}"
            )

    if max_concurrency > 1 and len(eligible) > 1:
        logger.info("running with max_concurrency=%d", max_concurrency)
        return _extract_batch_concurrent(
            eligible, extractor,
            skipped=skipped,
            cost_tracker=cost_tracker,
            max_concurrency=max_concurrency,
            on_result=on_result,
        )

    return _extract_batch_sequential(
        eligible, extractor,
        skipped=skipped,
        cost_tracker=cost_tracker,
        on_result=on_result,
    )


def _extract_batch_sequential(
    eligible: list[Article],
    extractor: BaseExtractor,
    *,
    skipped: int = 0,
    cost_tracker: CostTracker | None = None,
    on_result: ResultCallback | None = None,
) -> list[tuple[Article, ArticleExtraction]]:
    total = len(eligible)
    results: list[tuple[Article, ArticleExtraction]] = []
    failures = 0

    for i, article in enumerate(eligible, 1):
        if cost_tracker and cost_tracker.budget_usd is not None:
            if cost_tracker.total_cost_usd >= cost_tracker.budget_usd:
                logger.warning(
                    "budget exhausted ($%.4f / $%.2f) — stopping batch after %d/%d articles",
                    cost_tracker.total_cost_usd,
                    cost_tracker.budget_usd,
                    len(results),
                    total,
                )
                break

        logger.info(
            "[%d/%d] extracting %s — %r",
            i, total, article.source_id, article.title[:80],
        )
        extraction = extract_article(article, extractor)
        if extraction is not None:
            results.append((article, extraction))
            if on_result:
                on_result(article, extraction)
            cost_str = f"  ${cost_tracker.total_cost_usd:.4f}" if cost_tracker else ""
            logger.info(
                "[%d/%d] ✔ %d technologies, %d claims  (%s / %s)%s",
                i, total,
                len(extraction.technologies),
                len(extraction.claims),
                extraction.novelty.value,
                extraction.sentiment.value,
                cost_str,
            )
        else:
            failures += 1

    logger.info(
        "batch complete: %d/%d extracted, %d failed, %d skipped (no abstract)",
        len(results), total + skipped, failures, skipped,
    )
    return results


def _extract_batch_concurrent(
    eligible: list[Article],
    extractor: BaseExtractor,
    *,
    skipped: int = 0,
    cost_tracker: CostTracker | None = None,
    max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    on_result: ResultCallback | None = None,
) -> list[tuple[Article, ArticleExtraction]]:
    """Run extractions concurrently using asyncio + semaphore."""
    total = len(eligible)
    results: list[tuple[Article, ArticleExtraction]] = []
    failures = 0
    lock = threading.Lock()
    completed = 0

    async def _run() -> None:
        nonlocal completed, failures
        sem = asyncio.Semaphore(max_concurrency)

        async def _extract_one(idx: int, article: Article) -> None:
            nonlocal completed, failures
            async with sem:
                logger.info(
                    "[%d/%d] extracting %s — %r",
                    idx, total, article.source_id, article.title[:80],
                )
                try:
                    extraction = await extractor.extract_async(article)
                except Exception:
                    logger.exception("extraction failed for article %s", article.source_id)
                    with lock:
                        failures += 1
                    return

                with lock:
                    completed += 1
                    results.append((article, extraction))
                    if on_result:
                        on_result(article, extraction)
                    cost_str = f"  ${cost_tracker.total_cost_usd:.4f}" if cost_tracker else ""
                    logger.info(
                        "[%d/%d] ✔ %d technologies, %d claims  (%s / %s)%s",
                        completed, total,
                        len(extraction.technologies),
                        len(extraction.claims),
                        extraction.novelty.value,
                        extraction.sentiment.value,
                        cost_str,
                    )

        tasks = [
            asyncio.create_task(_extract_one(i, article))
            for i, article in enumerate(eligible, 1)
        ]
        await asyncio.gather(*tasks)

    asyncio.run(_run())

    logger.info(
        "batch complete: %d/%d extracted, %d failed, %d skipped (no abstract)",
        len(results), total + skipped, failures, skipped,
    )
    return results
