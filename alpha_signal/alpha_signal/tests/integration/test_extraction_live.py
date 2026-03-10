"""Integration test that calls the OpenAI API to validate extraction.

Run with:  pytest -m integration
Requires:  OPENAI_API_KEY environment variable to be set.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from alpha_signal.extractors.openai import OpenAIExtractor
from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction, Maturity

pytestmark = pytest.mark.integration

BATTERY_ARTICLE = Article(
    source="test",
    source_id="integration-1",
    title="A Novel Solid-State Electrolyte for Lithium-Sulfur Batteries",
    abstract=(
        "We demonstrate a new ceramic electrolyte enabling stable cycling of "
        "lithium-sulfur cells at room temperature, achieving 400 Wh/kg energy "
        "density over 500 cycles with minimal capacity fade. The electrolyte "
        "is fabricated using scalable sol-gel synthesis and shows ionic "
        "conductivity of 1.2 mS/cm at 25°C."
    ),
    authors=["Jane Smith", "John Doe"],
    publication_date=date(2024, 1, 15),
    venue="Nature Energy",
)

QUANTUM_ARTICLE = Article(
    source="test",
    source_id="integration-2",
    title="Topological Qubits in Silicon Germanium Heterostructures",
    abstract=(
        "We report the first experimental observation of non-Abelian anyons in "
        "a silicon-germanium heterostructure, providing a path toward "
        "topological quantum computing. Our device operates at 20 millikelvin "
        "and demonstrates braiding operations with 99.1% fidelity."
    ),
    authors=["Alice Chen"],
    publication_date=date(2024, 6, 1),
    venue="Physical Review Letters",
)


def _skip_if_no_api_key():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")


class TestOpenAIExtractionLive:
    def test_battery_article_extraction(self):
        _skip_if_no_api_key()
        extractor = OpenAIExtractor()
        result = extractor.extract(BATTERY_ARTICLE)

        assert isinstance(result, ArticleExtraction)
        assert len(result.technologies) > 0

        tech_names = " ".join(t.technology.lower() for t in result.technologies)
        assert "lithium" in tech_names or "battery" in tech_names or "electrolyte" in tech_names

        sectors = {t.sector.lower() for t in result.technologies}
        assert any("energy" in s or "battery" in s or "storage" in s for s in sectors)

        assert any(c.quantitative for c in result.claims)
        assert result.summary

    def test_quantum_article_extraction(self):
        _skip_if_no_api_key()
        extractor = OpenAIExtractor()
        result = extractor.extract(QUANTUM_ARTICLE)

        assert isinstance(result, ArticleExtraction)
        assert len(result.technologies) > 0

        tech_names = " ".join(t.technology.lower() for t in result.technologies)
        assert "qubit" in tech_names or "quantum" in tech_names or "topological" in tech_names

        maturities = {t.maturity for t in result.technologies}
        assert Maturity.commercial not in maturities

        assert result.summary

    def test_no_abstract_handled(self):
        _skip_if_no_api_key()
        article = Article(source="test", source_id="no-abs", title="Empty")
        extractor = OpenAIExtractor()
        result = extractor.extract(article)

        assert result.technologies == []
        assert result.claims == []
