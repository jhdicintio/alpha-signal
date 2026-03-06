"""Unit tests for LocalExtractor — model loading and generation are mocked."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from alpha_signal.extractors.local import (
    LocalExtractionError,
    LocalExtractor,
    _fallback_extraction,
)
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import (
    Novelty,
    Sentiment,
)

SAMPLE_ARTICLE = Article(
    source="arxiv",
    source_id="2401.12345",
    title="A Novel Solid-State Electrolyte for Lithium-Sulfur Batteries",
    abstract=(
        "We demonstrate a new ceramic electrolyte enabling stable cycling of "
        "lithium-sulfur cells at room temperature."
    ),
    authors=["Jane Smith"],
    publication_date=date(2024, 1, 15),
    doi="10.1234/test",
    venue="Nature Energy",
)

VALID_JSON_OUTPUT = """{"technologies": [{"technology": "solid-state electrolyte", "sector": "Energy Storage", "maturity": "lab_scale", "relevance": "For EVs."}], "claims": [{"statement": "stable cycling", "quantitative": false}], "novelty": "novel", "sentiment": "optimistic", "summary": "New electrolyte for Li-S batteries."}"""


NO_ABSTRACT_ARTICLE = Article(
    source="test",
    source_id="no-abstract",
    title="No Abstract",
    abstract=None,
)


class TestLocalExtractorNoAbstract:
    def test_no_abstract_returns_empty_extraction(self):
        extractor = LocalExtractor(model="Qwen/Qwen2.5-0.5B-Instruct")
        with patch.object(extractor, "_ensure_loaded"):
            result = extractor.extract(NO_ABSTRACT_ARTICLE)
        assert result.technologies == []
        assert result.claims == []
        assert result.novelty == Novelty.review
        assert result.sentiment == Sentiment.neutral
        assert "No abstract" in result.summary
        assert result.extraction_model == "Qwen/Qwen2.5-0.5B-Instruct"


class TestLocalExtractorExtract:
    @patch.object(LocalExtractor, "_ensure_loaded")
    @patch.object(LocalExtractor, "_run_generation")
    def test_returns_parsed_extraction(self, mock_run, mock_load):
        mock_run.return_value = (VALID_JSON_OUTPUT, 100, 200)
        extractor = LocalExtractor(model="local/test-model")
        result = extractor.extract(SAMPLE_ARTICLE)
        assert len(result.technologies) == 1
        assert result.technologies[0].technology == "solid-state electrolyte"
        assert result.novelty == Novelty.novel
        assert result.sentiment == Sentiment.optimistic
        assert result.extraction_model == "local/test-model"
        assert result.extraction_timestamp is not None
        mock_run.assert_called_once_with(SAMPLE_ARTICLE)

    @patch.object(LocalExtractor, "_ensure_loaded")
    @patch.object(LocalExtractor, "_run_generation")
    def test_records_usage_when_cost_tracker_present(self, mock_run, mock_load):
        from alpha_signal.monitoring.costs import CostTracker
        mock_run.return_value = (VALID_JSON_OUTPUT, 50, 150)
        tracker = CostTracker(model="local", budget_usd=None)
        extractor = LocalExtractor(model="local/model", cost_tracker=tracker)
        extractor.extract(SAMPLE_ARTICLE)
        assert tracker.num_calls == 1
        assert tracker.total_input_tokens == 50
        assert tracker.total_output_tokens == 150

    @patch.object(LocalExtractor, "_ensure_loaded")
    @patch.object(LocalExtractor, "_run_generation")
    def test_retry_on_parse_failure_then_succeed(self, mock_run, mock_load):
        mock_run.side_effect = [
            ("not valid json", 10, 5),
            (VALID_JSON_OUTPUT, 10, 200),
        ]
        extractor = LocalExtractor(model="local/model")
        result = extractor.extract(SAMPLE_ARTICLE)
        assert mock_run.call_count == 2
        assert result.summary == "New electrolyte for Li-S batteries."

    @patch.object(LocalExtractor, "_ensure_loaded")
    @patch.object(LocalExtractor, "_run_generation")
    def test_raise_after_retry_when_on_parse_failure_raise(self, mock_run, mock_load):
        mock_run.return_value = ("garbage", 10, 5)
        extractor = LocalExtractor(model="local/model", on_parse_failure="raise")
        with pytest.raises(LocalExtractionError) as exc_info:
            extractor.extract(SAMPLE_ARTICLE)
        assert SAMPLE_ARTICLE.source_id in str(exc_info.value)
        assert mock_run.call_count == 2

    @patch.object(LocalExtractor, "_ensure_loaded")
    @patch.object(LocalExtractor, "_run_generation")
    def test_fallback_extraction_when_on_parse_failure_fallback(self, mock_run, mock_load):
        mock_run.return_value = ("garbage", 10, 5)
        extractor = LocalExtractor(model="local/model", on_parse_failure="fallback")
        result = extractor.extract(SAMPLE_ARTICLE)
        assert result.technologies == []
        assert result.claims == []
        assert result.novelty == Novelty.review
        assert result.sentiment == Sentiment.neutral
        assert "Extraction failed" in result.summary
        assert result.extraction_model == "local/model"


class TestLocalExtractorEstimateCost:
    def test_estimate_cost_returns_zero_cost(self):
        extractor = LocalExtractor(model="Qwen/Qwen2.5-0.5B-Instruct")
        articles = [SAMPLE_ARTICLE, SAMPLE_ARTICLE]
        estimate = extractor.estimate_cost(articles)
        assert estimate.model == "Qwen/Qwen2.5-0.5B-Instruct"
        assert estimate.num_articles == 2
        assert estimate.estimated_cost_usd == 0.0


class TestFallbackExtraction:
    def test_fallback_has_expected_shape(self):
        out = _fallback_extraction("my-model")
        assert out.technologies == []
        assert out.claims == []
        assert out.novelty == Novelty.review
        assert out.sentiment == Sentiment.neutral
        assert "Extraction failed" in out.summary
        assert out.extraction_model == "my-model"
