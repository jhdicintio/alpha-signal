"""Service functions for LLM-powered article extraction.

These functions orchestrate extraction across batches of articles and are the
primary public API for the extraction layer.
"""

from __future__ import annotations

import logging

from alpha_signal.extractors.base import BaseExtractor
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction
from alpha_signal.monitoring.costs import CostTracker

logger = logging.getLogger(__name__)


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
) -> list[tuple[Article, ArticleExtraction]]:
    """Extract structured data from every article in *articles*.

    Returns a list of ``(article, extraction)`` pairs.  Articles that fail
    extraction or lack an abstract (when *skip_no_abstract* is True) are
    silently omitted from the output.

    When *cost_tracker* is provided with a budget, the batch will:

    1. **Pre-check**: estimate the total cost and raise
       :class:`BudgetExceededError` if the estimate exceeds the remaining
       budget.
    2. **Mid-batch check**: after each extraction, verify that the running
       actual cost has not exceeded the budget.  If it has, stop early and
       return whatever has been extracted so far.
    """
    eligible = [
        a for a in articles
        if not skip_no_abstract or a.abstract
    ]
    skipped = len(articles) - len(eligible)
    if skipped:
        logger.debug("skipping %d articles without abstracts", skipped)

    if cost_tracker and system_prompt and eligible:
        estimate = cost_tracker.estimate_batch(eligible, system_prompt)
        logger.info("cost estimate: %s", estimate)

        if cost_tracker.would_exceed_budget(estimate.estimated_cost_usd):
            raise BudgetExceededError(
                f"Estimated cost ${estimate.estimated_cost_usd:.4f} would exceed "
                f"remaining budget ${cost_tracker.budget_remaining_usd:.4f}"
            )

    results: list[tuple[Article, ArticleExtraction]] = []

    for article in eligible:
        if cost_tracker and cost_tracker.budget_usd is not None:
            if cost_tracker.total_cost_usd >= cost_tracker.budget_usd:
                logger.warning(
                    "budget exhausted ($%.4f / $%.2f) — stopping batch after %d/%d articles",
                    cost_tracker.total_cost_usd,
                    cost_tracker.budget_usd,
                    len(results),
                    len(eligible),
                )
                break

        extraction = extract_article(article, extractor)
        if extraction is not None:
            results.append((article, extraction))

    logger.info("batch complete: %d/%d articles extracted", len(results), len(articles))
    return results
