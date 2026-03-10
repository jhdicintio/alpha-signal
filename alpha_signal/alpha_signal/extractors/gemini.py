"""Google Gemini-backed extractor using structured output.

Requires a Google AI API key — either pass it directly or set the
``GOOGLE_API_KEY`` environment variable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from google import genai
from google.genai import types

from alpha_signal.extractors.base import SYSTEM_PROMPT, BaseExtractor, build_user_message
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction

_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiExtractor(BaseExtractor):
    """Extract structured data from abstracts using Google's Gemini API
    with JSON-schema constrained output."""

    name = "gemini"
    DEFAULT_MODEL = _DEFAULT_MODEL

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._temperature = temperature

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

        response = self._client.models.generate_content(
            model=self._model,
            contents=[user_content],
            config=types.GenerateContentConfig(
                system_instruction=prompt,
                temperature=self._temperature,
                response_mime_type="application/json",
                response_schema=ArticleExtraction.model_json_schema(),
            ),
        )

        data = json.loads(response.text)
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

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[user_content],
            config=types.GenerateContentConfig(
                system_instruction=prompt,
                temperature=self._temperature,
                response_mime_type="application/json",
                response_schema=ArticleExtraction.model_json_schema(),
            ),
        )

        data = json.loads(response.text)
        data["extraction_model"] = self._model
        data["extraction_timestamp"] = datetime.now(timezone.utc)
        return ArticleExtraction(**data)
