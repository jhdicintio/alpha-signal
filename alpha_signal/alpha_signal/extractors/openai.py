"""OpenAI-backed extractor using structured outputs.

Requires an OpenAI API key — either pass it directly or set the
``OPENAI_API_KEY`` environment variable.
"""

from __future__ import annotations

from datetime import datetime, timezone

import openai

from alpha_signal.extractors.base import SYSTEM_PROMPT, BaseExtractor, build_user_message
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction
from alpha_signal.monitoring.costs import CostEstimate, CostTracker

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIExtractor(BaseExtractor):
    """Extract structured data from abstracts using OpenAI's chat completions
    with enforced JSON-schema output."""

    name = "openai"
    DEFAULT_MODEL = _DEFAULT_MODEL

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self._client = openai.OpenAI(api_key=api_key)
        self._async_client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._cost_tracker = cost_tracker

    @property
    def cost_tracker(self) -> CostTracker | None:
        return self._cost_tracker

    def extract(self, article: Article, system_prompt: str | None = None) -> ArticleExtraction:
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

        prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
        user_content = build_user_message(article)

        response = self._client.beta.chat.completions.parse(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": prompt},
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

    async def extract_async(
        self, article: Article, system_prompt: str | None = None
    ) -> ArticleExtraction:
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

        prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
        user_content = build_user_message(article)

        response = await self._async_client.beta.chat.completions.parse(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": prompt},
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

    def estimate_cost(
        self, articles: list[Article], system_prompt: str | None = None
    ) -> CostEstimate:
        """Estimate extraction cost without calling the API.

        Uses tiktoken to count input tokens and a heuristic for output tokens.
        Requires no API key.
        """
        tracker = self._cost_tracker or CostTracker(model=self._model)
        prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
        return tracker.estimate_batch(articles, prompt)
