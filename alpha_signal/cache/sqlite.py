"""SQLite-backed article cache.

Uses the stdlib :mod:`sqlite3` module — no extra dependencies, file-based,
and suitable for local development and moderate-scale pipelines.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from alpha_signal.cache.base import BaseArticleCache
from alpha_signal.models.articles import Article

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS articles (
    source          TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    abstract        TEXT,
    authors         TEXT,
    publication_date TEXT,
    doi             TEXT,
    url             TEXT,
    venue           TEXT,
    citation_count  INTEGER,
    categories      TEXT,
    raw             TEXT,
    cached_at       TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_articles_doi ON articles(doi);
"""


class SQLiteArticleCache(BaseArticleCache):
    """Persist articles in a local SQLite database.

    Parameters
    ----------
    db_path:
        Path to the SQLite file.  Use ``":memory:"`` for an in-memory store
        (useful in tests).
    """

    def __init__(self, db_path: str | Path = "articles.db") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def put(self, article: Article) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO articles
                (source, source_id, title, abstract, authors, publication_date,
                 doi, url, venue, citation_count, categories, raw, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._to_row(article),
        )
        self._conn.commit()

    def put_many(self, articles: list[Article]) -> None:
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO articles
                (source, source_id, title, abstract, authors, publication_date,
                 doi, url, venue, citation_count, categories, raw, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [self._to_row(a) for a in articles],
        )
        self._conn.commit()

    def get(self, source: str, source_id: str) -> Article | None:
        row = self._conn.execute(
            "SELECT * FROM articles WHERE source = ? AND source_id = ?",
            (source, source_id),
        ).fetchone()
        return self._from_row(row) if row else None

    def contains(self, source: str, source_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM articles WHERE source = ? AND source_id = ?",
            (source, source_id),
        ).fetchone()
        return row is not None

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM articles").fetchone()
        return row[0]

    def all(self) -> list[Article]:
        rows = self._conn.execute("SELECT * FROM articles ORDER BY cached_at DESC").fetchall()
        return [self._from_row(r) for r in rows]

    def clear(self) -> None:
        self._conn.execute("DELETE FROM articles")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SQLiteArticleCache:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- serialisation -------------------------------------------------------

    @staticmethod
    def _to_row(article: Article) -> tuple:
        return (
            article.source,
            article.source_id,
            article.title,
            article.abstract,
            json.dumps(article.authors),
            article.publication_date.isoformat() if article.publication_date else None,
            article.doi,
            article.url,
            article.venue,
            article.citation_count,
            json.dumps(article.categories),
            json.dumps(article.raw),
            datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Article:
        pub_date: date | None = None
        if row["publication_date"]:
            try:
                pub_date = date.fromisoformat(row["publication_date"])
            except ValueError:
                pass

        return Article(
            source=row["source"],
            source_id=row["source_id"],
            title=row["title"],
            abstract=row["abstract"],
            authors=json.loads(row["authors"]) if row["authors"] else [],
            publication_date=pub_date,
            doi=row["doi"],
            url=row["url"],
            venue=row["venue"],
            citation_count=row["citation_count"],
            categories=json.loads(row["categories"]) if row["categories"] else [],
            raw=json.loads(row["raw"]) if row["raw"] else {},
        )
