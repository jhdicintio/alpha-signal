"""Unit tests for ArxivSource — XML parsing and normalisation."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from alpha_signal.sources.arxiv import ArxivSource
from tests.conftest import make_response

ATOM_FEED = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>  Advances in Solid-State\n    Battery Technology  </title>
    <summary>  We present a novel approach\n    to solid-state batteries.  </summary>
    <author><name>Jane Smith</name></author>
    <author><name>John Doe</name></author>
    <published>2024-01-15T18:30:00Z</published>
    <arxiv:doi>10.1234/test.2024</arxiv:doi>
    <category term="cond-mat.mtrl-sci"/>
    <category term="physics.chem-ph"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related"/>
    <link href="http://arxiv.org/abs/2401.12345v1" rel="alternate"/>
  </entry>
</feed>
"""

EMPTY_FEED = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>
"""

ENTRY_NO_ID = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Missing ID Paper</title>
    <summary>No id element here.</summary>
  </entry>
</feed>
"""


class TestArxivSearch:
    @patch.object(ArxivSource, "_get")
    def test_search_parses_atom_feed(self, mock_get):
        mock_get.return_value = make_response(text=ATOM_FEED)

        with ArxivSource() as src:
            results = src.search("solid state batteries")

        assert len(results) == 1
        art = results[0]
        assert art.source == "arxiv"
        assert art.source_id == "2401.12345v1"
        assert art.title == "Advances in Solid-State Battery Technology"
        assert art.abstract == "We present a novel approach to solid-state batteries."
        assert art.authors == ["Jane Smith", "John Doe"]
        assert art.publication_date == date(2024, 1, 15)
        assert art.doi == "10.1234/test.2024"
        assert art.url == "http://arxiv.org/pdf/2401.12345v1"
        assert art.venue == "arXiv"
        assert "cond-mat.mtrl-sci" in art.categories
        assert "physics.chem-ph" in art.categories

    @patch.object(ArxivSource, "_get")
    def test_search_empty_feed(self, mock_get):
        mock_get.return_value = make_response(text=EMPTY_FEED)

        with ArxivSource() as src:
            results = src.search("xyznonexistent")

        assert results == []

    @patch.object(ArxivSource, "_get")
    def test_search_query_format(self, mock_get):
        mock_get.return_value = make_response(text=EMPTY_FEED)

        with ArxivSource() as src:
            src.search("quantum computing", max_results=25)

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["search_query"] == "all:quantum computing"
        assert kwargs["params"]["max_results"] == 25

    @patch.object(ArxivSource, "_get")
    def test_search_adds_submitted_date_filter_when_date_range_given(self, mock_get):
        mock_get.return_value = make_response(text=EMPTY_FEED)

        with ArxivSource() as src:
            src.search(
                "battery",
                max_results=10,
                date_from=date(2024, 6, 1),
                date_to=date(2024, 6, 30),
            )

        _, kwargs = mock_get.call_args
        assert "submittedDate:[20240601 TO 20240630]" in kwargs["params"]["search_query"]
        assert kwargs["params"]["search_query"].startswith("all:battery AND ")

    @patch.object(ArxivSource, "_get")
    def test_search_date_filter_single_day(self, mock_get):
        mock_get.return_value = make_response(text=EMPTY_FEED)

        with ArxivSource() as src:
            src.search(
                "quantum",
                date_from=date(2024, 3, 15),
                date_to=date(2024, 3, 15),
            )

        _, kwargs = mock_get.call_args
        assert "submittedDate:[20240315 TO 20240315]" in kwargs["params"]["search_query"]

    @patch.object(ArxivSource, "_get")
    def test_search_caps_max_results(self, mock_get):
        mock_get.return_value = make_response(text=EMPTY_FEED)

        with ArxivSource() as src:
            src.search("test", max_results=500)

        _, kwargs = mock_get.call_args
        assert kwargs["params"]["max_results"] == 100


class TestArxivFetchById:
    @patch.object(ArxivSource, "_get")
    def test_fetch_existing_paper(self, mock_get):
        mock_get.return_value = make_response(text=ATOM_FEED)

        with ArxivSource() as src:
            art = src.fetch_by_id("2401.12345")

        assert art is not None
        assert art.source_id == "2401.12345v1"

    @patch.object(ArxivSource, "_get")
    def test_fetch_empty_feed_returns_none(self, mock_get):
        mock_get.return_value = make_response(text=EMPTY_FEED)

        with ArxivSource() as src:
            art = src.fetch_by_id("nonexistent")

        assert art is None


class TestArxivEdgeCases:
    @patch.object(ArxivSource, "_get")
    def test_whitespace_in_title_and_abstract_is_normalised(self, mock_get):
        mock_get.return_value = make_response(text=ATOM_FEED)

        with ArxivSource() as src:
            results = src.search("test")

        art = results[0]
        assert "\n" not in art.title
        assert "  " not in art.title
        assert "\n" not in (art.abstract or "")

    @patch.object(ArxivSource, "_get")
    def test_entry_without_id_is_skipped(self, mock_get):
        mock_get.return_value = make_response(text=ENTRY_NO_ID)

        with ArxivSource() as src:
            results = src.search("test")

        assert results == []

    @patch.object(ArxivSource, "_get")
    def test_entry_without_doi(self, mock_get):
        feed = ATOM_FEED.replace(
            "<arxiv:doi>10.1234/test.2024</arxiv:doi>", ""
        )
        mock_get.return_value = make_response(text=feed)

        with ArxivSource() as src:
            results = src.search("test")

        assert results[0].doi is None

    @patch.object(ArxivSource, "_get")
    def test_falls_back_to_abs_url_when_no_pdf_link(self, mock_get):
        feed = ATOM_FEED.replace(
            '<link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related"/>',
            "",
        )
        mock_get.return_value = make_response(text=feed)

        with ArxivSource() as src:
            results = src.search("test")

        assert results[0].url == "http://arxiv.org/abs/2401.12345v1"
