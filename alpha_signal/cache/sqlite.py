"""SQLite-backed article cache.

Uses the stdlib :mod:`sqlite3` module — no extra dependencies, file-based,
and suitable for local development and moderate-scale pipelines.

The ``raw`` column is stored as zlib-compressed JSON (BLOB) to reduce disk
usage by 5-10x.  Compression and decompression are handled transparently in
:meth:`_to_row` and :meth:`_from_row`; callers always see a plain ``dict``.
"""

from __future__ import annotations

import json
import sqlite3
import zlib
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
    raw             BLOB,
    cached_at       TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_articles_doi ON articles(doi);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_pub_date ON articles(publication_date);
CREATE INDEX IF NOT EXISTS idx_articles_source_pub_date ON articles(source, publication_date);
CREATE INDEX IF NOT EXISTS idx_articles_cached_at ON articles(cached_at);
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
        if self._db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate()

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

    def latest_date(self, source: str) -> date | None:
        row = self._conn.execute(
            "SELECT MAX(publication_date) AS max_date FROM articles WHERE source = ?",
            (source,),
        ).fetchone()
        val = row["max_date"] if row else None
        if val is None:
            return None
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None

    def source_ids(self, source: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT source_id FROM articles WHERE source = ?", (source,)
        ).fetchall()
        return {r["source_id"] for r in rows}

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SQLiteArticleCache:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- migration -----------------------------------------------------------

    def _migrate(self) -> None:
        """Migrate legacy TEXT raw columns to compressed BLOB in-place."""
        col_info = self._conn.execute("PRAGMA table_info(articles)").fetchall()
        raw_col = next((c for c in col_info if c["name"] == "raw"), None)
        if raw_col is None or raw_col["type"].upper() == "BLOB":
            return

        rows = self._conn.execute(
            "SELECT source, source_id, raw FROM articles WHERE raw IS NOT NULL"
        ).fetchall()
        if not rows:
            return

        for row in rows:
            raw_value = row["raw"]
            if isinstance(raw_value, str):
                compressed = zlib.compress(raw_value.encode("utf-8"))
                self._conn.execute(
                    "UPDATE articles SET raw = ? WHERE source = ? AND source_id = ?",
                    (compressed, row["source"], row["source_id"]),
                )
        self._conn.commit()

    # -- serialisation -------------------------------------------------------

    @staticmethod
    def _compress_raw(raw: dict) -> bytes | None:
        """JSON-encode and zlib-compress a raw dict for storage."""
        if not raw:
            return None
        return zlib.compress(json.dumps(raw, separators=(",", ":")).encode("utf-8"))

    @staticmethod
    def _decompress_raw(data: bytes | str | None) -> dict:
        """Decompress a stored raw value back to a dict.

        Handles both compressed BLOB (new) and plain TEXT JSON (legacy).
        """
        if data is None:
            return {}
        if isinstance(data, str):
            return json.loads(data)
        return json.loads(zlib.decompress(data).decode("utf-8"))

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
            SQLiteArticleCache._compress_raw(article.raw),
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
            raw=SQLiteArticleCache._decompress_raw(row["raw"]),
        )
