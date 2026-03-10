"""Europe PMC article source — provides free access to PubMed / life-sciences
literature with a simpler JSON API than NCBI E-utilities.

API docs: https://europepmc.org/RestfulWebService
"""

from __future__ import annotations

import logging
from datetime import date

from alpha_signal.models.articles import Article
from alpha_signal.sources.base import BaseSource

logger = logging.getLogger(__name__)


class EuropePMCSource(BaseSource):
    """Fetch biomedical articles from the Europe PMC REST API."""

    name = "europe_pmc"
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    rate_delay = 0.2

    def search(
        self,
        *,
        query: str | None = None,
        max_results: int | None = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        from_str = date_from.isoformat() if date_from else "1900-01-01"
        to_str = date_to.isoformat() if date_to else "2099-12-31"
        if query is not None:
            q = f"({query}) AND FIRST_PDATE:{from_str}:{to_str}" if (date_from or date_to) else query
        else:
            q = f"FIRST_PDATE:{from_str}:{to_str}"

        page_size = 100
        all_articles: list[Article] = []
        cursor_mark: str = "*"
        page = 0

        while True:
            want = page_size if max_results is None else min(max_results - len(all_articles), page_size)
            if want <= 0:
                break
            page += 1
            logger.info("europe_pmc: page %d  pageSize=%d", page, want)
            resp = self._get(
                "/search",
                params={
                    "query": q,
                    "format": "json",
                    "pageSize": want,
                    "resultType": "core",
                    "cursorMark": cursor_mark,
                },
            )
            data = resp.json()
            result_list = data.get("resultList", {}).get("result", [])
            batch = [self._to_article(r) for r in result_list]
            raw_count = len(batch)
            if date_from is not None or date_to is not None:
                batch = [
                    a
                    for a in batch
                    if a.publication_date is not None
                    and (date_from is None or a.publication_date >= date_from)
                    and (date_to is None or a.publication_date <= date_to)
                ]
            all_articles.extend(batch)
            logger.info("europe_pmc: page %d returned %d raw, %d after date filter, %d total", page, raw_count, len(batch), len(all_articles))
            next_mark = data.get("nextCursorMark")
            if not next_mark or next_mark == cursor_mark or not result_list:
                break
            if max_results is not None and len(all_articles) >= max_results:
                break
            cursor_mark = next_mark

        if max_results is not None:
            all_articles = all_articles[:max_results]
        logger.info("europe_pmc: done — %d articles collected", len(all_articles))
        return all_articles

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
