"""Unit tests for AnthropicExtractor — all Anthropic calls are mocked."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from alpha_signal.extractors.anthropic import AnthropicExtractor
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

_TOOL_OUTPUT = {
    "technologies": [],
    "claims": [],
    "novelty": "novel",
    "sentiment": "optimistic",
    "summary": "Promising solid-state electrolyte for EVs.",
}


def _mock_tool_response(tool_input: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = tool_input

    response = MagicMock()
    response.content = [tool_block]
    return response


class TestAnthropicExtractorExtract:
    @patch("alpha_signal.extractors.anthropic.anthropic.Anthropic")
    def test_returns_parsed_extraction(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_tool_response(_TOOL_OUTPUT)

        extractor = AnthropicExtractor(api_key="test-key")
        result = extractor.extract(SAMPLE_ARTICLE)

        assert isinstance(result, ArticleExtraction)
        assert result.novelty == Novelty.novel
        assert result.sentiment == Sentiment.optimistic
        assert result.extraction_model == "claude-sonnet-4-20250514"
        assert result.extraction_timestamp is not None

    @patch("alpha_signal.extractors.anthropic.anthropic.Anthropic")
    def test_no_abstract_returns_empty_extraction(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        extractor = AnthropicExtractor(api_key="test-key")
        result = extractor.extract(NO_ABSTRACT_ARTICLE)

        assert result.technologies == []
        assert result.summary == "No abstract available for analysis."
        mock_client.messages.create.assert_not_called()

    @patch("alpha_signal.extractors.anthropic.anthropic.Anthropic")
    def test_forces_tool_use(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_tool_response(_TOOL_OUTPUT)

        extractor = AnthropicExtractor(api_key="test-key")
        extractor.extract(SAMPLE_ARTICLE)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "article_extraction"}
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "article_extraction"

    @patch("alpha_signal.extractors.anthropic.anthropic.Anthropic")
    def test_raises_when_no_tool_block(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        response = MagicMock()
        response.content = [text_block]
        mock_client.messages.create.return_value = response

        extractor = AnthropicExtractor(api_key="test-key")
        with pytest.raises(RuntimeError, match="no tool_use block"):
            extractor.extract(SAMPLE_ARTICLE)
