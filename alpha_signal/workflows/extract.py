"""Flyte workflows for cost estimation and LLM extraction.

Usage::

    # Estimate cost (no API calls, free)
    pyflyte run alpha_signal/workflows/extract.py estimate_wf \
        --cache_path articles.db \
        --model gpt-4o-mini

    # Run extraction (costs money)
    pyflyte run alpha_signal/workflows/extract.py extract_wf \
        --cache_path articles.db \
        --model gpt-4o-mini \
        --budget_usd 0.50 \
        --output_path extractions.json
"""

from __future__ import annotations

import json

from flytekit import task, workflow

from alpha_signal.cache.sqlite import SQLiteArticleCache
from alpha_signal.extractors.openai import OpenAIExtractor
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction
from alpha_signal.monitoring.costs import CostTracker
from alpha_signal.services.extraction import extract_batch


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
        print(msg)
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
    print(summary)
    return summary


@task
def extract(
    cache_path: str = "articles.db",
    model: str = "gpt-4o-mini",
    budget_usd: float = 1.0,
    output_path: str = "extractions.json",
) -> str:
    """Run LLM extraction on all cached articles.

    Writes results to *output_path* as JSON and returns a cost summary.
    """
    with SQLiteArticleCache(cache_path) as cache:
        articles = cache.all()

    if not articles:
        msg = "No articles in cache. Run the ingest workflow first."
        print(msg)
        return msg

    print(f"Extracting {len(articles)} articles with {model} (budget: ${budget_usd:.2f})")

    tracker = CostTracker(model=model, budget_usd=budget_usd)
    extractor = OpenAIExtractor(model=model, cost_tracker=tracker)

    results = extract_batch(
        articles,
        extractor,
        cost_tracker=tracker,
        system_prompt=OpenAIExtractor.SYSTEM_PROMPT,
    )

    _write_results(results, output_path)
    print(f"Wrote {len(results)} extractions to {output_path}")

    summary = tracker.summary()
    print(f"Cost: {summary}")
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
    model: str = "gpt-4o-mini",
    budget_usd: float = 1.0,
    output_path: str = "extractions.json",
) -> str:
    """Run LLM extraction on cached articles with budget enforcement."""
    return extract(
        cache_path=cache_path,
        model=model,
        budget_usd=budget_usd,
        output_path=output_path,
    )


def _write_results(
    results: list[tuple[Article, ArticleExtraction]],
    output_path: str,
) -> None:
    output = []
    for article, extraction in results:
        output.append({
            "article": {
                "source": article.source,
                "source_id": article.source_id,
                "title": article.title,
                "doi": article.doi,
                "publication_date": (
                    article.publication_date.isoformat() if article.publication_date else None
                ),
                "url": article.url,
                "venue": article.venue,
                "authors": article.authors,
            },
            "extraction": extraction.model_dump(mode="json"),
        })
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
