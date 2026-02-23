"""Semantic Scholar article source.

API docs: https://api.semanticscholar.org/api-docs/graph
Free tier: 100 requests / 5 minutes (higher with an API key).
"""

from __future__ import annotations

from datetime import date

from alpha_signal.models.articles import Article
from alpha_signal.sources.base import BaseSource

_FIELDS = ",".join([
    "paperId",
    "title",
    "abstract",
    "year",
    "authors",
    "citationCount",
    "externalIds",
    "publicationDate",
    "venue",
    "url",
    "fieldsOfStudy",
])


class SemanticScholarSource(BaseSource):
    """Fetch articles from the Semantic Scholar Academic Graph API."""

    name = "semantic_scholar"
    base_url = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if api_key:
            self._client.headers["x-api-key"] = api_key

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        params: dict = {"query": query, "limit": min(max_results, 100), "fields": _FIELDS}
        if date_from is not None and date_to is not None:
            params["year"] = f"{date_from.year}-{date_to.year}"
        elif date_from is not None:
            params["year"] = str(date_from.year)
        elif date_to is not None:
            params["year"] = str(date_to.year)

        resp = self._get("/paper/search", params=params)
        articles = [self._to_article(hit) for hit in resp.json().get("data", [])]
        if date_from is not None or date_to is not None:
            articles = [
                a
                for a in articles
                if a.publication_date is not None
                and (date_from is None or a.publication_date >= date_from)
                and (date_to is None or a.publication_date <= date_to)
            ]
        return articles

    def fetch_by_id(self, identifier: str) -> Article | None:
        resp = self._get(f"/paper/{identifier}", params={"fields": _FIELDS})
        data = resp.json()
        if not data.get("paperId"):
            return None
        return self._to_article(data)

    @staticmethod
    def _to_article(raw: dict) -> Article:
        pub_date: date | None = None
        if raw.get("publicationDate"):
            try:
                pub_date = date.fromisoformat(raw["publicationDate"])
            except ValueError:
                pass

        external = raw.get("externalIds") or {}
        return Article(
            source="semantic_scholar",
            source_id=raw["paperId"],
            title=raw.get("title", ""),
            abstract=raw.get("abstract"),
            authors=[a.get("name", "") for a in raw.get("authors", [])],
            publication_date=pub_date,
            doi=external.get("DOI"),
            url=raw.get("url"),
            venue=raw.get("venue") or None,
            citation_count=raw.get("citationCount"),
            categories=raw.get("fieldsOfStudy") or [],
            raw=raw,
        )
