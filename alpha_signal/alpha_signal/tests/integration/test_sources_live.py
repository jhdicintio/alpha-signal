"""Integration tests that hit live APIs.

Run with:  pytest -m integration
Skip with: pytest -m 'not integration'

These tests make real HTTP requests.  They validate that our parsing logic
works against the actual API responses (which can change without notice).
Each test uses a well-known query that should always return results.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from alpha_signal.models.articles import Article
from alpha_signal.services.ingestion import search
from alpha_signal.sources.arxiv import ArxivSource
from alpha_signal.sources.europe_pmc import EuropePMCSource
from alpha_signal.sources.openalex import OpenAlexSource
from alpha_signal.sources.semantic_scholar import SemanticScholarSource


def _skip_on_rate_limit(func):
    """Decorator that converts HTTP 429 into a ``pytest.skip``."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                pytest.skip(f"Rate-limited by {exc.request.url.host}")
            raise
    wrapper.__name__ = func.__name__
    wrapper.__qualname__ = func.__qualname__
    return wrapper

pytestmark = pytest.mark.integration


def _assert_valid_article(article: Article) -> None:
    """Shared assertions — every article from every source should pass these."""
    assert isinstance(article, Article)
    assert article.source
    assert article.source_id
    assert article.title
    assert isinstance(article.authors, list)
    assert isinstance(article.categories, list)


class TestSemanticScholarLive:
    @_skip_on_rate_limit
    def test_search(self):
        with SemanticScholarSource() as src:
            results = src.search(query="machine learning", max_results=3)

        assert len(results) > 0
        for art in results:
            _assert_valid_article(art)
            assert art.source == "semantic_scholar"

    @_skip_on_rate_limit
    def test_search_with_date_range(self):
        """Live call with date filter; all returned articles should be in range."""
        date_from = date(2024, 1, 1)
        date_to = date(2024, 12, 31)
        with SemanticScholarSource() as src:
            results = src.search(
                query="transformer neural network",
                max_results=20,
                date_from=date_from,
                date_to=date_to,
            )
        for art in results:
            _assert_valid_article(art)
            assert art.source == "semantic_scholar"
            assert art.publication_date is not None
            assert date_from <= art.publication_date <= date_to

    @_skip_on_rate_limit
    def test_fetch_by_id(self):
        with SemanticScholarSource() as src:
            art = src.fetch_by_id("204e3073870fae3d05bcbc2f6a8e263d9b72e776")

        assert art is not None
        _assert_valid_article(art)
        assert "attention" in art.title.lower()


class TestOpenAlexLive:
    def test_search(self):
        with OpenAlexSource() as src:
            results = src.search(query="quantum computing", max_results=3)

        assert len(results) > 0
        for art in results:
            _assert_valid_article(art)
            assert art.source == "openalex"

    def test_search_with_date_range(self):
        """Live call with date filter; all returned articles should be in range."""
        date_from = date(2024, 1, 1)
        date_to = date(2024, 12, 31)
        with OpenAlexSource() as src:
            results = src.search(
                query="perovskite solar",
                max_results=20,
                date_from=date_from,
                date_to=date_to,
            )
        for art in results:
            _assert_valid_article(art)
            assert art.source == "openalex"
            assert art.publication_date is not None
            assert date_from <= art.publication_date <= date_to

    def test_fetch_by_id(self):
        with OpenAlexSource() as src:
            art = src.fetch_by_id("W2741809807")

        assert art is not None
        _assert_valid_article(art)


class TestArxivLive:
    def test_search(self):
        with ArxivSource() as src:
            results = src.search(query="neural network", max_results=3)

        assert len(results) > 0
        for art in results:
            _assert_valid_article(art)
            assert art.source == "arxiv"
            assert art.venue == "arXiv"

    def test_search_with_date_range(self):
        """Live call with date filter; all returned articles should be in range."""
        date_from = date(2024, 1, 1)
        date_to = date(2024, 12, 31)
        with ArxivSource() as src:
            results = src.search(
                query="machine learning",
                max_results=20,
                date_from=date_from,
                date_to=date_to,
            )
        # We may get 0 or more; if we get any, they must be in range
        for art in results:
            _assert_valid_article(art)
            assert art.source == "arxiv"
            assert art.publication_date is not None
            assert date_from <= art.publication_date <= date_to

    def test_fetch_by_id(self):
        # "Attention Is All You Need" on arXiv
        with ArxivSource() as src:
            art = src.fetch_by_id("1706.03762")

        assert art is not None
        _assert_valid_article(art)
        assert "attention" in art.title.lower()


class TestEuropePMCLive:
    def test_search(self):
        with EuropePMCSource() as src:
            results = src.search(query="CRISPR", max_results=3)

        assert len(results) > 0
        for art in results:
            _assert_valid_article(art)
            assert art.source == "europe_pmc"

    def test_search_with_date_range(self):
        """Live call with date filter; all returned articles should be in range."""
        date_from = date(2023, 1, 1)
        date_to = date(2023, 12, 31)
        with EuropePMCSource() as src:
            results = src.search(
                "CRISPR",
                max_results=20,
                date_from=date_from,
                date_to=date_to,
            )
        for art in results:
            _assert_valid_article(art)
            assert art.source == "europe_pmc"
            assert art.publication_date is not None
            assert date_from <= art.publication_date <= date_to

    def test_fetch_by_id(self):
        # A well-known CRISPR review paper
        with EuropePMCSource() as src:
            art = src.fetch_by_id("26422227")

        assert art is not None
        _assert_valid_article(art)


class TestIngestionSearchDateRangeLive:
    """Integration tests for ingestion.search() with date range across sources."""

    def test_search_with_date_range_returns_only_in_range(self):
        """Service search with date_from/date_to; all articles should be in range."""
        date_from = date(2024, 1, 1)
        date_to = date(2024, 6, 30)
        sources = [ArxivSource(), OpenAlexSource()]

        articles = search(
            sources=sources,
            query="battery",
            max_results_per_source=15,
            date_from=date_from,
            date_to=date_to,
        )

        for art in articles:
            _assert_valid_article(art)
            assert art.publication_date is not None, (
                f"Article {art.source_id} has no publication_date"
            )
            assert date_from <= art.publication_date <= date_to, (
                f"Article {art.source_id} date {art.publication_date} outside "
                f"[{date_from}, {date_to}]"
            )

    def test_search_without_date_range_returns_articles(self):
        """Sanity check: search without date filter still returns results."""
        sources = [ArxivSource(), OpenAlexSource()]
        articles = search(sources=sources, query="quantum", max_results_per_source=5)
        assert len(articles) > 0
        for art in articles:
            _assert_valid_article(art)
