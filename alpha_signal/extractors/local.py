"""Local SLM extractor: Hugging Face models on CPU (vanilla or fine-tuned).

Requires optional dependencies: pip install -e '.[local]'
Uses prompt-based JSON output; no API key needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from alpha_signal.extractors.base import SYSTEM_PROMPT, BaseExtractor, build_user_message
from alpha_signal.extractors.parse_json import extract_json_object
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction, Novelty, Sentiment
from alpha_signal.monitoring.costs import CostEstimate, CostTracker

logger = logging.getLogger(__name__)

JSON_INSTRUCTIONS = """

Respond with only a single JSON object, no other text or markdown. Use exactly these keys:
- "technologies": list of objects with "technology", "sector", "maturity" (one of: theoretical, lab_scale, pilot, commercial), "relevance"
- "claims": list of objects with "statement", "quantitative" (boolean)
- "novelty": one of "novel", "incremental", "review"
- "sentiment": one of "optimistic", "neutral", "cautious", "negative"
- "summary": one sentence string
"""


class LocalExtractionError(Exception):
    """Raised when local model output could not be parsed or validated."""

    def __init__(self, article_source_id: str, reason: str) -> None:
        self.article_source_id = article_source_id
        self.reason = reason
        super().__init__(f"Extraction failed for {article_source_id}: {reason}")


def _fallback_extraction(model_name: str) -> ArticleExtraction:
    """Minimal extraction used when on_parse_failure='fallback' and retry failed."""
    return ArticleExtraction(
        technologies=[],
        claims=[],
        novelty=Novelty.review,
        sentiment=Sentiment.neutral,
        summary="Extraction failed (parse error).",
        extraction_model=model_name,
        extraction_timestamp=datetime.now(timezone.utc),
    )


class LocalExtractor(BaseExtractor):
    """Extract structured data from abstracts using a local Hugging Face model on CPU.

    Supports vanilla HF models and fine-tuned adapters (PEFT). Output is parsed
    from prompt-requested JSON; malformed output is retried once, then either
    raised (skip article) or replaced with a fallback extraction.
    """

    name = "local"

    def __init__(
        self,
        model: str,
        device: str = "cpu",
        *,
        temperature: float = 0.0,
        cost_tracker: CostTracker | None = None,
        model_path: str | None = None,
        on_parse_failure: Literal["raise", "fallback"] = "raise",
        max_new_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._device = device
        self._temperature = temperature
        self._cost_tracker = cost_tracker
        self._model_path = model_path or model
        self._on_parse_failure = on_parse_failure
        self._max_new_tokens = max_new_tokens
        self._pipe: object = None
        self._tokenizer: object = None
        self._model_obj: object = None

    @property
    def cost_tracker(self) -> CostTracker | None:
        return self._cost_tracker

    def _ensure_loaded(self) -> None:
        if self._model_obj is not None:
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as e:
            raise ImportError(
                "Local extractor requires optional dependencies: pip install -e '.[local]'"
            ) from e

        load_path = self._model_path
        path_obj = Path(load_path)
        adapter_config = path_obj / "adapter_config.json"
        is_adapter = adapter_config.exists()

        if is_adapter:
            import json as _json
            with open(adapter_config) as f:
                adapter_cfg = _json.load(f)
            base_name = adapter_cfg.get("base_model_name_or_path", load_path)
            tokenizer_path = base_name
        else:
            base_name = load_path
            tokenizer_path = load_path

        self._tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_path,
            trust_remote_code=True,
        )
        if self._tokenizer.pad_token_id is None:
            self._tokenizer.pad_token_id = self._tokenizer.eos_token_id

        if is_adapter:
            try:
                from peft import PeftModel
            except ImportError:
                raise ImportError(
                    "PEFT is required to load adapter. pip install -e '.[local]'"
                ) from None
            base_model = AutoModelForCausalLM.from_pretrained(
                base_name,
                device_map=self._device,
                torch_dtype="auto",
                trust_remote_code=True,
            )
            self._model_obj = PeftModel.from_pretrained(base_model, load_path)
        else:
            self._model_obj = AutoModelForCausalLM.from_pretrained(
                load_path,
                device_map=self._device,
                torch_dtype="auto",
                trust_remote_code=True,
            )
        self._model_obj.eval()

    def _run_generation(self, article: Article) -> tuple[str, int, int]:
        """Return (decoded_text, input_token_count, output_token_count)."""
        self._ensure_loaded()
        tokenizer = self._tokenizer
        model = self._model_obj

        system_content = SYSTEM_PROMPT + JSON_INSTRUCTIONS
        user_content = build_user_message(article)

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        try:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        except Exception:
            prompt = f"{system_content}\n\n{user_content}\n\n"

        import torch
        inputs = tokenizer(prompt, return_tensors="pt")
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        input_ids = inputs["input_ids"]
        input_length = input_ids.shape[1]

        with torch.no_grad():
            out = model.generate(
                input_ids,
                max_new_tokens=self._max_new_tokens,
                temperature=self._temperature if self._temperature > 0 else 1e-7,
                do_sample=self._temperature > 0,
                pad_token_id=tokenizer.pad_token_id,
            )

        output_ids = out[0][input_length:]
        output_length = output_ids.shape[0]
        decoded = tokenizer.decode(output_ids, skip_special_tokens=True)

        return decoded.strip(), input_length, output_length

    def _parse_output(
        self, raw: str, article: Article
    ) -> ArticleExtraction | None:
        """Parse raw model output into ArticleExtraction. Returns None on failure."""
        data = extract_json_object(raw)
        if data is None:
            return None
        for key in ("extraction_model", "extraction_timestamp"):
            data.pop(key, None)
        try:
            extraction = ArticleExtraction.model_validate(data)
        except Exception:
            return None
        extraction.extraction_model = self._model
        extraction.extraction_timestamp = datetime.now(timezone.utc)
        return extraction

    def extract(self, article: Article) -> ArticleExtraction:
        if not article.abstract:
            return ArticleExtraction(
                technologies=[],
                claims=[],
                novelty=Novelty.review,
                sentiment=Sentiment.neutral,
                summary="No abstract available for analysis.",
                extraction_model=self._model,
                extraction_timestamp=datetime.now(timezone.utc),
            )

        last_error: str | None = None
        for attempt in range(2):
            try:
                raw, input_tokens, output_tokens = self._run_generation(article)
                extraction = self._parse_output(raw, article)
                if extraction is not None:
                    if self._cost_tracker:
                        self._cost_tracker.record(
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            article_source_id=article.source_id,
                        )
                    return extraction
                last_error = "JSON parse or validation failed"
            except Exception as e:
                last_error = str(e)

            logger.warning(
                "parse/validation failure for article %s (attempt %d): %s",
                article.source_id,
                attempt + 1,
                last_error,
            )

        logger.error(
            "extraction failed for article %s after retry: %s",
            article.source_id,
            last_error,
        )
        if self._on_parse_failure == "fallback":
            return _fallback_extraction(self._model)
        raise LocalExtractionError(article.source_id, last_error or "unknown")

    def estimate_cost(self, articles: list[Article]) -> CostEstimate:
        """Estimate for local model: $0; token counts optional."""
        n = len(articles)
        total_out = n * min(self._max_new_tokens, 400)
        total_in = 0
        if self._tokenizer is not None:
            for a in articles:
                text = build_user_message(a)
                total_in += len(self._tokenizer.encode(SYSTEM_PROMPT + JSON_INSTRUCTIONS + text))
        return CostEstimate(
            num_articles=n,
            model=self._model,
            total_input_tokens=total_in,
            estimated_output_tokens=total_out,
            estimated_cost_usd=0.0,
        )
