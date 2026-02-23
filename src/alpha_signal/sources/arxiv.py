"""arXiv article source.

API docs: https://info.arxiv.org/help/api/basics.html
Free, no authentication required.  Returns Atom XML.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

import httpx

from alpha_signal.models.articles import Article
from alpha_signal.sources.base import BaseSource, _DEFAULT_TIMEOUT

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ArxivSource(BaseSource):
    """Fetch pre-prints from the arXiv API."""

    name = "arxiv"
    base_url = "https://export.arxiv.org"

    def __init__(self, **kwargs) -> None:
        timeout = kwargs.pop("timeout", _DEFAULT_TIMEOUT)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/xml"},
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        search_query = f"all:{query}"
        if date_from is not None or date_to is not None:
            from_str = date_from.strftime("%Y%m%d") if date_from else "*"
            to_str = date_to.strftime("%Y%m%d") if date_to else "*"
            search_query += f" AND submittedDate:[{from_str} TO {to_str}]"
        resp = self._get(
            "/api/query",
            params={
                "search_query": search_query,
                "start": 0,
                "max_results": min(max_results, 100),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
        )
        articles = self._parse_feed(resp.text)
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
        resp = self._get("/api/query", params={"id_list": identifier})
        articles = self._parse_feed(resp.text)
        return articles[0] if articles else None

    @classmethod
    def _parse_feed(cls, xml_text: str) -> list[Article]:
        root = ET.fromstring(xml_text)
        articles: list[Article] = []
        for entry in root.findall(f"{_ATOM_NS}entry"):
            article = cls._entry_to_article(entry)
            if article:
                articles.append(article)
        return articles

    @classmethod
    def _entry_to_article(cls, entry: ET.Element) -> Article | None:
        raw_id = (entry.findtext(f"{_ATOM_NS}id") or "").strip()
        if not raw_id:
            return None

        arxiv_id = raw_id.split("/abs/")[-1]

        title = " ".join((entry.findtext(f"{_ATOM_NS}title") or "").split())
        abstract = " ".join((entry.findtext(f"{_ATOM_NS}summary") or "").split()) or None

        authors = [
            name.text.strip()
            for author in entry.findall(f"{_ATOM_NS}author")
            if (name := author.find(f"{_ATOM_NS}name")) is not None and name.text
        ]

        pub_date: date | None = None
        published = entry.findtext(f"{_ATOM_NS}published")
        if published:
            try:
                pub_date = date.fromisoformat(published[:10])
            except ValueError:
                pass

        doi_el = entry.find(f"{_ARXIV_NS}doi")
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

        categories = [
            cat.get("term", "")
            for cat in entry.findall(f"{_ATOM_NS}category")
            if cat.get("term")
        ]

        pdf_url = None
        for link in entry.findall(f"{_ATOM_NS}link"):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
                break

        raw = {
            "id": raw_id,
            "title": title,
            "summary": abstract,
            "authors": authors,
            "published": published,
            "doi": doi,
            "categories": categories,
        }

        return Article(
            source="arxiv",
            source_id=arxiv_id,
            title=title,
            abstract=abstract,
            authors=authors,
            publication_date=pub_date,
            doi=doi,
            url=pdf_url or raw_id,
            venue="arXiv",
            citation_count=None,
            categories=categories,
            raw=raw,
        )
