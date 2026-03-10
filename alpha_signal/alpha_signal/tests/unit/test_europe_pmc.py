"""Unit tests for EuropePMCSource — parsing and normalisation."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from alpha_signal.sources.europe_pmc import EuropePMCSource
from tests.conftest import make_response

PMC_RESULT = {
    "id": "12345678",
    "pmid": "12345678",
    "source": "MED",
    "title": "CRISPR-Cas9 in Agricultural Biotechnology",
    "abstractText": "We review applications of CRISPR-Cas9 in crop improvement.",
    "authorList": {
        "author": [
            {"fullName": "Alice Chen"},
            {"fullName": "Bob Williams"},
        ]
    },
    "firstPublicationDate": "2024-04-10",
    "doi": "10.9999/crispr.2024",
    "journalTitle": "Nature Biotechnology",
    "citedByCount": 73,
    "meshHeadingList": {
        "meshHeading": [
            {"descriptorName": "CRISPR-Cas Systems"},
            {"descriptorName": "Gene Editing"},
        ]
    },
}

SEARCH_RESPONSE = {"resultList": {"result": [PMC_RESULT]}}


class TestEuropePMCSearch:
    @patch.object(EuropePMCSource, "_get")
    def test_search_returns_articles(self, mock_get):
        mock_get.return_value = make_response(json_data=SEARCH_RESPONSE)

        with EuropePMCSource() as src:
            results = src.search(query="CRISPR agriculture")

        assert len(results) == 1
        art = results[0]
        assert art.source == "europe_pmc"
        assert art.source_id == "12345678"
        assert art.title == "CRISPR-Cas9 in Agricultural Biotechnology"
        assert "CRISPR-Cas9" in art.abstract
        assert art.authors == ["Alice Chen", "Bob Williams"]
        assert art.publication_date == date(2024, 4, 10)
        assert art.doi == "10.9999/crispr.2024"
        assert art.venue == "Nature Biotechnology"
        assert art.citation_count == 73
        assert "CRISPR-Cas Systems" in art.categories
        assert "Gene Editing" in art.categories

    @patch.object(EuropePMCSource, "_get")
    def test_search_empty(self, mock_get):
        mock_get.return_value = make_response(json_data={"resultList": {"result": []}})

        with EuropePMCSource() as src:
            results = src.search(query="xyznonexistent")

        assert results == []

    @patch.object(EuropePMCSource, "_get")
    def test_search_caps_max_results(self, mock_get):
        mock_get.return_value = make_response(json_data={"resultList": {"result": []}})

        with EuropePMCSource() as src:
            src.search(query="test", max_results=500)

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["pageSize"] == 100

    @patch.object(EuropePMCSource, "_get")
    def test_search_adds_first_pdate_filter_when_date_range_given(self, mock_get):
        mock_get.return_value = make_response(json_data={"resultList": {"result": []}})

        with EuropePMCSource() as src:
            src.search(
                query="CRISPR",
                date_from=date(2024, 2, 1),
                date_to=date(2024, 2, 29),
            )

        _, kwargs = mock_get.call_args
        assert "FIRST_PDATE:2024-02-01:2024-02-29" in kwargs["params"]["query"]
        assert kwargs["params"]["query"].startswith("(CRISPR) AND ")


class TestEuropePMCFetchById:
    @patch.object(EuropePMCSource, "_get")
    def test_fetch_existing(self, mock_get):
        mock_get.return_value = make_response(json_data=SEARCH_RESPONSE)

        with EuropePMCSource() as src:
            art = src.fetch_by_id("12345678")

        assert art is not None
        assert art.source_id == "12345678"

    @patch.object(EuropePMCSource, "_get")
    def test_fetch_missing(self, mock_get):
        mock_get.return_value = make_response(json_data={"resultList": {"result": []}})

        with EuropePMCSource() as src:
            art = src.fetch_by_id("nonexistent")

        assert art is None


class TestEuropePMCEdgeCases:
    @patch.object(EuropePMCSource, "_get")
    def test_falls_back_to_electronic_publication_date(self, mock_get):
        result = {**PMC_RESULT}
        del result["firstPublicationDate"]
        result["electronicPublicationDate"] = "2024-05-01"
        mock_get.return_value = make_response(
            json_data={"resultList": {"result": [result]}}
        )

        with EuropePMCSource() as src:
            results = src.search(query="test")

        assert results[0].publication_date == date(2024, 5, 1)

    @patch.object(EuropePMCSource, "_get")
    def test_no_dates_gives_none(self, mock_get):
        result = {**PMC_RESULT}
        del result["firstPublicationDate"]
        mock_get.return_value = make_response(
            json_data={"resultList": {"result": [result]}}
        )

        with EuropePMCSource() as src:
            results = src.search(query="test")

        assert results[0].publication_date is None

    @patch.object(EuropePMCSource, "_get")
    def test_no_mesh_headings(self, mock_get):
        result = {**PMC_RESULT}
        del result["meshHeadingList"]
        mock_get.return_value = make_response(
            json_data={"resultList": {"result": [result]}}
        )

        with EuropePMCSource() as src:
            results = src.search(query="test")

        assert results[0].categories == []

    @patch.object(EuropePMCSource, "_get")
    def test_url_construction(self, mock_get):
        mock_get.return_value = make_response(json_data=SEARCH_RESPONSE)

        with EuropePMCSource() as src:
            results = src.search(query="test")

        assert results[0].url == "https://europepmc.org/article/MED/12345678"
