"""Flyte workflow that runs the full pipeline: ingest → extract.

Usage::

    pyflyte run alpha_signal/workflows/pipeline.py pipeline_wf \
        --query "solid state batteries" \
        --sources "arxiv,openalex,europe_pmc" \
        --max_results_per_source 20 \
        --model gpt-4o-mini \
        --budget_usd 0.50
"""

from __future__ import annotations

from typing import Optional

from flytekit import workflow

from alpha_signal.workflows.extract import extract
from alpha_signal.workflows.ingest import ingest


@workflow
def pipeline_wf(
    query: str,
    sources: str = "arxiv,openalex,europe_pmc",
    max_results_per_source: int = 20,
    cache_path: str = "articles.db",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    model: str = "gpt-4o-mini",
    budget_usd: float = 1.0,
    output_path: str = "extractions.json",
) -> str:
    """Full pipeline: ingest articles from sources, then extract with LLM.

    Optional *date_from* and *date_to* are ISO dates (YYYY-MM-DD) to restrict
    ingestion to a publication/submission date range.

    Returns the extraction cost summary.
    """
    ingest(
        query=query,
        sources=sources,
        max_results_per_source=max_results_per_source,
        cache_path=cache_path,
        date_from=date_from,
        date_to=date_to,
    )
    return extract(
        cache_path=cache_path,
        model=model,
        budget_usd=budget_usd,
        output_path=output_path,
    )
