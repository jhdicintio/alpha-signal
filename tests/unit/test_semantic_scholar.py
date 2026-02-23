"""Unit tests for SemanticScholarSource — parsing / normalisation only."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from alpha_signal.sources.semantic_scholar import SemanticScholarSource
from tests.conftest import make_response

SEARCH_RESPONSE = {
    "total": 1,
    "data": [
        {
            "paperId": "abc123",
            "title": "Advances in Solid-State Battery Technology",
            "abstract": "We present a novel approach to solid-state batteries.",
            "year": 2024,
            "authors": [
                {"authorId": "1", "name": "Jane Smith"},
                {"authorId": "2", "name": "John Doe"},
            ],
            "citationCount": 42,
            "externalIds": {"DOI": "10.1234/test.2024", "ArXiv": "2401.99999"},
            "publicationDate": "2024-06-15",
            "venue": "Nature Energy",
            "url": "https://www.semanticscholar.org/paper/abc123",
            "fieldsOfStudy": ["Materials Science", "Chemistry"],
        }
    ],
}


SINGLE_PAPER = SEARCH_RESPONSE["data"][0]


class TestSemanticScholarSearch:
    @patch.object(SemanticScholarSource, "_get")
    def test_search_returns_articles(self, mock_get):
        mock_get.return_value = make_response(json_data=SEARCH_RESPONSE)

        with SemanticScholarSource() as src:
            results = src.search("solid state batteries")

        assert len(results) == 1
        art = results[0]
        assert art.source == "semantic_scholar"
        assert art.source_id == "abc123"
        assert art.title == "Advances in Solid-State Battery Technology"
        assert art.abstract == "We present a novel approach to solid-state batteries."
        assert art.authors == ["Jane Smith", "John Doe"]
        assert art.publication_date == date(2024, 6, 15)
        assert art.doi == "10.1234/test.2024"
        assert art.venue == "Nature Energy"
        assert art.citation_count == 42
        assert "Materials Science" in art.categories

    @patch.object(SemanticScholarSource, "_get")
    def test_search_empty_response(self, mock_get):
        mock_get.return_value = make_response(json_data={"total": 0, "data": []})

        with SemanticScholarSource() as src:
            results = src.search("xyznonexistent")

        assert results == []

    @patch.object(SemanticScholarSource, "_get")
    def test_search_caps_max_results(self, mock_get):
        mock_get.return_value = make_response(json_data={"total": 0, "data": []})

        with SemanticScholarSource() as src:
            src.search("test", max_results=500)

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["limit"] == 100

    @patch.object(SemanticScholarSource, "_get")
    def test_search_adds_year_and_filters_by_date_range(self, mock_get):
        mock_get.return_value = make_response(json_data=SEARCH_RESPONSE)

        with SemanticScholarSource() as src:
            results = src.search(
                "battery",
                date_from=date(2024, 1, 1),
                date_to=date(2024, 12, 31),
            )

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["year"] == "2024-2024"
        assert len(results) == 1
        assert results[0].publication_date == date(2024, 6, 15)

    @patch.object(SemanticScholarSource, "_get")
    def test_search_filters_out_article_outside_date_range(self, mock_get):
        mock_get.return_value = make_response(json_data=SEARCH_RESPONSE)

        with SemanticScholarSource() as src:
            results = src.search(
                "battery",
                date_from=date(2024, 7, 1),
                date_to=date(2024, 12, 31),
            )

        assert len(results) == 0


class TestSemanticScholarFetchById:
    @patch.object(SemanticScholarSource, "_get")
    def test_fetch_existing_paper(self, mock_get):
        mock_get.return_value = make_response(json_data=SINGLE_PAPER)

        with SemanticScholarSource() as src:
            art = src.fetch_by_id("abc123")

        assert art is not None
        assert art.source_id == "abc123"

    @patch.object(SemanticScholarSource, "_get")
    def test_fetch_missing_paper(self, mock_get):
        mock_get.return_value = make_response(json_data={})

        with SemanticScholarSource() as src:
            art = src.fetch_by_id("nonexistent")

        assert art is None


class TestSemanticScholarEdgeCases:
    @patch.object(SemanticScholarSource, "_get")
    def test_missing_optional_fields(self, mock_get):
        sparse = {
            "paperId": "sparse1",
            "title": "Sparse Paper",
        }
        mock_get.return_value = make_response(json_data={"total": 1, "data": [sparse]})

        with SemanticScholarSource() as src:
            results = src.search("sparse")

        art = results[0]
        assert art.abstract is None
        assert art.authors == []
        assert art.publication_date is None
        assert art.doi is None
        assert art.venue is None
        assert art.citation_count is None
        assert art.categories == []

    @patch.object(SemanticScholarSource, "_get")
    def test_malformed_date_is_handled(self, mock_get):
        bad_date = {**SINGLE_PAPER, "publicationDate": "not-a-date"}
        mock_get.return_value = make_response(json_data={"total": 1, "data": [bad_date]})

        with SemanticScholarSource() as src:
            results = src.search("test")

        assert results[0].publication_date is None
