"""Cost estimation and tracking for LLM extraction.

Provides pre-call estimation (via tiktoken token counting) and post-call
tracking (from API response usage data) so you always know what a batch
will cost before you run it, and what it actually cost after.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import tiktoken

from alpha_signal.models.articles import Article

logger = logging.getLogger(__name__)

# Prices per token (USD).  Update when providers change pricing.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15e-6, "output": 0.60e-6},
    "gpt-4o": {"input": 2.50e-6, "output": 10.00e-6},
    "gpt-4-turbo": {"input": 10.00e-6, "output": 30.00e-6},
}

_DEFAULT_OUTPUT_TOKENS_PER_ARTICLE = 400


def _get_encoder(model: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str) -> int:
    """Return the number of tokens in *text* for *model*."""
    return len(_get_encoder(model).encode(text))


def token_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Compute cost in USD for given token counts and model."""
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        logger.warning("no pricing data for model %r — returning $0.00", model)
        return 0.0
    return input_tokens * pricing["input"] + output_tokens * pricing["output"]


# -- Data classes -----------------------------------------------------------


@dataclass
class CostEstimate:
    """Pre-extraction cost forecast for a batch of articles."""

    num_articles: int
    model: str
    total_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float

    def __str__(self) -> str:
        return (
            f"Estimate: {self.num_articles} articles | "
            f"~{self.total_input_tokens:,} input tokens | "
            f"~{self.estimated_output_tokens:,} est. output tokens | "
            f"~${self.estimated_cost_usd:.4f}"
        )


@dataclass
class UsageRecord:
    """A single recorded API call."""

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    article_source_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# -- Tracker ----------------------------------------------------------------


class CostTracker:
    """Records actual API usage and enforces an optional spending budget.

    Also provides pre-call batch estimation via :meth:`estimate_batch`.
    """

    def __init__(self, model: str = "gpt-4o-mini", budget_usd: float | None = None) -> None:
        self._model = model
        self._budget_usd = budget_usd
        self._records: list[UsageRecord] = []
        self._encoder = _get_encoder(model)

    # -- estimation ----------------------------------------------------------

    def estimate_article(
        self,
        article: Article,
        system_prompt: str,
        *,
        estimated_output_tokens: int = _DEFAULT_OUTPUT_TOKENS_PER_ARTICLE,
    ) -> CostEstimate:
        """Estimate the cost of extracting a single article."""
        return self.estimate_batch(
            [article],
            system_prompt,
            estimated_output_tokens=estimated_output_tokens,
        )

    def estimate_batch(
        self,
        articles: list[Article],
        system_prompt: str,
        *,
        estimated_output_tokens: int = _DEFAULT_OUTPUT_TOKENS_PER_ARTICLE,
    ) -> CostEstimate:
        """Estimate the cost of extracting a batch of articles.

        The *system_prompt* is counted once per call (OpenAI includes it in
        every request).  The user message is counted per article.
        """
        system_tokens = len(self._encoder.encode(system_prompt))

        total_input = 0
        for article in articles:
            user_text = _build_estimation_text(article)
            user_tokens = len(self._encoder.encode(user_text))
            # +4 accounts for chat-format overhead per message pair
            total_input += system_tokens + user_tokens + 4

        total_output = estimated_output_tokens * len(articles)
        cost = token_cost(total_input, total_output, self._model)

        return CostEstimate(
            num_articles=len(articles),
            model=self._model,
            total_input_tokens=total_input,
            estimated_output_tokens=total_output,
            estimated_cost_usd=cost,
        )

    # -- recording -----------------------------------------------------------

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        article_source_id: str,
    ) -> UsageRecord:
        """Record actual token usage from an API response."""
        cost = token_cost(input_tokens, output_tokens, self._model)
        rec = UsageRecord(
            model=self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            article_source_id=article_source_id,
        )
        self._records.append(rec)
        return rec

    # -- querying ------------------------------------------------------------

    @property
    def records(self) -> list[UsageRecord]:
        return list(self._records)

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self._records)

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self._records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self._records)

    @property
    def num_calls(self) -> int:
        return len(self._records)

    @property
    def budget_usd(self) -> float | None:
        return self._budget_usd

    @property
    def budget_remaining_usd(self) -> float | None:
        if self._budget_usd is None:
            return None
        return self._budget_usd - self.total_cost_usd

    def would_exceed_budget(self, additional_cost: float) -> bool:
        """Return ``True`` if spending *additional_cost* would breach the budget."""
        if self._budget_usd is None:
            return False
        return (self.total_cost_usd + additional_cost) > self._budget_usd

    def summary(self) -> str:
        """Human-readable summary of usage so far."""
        parts = [
            f"{self.num_calls} calls",
            f"{self.total_input_tokens:,} input + {self.total_output_tokens:,} output tokens",
            f"${self.total_cost_usd:.4f} spent",
        ]
        if self._budget_usd is not None:
            parts.append(f"${self.budget_remaining_usd:.4f} remaining of ${self._budget_usd:.2f}")
        return " | ".join(parts)


# -- helpers ----------------------------------------------------------------


def _build_estimation_text(article: Article) -> str:
    """Approximate the user-message that the extractor would build."""
    parts = [f"Title: {article.title}"]
    if article.venue:
        parts.append(f"Venue: {article.venue}")
    if article.publication_date:
        parts.append(f"Date: {article.publication_date.isoformat()}")
    parts.append(f"\nAbstract:\n{article.abstract or ''}")
    return "\n".join(parts)
