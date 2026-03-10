"""Semantic Scholar article source.

API docs: https://api.semanticscholar.org/api-docs/graph
Free tier: 100 requests / 5 minutes (higher with an API key).
"""

from __future__ import annotations

import logging
from datetime import date

from alpha_signal.models.articles import Article
from alpha_signal.sources.base import BaseSource

logger = logging.getLogger(__name__)

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
    rate_delay = 3.0

    def __init__(self, api_key: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if api_key:
            self._client.headers["x-api-key"] = api_key

    def search(
        self,
        *,
        query: str | None = None,
        max_results: int | None = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        page_size = 100
        all_articles: list[Article] = []
        offset = 0
        page = 0

        while True:
            want = page_size if max_results is None else min(max_results - len(all_articles), page_size)
            if want <= 0:
                break
            page += 1
            logger.info("semantic_scholar: page %d  offset=%d  limit=%d", page, offset, want)
            params: dict = {"limit": want, "offset": offset, "fields": _FIELDS}
            if query is not None:
                params["query"] = query
            else:
                params["query"] = "*"
            if date_from is not None and date_to is not None:
                params["year"] = f"{date_from.year}-{date_to.year}"
            elif date_from is not None:
                params["year"] = str(date_from.year)
            elif date_to is not None:
                params["year"] = str(date_to.year)

            resp = self._get("/paper/search", params=params)
            batch = resp.json().get("data", [])
            articles = [self._to_article(hit) for hit in batch]
            raw_count = len(batch)
            if date_from is not None or date_to is not None:
                articles = [
                    a
                    for a in articles
                    if a.publication_date is not None
                    and (date_from is None or a.publication_date >= date_from)
                    and (date_to is None or a.publication_date <= date_to)
                ]
            all_articles.extend(articles)
            logger.info("semantic_scholar: page %d returned %d raw, %d after date filter, %d total", page, raw_count, len(articles), len(all_articles))
            if len(batch) < want:
                break
            if max_results is not None and len(all_articles) >= max_results:
                break
            offset += len(batch)

        if max_results is not None:
            all_articles = all_articles[:max_results]
        logger.info("semantic_scholar: done — %d articles collected", len(all_articles))
        return all_articles

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
