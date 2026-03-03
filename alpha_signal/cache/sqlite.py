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
from typing import TYPE_CHECKING

from alpha_signal.cache.base import BaseArticleCache
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction

if TYPE_CHECKING:
    import pandas as pd

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

CREATE TABLE IF NOT EXISTS extractions (
    source           TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    extraction_model TEXT NOT NULL,
    extraction_data  BLOB NOT NULL,
    extracted_at     TEXT NOT NULL,
    PRIMARY KEY (source, source_id, extraction_model),
    FOREIGN KEY (source, source_id) REFERENCES articles(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_extractions_model ON extractions(extraction_model);
CREATE INDEX IF NOT EXISTS idx_extractions_extracted_at ON extractions(extracted_at);
"""


def _is_nan(value: object) -> bool:
    """Return True if *value* is a float NaN (from pandas NULL columns)."""
    try:
        return value != value  # noqa: PLR0124  — NaN != NaN
    except (TypeError, ValueError):
        return False


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

    def to_dataframe(self) -> pd.DataFrame:
        """Return every cached article as a pandas DataFrame.

        JSON-encoded columns (``authors``, ``categories``) are decoded to
        Python lists and the compressed ``raw`` BLOB is decompressed to a dict
        so the DataFrame is immediately usable without extra post-processing.
        """
        import pandas as pd

        df = pd.read_sql("SELECT * FROM articles ORDER BY cached_at DESC", self._conn)
        df["authors"] = df["authors"].apply(lambda v: json.loads(v) if v else [])
        df["categories"] = df["categories"].apply(lambda v: json.loads(v) if v else [])
        df["raw"] = df["raw"].apply(self._decompress_raw)
        return df

    @staticmethod
    def dataframe_to_articles(df: pd.DataFrame) -> list[Article]:
        """Convert a DataFrame (or any slice of one) back to Article objects.

        Handles both *decoded* DataFrames (from :meth:`to_dataframe`, where
        ``authors``/``categories`` are already lists and ``raw`` is a dict) and
        *raw* DataFrames loaded directly via ``pd.read_sql`` (where those
        columns are still JSON strings / compressed bytes).
        """
        articles: list[Article] = []
        for _, row in df.iterrows():
            pub_date: date | None = None
            if row.get("publication_date"):
                try:
                    pub_date = date.fromisoformat(str(row["publication_date"]))
                except ValueError:
                    pass

            authors = row.get("authors", [])
            if isinstance(authors, str):
                authors = json.loads(authors)

            categories = row.get("categories", [])
            if isinstance(categories, str):
                categories = json.loads(categories)

            raw = row.get("raw", {})
            if isinstance(raw, (bytes, str)):
                raw = SQLiteArticleCache._decompress_raw(raw)
            if raw is None:
                raw = {}

            citation_count = row.get("citation_count")
            if citation_count is not None:
                import pandas as pd

                if pd.isna(citation_count):
                    citation_count = None
                else:
                    citation_count = int(citation_count)

            articles.append(
                Article(
                    source=row["source"],
                    source_id=row["source_id"],
                    title=row["title"],
                    abstract=row.get("abstract"),
                    authors=authors or [],
                    publication_date=pub_date,
                    doi=row.get("doi") if row.get("doi") and not _is_nan(row.get("doi")) else None,
                    url=row.get("url") if row.get("url") and not _is_nan(row.get("url")) else None,
                    venue=row.get("venue") if row.get("venue") and not _is_nan(row.get("venue")) else None,
                    citation_count=citation_count,
                    categories=categories or [],
                    raw=raw,
                )
            )
        return articles

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

    # -- extraction persistence ------------------------------------------------

    def put_extraction(
        self,
        source: str,
        source_id: str,
        extraction: ArticleExtraction,
    ) -> None:
        """Store (or overwrite) an extraction for the given article + model."""
        model = extraction.extraction_model or "unknown"
        data = self._compress_raw(extraction.model_dump(mode="json"))
        extracted_at = (
            extraction.extraction_timestamp.isoformat()
            if extraction.extraction_timestamp
            else datetime.now(timezone.utc).isoformat()
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO extractions
                (source, source_id, extraction_model, extraction_data, extracted_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source, source_id, model, data, extracted_at),
        )
        self._conn.commit()

    def put_extractions(
        self,
        items: list[tuple[str, str, ArticleExtraction]],
    ) -> None:
        """Batch-store extractions. Each item is ``(source, source_id, extraction)``."""
        rows = []
        for source, source_id, extraction in items:
            model = extraction.extraction_model or "unknown"
            data = self._compress_raw(extraction.model_dump(mode="json"))
            extracted_at = (
                extraction.extraction_timestamp.isoformat()
                if extraction.extraction_timestamp
                else datetime.now(timezone.utc).isoformat()
            )
            rows.append((source, source_id, model, data, extracted_at))
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO extractions
                (source, source_id, extraction_model, extraction_data, extracted_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()

    def get_extraction(
        self,
        source: str,
        source_id: str,
        model: str | None = None,
    ) -> ArticleExtraction | None:
        """Retrieve an extraction. If *model* is None, return the most recent."""
        if model:
            row = self._conn.execute(
                "SELECT extraction_data FROM extractions "
                "WHERE source = ? AND source_id = ? AND extraction_model = ?",
                (source, source_id, model),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT extraction_data FROM extractions "
                "WHERE source = ? AND source_id = ? ORDER BY extracted_at DESC LIMIT 1",
                (source, source_id),
            ).fetchone()
        if row is None:
            return None
        return ArticleExtraction(**self._decompress_raw(row["extraction_data"]))

    def has_extraction(
        self,
        source: str,
        source_id: str,
        model: str | None = None,
    ) -> bool:
        """Return True if an extraction exists for this article (optionally for a specific model)."""
        if model:
            row = self._conn.execute(
                "SELECT 1 FROM extractions "
                "WHERE source = ? AND source_id = ? AND extraction_model = ?",
                (source, source_id, model),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT 1 FROM extractions WHERE source = ? AND source_id = ?",
                (source, source_id),
            ).fetchone()
        return row is not None

    def extraction_count(self, model: str | None = None) -> int:
        """Return the total number of stored extractions, optionally filtered by model."""
        if model:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM extractions WHERE extraction_model = ?", (model,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM extractions").fetchone()
        return row[0]

    def all_extractions(
        self,
        model: str | None = None,
    ) -> list[tuple[str, str, ArticleExtraction]]:
        """Return all stored extractions as ``(source, source_id, extraction)`` triples."""
        if model:
            rows = self._conn.execute(
                "SELECT source, source_id, extraction_data FROM extractions "
                "WHERE extraction_model = ? ORDER BY extracted_at DESC",
                (model,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT source, source_id, extraction_data FROM extractions "
                "ORDER BY extracted_at DESC"
            ).fetchall()
        return [
            (r["source"], r["source_id"], ArticleExtraction(**self._decompress_raw(r["extraction_data"])))
            for r in rows
        ]

    def extractions_to_dataframe(self, model: str | None = None) -> pd.DataFrame:
        """Return extractions as a DataFrame with decoded fields.

        Each row contains the article key columns plus flattened extraction
        fields.  Nested lists (technologies, claims) remain as Python objects.
        """
        import pandas as pd

        if model:
            query = (
                "SELECT e.source, e.source_id, e.extraction_model, e.extraction_data, "
                "e.extracted_at, a.title, a.publication_date "
                "FROM extractions e LEFT JOIN articles a "
                "ON e.source = a.source AND e.source_id = a.source_id "
                "WHERE e.extraction_model = ? ORDER BY e.extracted_at DESC"
            )
            rows = self._conn.execute(query, (model,)).fetchall()
        else:
            query = (
                "SELECT e.source, e.source_id, e.extraction_model, e.extraction_data, "
                "e.extracted_at, a.title, a.publication_date "
                "FROM extractions e LEFT JOIN articles a "
                "ON e.source = a.source AND e.source_id = a.source_id "
                "ORDER BY e.extracted_at DESC"
            )
            rows = self._conn.execute(query).fetchall()

        records = []
        for r in rows:
            ext_data = self._decompress_raw(r["extraction_data"])
            records.append({
                "source": r["source"],
                "source_id": r["source_id"],
                "title": r["title"],
                "publication_date": r["publication_date"],
                "extraction_model": r["extraction_model"],
                "extracted_at": r["extracted_at"],
                **ext_data,
            })
        return pd.DataFrame(records)

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
