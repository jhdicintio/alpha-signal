"""Serialize Alpha Signal models to API JSON."""

from __future__ import annotations

from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction


def article_to_dict(article: Article, include_raw: bool = False) -> dict:
    """Serialize Article to JSON-suitable dict."""
    d = {
        "source": article.source,
        "source_id": article.source_id,
        "title": article.title,
        "abstract": article.abstract,
        "authors": article.authors,
        "publication_date": article.publication_date.isoformat() if article.publication_date else None,
        "doi": article.doi,
        "url": article.url,
        "venue": article.venue,
        "citation_count": article.citation_count,
        "categories": article.categories,
    }
    if include_raw:
        d["raw"] = article.raw
    return d


def extraction_to_dict(extraction: ArticleExtraction) -> dict:
    """Serialize ArticleExtraction to JSON-suitable dict."""
    return extraction.model_dump(mode="json")


def extraction_with_article_to_dict(
    source: str,
    source_id: str,
    article: Article | None,
    extraction: ArticleExtraction,
) -> dict:
    """Build the combined article + extraction payload used by the API."""
    return {
        "article": article_to_dict(article, include_raw=False) if article else {
            "source": source,
            "source_id": source_id,
            "title": None,
            "abstract": None,
            "authors": [],
            "publication_date": None,
            "doi": None,
            "url": None,
            "venue": None,
            "citation_count": None,
            "categories": [],
        },
        "extraction": extraction_to_dict(extraction),
    }
