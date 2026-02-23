"""Unit tests for OpenAlexSource — parsing, abstract reconstruction, normalisation."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from alpha_signal.sources.openalex import OpenAlexSource
from tests.conftest import make_response

WORK = {
    "id": "https://openalex.org/W12345",
    "title": "Perovskite Solar Cell Efficiency Gains",
    "abstract_inverted_index": {
        "We": [0],
        "demonstrate": [1],
        "a": [2, 7],
        "new": [3],
        "perovskite": [4],
        "architecture": [5],
        "achieving": [6],
        "record": [8],
        "efficiency.": [9],
    },
    "publication_date": "2024-03-20",
    "authorships": [
        {"author": {"id": "A1", "display_name": "Alice Chen"}},
        {"author": {"id": "A2", "display_name": "Bob Müller"}},
    ],
    "cited_by_count": 18,
    "doi": "https://doi.org/10.5678/perovskite.2024",
    "primary_location": {"source": {"display_name": "Advanced Materials"}},
    "concepts": [
        {"display_name": "Solar cell", "level": 1},
        {"display_name": "Perovskite", "level": 0},
        {"display_name": "Methylammonium lead halide", "level": 3},
    ],
}

SEARCH_RESPONSE = {"results": [WORK]}


class TestOpenAlexSearch:
    @patch.object(OpenAlexSource, "_get")
    def test_search_returns_articles(self, mock_get):
        mock_get.return_value = make_response(json_data=SEARCH_RESPONSE)

        with OpenAlexSource() as src:
            results = src.search("perovskite solar cells")

        assert len(results) == 1
        art = results[0]
        assert art.source == "openalex"
        assert art.source_id == "https://openalex.org/W12345"
        assert art.title == "Perovskite Solar Cell Efficiency Gains"
        assert art.authors == ["Alice Chen", "Bob Müller"]
        assert art.publication_date == date(2024, 3, 20)
        assert art.doi == "10.5678/perovskite.2024"
        assert art.venue == "Advanced Materials"
        assert art.citation_count == 18

    @patch.object(OpenAlexSource, "_get")
    def test_mailto_is_included_when_set(self, mock_get):
        mock_get.return_value = make_response(json_data={"results": []})

        with OpenAlexSource(mailto="test@example.com") as src:
            src.search("test")

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["mailto"] == "test@example.com"

    @patch.object(OpenAlexSource, "_get")
    def test_search_caps_max_results(self, mock_get):
        mock_get.return_value = make_response(json_data={"results": []})

        with OpenAlexSource() as src:
            src.search("test", max_results=999)

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["per_page"] == 200

    @patch.object(OpenAlexSource, "_get")
    def test_search_adds_publication_date_filter_when_given(self, mock_get):
        mock_get.return_value = make_response(json_data={"results": []})

        with OpenAlexSource() as src:
            src.search(
                "battery",
                date_from=date(2024, 1, 1),
                date_to=date(2024, 12, 31),
            )

        _, kwargs = mock_get.call_args
        assert "filter" in kwargs["params"]
        assert "from_publication_date:2024-01-01" in kwargs["params"]["filter"]
        assert "to_publication_date:2024-12-31" in kwargs["params"]["filter"]


class TestOpenAlexAbstractReconstruction:
    def test_reconstruct_basic(self):
        idx = {"Hello": [0], "world": [1]}
        assert OpenAlexSource._reconstruct_abstract(idx) == "Hello world"

    def test_reconstruct_with_repeated_words(self):
        idx = {"the": [0, 2], "cat": [1], "sat": [3]}
        assert OpenAlexSource._reconstruct_abstract(idx) == "the cat the sat"

    def test_reconstruct_empty(self):
        assert OpenAlexSource._reconstruct_abstract({}) == ""

    def test_reconstruct_from_fixture(self):
        result = OpenAlexSource._reconstruct_abstract(WORK["abstract_inverted_index"])
        assert result == (
            "We demonstrate a new perovskite architecture achieving a record efficiency."
        )


class TestOpenAlexFetchById:
    @patch.object(OpenAlexSource, "_get")
    def test_fetch_existing_work(self, mock_get):
        mock_get.return_value = make_response(json_data=WORK)

        with OpenAlexSource() as src:
            art = src.fetch_by_id("W12345")

        assert art is not None
        assert art.source_id == "https://openalex.org/W12345"

    @patch.object(OpenAlexSource, "_get")
    def test_fetch_missing_work(self, mock_get):
        mock_get.return_value = make_response(json_data={})

        with OpenAlexSource() as src:
            art = src.fetch_by_id("nonexistent")

        assert art is None


class TestOpenAlexEdgeCases:
    @patch.object(OpenAlexSource, "_get")
    def test_no_abstract_inverted_index(self, mock_get):
        work = {**WORK, "abstract_inverted_index": None}
        mock_get.return_value = make_response(json_data={"results": [work]})

        with OpenAlexSource() as src:
            results = src.search("test")

        assert results[0].abstract is None

    @patch.object(OpenAlexSource, "_get")
    def test_high_level_concepts_are_filtered(self, mock_get):
        mock_get.return_value = make_response(json_data={"results": [WORK]})

        with OpenAlexSource() as src:
            results = src.search("test")

        cats = results[0].categories
        assert "Solar cell" in cats
        assert "Perovskite" in cats
        assert "Methylammonium lead halide" not in cats

    @patch.object(OpenAlexSource, "_get")
    def test_missing_primary_location(self, mock_get):
        work = {**WORK, "primary_location": None}
        mock_get.return_value = make_response(json_data={"results": [work]})

        with OpenAlexSource() as src:
            results = src.search("test")

        assert results[0].venue is None
