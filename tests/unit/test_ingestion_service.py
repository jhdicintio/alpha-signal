"""Unit tests for the ingestion service layer."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from alpha_signal.models.articles import Article
from alpha_signal.services.ingestion import deduplicate, fetch, search


def _make_article(**overrides) -> Article:
    defaults = dict(
        source="test",
        source_id="1",
        title="Default Title",
        abstract="An abstract.",
        authors=["Author"],
        publication_date=date(2024, 1, 1),
        doi="10.1234/default",
    )
    defaults.update(overrides)
    return Article(**defaults)


class TestSearch:
    def test_aggregates_from_multiple_sources(self):
        src_a = MagicMock()
        src_a.name = "a"
        src_a.search.return_value = [_make_article(source="a", source_id="1")]

        src_b = MagicMock()
        src_b.name = "b"
        src_b.search.return_value = [_make_article(source="b", source_id="2")]

        results = search(
            sources=[src_a, src_b],
            query="test",
            max_results_per_source=5,
        )

        assert len(results) == 2
        assert results[0].source == "a"
        assert results[1].source == "b"
        src_a.search.assert_called_once_with(
            query="test", max_results=5, date_from=None, date_to=None
        )
        src_b.search.assert_called_once_with(
            query="test", max_results=5, date_from=None, date_to=None
        )

    def test_search_passes_date_range_to_sources(self):
        src = MagicMock()
        src.name = "s"
        src.search.return_value = []
        date_from = date(2024, 1, 1)
        date_to = date(2024, 12, 31)

        search(
            sources=[src],
            query="battery",
            max_results_per_source=10,
            date_from=date_from,
            date_to=date_to,
        )

        src.search.assert_called_once_with(
            query="battery",
            max_results=10,
            date_from=date_from,
            date_to=date_to,
        )

    def test_raises_when_no_query_nor_dates(self):
        src = MagicMock()
        src.name = "s"
        with pytest.raises(ValueError, match="Either query or at least one"):
            search(sources=[src])

    def test_skips_failing_source(self):
        good = MagicMock()
        good.name = "good"
        good.search.return_value = [_make_article(source="good")]

        bad = MagicMock()
        bad.name = "bad"
        bad.search.side_effect = ConnectionError("timeout")

        results = search(sources=[bad, good], query="test")

        assert len(results) == 1
        assert results[0].source == "good"

    def test_empty_sources(self):
        results = search(sources=[], query="test")
        assert results == []


class TestFetch:
    def test_fetch_delegates_to_source(self):
        article = _make_article()
        src = MagicMock()
        src.name = "test"
        src.fetch_by_id.return_value = article

        result = fetch("1", src)

        assert result is article
        src.fetch_by_id.assert_called_once_with("1")

    def test_fetch_returns_none_on_error(self):
        src = MagicMock()
        src.name = "test"
        src.fetch_by_id.side_effect = RuntimeError("boom")

        result = fetch("1", src)

        assert result is None


class TestDeduplicate:
    def test_removes_doi_duplicates(self):
        a = _make_article(source="s1", source_id="1", doi="10.1234/same")
        b = _make_article(source="s2", source_id="2", doi="10.1234/same")
        result = deduplicate([a, b])
        assert len(result) == 1

    def test_keeps_richer_article_on_doi_collision(self):
        sparse = _make_article(
            source="sparse",
            source_id="1",
            doi="10.1234/same",
            abstract=None,
            citation_count=None,
            categories=[],
        )
        rich = _make_article(
            source="rich",
            source_id="2",
            doi="10.1234/same",
            abstract="Full abstract here.",
            citation_count=42,
            categories=["Physics"],
        )
        result = deduplicate([sparse, rich])
        assert len(result) == 1
        assert result[0].source == "rich"

    def test_removes_title_duplicates(self):
        a = _make_article(source="s1", source_id="1", doi=None, title="Same Title")
        b = _make_article(source="s2", source_id="2", doi=None, title="Same Title")
        result = deduplicate([a, b])
        assert len(result) == 1

    def test_title_dedup_is_case_insensitive(self):
        a = _make_article(source="s1", source_id="1", doi=None, title="A Great Paper")
        b = _make_article(source="s2", source_id="2", doi=None, title="a great paper")
        result = deduplicate([a, b])
        assert len(result) == 1

    def test_different_articles_are_preserved(self):
        a = _make_article(source="s1", source_id="1", doi="10.1/a", title="Paper A")
        b = _make_article(source="s2", source_id="2", doi="10.1/b", title="Paper B")
        result = deduplicate([a, b])
        assert len(result) == 2

    def test_doi_dedup_is_case_insensitive(self):
        a = _make_article(source="s1", source_id="1", doi="10.1234/ABC")
        b = _make_article(source="s2", source_id="2", doi="10.1234/abc")
        result = deduplicate([a, b])
        assert len(result) == 1

    def test_empty_list(self):
        assert deduplicate([]) == []

    def test_single_article(self):
        a = _make_article()
        assert deduplicate([a]) == [a]
