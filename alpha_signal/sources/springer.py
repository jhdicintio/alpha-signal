"""Springer Nature article source.

API docs: https://dev.springernature.com/docs
Requires a free API key — register at https://dev.springernature.com.
"""

from __future__ import annotations

from datetime import date

from alpha_signal.models.articles import Article
from alpha_signal.sources.base import BaseSource


class SpringerSource(BaseSource):
    """Fetch articles from the Springer Nature Metadata API."""

    name = "springer"
    base_url = "https://api.springernature.com/meta/v2"

    def __init__(self, api_key: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._api_key = api_key

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        params: dict = {"q": query, "p": min(max_results, 50), "api_key": self._api_key}
        if date_from is not None:
            params["datefrom"] = date_from.isoformat()
        if date_to is not None:
            params["dateto"] = date_to.isoformat()

        resp = self._get("/json", params=params)
        articles = [self._to_article(rec) for rec in resp.json().get("records", [])]
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
        resp = self._get(
            "/json",
            params={"q": f"doi:{identifier}", "p": 1, "api_key": self._api_key},
        )
        records = resp.json().get("records", [])
        return self._to_article(records[0]) if records else None

    @staticmethod
    def _to_article(raw: dict) -> Article:
        pub_date: date | None = None
        for date_field in ("onlineDate", "printDate", "publicationDate"):
            if raw.get(date_field):
                try:
                    pub_date = date.fromisoformat(raw[date_field])
                    break
                except ValueError:
                    continue

        creators = raw.get("creators", [])
        authors = [c.get("creator", "") for c in creators if c.get("creator")]

        subjects = [s.get("term", "") for s in raw.get("subjects", []) if s.get("term")]

        doi = raw.get("doi", "")
        url = raw.get("url", [{}])
        primary_url = url[0].get("value") if isinstance(url, list) and url else None

        return Article(
            source="springer",
            source_id=doi,
            title=raw.get("title", ""),
            abstract=raw.get("abstract"),
            authors=authors,
            publication_date=pub_date,
            doi=doi or None,
            url=primary_url or (f"https://doi.org/{doi}" if doi else None),
            venue=raw.get("publicationName"),
            citation_count=None,
            categories=subjects,
            raw=raw,
        )
