"""Unit tests for GeminiExtractor — all Gemini calls are mocked."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

from alpha_signal.extractors.gemini import GeminiExtractor
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import (
    ArticleExtraction,
    Novelty,
    Sentiment,
)

SAMPLE_ARTICLE = Article(
    source="arxiv",
    source_id="2401.12345",
    title="A Novel Solid-State Electrolyte for Lithium-Sulfur Batteries",
    abstract="We demonstrate a new ceramic electrolyte enabling stable cycling.",
    authors=["Jane Smith"],
    publication_date=date(2024, 1, 15),
)

NO_ABSTRACT_ARTICLE = Article(
    source="test",
    source_id="no-abstract",
    title="A Paper Without An Abstract",
)

_JSON_OUTPUT = json.dumps({
    "technologies": [],
    "claims": [],
    "novelty": "novel",
    "sentiment": "optimistic",
    "summary": "Promising solid-state electrolyte for EVs.",
})


def _mock_response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    return response


class TestGeminiExtractorExtract:
    @patch("alpha_signal.extractors.gemini.genai.Client")
    def test_returns_parsed_extraction(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = _mock_response(_JSON_OUTPUT)

        extractor = GeminiExtractor(api_key="test-key")
        result = extractor.extract(SAMPLE_ARTICLE)

        assert isinstance(result, ArticleExtraction)
        assert result.novelty == Novelty.novel
        assert result.sentiment == Sentiment.optimistic
        assert result.extraction_model == "gemini-2.0-flash"
        assert result.extraction_timestamp is not None

    @patch("alpha_signal.extractors.gemini.genai.Client")
    def test_no_abstract_returns_empty_extraction(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        extractor = GeminiExtractor(api_key="test-key")
        result = extractor.extract(NO_ABSTRACT_ARTICLE)

        assert result.technologies == []
        assert result.summary == "No abstract available for analysis."
        mock_client.models.generate_content.assert_not_called()

    @patch("alpha_signal.extractors.gemini.genai.Client")
    def test_passes_json_schema_config(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = _mock_response(_JSON_OUTPUT)

        extractor = GeminiExtractor(api_key="test-key")
        extractor.extract(SAMPLE_ARTICLE)

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]
        assert config.response_mime_type == "application/json"
        assert config.response_schema is not None
