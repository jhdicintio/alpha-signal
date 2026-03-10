"""Flyte workflows for cost estimation and LLM extraction.

Default is local SLM on CPU (no API key, $0 cost). Usage::

    # Default: local SLM (Qwen 0.5B on CPU)
    pyflyte run alpha_signal/workflows/extract.py estimate_wf
    pyflyte run alpha_signal/workflows/extract.py extract_wf

    # Cloud providers — set model and optionally provider (auto-detected from model name)
    pyflyte run alpha_signal/workflows/extract.py extract_wf \
        --model gpt-4o-mini --provider openai --budget_usd 0.50
    pyflyte run alpha_signal/workflows/extract.py extract_wf \
        --model claude-sonnet-4-20250514 --provider anthropic
    pyflyte run alpha_signal/workflows/extract.py extract_wf \
        --model gemini-2.0-flash --provider gemini
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from flytekit import task, workflow

from alpha_signal.cache.sqlite import SQLiteArticleCache
from alpha_signal.extractors.anthropic import AnthropicExtractor
from alpha_signal.extractors.base import SYSTEM_PROMPT, BaseExtractor
from alpha_signal.extractors.gemini import GeminiExtractor
from alpha_signal.extractors.local import LocalExtractor
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
    local = "local"


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
        f"Pass an explicit --provider (e.g. local) or use a model name starting with "
        f"gpt-/claude-/gemini-."
    )


def _build_extractor(
    model: str,
    provider: Provider | None = None,
    cost_tracker: CostTracker | None = None,
    device: str | None = None,
) -> BaseExtractor:
    prov = provider or _detect_provider(model)
    if prov == Provider.openai:
        return OpenAIExtractor(model=model, cost_tracker=cost_tracker)
    if prov == Provider.anthropic:
        return AnthropicExtractor(model=model)
    if prov == Provider.gemini:
        return GeminiExtractor(model=model)
    if prov == Provider.local:
        return LocalExtractor(
            model=model,
            cost_tracker=cost_tracker,
            device=device or "cpu",
        )
    raise ValueError(f"Unknown provider: {prov}")


_DEFAULT_LOCAL_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def _load_system_prompt(system_prompt_path: str | None) -> str:
    """Return system prompt from file if path given, else default."""
    if system_prompt_path and Path(system_prompt_path).is_file():
        return Path(system_prompt_path).read_text()
    return SYSTEM_PROMPT


@task
def estimate_cost(
    cache_path: str = "articles.db",
    model: str = _DEFAULT_LOCAL_MODEL,
    provider: str | None = "local",
    system_prompt_path: str | None = None,
) -> str:
    """Estimate extraction cost for all cached articles (no API calls).

    Default is local SLM (no API cost). Returns a formatted cost summary string.
    For local provider, cost is $0. Pass *system_prompt_path* to use a custom prompt.
    """
    with SQLiteArticleCache(cache_path) as cache:
        articles = cache.all()

    if not articles:
        msg = "No articles in cache. Run the ingest workflow first."
        logger.warning("%s", msg)
        return msg

    prov = Provider(provider) if (provider and str(provider).strip()) else None
    extractor = _build_extractor(model, provider=prov)
    system_prompt = _load_system_prompt(system_prompt_path)
    estimate = extractor.estimate_cost(articles, system_prompt=system_prompt)

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
    model: str = _DEFAULT_LOCAL_MODEL,
    budget_usd: float = 1.0,
    skip_existing: bool = True,
    max_concurrency: int = 1,
    provider: str | None = "local",
    device: str | None = None,
    system_prompt_path: str | None = None,
) -> str:
    """Run LLM extraction on cached articles and persist results.

    Default is local SLM on CPU (no API key, $0 cost). For GPU pass device=cuda.
    CPU: keep max_concurrency=1. GPU: try 2–4 to overlap work.

    Extractions are stored in the same SQLite database alongside articles.
    When *skip_existing* is True, articles that already have an extraction
    for the given model are skipped. Pass *system_prompt_path* to use a custom
    extraction prompt (file path).

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

        prov = Provider(provider) if (provider and str(provider).strip()) else None
        tracker = CostTracker(model=model, budget_usd=budget_usd)
        extractor = _build_extractor(
            model, provider=prov, cost_tracker=tracker, device=device
        )

        def _persist(article: Article, extraction: ArticleExtraction) -> None:
            cache.put_extraction(article.source, article.source_id, extraction)

        system_prompt = _load_system_prompt(system_prompt_path)
        results = extract_batch(
            articles,
            extractor,
            cost_tracker=tracker,
            system_prompt=system_prompt,
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
    model: str = _DEFAULT_LOCAL_MODEL,
    provider: str | None = "local",
    system_prompt_path: str | None = None,
) -> str:
    """Estimate extraction cost without spending anything. Default is local SLM."""
    return estimate_cost(
        cache_path=cache_path,
        model=model,
        provider=provider,
        system_prompt_path=system_prompt_path,
    )


@workflow
def extract_wf(
    cache_path: str = "articles.db",
    model: str = _DEFAULT_LOCAL_MODEL,
    budget_usd: float = 1.0,
    skip_existing: bool = True,
    max_concurrency: int = 1,
    provider: str | None = "local",
    device: str | None = None,
    system_prompt_path: str | None = None,
) -> str:
    """Run LLM extraction on cached articles. Default is local SLM on CPU."""
    return extract(
        cache_path=cache_path,
        model=model,
        budget_usd=budget_usd,
        skip_existing=skip_existing,
        max_concurrency=max_concurrency,
        provider=provider,
        device=device,
        system_prompt_path=system_prompt_path,
    )
