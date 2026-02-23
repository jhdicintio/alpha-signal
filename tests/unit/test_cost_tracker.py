"""Unit tests for cost estimation and tracking."""

from __future__ import annotations

from datetime import date

from alpha_signal.models.articles import Article
from alpha_signal.monitoring.costs import (
    CostEstimate,
    CostTracker,
    count_tokens,
    token_cost,
)

SYSTEM_PROMPT = "You are a helpful assistant."

ARTICLE = Article(
    source="test",
    source_id="1",
    title="Solid-State Batteries for Electric Vehicles",
    abstract="We demonstrate a new electrolyte achieving 400 Wh/kg over 500 cycles.",
    authors=["Jane Smith"],
    publication_date=date(2024, 1, 15),
    venue="Nature Energy",
)

ARTICLE_NO_ABSTRACT = Article(
    source="test",
    source_id="2",
    title="No Abstract Paper",
)


class TestCountTokens:
    def test_counts_tokens(self):
        tokens = count_tokens("Hello, world!", "gpt-4o-mini")
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_empty_string(self):
        assert count_tokens("", "gpt-4o-mini") == 0

    def test_unknown_model_uses_fallback(self):
        tokens = count_tokens("Hello, world!", "unknown-model-xyz")
        assert tokens > 0


class TestTokenCost:
    def test_gpt4o_mini_pricing(self):
        cost = token_cost(1_000_000, 1_000_000, "gpt-4o-mini")
        assert abs(cost - 0.75) < 0.001  # $0.15 input + $0.60 output

    def test_gpt4o_pricing(self):
        cost = token_cost(1_000_000, 1_000_000, "gpt-4o")
        assert abs(cost - 12.50) < 0.01  # $2.50 input + $10.00 output

    def test_unknown_model_returns_zero(self):
        assert token_cost(1000, 1000, "unknown-model") == 0.0

    def test_zero_tokens(self):
        assert token_cost(0, 0, "gpt-4o-mini") == 0.0


class TestCostEstimate:
    def test_str_format(self):
        est = CostEstimate(
            num_articles=50,
            model="gpt-4o-mini",
            total_input_tokens=30000,
            estimated_output_tokens=20000,
            estimated_cost_usd=0.0165,
        )
        s = str(est)
        assert "50 articles" in s
        assert "30,000" in s
        assert "$0.0165" in s


class TestCostTrackerEstimation:
    def test_estimate_single_article(self):
        tracker = CostTracker(model="gpt-4o-mini")
        estimate = tracker.estimate_article(ARTICLE, SYSTEM_PROMPT)

        assert estimate.num_articles == 1
        assert estimate.model == "gpt-4o-mini"
        assert estimate.total_input_tokens > 0
        assert estimate.estimated_output_tokens == 400
        assert estimate.estimated_cost_usd > 0

    def test_estimate_batch(self):
        tracker = CostTracker(model="gpt-4o-mini")
        articles = [ARTICLE] * 10
        estimate = tracker.estimate_batch(articles, SYSTEM_PROMPT)

        assert estimate.num_articles == 10
        assert estimate.estimated_output_tokens == 4000

        single = tracker.estimate_article(ARTICLE, SYSTEM_PROMPT)
        assert abs(estimate.estimated_cost_usd - single.estimated_cost_usd * 10) < 0.0001

    def test_estimate_empty_batch(self):
        tracker = CostTracker(model="gpt-4o-mini")
        estimate = tracker.estimate_batch([], SYSTEM_PROMPT)

        assert estimate.num_articles == 0
        assert estimate.total_input_tokens == 0
        assert estimate.estimated_cost_usd == 0.0

    def test_custom_output_tokens(self):
        tracker = CostTracker(model="gpt-4o-mini")
        est_default = tracker.estimate_article(ARTICLE, SYSTEM_PROMPT)
        est_custom = tracker.estimate_article(
            ARTICLE, SYSTEM_PROMPT, estimated_output_tokens=800
        )

        assert est_custom.estimated_output_tokens == 800
        assert est_custom.estimated_cost_usd > est_default.estimated_cost_usd


class TestCostTrackerRecording:
    def test_record_usage(self):
        tracker = CostTracker(model="gpt-4o-mini")
        rec = tracker.record(input_tokens=500, output_tokens=300, article_source_id="art-1")

        assert rec.model == "gpt-4o-mini"
        assert rec.input_tokens == 500
        assert rec.output_tokens == 300
        assert rec.cost_usd > 0
        assert rec.article_source_id == "art-1"

    def test_running_totals(self):
        tracker = CostTracker(model="gpt-4o-mini")
        tracker.record(input_tokens=500, output_tokens=300, article_source_id="1")
        tracker.record(input_tokens=600, output_tokens=400, article_source_id="2")

        assert tracker.num_calls == 2
        assert tracker.total_input_tokens == 1100
        assert tracker.total_output_tokens == 700
        assert tracker.total_cost_usd > 0

    def test_records_are_copies(self):
        tracker = CostTracker(model="gpt-4o-mini")
        tracker.record(input_tokens=100, output_tokens=50, article_source_id="1")

        records = tracker.records
        assert len(records) == 1
        records.clear()
        assert tracker.num_calls == 1


class TestCostTrackerBudget:
    def test_no_budget_never_exceeds(self):
        tracker = CostTracker(model="gpt-4o-mini", budget_usd=None)
        assert tracker.would_exceed_budget(999999.0) is False

    def test_budget_tracking(self):
        tracker = CostTracker(model="gpt-4o-mini", budget_usd=0.01)
        assert tracker.budget_usd == 0.01
        assert tracker.budget_remaining_usd == 0.01

        tracker.record(input_tokens=10000, output_tokens=5000, article_source_id="1")
        assert tracker.budget_remaining_usd < 0.01

    def test_would_exceed_budget(self):
        tracker = CostTracker(model="gpt-4o-mini", budget_usd=0.001)
        assert tracker.would_exceed_budget(0.0005) is False
        assert tracker.would_exceed_budget(0.002) is True

    def test_would_exceed_after_spending(self):
        tracker = CostTracker(model="gpt-4o-mini", budget_usd=0.001)
        tracker.record(input_tokens=5000, output_tokens=1000, article_source_id="1")
        assert tracker.would_exceed_budget(0.001) is True


class TestCostTrackerSummary:
    def test_summary_without_budget(self):
        tracker = CostTracker(model="gpt-4o-mini")
        tracker.record(input_tokens=500, output_tokens=300, article_source_id="1")
        s = tracker.summary()
        assert "1 calls" in s
        assert "500" in s
        assert "$" in s

    def test_summary_with_budget(self):
        tracker = CostTracker(model="gpt-4o-mini", budget_usd=1.00)
        s = tracker.summary()
        assert "remaining" in s
        assert "$1.00" in s
