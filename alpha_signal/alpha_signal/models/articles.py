"""Unified data model for scientific articles across all sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Article:
    """Source-agnostic representation of a scientific article.

    Every ingestion source normalises its API response into this shape so that
    downstream stages (extraction, analysis, signal generation) never need to
    know which source the article came from.
    """

    source: str
    source_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = field(default_factory=list)
    publication_date: date | None = None
    doi: str | None = None
    url: str | None = None
    venue: str | None = None
    citation_count: int | None = None
    categories: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)
