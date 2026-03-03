"""Flyte workflows for cost estimation and LLM extraction.

Usage::

    # Estimate cost (no API calls, free)
    pyflyte run alpha_signal/workflows/extract.py estimate_wf \
        --cache_path articles.db \
        --model gpt-4o-mini

    # Run extraction (costs money) — provider is auto-detected from model name
    pyflyte run alpha_signal/workflows/extract.py extract_wf \
        --cache_path articles.db \
        --model gpt-4o-mini \
        --budget_usd 0.50

    # Anthropic
    pyflyte run alpha_signal/workflows/extract.py extract_wf \
        --model claude-sonnet-4-20250514

    # Gemini
    pyflyte run alpha_signal/workflows/extract.py extract_wf \
        --model gemini-2.0-flash
"""

from __future__ import annotations

import logging
from enum import Enum

from flytekit import task, workflow

from alpha_signal.cache.sqlite import SQLiteArticleCache
from alpha_signal.extractors.anthropic import AnthropicExtractor
from alpha_signal.extractors.base import SYSTEM_PROMPT, BaseExtractor
from alpha_signal.extractors.gemini import GeminiExtractor
from alpha_signal.extractors.openai import OpenAIExtractor
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction
from alpha_signal.monitoring.costs import CostTracker
from alpha_signal.services.extraction import extract_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class Provider(str, Enum):
    openai = "openai"
    anthropic = "anthropic"
    gemini = "gemini"


_PROVIDER_PREFIXES: list[tuple[str, Provider]] = [
    ("gpt-", Provider.openai),
    ("o1", Provider.openai),
    ("o3", Provider.openai),
    ("o4", Provider.openai),
    ("claude-", Provider.anthropic),
    ("gemini-", Provider.gemini),
]


def _detect_provider(model: str) -> Provider:
    for prefix, provider in _PROVIDER_PREFIXES:
        if model.startswith(prefix):
            return provider
    raise ValueError(
        f"Cannot detect provider for model {model!r}. "
        f"Pass an explicit --provider or use a model name starting with "
        f"gpt-/claude-/gemini-."
    )


def _build_extractor(
    model: str,
    provider: Provider | None = None,
    cost_tracker: CostTracker | None = None,
) -> BaseExtractor:
    prov = provider or _detect_provider(model)
    if prov == Provider.openai:
        return OpenAIExtractor(model=model, cost_tracker=cost_tracker)
    if prov == Provider.anthropic:
        return AnthropicExtractor(model=model)
    if prov == Provider.gemini:
        return GeminiExtractor(model=model)
    raise ValueError(f"Unknown provider: {prov}")


@task
def estimate_cost(
    cache_path: str = "articles.db",
    model: str = "gpt-4o-mini",
) -> str:
    """Estimate extraction cost for all cached articles (no API calls).

    Returns a formatted cost summary string.
    """
    with SQLiteArticleCache(cache_path) as cache:
        articles = cache.all()

    if not articles:
        msg = "No articles in cache. Run the ingest workflow first."
        logger.warning("%s", msg)
        return msg

    extractor = OpenAIExtractor(api_key="unused", model=model)
    estimate = extractor.estimate_cost(articles)

    lines = [
        "=== Cost Estimate ===",
        str(estimate),
        "",
        f"  Model:          {estimate.model}",
        f"  Articles:       {estimate.num_articles}",
        f"  Input tokens:   ~{estimate.total_input_tokens:,}",
        f"  Output tokens:  ~{estimate.estimated_output_tokens:,}",
        f"  Estimated cost: ${estimate.estimated_cost_usd:.4f}",
    ]
    summary = "\n".join(lines)
    logger.info("%s", summary)
    return summary


@task
def extract(
    cache_path: str = "articles.db",
    model: str = "gemini-2.5-flash",
    budget_usd: float = 1.0,
    skip_existing: bool = True,
    max_concurrency: int = 10,
) -> str:
    """Run LLM extraction on cached articles and persist results.

    Extractions are stored in the same SQLite database alongside articles.
    When *skip_existing* is True, articles that already have an extraction
    for the given model are skipped.

    *max_concurrency* controls how many API requests run in parallel.
    Set to 1 for sequential execution.
    """
    with SQLiteArticleCache(cache_path) as cache:
        all_articles = cache.all()
        total_cached = len(all_articles)

        if not all_articles:
            msg = "No articles in cache. Run the ingest workflow first."
            logger.warning("%s", msg)
            return msg

        logger.info("▶ extract  model=%s  budget=$%.2f  skip_existing=%s  max_concurrency=%d",
                     model, budget_usd, skip_existing, max_concurrency)
        logger.info("  cache contains %d articles, %d existing extractions for %s",
                     total_cached, cache.extraction_count(model=model), model)

        articles = all_articles
        if skip_existing:
            articles = [
                a for a in all_articles
                if not cache.has_extraction(a.source, a.source_id, model=model)
            ]
            skipped = total_cached - len(articles)
            if skipped:
                logger.info("  skipping %d articles already extracted with %s", skipped, model)
            if not articles:
                msg = f"All {total_cached} articles already extracted with {model}."
                logger.info("✔ %s", msg)
                return msg

        logger.info("  %d articles to extract", len(articles))

        tracker = CostTracker(model=model, budget_usd=budget_usd)
        extractor = _build_extractor(model, cost_tracker=tracker)

        def _persist(article: Article, extraction: ArticleExtraction) -> None:
            cache.put_extraction(article.source, article.source_id, extraction)

        results = extract_batch(
            articles,
            extractor,
            cost_tracker=tracker,
            system_prompt=SYSTEM_PROMPT,
            max_concurrency=max_concurrency,
            on_result=_persist,
        )

        logger.info("✔ persisted %d extractions to cache (%d total for %s)",
                     len(results), cache.extraction_count(model=model), model)

    summary = tracker.summary()
    logger.info("  cost: %s", summary)
    return summary


@workflow
def estimate_wf(
    cache_path: str = "articles.db",
    model: str = "gpt-4o-mini",
) -> str:
    """Estimate extraction cost without spending anything."""
    return estimate_cost(cache_path=cache_path, model=model)


@workflow
def extract_wf(
    cache_path: str = "articles.db",
    model: str = "gemini-2.5-flash",
    budget_usd: float = 1.0,
    skip_existing: bool = True,
    max_concurrency: int = 10,
) -> str:
    """Run LLM extraction on cached articles with budget enforcement."""
    return extract(
        cache_path=cache_path,
        model=model,
        budget_usd=budget_usd,
        skip_existing=skip_existing,
        max_concurrency=max_concurrency,
    )
