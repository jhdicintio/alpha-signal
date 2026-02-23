"""Europe PMC article source — provides free access to PubMed / life-sciences
literature with a simpler JSON API than NCBI E-utilities.

API docs: https://europepmc.org/RestfulWebService
"""

from __future__ import annotations

from datetime import date

from alpha_signal.models.articles import Article
from alpha_signal.sources.base import BaseSource


class EuropePMCSource(BaseSource):
    """Fetch biomedical articles from the Europe PMC REST API."""

    name = "europe_pmc"
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        q = query
        if date_from is not None or date_to is not None:
            from_str = date_from.isoformat() if date_from else "1900-01-01"
            to_str = date_to.isoformat() if date_to else "2099-12-31"
            q = f"({query}) AND FIRST_PDATE:{from_str}:{to_str}"
        resp = self._get(
            "/search",
            params={
                "query": q,
                "format": "json",
                "pageSize": min(max_results, 100),
                "resultType": "core",
            },
        )
        articles = [
            self._to_article(r)
            for r in resp.json().get("resultList", {}).get("result", [])
        ]
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
            "/search",
            params={
                "query": f'EXT_ID:"{identifier}"',
                "format": "json",
                "pageSize": 1,
                "resultType": "core",
            },
        )
        results = resp.json().get("resultList", {}).get("result", [])
        return self._to_article(results[0]) if results else None

    @staticmethod
    def _to_article(raw: dict) -> Article:
        pub_date: date | None = None
        for date_field in ("firstPublicationDate", "electronicPublicationDate"):
            if raw.get(date_field):
                try:
                    pub_date = date.fromisoformat(raw[date_field])
                    break
                except ValueError:
                    continue

        authors: list[str] = []
        for author in raw.get("authorList", {}).get("author", []):
            full = author.get("fullName")
            if full:
                authors.append(full)

        mesh = [
            term.get("descriptorName", "")
            for term in raw.get("meshHeadingList", {}).get("meshHeading", [])
            if term.get("descriptorName")
        ]

        return Article(
            source="europe_pmc",
            source_id=raw.get("id", raw.get("pmid", "")),
            title=raw.get("title", ""),
            abstract=raw.get("abstractText"),
            authors=authors,
            publication_date=pub_date,
            doi=raw.get("doi"),
            url=f"https://europepmc.org/article/{raw.get('source', 'MED')}/{raw.get('id', '')}",
            venue=raw.get("journalTitle"),
            citation_count=raw.get("citedByCount"),
            categories=mesh,
            raw=raw,
        )
