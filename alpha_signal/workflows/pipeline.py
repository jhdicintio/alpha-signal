"""Flyte workflow that runs the full pipeline: ingest → extract.

Usage::

    pyflyte run alpha_signal/workflows/pipeline.py pipeline_wf \
        --query "solid state batteries" \
        --sources "[arxiv,openalex,europe_pmc]" \
        --max_results_per_source 20 \
        --model gpt-4o-mini \
        --budget_usd 0.50

    # Date-only ingest (no query):
    pyflyte run alpha_signal/workflows/pipeline.py pipeline_wf \
        --date_from 2024-01-01 --date_to 2024-12-31
"""

from __future__ import annotations

from typing import Optional

from flytekit import dynamic

from alpha_signal.workflows.extract import extract
from alpha_signal.workflows.ingest import SourceEnum, ingest_wf


@dynamic
def pipeline_wf(
    query: Optional[str] = None,
    sources: Optional[list[SourceEnum]] = None,
    max_results_per_source: Optional[int] = 20,
    cache_path: str = "articles.db",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    model: str = "gpt-4o-mini",
    budget_usd: float = 1.0,
    output_path: str = "extractions.json",
) -> str:
    """Full pipeline: ingest articles from sources, then extract with LLM.

    Pass *query* to search, or omit *query* and pass *date_from* and/or
    *date_to* to ingest all articles in that date range.

    Returns the extraction cost summary.
    """
    ingest_wf(
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
