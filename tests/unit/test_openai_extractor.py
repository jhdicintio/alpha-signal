"""Unit tests for OpenAIExtractor — all OpenAI calls are mocked."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from alpha_signal.extractors.openai import OpenAIExtractor
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import (
    ArticleExtraction,
    Claim,
    Maturity,
    Novelty,
    Sentiment,
    TechnologyMention,
)
from alpha_signal.monitoring.costs import CostTracker

SAMPLE_ARTICLE = Article(
    source="arxiv",
    source_id="2401.12345",
    title="A Novel Solid-State Electrolyte for Lithium-Sulfur Batteries",
    abstract=(
        "We demonstrate a new ceramic electrolyte enabling stable cycling of "
        "lithium-sulfur cells at room temperature, achieving 400 Wh/kg energy "
        "density over 500 cycles with minimal capacity fade."
    ),
    authors=["Jane Smith", "John Doe"],
    publication_date=date(2024, 1, 15),
    doi="10.1234/test",
    venue="Nature Energy",
)

SAMPLE_EXTRACTION = ArticleExtraction(
    technologies=[
        TechnologyMention(
            technology="ceramic solid-state electrolyte for lithium-sulfur batteries",
            sector="Energy Storage",
            maturity=Maturity.lab_scale,
            relevance="Could enable safer, higher-density EV batteries.",
        ),
    ],
    claims=[
        Claim(statement="400 Wh/kg energy density over 500 cycles", quantitative=True),
    ],
    novelty=Novelty.novel,
    sentiment=Sentiment.optimistic,
    summary="New solid-state electrolyte could make lithium-sulfur batteries viable for EVs.",
)

NO_ABSTRACT_ARTICLE = Article(
    source="test",
    source_id="no-abstract",
    title="A Paper Without An Abstract",
)


def _mock_parse_response(
    extraction: ArticleExtraction,
    prompt_tokens: int = 500,
    completion_tokens: int = 300,
) -> MagicMock:
    """Build a mock that mimics ``client.beta.chat.completions.parse(...)``."""
    message = MagicMock()
    message.parsed = extraction
    message.refusal = None

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


class TestOpenAIExtractorExtract:
    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_returns_parsed_extraction(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value = _mock_parse_response(
            SAMPLE_EXTRACTION
        )

        extractor = OpenAIExtractor(api_key="test-key")
        result = extractor.extract(SAMPLE_ARTICLE)

        assert result == SAMPLE_EXTRACTION
        assert len(result.technologies) == 1
        assert result.technologies[0].sector == "Energy Storage"
        assert result.novelty == Novelty.novel

    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_passes_correct_model_and_temperature(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value = _mock_parse_response(
            SAMPLE_EXTRACTION
        )

        extractor = OpenAIExtractor(api_key="test-key", model="gpt-4o", temperature=0.1)
        extractor.extract(SAMPLE_ARTICLE)

        call_kwargs = mock_client.beta.chat.completions.parse.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["response_format"] is ArticleExtraction

    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_system_and_user_messages_are_sent(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value = _mock_parse_response(
            SAMPLE_EXTRACTION
        )

        extractor = OpenAIExtractor(api_key="test-key")
        extractor.extract(SAMPLE_ARTICLE)

        call_kwargs = mock_client.beta.chat.completions.parse.call_args.kwargs
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Solid-State Electrolyte" in messages[1]["content"]
        assert "400 Wh/kg" in messages[1]["content"]

    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_user_message_includes_venue_and_date(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value = _mock_parse_response(
            SAMPLE_EXTRACTION
        )

        extractor = OpenAIExtractor(api_key="test-key")
        extractor.extract(SAMPLE_ARTICLE)

        user_msg = mock_client.beta.chat.completions.parse.call_args.kwargs["messages"][1]
        assert "Nature Energy" in user_msg["content"]
        assert "2024-01-15" in user_msg["content"]

    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_no_abstract_returns_empty_extraction(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        extractor = OpenAIExtractor(api_key="test-key")
        result = extractor.extract(NO_ABSTRACT_ARTICLE)

        assert result.technologies == []
        assert result.claims == []
        assert result.summary == "No abstract available for analysis."
        mock_client.beta.chat.completions.parse.assert_not_called()

    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_refusal_raises_runtime_error(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        message = MagicMock()
        message.parsed = None
        message.refusal = "I cannot process this content."
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        mock_client.beta.chat.completions.parse.return_value = response

        extractor = OpenAIExtractor(api_key="test-key")
        with pytest.raises(RuntimeError, match="refused"):
            extractor.extract(SAMPLE_ARTICLE)


class TestOpenAIExtractorCostTracking:
    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_records_usage_when_tracker_present(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value = _mock_parse_response(
            SAMPLE_EXTRACTION, prompt_tokens=600, completion_tokens=350
        )

        tracker = CostTracker(model="gpt-4o-mini")
        extractor = OpenAIExtractor(api_key="test-key", cost_tracker=tracker)
        extractor.extract(SAMPLE_ARTICLE)

        assert tracker.num_calls == 1
        assert tracker.total_input_tokens == 600
        assert tracker.total_output_tokens == 350
        assert tracker.total_cost_usd > 0

    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_no_tracking_without_tracker(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value = _mock_parse_response(
            SAMPLE_EXTRACTION
        )

        extractor = OpenAIExtractor(api_key="test-key")
        extractor.extract(SAMPLE_ARTICLE)

        assert extractor.cost_tracker is None

    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_no_abstract_does_not_record(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        tracker = CostTracker(model="gpt-4o-mini")
        extractor = OpenAIExtractor(api_key="test-key", cost_tracker=tracker)
        extractor.extract(NO_ABSTRACT_ARTICLE)

        assert tracker.num_calls == 0


class TestOpenAIExtractorEstimateCost:
    @patch("alpha_signal.extractors.openai.openai.OpenAI")
    def test_estimate_without_calling_api(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        extractor = OpenAIExtractor(api_key="test-key")
        estimate = extractor.estimate_cost([SAMPLE_ARTICLE] * 10)

        assert estimate.num_articles == 10
        assert estimate.total_input_tokens > 0
        assert estimate.estimated_cost_usd > 0
        mock_client.beta.chat.completions.parse.assert_not_called()
