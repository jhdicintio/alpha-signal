"""Unit tests for SQLiteArticleCache."""

from __future__ import annotations

import json
import sqlite3
import zlib
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


class TestRawCompression:
    def test_raw_round_trips_through_compression(self):
        raw = {"nested": {"key": [1, 2, 3]}, "text": "hello world" * 100}
        article = _make_article(raw=raw)

        with SQLiteArticleCache(":memory:") as cache:
            cache.put(article)
            retrieved = cache.get("test", "1")

        assert retrieved.raw == raw

    def test_raw_stored_as_blob(self):
        article = _make_article(raw={"big": "data" * 500})

        with SQLiteArticleCache(":memory:") as cache:
            cache.put(article)
            row = cache._conn.execute(
                "SELECT typeof(raw) as t, raw FROM articles WHERE source = 'test'"
            ).fetchone()

        assert row["t"] == "blob"
        decompressed = json.loads(zlib.decompress(row["raw"]))
        assert decompressed == {"big": "data" * 500}

    def test_empty_raw_stores_null(self):
        article = _make_article(raw={})

        with SQLiteArticleCache(":memory:") as cache:
            cache.put(article)
            retrieved = cache.get("test", "1")

        assert retrieved.raw == {}

    def test_compressed_is_smaller_than_json(self):
        raw = {"abstract": "a " * 5000, "authors": ["x"] * 100}
        json_size = len(json.dumps(raw).encode("utf-8"))
        compressed = SQLiteArticleCache._compress_raw(raw)

        assert compressed is not None
        assert len(compressed) < json_size

    def test_legacy_text_raw_is_migrated(self):
        """Simulate a pre-compression database with TEXT raw values."""
        conn = sqlite3.connect(":memory:")
        conn.executescript("""\
            CREATE TABLE articles (
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                abstract TEXT,
                authors TEXT,
                publication_date TEXT,
                doi TEXT,
                url TEXT,
                venue TEXT,
                citation_count INTEGER,
                categories TEXT,
                raw TEXT,
                cached_at TEXT NOT NULL,
                PRIMARY KEY (source, source_id)
            );
        """)
        raw_dict = {"legacy": True, "data": [1, 2, 3]}
        conn.execute(
            "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "test", "1", "Legacy Article", None,
                json.dumps([]), None, None, None, None, None,
                json.dumps([]), json.dumps(raw_dict),
                "2024-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
        conn.close()

        # Re-open through SQLiteArticleCache which triggers migration
        # Can't use :memory: here since we need to re-open the same DB,
        # so we test the migration logic directly instead.
        cache = SQLiteArticleCache.__new__(SQLiteArticleCache)
        cache._db_path = ":memory:"
        cache._conn = sqlite3.connect(":memory:")
        cache._conn.row_factory = sqlite3.Row

        # Create legacy schema with TEXT raw
        cache._conn.executescript("""\
            CREATE TABLE articles (
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                abstract TEXT,
                authors TEXT,
                publication_date TEXT,
                doi TEXT,
                url TEXT,
                venue TEXT,
                citation_count INTEGER,
                categories TEXT,
                raw TEXT,
                cached_at TEXT NOT NULL,
                PRIMARY KEY (source, source_id)
            );
        """)
        cache._conn.execute(
            "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "test", "1", "Legacy Article", None,
                json.dumps([]), None, None, None, None, None,
                json.dumps([]), json.dumps(raw_dict),
                "2024-01-01T00:00:00+00:00",
            ),
        )
        cache._conn.commit()

        cache._migrate()

        retrieved = cache.get("test", "1")
        assert retrieved is not None
        assert retrieved.raw == raw_dict

        cache.close()
