"""Anthropic-backed extractor using tool_use for structured output.

Requires an Anthropic API key — either pass it directly or set the
``ANTHROPIC_API_KEY`` environment variable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import anthropic

from alpha_signal.extractors.base import SYSTEM_PROMPT, BaseExtractor, build_user_message
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction

_DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicExtractor(BaseExtractor):
    """Extract structured data from abstracts using Anthropic's Messages API
    with tool_use to enforce the JSON schema."""

    name = "anthropic"
    DEFAULT_MODEL = _DEFAULT_MODEL

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._tool_schema = self._build_tool_schema()

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

        user_content = build_user_message(article)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=SYSTEM_PROMPT,
            tools=[self._tool_schema],
            tool_choice={"type": "tool", "name": "article_extraction"},
            messages=[{"role": "user", "content": user_content}],
        )

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"),
            None,
        )
        if tool_block is None:
            raise RuntimeError(
                f"Anthropic response contained no tool_use block: "
                f"{[b.type for b in response.content]}"
            )

        data = tool_block.input if isinstance(tool_block.input, dict) else json.loads(tool_block.input)
        data["extraction_model"] = self._model
        data["extraction_timestamp"] = datetime.now(timezone.utc)
        return ArticleExtraction(**data)

    async def extract_async(self, article: Article) -> ArticleExtraction:
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

        user_content = build_user_message(article)

        response = await self._async_client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=SYSTEM_PROMPT,
            tools=[self._tool_schema],
            tool_choice={"type": "tool", "name": "article_extraction"},
            messages=[{"role": "user", "content": user_content}],
        )

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"),
            None,
        )
        if tool_block is None:
            raise RuntimeError(
                f"Anthropic response contained no tool_use block: "
                f"{[b.type for b in response.content]}"
            )

        data = tool_block.input if isinstance(tool_block.input, dict) else json.loads(tool_block.input)
        data["extraction_model"] = self._model
        data["extraction_timestamp"] = datetime.now(timezone.utc)
        return ArticleExtraction(**data)

    @staticmethod
    def _build_tool_schema() -> dict:
        schema = ArticleExtraction.model_json_schema()
        schema.pop("title", None)
        schema.pop("description", None)
        return {
            "name": "article_extraction",
            "description": "Extract structured data from a scientific article abstract.",
            "input_schema": schema,
        }
