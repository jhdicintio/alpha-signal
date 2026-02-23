"""Unit tests for the extraction service layer."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import (
    ArticleExtraction,
    Novelty,
    Sentiment,
)
from alpha_signal.monitoring.costs import CostTracker
from alpha_signal.services.extraction import BudgetExceededError, extract_article, extract_batch

ARTICLE_WITH_ABSTRACT = Article(
    source="test",
    source_id="1",
    title="Test Article",
    abstract="A test abstract about batteries.",
    publication_date=date(2024, 1, 1),
)

ARTICLE_NO_ABSTRACT = Article(
    source="test",
    source_id="2",
    title="No Abstract Here",
)

DUMMY_EXTRACTION = ArticleExtraction(
    technologies=[],
    claims=[],
    novelty=Novelty.incremental,
    sentiment=Sentiment.neutral,
    summary="A test summary.",
)


def _mock_extractor(return_value: ArticleExtraction = DUMMY_EXTRACTION) -> MagicMock:
    ext = MagicMock()
    ext.name = "mock"
    ext.extract.return_value = return_value
    return ext


class TestExtractArticle:
    def test_returns_extraction(self):
        extractor = _mock_extractor()
        result = extract_article(ARTICLE_WITH_ABSTRACT, extractor)

        assert result == DUMMY_EXTRACTION
        extractor.extract.assert_called_once_with(ARTICLE_WITH_ABSTRACT)

    def test_returns_none_on_error(self):
        extractor = _mock_extractor()
        extractor.extract.side_effect = RuntimeError("LLM error")

        result = extract_article(ARTICLE_WITH_ABSTRACT, extractor)

        assert result is None


class TestExtractBatch:
    def test_processes_all_articles(self):
        extractor = _mock_extractor()
        articles = [ARTICLE_WITH_ABSTRACT, ARTICLE_WITH_ABSTRACT]

        results = extract_batch(articles, extractor)

        assert len(results) == 2
        assert all(art is ARTICLE_WITH_ABSTRACT for art, _ in results)
        assert all(ext == DUMMY_EXTRACTION for _, ext in results)

    def test_skips_articles_without_abstract(self):
        extractor = _mock_extractor()
        articles = [ARTICLE_WITH_ABSTRACT, ARTICLE_NO_ABSTRACT]

        results = extract_batch(articles, extractor)

        assert len(results) == 1
        assert results[0][0] is ARTICLE_WITH_ABSTRACT
        assert extractor.extract.call_count == 1

    def test_includes_no_abstract_when_flag_is_false(self):
        extractor = _mock_extractor()
        articles = [ARTICLE_NO_ABSTRACT]

        results = extract_batch(articles, extractor, skip_no_abstract=False)

        assert len(results) == 1
        extractor.extract.assert_called_once()

    def test_skips_failed_extractions(self):
        extractor = _mock_extractor()
        call_count = 0

        def side_effect(article):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            return DUMMY_EXTRACTION

        extractor.extract.side_effect = side_effect
        articles = [ARTICLE_WITH_ABSTRACT, ARTICLE_WITH_ABSTRACT]

        results = extract_batch(articles, extractor)

        assert len(results) == 1

    def test_empty_batch(self):
        extractor = _mock_extractor()
        results = extract_batch([], extractor)
        assert results == []


class TestExtractBatchBudget:
    def test_raises_when_estimate_exceeds_budget(self):
        extractor = _mock_extractor()
        tracker = CostTracker(model="gpt-4o-mini", budget_usd=0.0000001)
        articles = [ARTICLE_WITH_ABSTRACT] * 100

        with pytest.raises(BudgetExceededError):
            extract_batch(
                articles,
                extractor,
                cost_tracker=tracker,
                system_prompt="You are a test assistant.",
            )

        extractor.extract.assert_not_called()

    def test_stops_mid_batch_when_budget_exhausted(self):
        tracker = CostTracker(model="gpt-4o-mini", budget_usd=0.0001)

        extractor = _mock_extractor()
        call_count = 0

        def extract_and_record(article):
            nonlocal call_count
            call_count += 1
            tracker.record(input_tokens=500, output_tokens=500, article_source_id=str(call_count))
            return DUMMY_EXTRACTION

        extractor.extract.side_effect = extract_and_record
        articles = [ARTICLE_WITH_ABSTRACT] * 100

        results = extract_batch(articles, extractor, cost_tracker=tracker)

        assert len(results) < 100
        assert len(results) > 0

    def test_no_budget_processes_all(self):
        extractor = _mock_extractor()
        tracker = CostTracker(model="gpt-4o-mini")
        articles = [ARTICLE_WITH_ABSTRACT] * 5

        results = extract_batch(articles, extractor, cost_tracker=tracker)

        assert len(results) == 5

    def test_works_without_system_prompt(self):
        """Budget pre-check is skipped when no system_prompt is provided,
        but mid-batch checks still apply."""
        extractor = _mock_extractor()
        tracker = CostTracker(model="gpt-4o-mini", budget_usd=10.0)
        articles = [ARTICLE_WITH_ABSTRACT]

        results = extract_batch(articles, extractor, cost_tracker=tracker)

        assert len(results) == 1
