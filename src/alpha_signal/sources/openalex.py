"""OpenAlex article source.

API docs: https://docs.openalex.org
Free and open — no API key required.  Setting ``mailto`` enables the polite
pool (faster, more reliable).
"""

from __future__ import annotations

from datetime import date

from alpha_signal.models.articles import Article
from alpha_signal.sources.base import BaseSource


class OpenAlexSource(BaseSource):
    """Fetch articles from the OpenAlex REST API."""

    name = "openalex"
    base_url = "https://api.openalex.org"

    def __init__(self, mailto: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._mailto = mailto

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        params: dict = {"search": query, "per_page": min(max_results, 200)}
        if self._mailto:
            params["mailto"] = self._mailto
        if date_from is not None or date_to is not None:
            parts = []
            if date_from is not None:
                parts.append(f"from_publication_date:{date_from.isoformat()}")
            if date_to is not None:
                parts.append(f"to_publication_date:{date_to.isoformat()}")
            params["filter"] = ",".join(parts)

        resp = self._get("/works", params=params)
        return [self._to_article(w) for w in resp.json().get("results", [])]

    def fetch_by_id(self, identifier: str) -> Article | None:
        params: dict = {}
        if self._mailto:
            params["mailto"] = self._mailto

        resp = self._get(f"/works/{identifier}", params=params)
        data = resp.json()
        if not data.get("id"):
            return None
        return self._to_article(data)

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict) -> str:
        """OpenAlex stores abstracts as ``{word: [positions]}``.  Reconstruct
        the original text by placing each word at its position(s)."""
        if not inverted_index:
            return ""
        words: dict[int, str] = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(words[i] for i in sorted(words))

    @classmethod
    def _to_article(cls, raw: dict) -> Article:
        pub_date: date | None = None
        if raw.get("publication_date"):
            try:
                pub_date = date.fromisoformat(raw["publication_date"])
            except ValueError:
                pass

        abstract = cls._reconstruct_abstract(raw.get("abstract_inverted_index") or {}) or None

        authors = []
        for authorship in raw.get("authorships", []):
            name = authorship.get("author", {}).get("display_name")
            if name:
                authors.append(name)

        doi_url: str | None = raw.get("doi")
        doi = doi_url.replace("https://doi.org/", "") if doi_url else None

        venue = None
        primary_location = raw.get("primary_location") or {}
        source = primary_location.get("source") or {}
        if source.get("display_name"):
            venue = source["display_name"]

        categories = [
            c.get("display_name", "")
            for c in raw.get("concepts", [])
            if c.get("level", 99) <= 1
        ]

        return Article(
            source="openalex",
            source_id=raw["id"],
            title=raw.get("title", ""),
            abstract=abstract,
            authors=authors,
            publication_date=pub_date,
            doi=doi,
            url=doi_url or raw.get("id"),
            venue=venue,
            citation_count=raw.get("cited_by_count"),
            categories=categories,
            raw=raw,
        )
