"""Unit tests for extract_json_object (raw LLM output parsing)."""

from __future__ import annotations


from alpha_signal.extractors.parse_json import extract_json_object


class TestExtractJsonObject:
    def test_plain_json_object(self):
        raw = '{"technologies": [], "claims": [], "novelty": "review", "sentiment": "neutral", "summary": "Test."}'
        out = extract_json_object(raw)
        assert out is not None
        assert out["novelty"] == "review"
        assert out["summary"] == "Test."

    def test_markdown_code_fence_json(self):
        raw = """Some text before.
```json
{"technologies": [], "claims": [], "novelty": "novel", "sentiment": "optimistic", "summary": "Done."}
```
Some text after."""
        out = extract_json_object(raw)
        assert out is not None
        assert out["novelty"] == "novel"
        assert out["sentiment"] == "optimistic"

    def test_markdown_code_fence_no_lang(self):
        raw = """```
{"a": 1}
```"""
        out = extract_json_object(raw)
        assert out is not None
        assert out["a"] == 1

    def test_nested_object(self):
        raw = '{"technologies": [{"technology": "x", "sector": "y", "maturity": "lab_scale", "relevance": "z"}], "claims": [], "novelty": "incremental", "sentiment": "cautious", "summary": "S"}'
        out = extract_json_object(raw)
        assert out is not None
        assert len(out["technologies"]) == 1
        assert out["technologies"][0]["technology"] == "x"
        assert out["novelty"] == "incremental"

    def test_no_brace_returns_none(self):
        assert extract_json_object("no json here") is None
        assert extract_json_object("") is None
        assert extract_json_object("   \n  ") is None

    def test_invalid_json_returns_none(self):
        raw = "{ invalid json }"
        out = extract_json_object(raw)
        assert out is None

    def test_trailing_text_after_object(self):
        raw = '{"novelty": "review", "sentiment": "neutral", "technologies": [], "claims": [], "summary": "x"} and more text'
        out = extract_json_object(raw)
        assert out is not None
        assert out["summary"] == "x"

    def test_leading_text_before_object(self):
        raw = 'Here is the result: {"technologies": [], "claims": [], "novelty": "review", "sentiment": "neutral", "summary": "y"}'
        out = extract_json_object(raw)
        assert out is not None
        assert out["summary"] == "y"
