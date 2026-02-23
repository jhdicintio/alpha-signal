"""Unit tests for the Article data model."""

from __future__ import annotations

from datetime import date

import pytest

from alpha_signal.models.articles import Article


class TestArticleCreation:
    def test_minimal_fields(self):
        article = Article(source="test", source_id="1", title="Test Title")

        assert article.source == "test"
        assert article.source_id == "1"
        assert article.title == "Test Title"
        assert article.abstract is None
        assert article.authors == []
        assert article.publication_date is None
        assert article.doi is None
        assert article.url is None
        assert article.venue is None
        assert article.citation_count is None
        assert article.categories == []
        assert article.raw == {}

    def test_all_fields(self):
        article = Article(
            source="test",
            source_id="42",
            title="Full Article",
            abstract="An abstract.",
            authors=["Alice", "Bob"],
            publication_date=date(2024, 6, 15),
            doi="10.1234/test",
            url="https://example.com/paper",
            venue="Nature",
            citation_count=99,
            categories=["Physics"],
            raw={"key": "value"},
        )

        assert article.authors == ["Alice", "Bob"]
        assert article.publication_date == date(2024, 6, 15)
        assert article.doi == "10.1234/test"
        assert article.citation_count == 99
        assert article.raw == {"key": "value"}


class TestArticleImmutability:
    def test_frozen_prevents_mutation(self):
        article = Article(source="test", source_id="1", title="Immutable")
        with pytest.raises(AttributeError):
            article.title = "Changed"  # type: ignore[misc]


class TestArticleEquality:
    def test_equal_articles(self):
        kwargs = dict(source="test", source_id="1", title="Same")
        assert Article(**kwargs) == Article(**kwargs)

    def test_different_articles(self):
        a = Article(source="test", source_id="1", title="A")
        b = Article(source="test", source_id="2", title="B")
        assert a != b
