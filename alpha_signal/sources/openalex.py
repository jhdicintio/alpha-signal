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
    rate_delay = 0.1

    def __init__(self, mailto: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._mailto = mailto

    def search(
        self,
        *,
        query: str | None = None,
        max_results: int | None = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        page_size = 200
        base_params: dict = {"per_page": page_size}
        if query is not None:
            base_params["search"] = query
        if self._mailto:
            base_params["mailto"] = self._mailto
        if date_from is not None or date_to is not None:
            parts = []
            if date_from is not None:
                parts.append(f"from_publication_date:{date_from.isoformat()}")
            if date_to is not None:
                parts.append(f"to_publication_date:{date_to.isoformat()}")
            base_params["filter"] = ",".join(parts)
        if "search" not in base_params and base_params.get("filter"):
            base_params["search"] = "*"
        elif "search" not in base_params:
            base_params["search"] = "*"

        all_articles: list[Article] = []
        cursor: str | None = "*"

        while True:
            want = (page_size if max_results is None else min(max_results - len(all_articles), page_size))
            if want <= 0:
                break
            request_params = {**base_params, "per_page": want, "cursor": cursor}
            resp = self._get("/works", params=request_params)
            data = resp.json()
            results = data.get("results", [])
            batch = [self._to_article(w) for w in results]
            all_articles.extend(batch)
            next_cursor = data.get("meta", {}).get("next_cursor")
            if not next_cursor or not results:
                break
            if max_results is not None and len(all_articles) >= max_results:
                break
            cursor = next_cursor

        if max_results is not None:
            all_articles = all_articles[:max_results]
        return all_articles

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
