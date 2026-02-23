"""Unit tests for SQLiteArticleCache."""

from __future__ import annotations

from datetime import date

from alpha_signal.cache.sqlite import SQLiteArticleCache
from alpha_signal.models.articles import Article


def _make_article(**overrides) -> Article:
    defaults = dict(
        source="test",
        source_id="1",
        title="Test Article",
        abstract="A test abstract.",
        authors=["Alice", "Bob"],
        publication_date=date(2024, 6, 15),
        doi="10.1234/test",
        url="https://example.com/paper",
        venue="Nature",
        citation_count=42,
        categories=["Physics", "Chemistry"],
        raw={"key": "value"},
    )
    defaults.update(overrides)
    return Article(**defaults)


class TestPutAndGet:
    def test_round_trip(self):
        with SQLiteArticleCache(":memory:") as cache:
            article = _make_article()
            cache.put(article)
            retrieved = cache.get("test", "1")

        assert retrieved is not None
        assert retrieved.source == article.source
        assert retrieved.source_id == article.source_id
        assert retrieved.title == article.title
        assert retrieved.abstract == article.abstract
        assert retrieved.authors == article.authors
        assert retrieved.publication_date == article.publication_date
        assert retrieved.doi == article.doi
        assert retrieved.url == article.url
        assert retrieved.venue == article.venue
        assert retrieved.citation_count == article.citation_count
        assert retrieved.categories == article.categories
        assert retrieved.raw == article.raw

    def test_get_nonexistent_returns_none(self):
        with SQLiteArticleCache(":memory:") as cache:
            assert cache.get("nope", "nope") is None

    def test_put_overwrites_existing(self):
        with SQLiteArticleCache(":memory:") as cache:
            cache.put(_make_article(title="Version 1"))
            cache.put(_make_article(title="Version 2"))

            retrieved = cache.get("test", "1")

        assert retrieved is not None
        assert retrieved.title == "Version 2"

    def test_nullable_fields(self):
        article = _make_article(
            abstract=None,
            publication_date=None,
            doi=None,
            url=None,
            venue=None,
            citation_count=None,
            raw={},
        )
        with SQLiteArticleCache(":memory:") as cache:
            cache.put(article)
            retrieved = cache.get("test", "1")

        assert retrieved is not None
        assert retrieved.abstract is None
        assert retrieved.publication_date is None
        assert retrieved.doi is None
        assert retrieved.citation_count is None


class TestPutMany:
    def test_batch_insert(self):
        articles = [
            _make_article(source_id="1", title="First"),
            _make_article(source_id="2", title="Second"),
            _make_article(source_id="3", title="Third"),
        ]
        with SQLiteArticleCache(":memory:") as cache:
            cache.put_many(articles)
            assert cache.count() == 3

    def test_batch_upsert(self):
        with SQLiteArticleCache(":memory:") as cache:
            cache.put(_make_article(source_id="1", title="Original"))
            cache.put_many([
                _make_article(source_id="1", title="Updated"),
                _make_article(source_id="2", title="New"),
            ])
            assert cache.count() == 2
            assert cache.get("test", "1").title == "Updated"


class TestContains:
    def test_returns_true_when_present(self):
        with SQLiteArticleCache(":memory:") as cache:
            cache.put(_make_article())
            assert cache.contains("test", "1") is True

    def test_returns_false_when_absent(self):
        with SQLiteArticleCache(":memory:") as cache:
            assert cache.contains("test", "1") is False


class TestCount:
    def test_empty_cache(self):
        with SQLiteArticleCache(":memory:") as cache:
            assert cache.count() == 0

    def test_after_inserts(self):
        with SQLiteArticleCache(":memory:") as cache:
            cache.put_many([
                _make_article(source_id="1"),
                _make_article(source_id="2"),
            ])
            assert cache.count() == 2


class TestAll:
    def test_returns_all_articles(self):
        with SQLiteArticleCache(":memory:") as cache:
            cache.put_many([
                _make_article(source_id="1", title="A"),
                _make_article(source_id="2", title="B"),
            ])
            articles = cache.all()

        assert len(articles) == 2
        titles = {a.title for a in articles}
        assert titles == {"A", "B"}


class TestClear:
    def test_removes_all(self):
        with SQLiteArticleCache(":memory:") as cache:
            cache.put_many([
                _make_article(source_id="1"),
                _make_article(source_id="2"),
            ])
            assert cache.count() == 2
            cache.clear()
            assert cache.count() == 0


class TestMultipleSources:
    def test_same_source_id_different_sources(self):
        with SQLiteArticleCache(":memory:") as cache:
            cache.put(_make_article(source="arxiv", source_id="1", title="arXiv paper"))
            cache.put(_make_article(source="openalex", source_id="1", title="OpenAlex paper"))

            assert cache.count() == 2
            assert cache.get("arxiv", "1").title == "arXiv paper"
            assert cache.get("openalex", "1").title == "OpenAlex paper"
