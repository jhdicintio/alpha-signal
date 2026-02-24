"""OpenAI-backed extractor using structured outputs.

Requires an OpenAI API key — either pass it directly or set the
``OPENAI_API_KEY`` environment variable.
"""

from __future__ import annotations

from datetime import datetime, timezone

import openai

from alpha_signal.extractors.base import BaseExtractor
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction
from alpha_signal.monitoring.costs import CostEstimate, CostTracker

_SYSTEM_PROMPT = """\
You are a scientific-article analyst specializing in identifying commercially \
relevant technologies and trends.  Your job is to extract structured \
information from scientific article abstracts that could inform investment \
and trading decisions.

For each abstract you receive, extract:

1. TECHNOLOGIES — Identify specific technologies, materials, methods, or \
innovations mentioned.
   • technology: the precise name (e.g. "solid-state lithium-sulfur batteries")
   • sector: the broad market sector (e.g. "Energy Storage", "Quantum Computing", \
"Biotechnology", "Semiconductors", "Artificial Intelligence", "Aerospace")
   • maturity: how close to commercial reality — theoretical, lab_scale, pilot, \
or commercial
   • relevance: one sentence on why this matters commercially

2. CLAIMS — Key quantitative or qualitative findings.

3. NOVELTY — Is this research novel, incremental, or a review?

4. SENTIMENT — Is the overall tone optimistic, neutral, cautious, or negative?

5. SUMMARY — One sentence focused on commercial / trading relevance.

Guidelines:
• Only extract technologies that are *explicitly* mentioned in the abstract.
• Do NOT infer or speculate about technologies not discussed.
• If the abstract has no commercially relevant technologies, return an empty \
technologies list.
• Be precise with maturity levels — most academic research is theoretical or \
lab_scale.
• Prefer specificity: "perovskite tandem solar cells" is better than "solar energy".\
"""

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIExtractor(BaseExtractor):
    """Extract structured data from abstracts using OpenAI's chat completions
    with enforced JSON-schema output."""

    name = "openai"
    SYSTEM_PROMPT = _SYSTEM_PROMPT
    DEFAULT_MODEL = _DEFAULT_MODEL

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._cost_tracker = cost_tracker

    @property
    def cost_tracker(self) -> CostTracker | None:
        return self._cost_tracker

    def extract(self, article: Article) -> ArticleExtraction:
        if not article.abstract:
            return ArticleExtraction(
                technologies=[],
                claims=[],
                novelty="review",
                sentiment="neutral",
                summary="No abstract available for analysis.",
                extraction_model=self._model,
                extraction_timestamp=datetime.now(timezone.utc),
            )

        user_content = self._build_user_message(article)

        response = self._client.beta.chat.completions.parse(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=ArticleExtraction,
        )

        if self._cost_tracker and response.usage:
            self._cost_tracker.record(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                article_source_id=article.source_id,
            )

        parsed = response.choices[0].message.parsed
        if parsed is None:
            refusal = response.choices[0].message.refusal
            raise RuntimeError(f"Extraction refused by model: {refusal}")

        data = parsed.model_dump()
        data["extraction_model"] = self._model
        data["extraction_timestamp"] = datetime.now(timezone.utc)
        return ArticleExtraction(**data)

    def estimate_cost(self, articles: list[Article]) -> CostEstimate:
        """Estimate extraction cost without calling the API.

        Uses tiktoken to count input tokens and a heuristic for output tokens.
        Requires no API key.
        """
        tracker = self._cost_tracker or CostTracker(model=self._model)
        return tracker.estimate_batch(articles, _SYSTEM_PROMPT)

    @staticmethod
    def _build_user_message(article: Article) -> str:
        parts = [f"Title: {article.title}"]
        if article.venue:
            parts.append(f"Venue: {article.venue}")
        if article.publication_date:
            parts.append(f"Date: {article.publication_date.isoformat()}")
        parts.append(f"\nAbstract:\n{article.abstract}")
        return "\n".join(parts)
